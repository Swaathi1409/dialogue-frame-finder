"""
matcher.py - Text normalization and fuzzy matching.

This module has zero external I/O and no model dependencies, so it can
be unit tested fully without mocks. It contains:
  - normalize(): strips punctuation, lowercases, collapses whitespace
  - score(): RapidFuzz partial_ratio on two normalized strings
  - confidence_bucket(): maps a score to 'High', 'Low', or 'Not Found'

All thresholds come from config.py so they are easy to tune.
"""

# STUB - implemented in Phase 2

from dialogue_finder import config


def normalize(text: str) -> str:
    """
    Lowercase, strip punctuation, collapse whitespace.
    Makes OCR character-level errors less likely to cause a full miss.
    """
    raise NotImplementedError("Phase 2 - not yet implemented")


def score(ocr_text: str, target: str) -> float:
    """
    Return RapidFuzz partial_ratio (0-100) between normalized versions
    of ocr_text and target. Uses partial matching so a caption that
    contains the target line somewhere in a larger block of text still
    scores correctly.
    """
    raise NotImplementedError("Phase 2 - not yet implemented")


def confidence_bucket(match_score: float, persists: bool) -> tuple:
    """
    Given a match_score (0-100) and whether the match persists across
    neighboring frames, return (bucket_string, reasoning_string).
    bucket_string is one of: 'High', 'Low', 'Not Found'
    """
    raise NotImplementedError("Phase 2 - not yet implemented")
