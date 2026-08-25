"""
localizer.py - Stage 1 and Stage 2 of the pipeline.

Stage 1 (ASR-guided):
  Takes the transcript from transcriber.py, fuzzy-matches the target
  dialogue against each segment using matcher.score(), picks the best
  match, and returns a SearchWindow padded around it. The padding
  (ASR_PAD_BEFORE_SEC / ASR_PAD_AFTER_SEC from config.py) accounts for
  the fact that captions can lag or lead the spoken line by several seconds.

Stage 2 (fallback):
  If Stage 1 finds nothing above ASR_MATCH_THRESHOLD, we fall back to a
  SearchWindow that covers the whole video. frame_search.py will then scan
  it at FALLBACK_SCAN_INTERVAL_SEC, which is slower but bounded.

The two stages return the same type (SearchWindow) with a 'source' field
('asr' or 'fallback') so downstream code can log where the window came
from without needing to know which path ran.
"""

import logging
from typing import List, Optional

from dialogue_finder import config
from dialogue_finder.models import TranscriptSegment, SearchWindow
from dialogue_finder import matcher

logger = logging.getLogger(__name__)


def find_asr_window(
    segments: List[TranscriptSegment],
    target: str,
    video_duration_sec: float,
) -> Optional[SearchWindow]:
    """
    Fuzzy-match target against each transcript segment.

    For each segment, score the segment text against the target using
    matcher.score(). Keep track of the best scoring segment overall.

    If the best score clears ASR_MATCH_THRESHOLD, pad the segment's
    time range and return it as a SearchWindow. Otherwise return None.

    The padding is applied to both ends of the segment:
      window start = max(0, segment.start - ASR_PAD_BEFORE_SEC)
      window end   = min(duration, segment.end + ASR_PAD_AFTER_SEC)

    Clamping at 0 and duration is important - without it a segment at the
    very start of the video would produce a negative start time.
    """
    if not segments:
        logger.info("No transcript segments - falling back to full-video scan")
        return None

    best_score = 0.0
    best_segment = None

    for seg in segments:
        s = matcher.score(seg.text, target)
        if s > best_score:
            best_score = s
            best_segment = seg

    logger.info(
        "Best ASR match: score=%.1f, text='%s'",
        best_score,
        best_segment.text if best_segment else "",
    )

    if best_score < config.ASR_MATCH_THRESHOLD:
        logger.info(
            "ASR score %.1f below threshold %.1f - will use fallback scan",
            best_score,
            config.ASR_MATCH_THRESHOLD,
        )
        return None

    start = max(0.0, best_segment.start_sec - config.ASR_PAD_BEFORE_SEC)
    end = min(video_duration_sec, best_segment.end_sec + config.ASR_PAD_AFTER_SEC)

    logger.info(
        "ASR window: %.1f - %.1f sec (segment was %.1f - %.1f)",
        start, end, best_segment.start_sec, best_segment.end_sec,
    )

    return SearchWindow(
        start_sec=start,
        end_sec=end,
        source="asr",
        asr_score=best_score,
        asr_segment=best_segment,
    )


def fallback_window(video_duration_sec: float) -> SearchWindow:
    """
    Return a SearchWindow covering the entire video, marked source='fallback'.

    Used when ASR finds nothing useful. frame_search.py will sample this
    at FALLBACK_SCAN_INTERVAL_SEC which is slower but covers the whole video.
    """
    logger.info(
        "Using fallback full-video window: 0.0 - %.1f sec", video_duration_sec
    )
    return SearchWindow(
        start_sec=0.0,
        end_sec=video_duration_sec,
        source="fallback",
        asr_score=0.0,
    )
