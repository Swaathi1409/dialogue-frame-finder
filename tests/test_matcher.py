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
