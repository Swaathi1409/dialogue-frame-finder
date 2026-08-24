"""
frame_extractor.py - Pulls individual frames from a video file.

Uses ffprobe to read the real fps (never assumes 30fps), then uses
OpenCV to seek to and decode specific frames. Raises FrameExtractionError
on failure. All timestamp math uses the real fps stored in VideoInfo.
"""

# STUB - implemented in Phase 1

from dataclasses import dataclass


class FrameExtractionError(Exception):
    """Raised when a frame cannot be extracted from the video."""
    pass


@dataclass
class VideoInfo:
    """Metadata about the video, read once from ffprobe."""
    fps: float
    total_frames: int
    duration_sec: float
    width: int
    height: int


def get_video_info(video_path: str) -> VideoInfo:
    """
    Use ffprobe to read fps, total frames, duration, and resolution.
    Raises FrameExtractionError if ffprobe fails or the output can't be parsed.
    """
    raise NotImplementedError("Phase 1 - not yet implemented")


def extract_frame(video_path: str, frame_number: int) -> "np.ndarray":
    """
    Extract the frame at frame_number (0-indexed) from video_path.
    Returns a numpy array (BGR, as OpenCV reads it).
    Raises FrameExtractionError if the frame can't be read.
    """
    raise NotImplementedError("Phase 1 - not yet implemented")


def save_frame(frame, output_path: str) -> str:
    """
    Save a numpy frame array as a PNG to output_path.
    Returns output_path.
    """
    raise NotImplementedError("Phase 1 - not yet implemented")
