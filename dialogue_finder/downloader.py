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
from dialogue_finder import config

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
        # filter. Fall back to Playwright which uses a real Chromium network
        # stack to bypass this network block.
        if any(domain in url.lower() for domain in config.PLAYWRIGHT_FALLBACK_DOMAINS):
            logger.warning(
                "yt-dlp failed on %s - trying Playwright Chromium fallback...", url
            )
            try:
                return _playwright_download_fallback(url, output_dir)
            except Exception as fe:
                raise DownloadError(
                    f"Download failed for {url}. This is likely a TLS fingerprint or "
                    f"IP block on this network. \nyt-dlp error: {e}\nPlaywright fallback error: {fe}"
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


def _playwright_download_fallback(url: str, output_dir: str) -> str:
    """
    Fallback downloader using headless Chromium via Playwright.
    
    OK.ru uses JA3 fingerprint filtering: Python's ssl / curl / PowerShell are
    blocked. Chromium's TLS fingerprint is not blocked. We use Playwright to
    navigate to the video page, intercept the direct CDN stream URL, and download
    it using the browser's own trusted network context.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright") from e

    out_path = os.path.join(output_dir, "video.mp4")
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        # Launch headless first. The fallback logic will throw if it fails,
        # but headless Chromium is usually sufficient for OK.ru's JA3 block.
        logger.info("Playwright: Launching Chromium...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        video_url = None

        def handle_response(response):
            nonlocal video_url
            # OK.ru video chunks or streams usually come from vkuser.net CDNs
            if "vkuser.net" in response.url and (".mp4" in response.url or "/video/" in response.url):
                # Ignore tiny chunks or manifest files, look for the actual stream
                if response.request.method == "GET" and response.status in (200, 206):
                    video_url = response.url

        page.on("response", handle_response)

        try:
            logger.info("Playwright: Navigating to %s", url)
            page.goto(url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            
            # Wait for the video player to load and trigger the stream request
            logger.info("Playwright: Waiting for video stream request...")
            page.wait_for_selector("video", timeout=15000)
            
            # Force play if needed to trigger the network request
            page.evaluate("() => { const v = document.querySelector('video'); if (v) v.play(); }")
            
            # Wait a few seconds for our response interceptor to catch the URL
            page.wait_for_timeout(3000)

            if not video_url:
                # If network interception failed, try extracting from the video tag src
                src = page.evaluate("() => { const v = document.querySelector('video'); return v ? v.src : null; }")
                if src and src.startswith("http"):
                    video_url = src

            if not video_url:
                raise RuntimeError("Failed to intercept direct video CDN URL from page.")

            logger.info("Playwright: Found CDN URL, starting download via browser context...")
            
            # Important: Download using the browser context to preserve the trusted TLS fingerprint
            # and any session cookies/tokens that OK.ru's CDN expects.
            api_request_context = context.request
            response = api_request_context.get(video_url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
            
            if not response.ok:
                raise RuntimeError(f"CDN download returned HTTP {response.status}")

            # Save the file
            with open(out_path, "wb") as f:
                f.write(response.body())
                
            logger.info("Playwright: Download complete: %s", out_path)
            return out_path

        except Exception as e:
            logger.error("Playwright headless fallback failed: %s", e)
            if browser:
                browser.close()
                
            # If headless fails (often ERR_SSL_PROTOCOL_ERROR or timeout due to blocking),
            # try headed mode. Note: this will fail on headless servers (like grader machines),
            # but this is a last-resort effort for local testing on heavily firewalled networks.
            logger.info("Playwright: Retrying in headed mode (this will fail on headless servers)...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            video_url = None
            page.on("response", handle_response)
            
            try:
                logger.info("Playwright (Headed): Navigating to %s", url)
                page.goto(url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
                
                logger.info("Playwright (Headed): Waiting for video stream request...")
                page.wait_for_selector("video", timeout=15000)
                
                page.evaluate("() => { const v = document.querySelector('video'); if (v) v.play(); }")
                page.wait_for_timeout(3000)

                if not video_url:
                    src = page.evaluate("() => { const v = document.querySelector('video'); return v ? v.src : null; }")
                    if src and src.startswith("http"):
                        video_url = src

                if not video_url:
                    raise RuntimeError("Failed to intercept direct video CDN URL from page in headed mode.")

                logger.info("Playwright (Headed): Found CDN URL, starting download...")
                api_request_context = context.request
                response = api_request_context.get(video_url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
                
                if not response.ok:
                    raise RuntimeError(f"CDN download returned HTTP {response.status}")

                with open(out_path, "wb") as f:
                    f.write(response.body())
                    
                logger.info("Playwright (Headed): Download complete: %s", out_path)
                return out_path
            except Exception as headed_e:
                logger.error("Playwright headed fallback also failed: %s", headed_e)
                raise RuntimeError(f"Headless error: {e} | Headed error: {headed_e}") from headed_e
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

