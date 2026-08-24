"""
test_frame_search.py - Tests for frame_search.py

No real video or OCR model needed. We inject a fake OCR function that
maps frame numbers to predetermined text via a closure, and a fake
video_path string (never opened - extract_frame is also mocked).
"""
import pytest
from unittest.mock import patch
import numpy as np

from dialogue_finder.models import SearchWindow
from dialogue_finder.frame_extractor import VideoInfo
from dialogue_finder.frame_search import (
    search_frames, _bisect_transition, _local_scan, _check_persistence,
)
from dialogue_finder import config


def make_video_info(fps=24.0, total_frames=2400):
    return VideoInfo(fps=fps, total_frames=total_frames,
                     duration_sec=total_frames / fps, width=1920, height=1080)


def make_ocr_fn(frame_text_map: dict, default=""):
    def ocr_fn(frame):
        idx = int(frame[0, 0, 0])
        text = frame_text_map.get(idx, default)
        return (text, 0.9 if text else 0.0)
    return ocr_fn


def make_extract(frame_text_map: dict):
    def fake_extract(video_path, frame_num):
        f = np.zeros((10, 10, 3), dtype=np.uint8)
        f[0, 0, 0] = frame_num % 256
        return f
    return fake_extract


def window(start=0.0, end=10.0, source="asr"):
    return SearchWindow(start_sec=start, end_sec=end, source=source, asr_score=80.0)


TARGET = "I am going home"
MATCH_TEXT = "she said I am going home now"


class TestLocalScan:
    def test_finds_first_matching_frame(self):
        frame_map = {5: MATCH_TEXT, 6: MATCH_TEXT}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            frame, score, text = _local_scan("fake.mp4", 3, 9, TARGET, make_ocr_fn(frame_map))
        assert frame == 5
        assert score >= config.LOW_CONF_THRESHOLD

    def test_returns_none_when_no_match(self):
        with patch("dialogue_finder.frame_search.extract_frame", make_extract({})):
            frame, score, text = _local_scan("fake.mp4", 0, 9, TARGET, make_ocr_fn({}))
        assert frame is None

    def test_returns_earliest_frame(self):
        frame_map = {3: MATCH_TEXT, 7: MATCH_TEXT}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            frame, _, _ = _local_scan("fake.mp4", 0, 9, TARGET, make_ocr_fn(frame_map))
        assert frame == 3


class TestCheckPersistence:
    def test_true_when_consecutive_matches(self):
        frame_map = {11: MATCH_TEXT, 12: MATCH_TEXT}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            result = _check_persistence("fake.mp4", 10, 100, TARGET, make_ocr_fn(frame_map))
        assert result is True

    def test_false_when_no_follow_matches(self):
        with patch("dialogue_finder.frame_search.extract_frame", make_extract({})):
            result = _check_persistence("fake.mp4", 10, 100, TARGET, make_ocr_fn({}))
        assert result is False

    def test_false_when_gap_in_persistence(self):
        # only frame 11 matches, not 12 — not consecutive enough
        frame_map = {11: MATCH_TEXT}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            result = _check_persistence("fake.mp4", 10, 100, TARGET, make_ocr_fn(frame_map))
        assert result is False


class TestSearchFrames:
    def test_returns_none_when_no_match(self):
        info = make_video_info(fps=1.0, total_frames=20)
        with patch("dialogue_finder.frame_search.extract_frame", make_extract({})):
            result = search_frames("fake.mp4", info, window(0, 20), TARGET, make_ocr_fn({}))
        assert result is None

    def test_finds_frame_when_match_exists(self):
        info = make_video_info(fps=1.0, total_frames=20)
        frame_map = {f: MATCH_TEXT for f in range(10, 16)}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            result = search_frames("fake.mp4", info, window(0, 20), TARGET, make_ocr_fn(frame_map))
        assert result is not None
        assert result.frame_number <= 12
        assert result.match_score >= config.LOW_CONF_THRESHOLD

    def test_fallback_window_works(self):
        info = make_video_info(fps=1.0, total_frames=30)
        frame_map = {f: MATCH_TEXT for f in range(20, 28)}
        w = SearchWindow(start_sec=0, end_sec=30, source="fallback", asr_score=0.0)
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            result = search_frames("fake.mp4", info, w, TARGET, make_ocr_fn(frame_map))
        assert result is not None

    def test_result_has_correct_fields(self):
        info = make_video_info(fps=1.0, total_frames=20)
        frame_map = {f: MATCH_TEXT for f in range(5, 15)}
        with patch("dialogue_finder.frame_search.extract_frame", make_extract(frame_map)):
            result = search_frames("fake.mp4", info, window(0, 20), TARGET, make_ocr_fn(frame_map))
        assert result is not None
        assert isinstance(result.frame_number, int)
        assert isinstance(result.timestamp_sec, float)
        assert isinstance(result.match_score, float)
        assert isinstance(result.persists, bool)

    def test_narrow_window_returns_none(self):
        info = make_video_info(fps=1.0, total_frames=100)
        w = SearchWindow(start_sec=5.0, end_sec=5.0, source="asr", asr_score=80.0)
        with patch("dialogue_finder.frame_search.extract_frame", make_extract({})):
            result = search_frames("fake.mp4", info, w, TARGET, make_ocr_fn({}))
        assert result is None
