"""
transcriber.py - Wraps faster-whisper to get word-level timestamped segments.

The output is a list of TranscriptSegment objects. Each segment has the
recognized text and the start/end time in seconds. We use this only to
narrow down where in the video to look, not to confirm visible text.
Raises TranscriptionError on failure.
"""

# STUB - implemented in Phase 2

from typing import List
from dialogue_finder.models import TranscriptSegment


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


def transcribe(audio_path: str, language: str = None) -> List[TranscriptSegment]:
    """
    Run faster-whisper on audio_path and return a list of TranscriptSegment.
    Each segment covers one sentence or phrase with a start and end timestamp.
    Raises TranscriptionError on failure.
    """
    raise NotImplementedError("Phase 2 - not yet implemented")
