"""
test_matcher.py - Unit tests for matcher.py

No mocks, no external dependencies, no model loading. Just plain function
calls. matcher.py has nothing external so every case here is deterministic.

Covers: normalize(), score(), confidence_bucket()
"""

import pytest
from dialogue_finder import matcher, config


class TestNormalize:
    def test_lowercases(self):
        assert matcher.normalize("HELLO") == "hello"

    def test_strips_punctuation(self):
        assert matcher.normalize("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert matcher.normalize("  hi   there  ") == "hi there"

    def test_handles_empty_string(self):
        assert matcher.normalize("") == ""

    def test_numbers_preserved(self):
        # digits are word characters so they should stay
        result = matcher.normalize("Episode 12")
        assert "12" in result

    def test_mixed_case_punctuation_spaces(self):
        # apostrophe becomes a space, so "It's" -> "it s"
        # this is fine for OCR matching since we use partial_ratio anyway
        result = matcher.normalize("  It's ALIVE!  ")
        assert result == "it s alive"

    def test_newlines_treated_as_whitespace(self):
        result = matcher.normalize("line one\nline two")
        assert result == "line one line two"


class TestScore:
    def test_exact_match_scores_100(self):
        s = matcher.score("hello world", "hello world")
        assert s == 100.0

    def test_case_insensitive(self):
        s = matcher.score("Hello World", "hello world")
        assert s == 100.0

    def test_target_in_longer_ocr_text(self):
        # partial_ratio should still score high when the target is a substring
        ocr = "subtitles: hello world, nice to meet you"
        target = "hello world"
        s = matcher.score(ocr, target)
        assert s >= 90.0

    def test_completely_different_text(self):
        s = matcher.score("the quick brown fox", "apple banana cherry")
        assert s < config.LOW_CONF_THRESHOLD

    def test_one_char_error(self):
        # OCR misread: 'I' became '1'
        s = matcher.score("1 am going home", "I am going home")
        assert s >= config.LOW_CONF_THRESHOLD

    def test_empty_ocr_returns_zero(self):
        assert matcher.score("", "hello world") == 0.0

    def test_empty_target_returns_zero(self):
        assert matcher.score("some ocr text", "") == 0.0

    def test_both_empty_returns_zero(self):
        assert matcher.score("", "") == 0.0

    def test_very_short_ocr_returns_zero(self):
        # "m" appears in "creative commons" so partial_ratio would give 100.0
        # without the length guard. This must return 0.
        assert matcher.score("M", "creative commons") == 0.0
        assert matcher.score("a", "I am going home") == 0.0

    def test_punctuation_differences_ignored(self):
        # target has comma and exclamation, ocr has neither
        s = matcher.score("hello world", "Hello, World!")
        assert s == 100.0

    def test_partial_word_overlap(self):
        # partial match - some words in common
        s = matcher.score("she said hello to the world", "hello world")
        assert s > 70.0


class TestConfidenceBucket:
    def test_high_confidence_when_score_and_persistence(self):
        label, reason = matcher.confidence_bucket(95.0, persists=True)
        assert label == "High"
        assert "95" in reason or "95.0" in reason

    def test_low_when_high_score_no_persistence(self):
        # score is good but match didn't persist across frames
        label, reason = matcher.confidence_bucket(95.0, persists=False)
        assert label == "Low"
        assert "persist" in reason.lower()

    def test_low_when_score_between_thresholds(self):
        mid = (config.LOW_CONF_THRESHOLD + config.HIGH_CONF_THRESHOLD) / 2
        label, reason = matcher.confidence_bucket(mid, persists=True)
        assert label == "Low"

    def test_not_found_when_score_below_low_threshold(self):
        label, reason = matcher.confidence_bucket(config.LOW_CONF_THRESHOLD - 1, persists=False)
        assert label == "Not Found"

    def test_boundary_at_high_threshold_with_persistence(self):
        # exactly at the high threshold with persistence should be High
        label, _ = matcher.confidence_bucket(float(config.HIGH_CONF_THRESHOLD), persists=True)
        assert label == "High"

    def test_boundary_at_low_threshold(self):
        # exactly at the low threshold should be Low (not Not Found)
        label, _ = matcher.confidence_bucket(float(config.LOW_CONF_THRESHOLD), persists=True)
        assert label == "Low"

    def test_reasoning_always_returned(self):
        for score_val in [50.0, 75.0, 95.0]:
            for persists in [True, False]:
                label, reason = matcher.confidence_bucket(score_val, persists)
                assert isinstance(reason, str)
                assert len(reason) > 0


class TestEdgeCases:
    """
    Tests covering false-positive bugs that were reported:

    Bug 1 (main reported bug): "run tired" incorrectly matched "run slow"
    because partial_ratio found the shared "run " prefix and scored high.
    The fix: hybrid scoring (min of partial_ratio + token_set_ratio) + word
    coverage gate means "tired" must be present in the OCR text.

    Bug 2: "run" matched "running" or "runner" because partial_ratio treats
    any substring as valid. The fix: word boundary check for short targets.

    Bug 3: Very short single-word queries on irrelevant text should score 0.
    """

    def test_run_tired_does_not_match_run_slow(self):
        # The primary reported bug: "run tired" was matching frames showing
        # "run slow" because both start with "run".
        s = matcher.score("run slow", "run tired")
        assert s < config.LOW_CONF_THRESHOLD, (
            f"'run tired' must not match 'run slow', got score={s}"
        )

    def test_run_tired_does_not_match_run_fast(self):
        s = matcher.score("run fast", "run tired")
        assert s < config.LOW_CONF_THRESHOLD

    def test_run_tired_does_not_match_run_angry(self):
        s = matcher.score("run angry", "run tired")
        assert s < config.LOW_CONF_THRESHOLD

    def test_run_tired_matches_run_tired(self):
        # The correct match must still score high.
        s = matcher.score("run tired", "run tired")
        assert s >= config.HIGH_CONF_THRESHOLD

    def test_run_tired_matches_in_longer_caption(self):
        # Target phrase embedded in a longer OCR block - must still score high.
        s = matcher.score("she was run tired from the day", "run tired")
        assert s >= config.LOW_CONF_THRESHOLD

    def test_run_does_not_match_running(self):
        # Word boundary check: "run" should not match "running"
        s = matcher.score("running fast", "run")
        assert s < config.LOW_CONF_THRESHOLD, (
            f"'run' must not match 'running', got score={s}"
        )

    def test_run_does_not_match_runner(self):
        s = matcher.score("the runner won", "run")
        assert s < config.LOW_CONF_THRESHOLD

    def test_run_matches_run_word(self):
        # Single word should match when it appears as a whole word.
        s = matcher.score("they run every day", "run")
        assert s >= config.LOW_CONF_THRESHOLD

    def test_ocr_noise_tolerance_preserved(self):
        # OCR often misreads letters. "rebels" -> "repels", "at" dropped.
        # This must still score above LOW threshold (real-world OCR case).
        s = matcher.score("My mind repels its stagnation", "My mind rebels at stagnation")
        assert s >= config.LOW_CONF_THRESHOLD, (
            f"OCR noise tolerance broken: score={s}"
        )

    def test_completely_different_phrases_with_one_common_word(self):
        # Sharing only one word should not be enough to match.
        s = matcher.score("the cat sat on the mat", "the dog ran in the park")
        assert s < config.LOW_CONF_THRESHOLD

    def test_empty_ocr_with_short_target(self):
        assert matcher.score("", "run") == 0.0

    def test_multiword_target_with_all_words_present(self):
        # All words of the target appear in OCR - should match.
        s = matcher.score("I cannot go on like this anymore", "cannot go on")
        assert s >= config.LOW_CONF_THRESHOLD

    def test_multiword_target_with_no_words_present(self):
        # None of the target words appear in OCR - must not match.
        s = matcher.score("hello there general kenobi", "run tired now")
        assert s < config.LOW_CONF_THRESHOLD
