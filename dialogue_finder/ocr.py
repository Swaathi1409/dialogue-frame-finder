"""
ocr.py - Runs PaddleOCR on a single frame and returns recognized text
         plus a confidence score.

Why PaddleOCR over the alternatives:
  - Tesseract: older engine, noticeably worse on video overlay / caption
    style text in benchmarks. Also requires a separate system install.
  - EasyOCR: slower and less accurate than PaddleOCR on this kind of text.
  - PaddleOCR: returns per-detection confidence scores which we need for
    the confidence bucketing logic in matcher.py. Works fully offline after
    the first model download.

The module keeps a single PaddleOCR instance alive in _ocr_instance so
the model is loaded once and reused for every frame call. Loading it per
frame would make the coarse scan completely impractical.

run_ocr() returns (text, confidence) where:
  - text is all detected text blocks joined with spaces
  - confidence is the average PaddleOCR confidence across all detected
    blocks (0.0 to 1.0). If no text is detected, returns ("", 0.0).
    An empty result is not an error - most frames won't have captions.

Raises OCRError only on hard failures (model not loaded, OpenCV crash, etc.).
A frame with no text just returns empty strings.
"""

import logging
from typing import Tuple

import numpy as np

from dialogue_finder import config

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Raised when OCR fails in a way that prevents any result."""
    pass


# Module-level PaddleOCR instance - loaded once on first call.
_ocr_instance = None


def _get_ocr():
    """
    Initialize and cache the PaddleOCR instance.

    use_angle_cls=True: detects rotated text. Some subtitles are at an angle.
    lang='en': the primary OCR language. For non-English videos this should
               be overridden - but for the frame-finding task, the actual
               language matters less than detecting where text is on screen.
               If the target video is in another language, change this here
               or expose it as a config option in Phase 5.
    show_log=False: suppress PaddleOCR's own verbose output.
    det_db_box_thresh: how aggressively to detect text boxes. Lower = more
                       boxes detected including faint captions. Value from config.
    drop_score: detections below this PaddleOCR confidence are ignored.
    """
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance

    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        raise OCRError(
            "PaddleOCR is not installed. Run: pip install paddlepaddle paddleocr"
        ) from e

    logger.info("Loading PaddleOCR model (first call - this takes a few seconds)...")
    try:
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False,
            det_db_box_thresh=config.PADDLE_DET_DB_BOX_THRESH,
            drop_score=config.PADDLE_DROP_SCORE,
        )
    except Exception as e:
        raise OCRError(f"Failed to initialize PaddleOCR: {e}") from e

    logger.info("PaddleOCR model loaded.")
    return _ocr_instance


def run_ocr(frame: np.ndarray) -> Tuple[str, float]:
    """
    Run PaddleOCR on a BGR numpy frame and return (text, confidence).

    text: all detected text blocks joined with a single space.
    confidence: average PaddleOCR confidence across all detections (0.0-1.0).

    Returns ("", 0.0) if no text is detected - this is normal for frames
    that don't have any visible caption.

    Raises OCRError on hard failure (model not loaded, unexpected crash).
    A single bad frame should be caught by the caller and skipped, not
    treated as fatal to the whole pipeline.
    """
    ocr = _get_ocr()

    try:
        # PaddleOCR expects BGR (which is what OpenCV gives us) or RGB.
        # result is a nested list: result[0] is a list of detections.
        # Each detection is [bounding_box, (text_string, confidence_float)].
        result = ocr.ocr(frame, cls=True)
    except Exception as e:
        raise OCRError(f"PaddleOCR.ocr() raised an exception: {e}") from e

    # result can be None or [[None]] if no text is detected.
    if not result or result[0] is None:
        return ("", 0.0)

    detections = result[0]
    if not detections:
        return ("", 0.0)

    texts = []
    confidences = []

    for detection in detections:
        if detection is None:
            continue
        # detection format: [box_points, (text, score)]
        try:
            _, (text, conf) = detection
            if text and text.strip():
                texts.append(text.strip())
                confidences.append(float(conf))
        except (TypeError, ValueError) as e:
            # Malformed detection - skip it, don't crash.
            logger.debug("Skipping malformed OCR detection: %s", e)
            continue

    if not texts:
        return ("", 0.0)

    combined_text = " ".join(texts)
    avg_confidence = sum(confidences) / len(confidences)

    logger.debug(
        "OCR result: '%s' (avg conf %.2f, %d detections)",
        combined_text[:80],
        avg_confidence,
        len(texts),
    )

    return (combined_text, avg_confidence)
