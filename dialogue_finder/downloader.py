"""
downloader.py - Wraps yt-dlp to download a video from a URL.

We use yt-dlp's Python API (not subprocess) so errors surface as
exceptions rather than exit codes we'd have to parse from shell output.

Format choice: "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
This prefers an mp4 container, which OpenCV reads reliably without
needing extra codec work. If mp4 is not available, yt-dlp's fallback
picks the best single file it can find.

ffmpeg note: yt-dlp needs ffmpeg to merge separate video and audio streams
(DASH format, which is what OK.ru and YouTube use). The ffmpeg binary is
bundled via imageio_ffmpeg with a platform-specific name like
ffmpeg-win-x86_64-v7.1.exe. yt-dlp looks for a file named exactly
'ffmpeg' or 'ffmpeg.exe' in the ffmpeg_location directory, so we copy
the bundled binary to a temp location under that name the first time
this module is used. This avoids requiring ffmpeg on the system PATH.

Raises DownloadError on any failure - network, extractor breakage,
region lock, or partial download. The rest of the pipeline never
sees yt-dlp directly.
"""

import os
import shutil
import tempfile
import logging
import yt_dlp
import imageio_ffmpeg
import requests as _requests

logger = logging.getLogger(__name__)

# API used as fallback when yt-dlp cannot reach ok.ru directly.
# okrudownloader.top runs this Vercel backend that proxies OK.ru video metadata.
_OKRU_API = "https://okrufunction7.vercel.app"

# Module-level cache: path to the directory containing 'ffmpeg.exe' (or 'ffmpeg')
# that yt-dlp can find. Created once, reused for the lifetime of the process.
_FFMPEG_DIR: str | None = None


class DownloadError(Exception):
    """Raised when the video cannot be downloaded for any reason."""
    pass


def _get_ffmpeg_dir() -> str:
    """
    Return a directory containing a file named 'ffmpeg' (Linux/Mac) or
    'ffmpeg.exe' (Windows) that yt-dlp can find.

    imageio_ffmpeg ships the binary with a versioned name like
    ffmpeg-win-x86_64-v7.1.exe, which yt-dlp won't recognize. We copy
    it to a temp directory under the plain name once, then cache that path.

    If the system already has ffmpeg on PATH (i.e. the binary can be found
    as just 'ffmpeg'), we return None and let yt-dlp use its default search.
    """
    global _FFMPEG_DIR

    # If already set up this session, reuse it.
    if _FFMPEG_DIR is not None:
        return _FFMPEG_DIR

    # Check if ffmpeg is already on the system PATH.
    if shutil.which("ffmpeg"):
        logger.debug("System ffmpeg found on PATH, using it directly.")
        _FFMPEG_DIR = ""  # empty string means "don't override ffmpeg_location"
        return _FFMPEG_DIR

    # Not on PATH - use the imageio_ffmpeg bundled binary.
    src_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not os.path.exists(src_exe):
        raise DownloadError(
            "ffmpeg binary not found. imageio_ffmpeg did not install correctly."
        )

    # Copy to a temp directory with the plain name yt-dlp expects.
    tmp_dir = tempfile.mkdtemp(prefix="dff_ffmpeg_")
    ext = ".exe" if os.name == "nt" else ""
    dst_exe = os.path.join(tmp_dir, f"ffmpeg{ext}")
    shutil.copy2(src_exe, dst_exe)

    logger.debug("Copied bundled ffmpeg to: %s", dst_exe)
    _FFMPEG_DIR = tmp_dir
    return _FFMPEG_DIR


