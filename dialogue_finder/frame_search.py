"""
frame_search.py - Stage 3: coarse-to-fine frame localization.

This is where the actual frame-finding happens. Given a SearchWindow,
the algorithm works in four steps:

Step 1 - Coarse scan:
  Sample frames at COARSE_SAMPLE_INTERVAL_SEC (for ASR windows) or
  FALLBACK_SCAN_INTERVAL_SEC (for full-video fallback). For each sampled
  frame, run OCR and score against the target. Stop at the first frame
  that clears LOW_CONF_THRESHOLD. Record the last non-matching frame
  before it - we need that for the bisection.

Step 2 - Bisection:
  We now know the text appears somewhere between last_no_match_frame and
  first_match_frame (the coarse hit). Binary search that range to find
  the exact transition frame. Stop when the gap is <= BISECT_MIN_FRAMES.
  Note: OCR results are not perfectly monotonic (a frame might score well
  while its neighbors score poorly due to rendering transitions). So we
  don't rely on bisection alone.

Step 3 - Local sequential scan:
  After bisection gives an approximate transition point, scan every frame
  in a small window around it (a few frames each side). This finds the
  true first frame in case OCR noise made bisection land slightly wrong.

Step 4 - Persistence check:
  Check PERSISTENCE_FRAMES consecutive frames after the candidate. If at
  least that many also clear LOW_CONF_THRESHOLD, the match is real.
  A single-frame hit is likely OCR noise.

ocr_fn is injectable (it takes a numpy frame and returns (text, conf)).
This makes the algorithm testable with a fake OCR function - no real
video or model needed for the unit tests.

Returns the first FrameCandidate that clears LOW_CONF_THRESHOLD, or None.
"""

import logging
from typing import Callable, Optional, Tuple

import numpy as np

from dialogue_finder import config, matcher
from dialogue_finder.models import SearchWindow, FrameCandidate
from dialogue_finder.frame_extractor import (
    VideoInfo, extract_frame,
    timestamp_to_frame, frame_to_timestamp,
)

logger = logging.getLogger(__name__)


def search_frames(
    video_path: str,
    video_info: VideoInfo,
    window: SearchWindow,
    target: str,
    ocr_fn: Callable[[np.ndarray], Tuple[str, float]],
) -> Optional[FrameCandidate]:
    """
    Run the full coarse-to-fine search within the given window.

    ocr_fn(frame) -> (text, confidence): injectable so tests can pass a fake.
    Returns a FrameCandidate on success, None if nothing clears the threshold.
    """
    fps = video_info.fps
    total = video_info.total_frames

    start_frame = max(0, timestamp_to_frame(window.start_sec, fps))
    end_frame = min(total - 1, timestamp_to_frame(window.end_sec, fps))

    if start_frame >= end_frame:
        logger.warning("Search window too narrow: frames %d-%d", start_frame, end_frame)
        return None

    # Use a wider interval for the full-video fallback to keep it bounded.
    interval_sec = (
        config.FALLBACK_SCAN_INTERVAL_SEC
        if window.source == "fallback"
        else config.COARSE_SAMPLE_INTERVAL_SEC
    )
    step = max(1, round(interval_sec * fps))

    logger.info(
        "Coarse scan: frames %d-%d, step=%d (%s window, %.1fs interval)",
        start_frame, end_frame, step, window.source, interval_sec,
    )

    # Step 1: Coarse scan
    last_no_match = start_frame
    first_coarse_match = None

    frame_nums = list(range(start_frame, end_frame + 1, step))
    for frame_num in frame_nums:
        text, _ = _safe_ocr(video_path, frame_num, ocr_fn)
        s = matcher.score(text, target)
        if s >= config.LOW_CONF_THRESHOLD:
            first_coarse_match = frame_num
            logger.info("Coarse match at frame %d (score=%.1f): '%s'", frame_num, s, text[:60])
            break
        else:
            last_no_match = frame_num

    if first_coarse_match is None:
        logger.info("Coarse scan found no match in window.")
        return None

    # Step 2: Bisection between last_no_match and first_coarse_match
    bisect_lo = last_no_match
    bisect_hi = first_coarse_match
    approx_first = _bisect_transition(video_path, bisect_lo, bisect_hi, target, ocr_fn)
    logger.info("Bisection narrowed to approx frame %d", approx_first)

    # Step 3: Local sequential scan around the transition
    # Check a small window around approx_first to find the true first frame.
    # This handles OCR non-monotonicity (a frame might score high while its
    # immediate neighbors score low due to subtitle fade-in effects).
    local_start = max(start_frame, approx_first - 3)
    local_end = min(end_frame, approx_first + 5)
    exact_frame, best_score, best_text = _local_scan(
        video_path, local_start, local_end, target, ocr_fn
    )

    if exact_frame is None:
        # The coarse hit didn't survive fine-grained scrutiny around the
        # transition - fall back to the coarse match itself.
        exact_frame = first_coarse_match
        text_at_coarse, _ = _safe_ocr(video_path, first_coarse_match, ocr_fn)
        best_score = matcher.score(text_at_coarse, target)
        best_text = text_at_coarse
        logger.warning(
            "Local scan found nothing; falling back to coarse frame %d", exact_frame
        )

    if best_score < config.LOW_CONF_THRESHOLD:
        logger.info("Best score %.1f below low threshold, returning None.", best_score)
        return None

    # Step 4: Persistence check
    persists = _check_persistence(video_path, exact_frame, end_frame, target, ocr_fn)
    timestamp = frame_to_timestamp(exact_frame, fps)

    logger.info(
        "Final candidate: frame=%d, ts=%.3fs, score=%.1f, persists=%s",
        exact_frame, timestamp, best_score, persists,
    )

    return FrameCandidate(
        frame_number=exact_frame,
        timestamp_sec=timestamp,
        ocr_text=best_text,
        match_score=best_score,
        ocr_confidence=0.0,   # re-read by caller if needed, not repeated here
        persists=persists,
    )


