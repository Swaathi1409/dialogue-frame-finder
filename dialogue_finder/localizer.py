"""
localizer.py - Stage 1 and Stage 2 of the pipeline.

Stage 1 (ASR-guided): takes the transcript, fuzzy-matches the target
  dialogue, and produces a SearchWindow padded around the best match.
Stage 2 (fallback): if Stage 1 finds no confident match, produces a
  SearchWindow covering the entire video at a fixed scan interval.

The output is always a SearchWindow; downstream code doesn't need to
know which path was taken (the 'source' field records it).
"""

# STUB - implemented in Phase 2

from typing import List, Optional
from dialogue_finder.models import TranscriptSegment, SearchWindow


def find_asr_window(
    segments: List[TranscriptSegment],
    target: str,
    video_duration_sec: float,
) -> Optional[SearchWindow]:
    """
    Fuzzy-match target against each segment. If the best match clears
    ASR_MATCH_THRESHOLD, return a SearchWindow padded by ASR_PAD_BEFORE/AFTER_SEC.
    Returns None if nothing matches well enough.
    """
    raise NotImplementedError("Phase 2 - not yet implemented")


def fallback_window(video_duration_sec: float) -> SearchWindow:
    """
    Return a SearchWindow covering the entire video, marked source='fallback'.
    The frame_search stage will sample it at FALLBACK_SCAN_INTERVAL_SEC.
    """
    raise NotImplementedError("Phase 2 - not yet implemented")
