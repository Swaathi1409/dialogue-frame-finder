"""
audio.py - Extracts audio from a video file using ffmpeg.

Raises AudioExtractionError on failure. The output is a WAV file
because faster-whisper reads WAV without additional dependencies.
"""

# STUB - implemented in Phase 1


class AudioExtractionError(Exception):
    """Raised when audio cannot be extracted from the video."""
    pass


def extract_audio(video_path: str, output_path: str) -> str:
    """
    Extract the audio track from video_path and write it to output_path as WAV.
    Returns output_path.
    Raises AudioExtractionError on failure.
    """
    raise NotImplementedError("Phase 1 - not yet implemented")
