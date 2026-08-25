"""
matcher.py - Text normalization and fuzzy matching.

This module has zero external I/O and no model dependencies. Every function
here can be unit tested with a plain pytest run, no mocks needed.

Why a hybrid scorer and not just partial_ratio?
-----------------------------------------------
partial_ratio finds the best same-length substring overlap between two strings.
This is great for OCR noise (a dropped letter, a comma vs period) but has a
known false-positive problem: "run tired" scores high against "run slow" because
the "run " prefix creates a strong substring overlap.

We fix this with a hybrid approach:
  1. partial_ratio  - catches OCR character-level noise and multi-line captions
  2. token_set_ratio - forces word-level comparison (sorts and deduplicates tokens
                       before matching), so "run tired" vs "run slow" scores low
                       because "tired" and "slow" are different words.
  3. Take the MINIMUM of both scores - a string can't score high unless it
     passes BOTH the substring and the word-level check.

We also add two extra guards:
  - Word coverage check: for multi-word targets, require that the majority of
    target words appear (individually fuzzy-matched) in the OCR text.
  - Word boundary check for short (1-2 word) targets: "run" must appear as a
    whole word, not inside "running" or "runner".

All thresholds come from config.py so they can be tuned without touching
this file.
"""

import re
from rapidfuzz import fuzz, process
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


def _word_coverage(norm_ocr: str, norm_target_words: list) -> float:
    """
    Return the fraction of target words that appear (fuzz-matched) in norm_ocr.

    Each target word is checked against all words in the OCR text using a
    simple token presence check. A word is considered 'covered' if rapidfuzz
    finds an 80+ score match for it among the OCR words.

    This prevents "run tired" from matching "run slow": "tired" is not present
    in "run slow", so coverage falls below 1.0.

    Returns a float in [0.0, 1.0].
    """
    if not norm_target_words:
        return 1.0
    ocr_words = norm_ocr.split()
    if not ocr_words:
        return 0.0

    covered = 0
    for word in norm_target_words:
        # rapidfuzz process.extractOne returns the best match and its score
        result = process.extractOne(word, ocr_words, scorer=fuzz.ratio)
        if result and result[1] >= 80:
            covered += 1

    return covered / len(norm_target_words)


def score(ocr_text: str, target: str) -> float:
    """
    Return a fuzzy match score (0-100) between ocr_text and target.

    Both strings are normalized before scoring. Uses a hybrid approach:

    1. partial_ratio  - robust to OCR character errors and multi-line text
    2. token_set_ratio - robust to word reordering, forces word-level matching
    3. Take the MINIMUM - a string must pass BOTH checks to score high.
    4. Word coverage gate - for multi-word targets, require most target words
       are actually present in the OCR text (prevents "run" prefix false hits).
    5. Word boundary check - for very short targets (<=2 words), require each
       target word appears as a whole word (not inside a longer word).

    Returns 0.0 if either string is empty after normalization.

    Examples of bugs this fixes:
      - score("run slow", "run tired")     -> low  (was: high with partial_ratio)
      - score("running fast", "run")       -> low  (was: high, prefix in substring)
      - score("run tired fast", "run tired") -> high (still works, correct match)
      - score("My mind repels stagnation", "My mind rebels at stagnation") -> ~85
        (still high, minor OCR noise tolerance is preserved)
    """
    norm_ocr = normalize(ocr_text)
    norm_target = normalize(target)

    if not norm_ocr or not norm_target:
        return 0.0

    # Reject OCR text that is much shorter than the target.
    # partial_ratio gives 100 for any 1-char match, so a 1-char OCR output
    # would always score 100. We block this by requiring OCR length be at
    # least 30% of target length.
    if len(norm_ocr) < len(norm_target) * 0.3:
        return 0.0

    target_words = norm_target.split()
    num_target_words = len(target_words)

    # --- Guard 1: Word boundary check for short targets ---
    # For targets of 1-2 words, require each word to appear as a whole word
    # (not embedded in a longer word like "run" inside "running").
    # This catches prefix false-positives on short queries.
    if num_target_words <= 2:
        for word in target_words:
            if not re.search(r"\b" + re.escape(word) + r"\b", norm_ocr):
                return 0.0

    # --- Guard 2: Word coverage gate for multi-word targets ---
    # For longer targets, require that the majority of target words appear
    # individually in the OCR text. This catches the "run slow" vs "run tired"
    # class of false positives where a shared prefix scores high.
    if num_target_words > 2:
        coverage = _word_coverage(norm_ocr, target_words)
        # Require at least 60% of words covered (generous to allow OCR errors
        # on individual words while still blocking completely wrong phrases).
        if coverage < 0.60:
            return 0.0

    # --- Hybrid fuzzy score: take the MINIMUM of two complementary metrics ---
    #
    # partial_ratio: best substring alignment (good for: OCR errors, extra text)
    # token_set_ratio: word-set comparison after sorting tokens (good for:
    #   word reordering, different words with shared prefix)
    #
    # Taking the minimum ensures neither can paper over the other's weakness.
    partial = fuzz.partial_ratio(norm_target, norm_ocr)
    token_set = fuzz.token_set_ratio(norm_target, norm_ocr)

    return min(partial, token_set)


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
