"""
matcher.py - Text normalization and fuzzy matching.

This module has zero external I/O and no model dependencies. Every function
here can be unit tested with a plain pytest run, no mocks needed.

Why RapidFuzz partial_ratio and not exact match?
OCR makes small errors - a capital I becomes a 1, punctuation gets
dropped, spacing shifts. Exact matching would miss real hits. partial_ratio
checks whether the target appears as a substring of the OCR text (or vice
versa) rather than requiring full string equality. That handles the common
case where a caption block contains the target line among other text.

All thresholds come from config.py so they can be tuned without touching
this file.
"""

import re
from rapidfuzz import fuzz
from dialogue_finder import config


def normalize(text: str) -> str:
    """
    Lowercase, strip punctuation, collapse whitespace.

    We do this to both the OCR output and the target before scoring so
    small character-level differences (punctuation, casing, extra spaces)
    don't cause a miss on what is clearly the right line.

    Example:
      normalize("Hello, World!") -> "hello world"
      normalize("  hi  there  ") -> "hi there"
    """
    text = text.lower()
    # Remove anything that isn't a letter, digit, or whitespace.
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse multiple spaces into one and strip edges.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score(ocr_text: str, target: str) -> float:
    """
    Return a fuzzy match score (0-100) between ocr_text and target.

    Both strings are normalized before scoring.

    Matching strategy (two-mode):
    ─────────────────────────────
    • Standalone caption mode (OCR text is within 2× the target length):
      The frame shows a caption that is roughly the same length as what
      we are looking for. In this case we blend partial_ratio with ratio
      (equal weight). partial_ratio alone is too permissive here: it finds
      the best same-length window inside the OCR text, so "run slow" scores
      ~72 against "run tired" just because they share the word "run".
      Taking the average forces full-string similarity to matter, so "run slow"
      vs "run tired" drops to ~50 and won't clear the LOW_CONF_THRESHOLD.

    • Substring mode (OCR text is much longer than the target):
      The caption block contains multiple lines or extra text beyond the
      target phrase. partial_ratio is exactly right here: we want to find
      whether the target appears *anywhere* inside the longer text.

    Returns 0.0 if either string is empty after normalization.
    """
    norm_ocr = normalize(ocr_text)
    norm_target = normalize(target)

    if not norm_ocr or not norm_target:
        return 0.0

    # Reject OCR text that is much shorter than the target - it can't
    # contain the full phrase even as a substring.
    if len(norm_ocr) < len(norm_target) * 0.3:
        return 0.0

    partial = fuzz.partial_ratio(norm_target, norm_ocr)

    # If the OCR text is roughly the same length as the target (standalone
    # caption), penalize mismatched content by blending in full-string ratio.
    # Threshold: 2× target length. Beyond that, the substring mode takes over.
    if len(norm_ocr) <= len(norm_target) * 2:
        full = fuzz.ratio(norm_target, norm_ocr)
        return (partial + full) / 2.0

    # Substring mode: OCR text is a long block; look for the target inside it.
    return partial


def confidence_bucket(match_score: float, persists: bool) -> tuple:
    """
    Map a numeric match score and persistence flag to a confidence label.

    Returns (label, reasoning) where label is 'High', 'Low', or 'Not Found'.

    Rules (thresholds are named constants in config.py, not magic numbers):
      - High: score >= HIGH_CONF_THRESHOLD AND the match persists across
              neighboring frames. Both conditions required because a single
              high-scoring frame could be an OCR fluke.
      - Low:  score >= LOW_CONF_THRESHOLD but either the score is below
              HIGH_CONF_THRESHOLD or persistence check failed. Worth
              reporting but flagged so the caller knows it's uncertain.
      - Not Found: score below LOW_CONF_THRESHOLD. We don't report this
              as a match at all.

    These thresholds are engineering heuristics picked by judgment. They
    are not derived from a statistical study. APPROACH.md says this clearly.
    """
    if match_score >= config.HIGH_CONF_THRESHOLD and persists:
        reasoning = (
            f"match score {match_score:.1f} >= {config.HIGH_CONF_THRESHOLD} "
            f"and confirmed across neighboring frames"
        )
        return ("High", reasoning)

    if match_score >= config.HIGH_CONF_THRESHOLD and not persists:
        reasoning = (
            f"match score {match_score:.1f} is high but match did not persist "
            f"across neighboring frames - could be a single-frame OCR noise hit"
        )
        return ("Low", reasoning)

    if match_score >= config.LOW_CONF_THRESHOLD:
        reasoning = (
            f"match score {match_score:.1f} is between {config.LOW_CONF_THRESHOLD} "
            f"and {config.HIGH_CONF_THRESHOLD} - possible match but not confident"
        )
        return ("Low", reasoning)

    reasoning = (
        f"best match score {match_score:.1f} is below the low threshold "
        f"of {config.LOW_CONF_THRESHOLD} - no reliable match found"
    )
    return ("Not Found", reasoning)
