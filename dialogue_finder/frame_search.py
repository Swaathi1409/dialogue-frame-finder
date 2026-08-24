"""
frame_search.py - Stage 3: coarse-to-fine frame localization.

Given a SearchWindow, this module:
  1. Samples frames at COARSE_SAMPLE_INTERVAL_SEC and scores each with OCR.
  2. On finding the first coarse match, bisects backward between the previous
     non-match and that frame to find the exact first matching frame.
  3. Checks PERSISTENCE_FRAMES consecutive frames after the candidate to
     confirm the match is real and not a single-frame OCR fluke.
  4. Falls back to a sequential scan near the transition when bisection
     produces noisy results (OCR is not perfectly monotonic).

Returns the best FrameCandidate or None if nothing clears LOW_CONF_THRESHOLD.
"""

# STUB - implemented in Phase 4

from typing import Callable, Optional
from dialogue_finder.models import SearchWindow, FrameCandidate
from dialogue_finder.frame_extractor import VideoInfo


def search_frames(
    video_path: str,
    video_info: VideoInfo,
    window: SearchWindow,
    target: str,
    ocr_fn: Callable,          # injectable for testing
) -> Optional[FrameCandidate]:
    """
    Run coarse-to-fine frame search inside window.
    ocr_fn(frame) -> (text, confidence) so tests can inject a fake.
    Returns the first FrameCandidate that clears LOW_CONF_THRESHOLD,
    or None if nothing found.
    """
    raise NotImplementedError("Phase 4 - not yet implemented")
