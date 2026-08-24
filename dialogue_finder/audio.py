"""
audio.py - Extracts audio from a video file using ffmpeg.

We call the ffmpeg binary directly via subprocess rather than using
the ffmpeg-python wrapper. This keeps the logic simple and visible -
it's just one subprocess call with known arguments.

We extract 16 kHz mono WAV because that is exactly what faster-whisper
expects. Passing the wrong sample rate or channel count here would make
transcription silently worse, so we set them explicitly rather than
relying on defaults.

The ffmpeg binary path comes from imageio_ffmpeg, which ships the binary
as part of its package. This means ffmpeg does not need to be on PATH,
which is important for Docker and for Windows environments where ffmpeg
is often not installed globally.

Raises AudioExtractionError on failure.
"""

import os
import subprocess
import logging
import imageio_ffmpeg

logger = logging.getLogger(__name__)


class AudioExtractionError(Exception):
    """Raised when audio cannot be extracted from the video."""
    pass


def get_ffmpeg_path() -> str:
    """
    Return the path to the ffmpeg binary.
    Uses imageio_ffmpeg's bundled binary so we don't depend on system PATH.
    """
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video_path: str, output_path: str) -> str:
    """
    Extract the audio track from video_path and write it to output_path as WAV.

    Output format: 16 kHz, mono, PCM signed 16-bit little-endian.
    This is the format faster-whisper reads without any additional decoding.

    Returns output_path on success.
    Raises AudioExtractionError if ffmpeg fails or the output file is missing.
    """
    if not os.path.exists(video_path):
        raise AudioExtractionError(f"Video file not found: {video_path}")

    ffmpeg = get_ffmpeg_path()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",                    # overwrite output without asking
        "-i", video_path,        # input file
        "-vn",                   # no video in output
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",          # 16 kHz sample rate
        "-ac", "1",              # mono
        output_path,
    ]

    logger.debug("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise AudioExtractionError(
            f"ffmpeg failed (exit {result.returncode}) extracting audio from "
            f"{video_path}.\nffmpeg stderr:\n{stderr_text}"
        )

    if not os.path.exists(output_path):
        raise AudioExtractionError(
            f"ffmpeg exited 0 but output file not found: {output_path}"
        )

    size_kb = os.path.getsize(output_path) // 1024
    logger.info("Audio extracted: %s (%d KB)", output_path, size_kb)
    return output_path
