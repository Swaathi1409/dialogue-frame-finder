"""
ocr.py - Runs PaddleOCR on a single frame and returns the recognized text
         plus the engine's own confidence score.

PaddleOCR is the primary engine. If it is not installed or raises an
exception, the module raises OCRError with a clear message. A Tesseract
fallback is mentioned in APPROACH.md as a documented option but is not
wired in here unless needed and tested.
Raises OCRError on hard failure.
"""

# STUB - implemented in Phase 3

from typing import Tuple
import numpy as np


class OCRError(Exception):
    """Raised when OCR fails in a way we cannot recover from."""
    pass


def run_ocr(frame: np.ndarray) -> Tuple[str, float]:
    """
    Run OCR on a BGR numpy frame array.
    Returns (recognized_text, confidence) where confidence is 0.0-1.0.
    If no text is found, returns ("", 0.0) - this is not an error.
    Raises OCRError on hard failure (model not loaded, etc.).
    """
    raise NotImplementedError("Phase 3 - not yet implemented")
