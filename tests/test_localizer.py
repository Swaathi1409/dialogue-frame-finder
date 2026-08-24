"""
test_localizer.py - Tests for find_asr_window() and fallback_window()

These run without any model or video file. We build fake TranscriptSegment
lists directly and pass them in. The tests check the window boundaries,
the source field, and the fallback behavior.
"""

import pytest
from dialogue_finder.models import TranscriptSegment
from dialogue_finder.localizer import find_asr_window, fallback_window
from dialogue_finder import config


def make_segments(*items):
    """Helper: make a list of TranscriptSegment from (text, start, end) tuples."""
    return [TranscriptSegment(text=t, start_sec=s, end_sec=e) for t, s, e in items]


class TestFindAsrWindow:
    def test_returns_window_when_good_match(self):
        segs = make_segments(
            ("some unrelated line", 5.0, 7.0),
            ("she said I am going home now", 20.0, 23.0),
            ("another line", 30.0, 32.0),
        )
        window = find_asr_window(segs, "I am going home", video_duration_sec=120.0)
        assert window is not None
        assert window.source == "asr"

    def test_window_padded_before_and_after(self):
        segs = make_segments(("I am going home", 20.0, 22.0))
        window = find_asr_window(segs, "I am going home", video_duration_sec=120.0)
        assert window is not None
        expected_start = 20.0 - config.ASR_PAD_BEFORE_SEC
        expected_end = 22.0 + config.ASR_PAD_AFTER_SEC
        assert abs(window.start_sec - expected_start) < 0.01
        assert abs(window.end_sec - expected_end) < 0.01

    def test_window_clamped_at_zero(self):
        # segment starts at 1 second, pad before is 3 seconds
        # window start should clamp to 0, not go negative
        segs = make_segments(("I am going home", 1.0, 3.0))
        window = find_asr_window(segs, "I am going home", video_duration_sec=120.0)
        assert window is not None
        assert window.start_sec >= 0.0

    def test_window_clamped_at_video_duration(self):
        # segment ends near the end of the video
        duration = 30.0
        segs = make_segments(("I am going home", 27.0, 29.0))
        window = find_asr_window(segs, "I am going home", video_duration_sec=duration)
        assert window is not None
        assert window.end_sec <= duration

    def test_returns_none_when_no_match(self):
        segs = make_segments(
            ("completely unrelated text", 5.0, 7.0),
            ("nothing relevant here at all", 10.0, 12.0),
        )
        window = find_asr_window(segs, "I am going home", video_duration_sec=60.0)
        assert window is None

    def test_returns_none_when_empty_segments(self):
        window = find_asr_window([], "I am going home", video_duration_sec=60.0)
        assert window is None

    def test_asr_score_stored_in_window(self):
        segs = make_segments(("I am going home", 10.0, 12.0))
        window = find_asr_window(segs, "I am going home", video_duration_sec=60.0)
        assert window is not None
        assert window.asr_score > 0.0

    def test_picks_best_matching_segment(self):
        # two segments, only the second one really matches
        segs = make_segments(
            ("random words", 5.0, 7.0),
            ("she said I am going home to rest", 20.0, 23.0),
        )
        window = find_asr_window(segs, "I am going home", video_duration_sec=120.0)
        assert window is not None
        # the window should be around the 20-23 second segment, not the 5-7 one
        assert window.start_sec > 10.0

    def test_case_insensitive_matching(self):
        segs = make_segments(("I AM GOING HOME", 10.0, 12.0))
        window = find_asr_window(segs, "i am going home", video_duration_sec=60.0)
        assert window is not None


class TestFallbackWindow:
    def test_covers_full_video(self):
        window = fallback_window(video_duration_sec=300.0)
        assert window.start_sec == 0.0
        assert window.end_sec == 300.0

    def test_source_is_fallback(self):
        window = fallback_window(video_duration_sec=100.0)
        assert window.source == "fallback"

    def test_asr_score_is_zero(self):
        window = fallback_window(video_duration_sec=100.0)
        assert window.asr_score == 0.0

    def test_zero_duration_video(self):
        # edge case - should not crash
        window = fallback_window(video_duration_sec=0.0)
        assert window.start_sec == 0.0
        assert window.end_sec == 0.0
