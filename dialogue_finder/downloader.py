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

logger = logging.getLogger(__name__)

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