def download_video(url: str, output_dir: str) -> str:
    """
    Download the video at url into output_dir.

    Returns the local file path of the downloaded video.
    Raises DownloadError if anything goes wrong - including a partial
    download, a region lock, or an extractor failure.

    The outtmpl pattern writes the file as <output_dir>/video.<ext>
    so the returned path is predictable without having to glob the dir.
    """
    os.makedirs(output_dir, exist_ok=True)

    ffmpeg_dir = _get_ffmpeg_dir()

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(output_dir, "video.%(ext)s"),
        "quiet": True,
        "no_warnings": False,
        "logger": logging.getLogger("yt_dlp"),
        # Use Node.js JS runtime so yt-dlp can handle YouTube's player challenge.
        # Python API expects {"node": {}} not the string "node".
        "js_runtimes": {"node": {}},
        # Retries: fail fast rather than hanging for minutes on a bad URL.
        "retries": 2,
        "fragment_retries": 2,
    }

    # Auto-detect cookies.txt in the project root for YouTube bot-detection bypass.
    # Users can export this once with the 'Get cookies.txt LOCALLY' Chrome extension.
    _cookies_path = _find_cookies_file()
    if _cookies_path:
        logger.info("Using cookies file: %s", _cookies_path)
        ydl_opts["cookiefile"] = _cookies_path

    # Tell yt-dlp where to find ffmpeg for stream merging.
    if ffmpeg_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_dir

    downloaded_path = None

    def _progress_hook(d):
        nonlocal downloaded_path
        if d["status"] == "finished":
            downloaded_path = d["filename"]
        elif d["status"] == "error":
            raise DownloadError(f"yt-dlp reported an error during download: {d}")

    ydl_opts["progress_hooks"] = [_progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([url])
            if ret != 0:
                raise DownloadError(
                    f"yt-dlp exited with return code {ret} for URL: {url}"
                )
    except DownloadError:
        raise
    except Exception as e:
        err_str = str(e)

        # YouTube bot-detection: retry with cookies from the local browser.
        # yt-dlp raises this when YouTube requires a logged-in session.
        if _is_bot_detection(err_str):
            raise DownloadError(
                f"YouTube requires authentication to download this video. "
                f"Export your YouTube cookies using the 'Get cookies.txt LOCALLY' "
                f"Chrome extension, save the file as 'cookies.txt' in the project "
                f"root folder, and try again. "
                f"(Original error: {str(e)[:120]})"
            )

        # For ok.ru, Python's TLS stack is blocked by OK.ru's JA3 fingerprint
        # filter. Fall back to the okrudownloader.top backend API which proxies
        # the metadata and returns direct CDN URLs we can download with requests.
        if "ok.ru" in url.lower():
            logger.warning(
                "yt-dlp failed on ok.ru (%s) - trying okrudownloader.top fallback", e
            )
            try:
                return _okru_fallback_download(url, output_dir)
            except Exception as fe:
                raise DownloadError(
                    f"Download failed for {url}: yt-dlp: {e}; fallback: {fe}"
                ) from fe
        raise DownloadError(f"Download failed for {url}: {e}") from e

    # yt-dlp may merge streams into a different extension than what the
    # progress hook captured. Walk the output_dir to find the video file.
    if downloaded_path is None or not os.path.exists(downloaded_path):
        downloaded_path = _find_video_file(output_dir)

    if downloaded_path is None:
        raise DownloadError(
            f"Download appeared to succeed but no video file found in {output_dir}"
        )

    logger.info("Downloaded: %s", downloaded_path)
    return downloaded_path


def _is_bot_detection(err_str: str) -> bool:
    """Check if the error string indicates YouTube bot detection."""
    return any(x in err_str.lower() for x in [
        "sign in to confirm you're not a bot",
        "bot detection",
        "suspended",
        "429"
    ])


def _find_cookies_file() -> str | None:
    """
    Search for a cookies.txt file to pass to yt-dlp.

    Users can export this once from Chrome using the
    'Get cookies.txt LOCALLY' extension (available on Chrome Web Store).
    Steps:
      1. Install the extension
      2. Log into YouTube in Chrome
      3. Click the extension icon on youtube.com -> Export
      4. Save as 'cookies.txt' in the project root folder

    We check several common locations so the user doesn't need to
    configure anything - just drop the file in the right place.
    """
    candidates = [
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(os.path.dirname(__file__), "..", "cookies.txt"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path):
            return path
    return None




def _ytdlp_with_cookies(url: str, output_dir: str, ydl_opts: dict) -> str:
    """Retry download using browser cookies to bypass bot detection."""
    opts = ydl_opts.copy()
    opts["cookiesfrombrowser"] = ("chrome",)
    
    downloaded_path = None
    def _progress_hook(d):
        nonlocal downloaded_path
        if d["status"] == "finished":
            downloaded_path = d["filename"]

    opts["progress_hooks"] = [_progress_hook]
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
        
    if downloaded_path and os.path.exists(downloaded_path):
        return downloaded_path
        
    path = _find_video_file(output_dir)
    if not path:
        raise DownloadError("Cookie-based download failed to produce a file.")
    return path


def _find_video_file(directory: str) -> str | None:
    """
    Walk directory and return the first file with a known video extension.
    yt-dlp can write .mp4, .mkv, .webm depending on what the site provides.
    Returns None if nothing is found.
    """
    video_extensions = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    for fname in os.listdir(directory):
        _, ext = os.path.splitext(fname)
        if ext.lower() in video_extensions:
            return os.path.join(directory, fname)
    return None


def _okru_fallback_download(url: str, output_dir: str) -> str:
    """
    Fallback downloader for ok.ru videos when yt-dlp is blocked at TLS level.

    OK.ru uses JA3 fingerprint filtering: Python's ssl / curl / PowerShell are
    all blocked. Chrome's QUIC or TLS fingerprint is not blocked.

    okrudownloader.top runs a Vercel backend (okrufunction7.vercel.app) that
    acts as a trusted proxy - it fetches the OK.ru metadata and returns direct
    CDN URLs (ok6-*.vkuser.net) that are accessible without TLS restrictions.

    Quality preference: 480p (good balance of size vs clarity for OCR).
    Falls back to 360p → 720p → first available quality.
    """
    logger.info("ok.ru fallback: calling okrufunction7.vercel.app/api/extract")

    session = _requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127.0.0.0",
        "Origin": "https://okrudownloader.top",
        "Referer": "https://okrudownloader.top/",
        "Content-Type": "application/json",
    })

    try:
        r = session.post(
            f"{_OKRU_API}/api/extract",
            json={"url": url},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"okrudownloader API call failed: {e}") from e

    if not data.get("success"):
        raise RuntimeError(f"okrudownloader API returned error: {data}")

    video_urls = data.get("videoUrls", {})
    title = data.get("title", "video")
    logger.info("ok.ru fallback: got URLs for qualities: %s", list(video_urls.keys()))

    # Pick quality - 480p preferred for OCR (readable text, manageable file size)
    preferred = ["480p", "360p", "720p", "240p", "144p", "adaptive"]
    chosen_url = None
    chosen_quality = None
    for q in preferred:
        if q in video_urls and q != "adaptive":
            chosen_url = video_urls[q]
            chosen_quality = q
            break

    if chosen_url is None:
        raise RuntimeError(f"No usable quality found in: {list(video_urls.keys())}")

    logger.info("ok.ru fallback: downloading %s quality", chosen_quality)

    out_path = os.path.join(output_dir, "video.mp4")
    os.makedirs(output_dir, exist_ok=True)

    # Stream download with progress logging
    dl_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127.0.0.0",
        "Referer": "https://ok.ru/",
    }
    with session.get(chosen_url, headers=dl_headers, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        logger.info("ok.ru fallback: %d%% (%d MB)", pct, downloaded // 1024 // 1024)

    logger.info("ok.ru fallback: saved to %s (%d MB)", out_path, os.path.getsize(out_path) // 1024 // 1024)
    return out_path