# ---- Internal helpers ----

def _safe_ocr(
    video_path: str,
    frame_num: int,
    ocr_fn: Callable,
) -> Tuple[str, float]:
    """
    Extract frame_num and run ocr_fn on it.
    On any failure returns ("", 0.0) and logs a warning.
    A single bad frame should never crash the whole search.
    """
    try:
        frame = extract_frame(video_path, frame_num)
        return ocr_fn(frame)
    except Exception as e:
        logger.warning("OCR failed on frame %d (skipping): %s", frame_num, e)
        return ("", 0.0)


def _bisect_transition(
    video_path: str,
    lo: int,
    hi: int,
    target: str,
    ocr_fn: Callable,
) -> int:
    """
    Binary search between lo (no match) and hi (first coarse match).
    Returns the frame number closest to the first real match.

    We stop when hi - lo <= BISECT_MIN_FRAMES because going frame-by-frame
    at native fps resolution is handled by the local sequential scan.
    """
    while hi - lo > config.BISECT_MIN_FRAMES:
        mid = (lo + hi) // 2
        text, _ = _safe_ocr(video_path, mid, ocr_fn)
        s = matcher.score(text, target)
        if s >= config.LOW_CONF_THRESHOLD:
            hi = mid   # match found earlier - keep looking left
        else:
            lo = mid   # no match - look right

    return hi  # hi is the earliest known matching frame


def _local_scan(
    video_path: str,
    start: int,
    end: int,
    target: str,
    ocr_fn: Callable,
) -> Tuple[Optional[int], float, str]:
    """
    Scan every frame from start to end (inclusive) and return the first
    frame that clears LOW_CONF_THRESHOLD, its score, and its OCR text.
    Returns (None, 0.0, "") if nothing matches.

    This is the frame-level sequential pass that handles non-monotonic OCR.
    """
    for frame_num in range(start, end + 1):
        text, _ = _safe_ocr(video_path, frame_num, ocr_fn)
        s = matcher.score(text, target)
        if s >= config.LOW_CONF_THRESHOLD:
            logger.debug("Local scan first match at frame %d (score=%.1f)", frame_num, s)
            return (frame_num, s, text)
    return (None, 0.0, "")


def _check_persistence(
    video_path: str,
    candidate_frame: int,
    end_frame: int,
    target: str,
    ocr_fn: Callable,
) -> bool:
    """
    Check whether the match holds for at least PERSISTENCE_FRAMES consecutive
    frames after candidate_frame.

    Returns True if the match persists, False if only one frame scored well.
    """
    hits = 0
    for i in range(1, config.PERSISTENCE_FRAMES + 1):
        check = candidate_frame + i
        if check > end_frame:
            break
        text, _ = _safe_ocr(video_path, check, ocr_fn)
        if matcher.score(text, target) >= config.LOW_CONF_THRESHOLD:
            hits += 1
        else:
            break   # persistence requires consecutive hits, not scattered ones

    result = hits >= config.PERSISTENCE_FRAMES
    logger.debug(
        "Persistence check: %d/%d hits -> %s",
        hits, config.PERSISTENCE_FRAMES, result,
    )
    return result
