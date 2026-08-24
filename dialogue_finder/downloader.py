"""
downloader.py - Wraps yt-dlp to download a video from a URL.

Raises DownloadError on any failure. The rest of the pipeline never
sees yt-dlp directly; it just gets a path to a local video file.
"""

# STUB - implemented in Phase 1


class DownloadError(Exception):
    """Raised when the video cannot be downloaded for any reason."""
    pass


def download_video(url: str, output_dir: str) -> str:
    """
    Download the video at url into output_dir.
    Returns the local file path of the downloaded video.
    Raises DownloadError if anything goes wrong.
    """
    raise NotImplementedError("Phase 1 - not yet implemented")
