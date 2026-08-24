"""
models.py - Data structures passed between pipeline stages.

Kept as plain dataclasses so every stage can import them without
creating circular dependencies. No logic lives here.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranscriptSegment:
    """One time-stamped piece of text from the ASR transcription."""
    text: str
    start_sec: float
    end_sec: float


@dataclass
class SearchWindow:
    """
    The time range (in seconds) that the frame searcher will scan.
    source says where this window came from: 'asr' or 'fallback'.
    """
    start_sec: float
    end_sec: float
    source: str          # 'asr' or 'fallback'
    asr_score: float = 0.0   # fuzzy match score that produced this window (0 if fallback)


@dataclass
class FrameCandidate:
    """
    A single frame that cleared the OCR fuzzy match threshold.
    All the raw signals are stored here so the confidence logic can
    look at them together rather than having them scattered.
    """
    frame_number: int
    timestamp_sec: float
    ocr_text: str
    match_score: float           # RapidFuzz partial_ratio, 0-100
    ocr_confidence: float        # PaddleOCR's own confidence, 0-1
    persists: bool = False       # True once the persistence check passes


@dataclass
class FinderResult:
    """
    The final answer returned by the pipeline.
    If found is False, all optional fields will be None.
    """
    found: bool
    confidence: str              # 'High', 'Low', or 'Not Found'
    reasoning: str               # plain-language explanation of why
    frame_number: Optional[int] = None
    timestamp_sec: Optional[float] = None
    ocr_text: Optional[str] = None
    frame_image_path: Optional[str] = None
    match_score: Optional[float] = None
