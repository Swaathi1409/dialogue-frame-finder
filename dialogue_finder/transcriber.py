"""
transcriber.py - Wraps faster-whisper to get timestamped text segments.

faster-whisper is a reimplementation of OpenAI Whisper that runs 4x faster
on CPU by using CTranslate2 under the hood. We use the "base" model by
default (configurable in config.py). It gives us word-level timestamps,
which is more than we need - we only use segment-level start/end times
to build a search window, not to do fine-grained alignment.

The output is a list of TranscriptSegment objects. Each has the text and
a start/end time in seconds. We hand these to localizer.py which fuzzy-
matches the target dialogue against them to find a time window to search.

This module only does ASR - it does not confirm text is visually on screen.
That job belongs to OCR in a later stage.

Raises TranscriptionError on failure.
"""

import logging
from typing import List, Optional

from dialogue_finder import config
from dialogue_finder.models import TranscriptSegment

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


# Module-level model cache so we don't reload the model for every call.
# faster-whisper model loading takes a few seconds the first time.
_model = None
_loaded_model_size = None


def _get_model(model_size: str):
    """
    Load and cache the faster-whisper model.
    Reloads only if a different model size is requested.
    """
    global _model, _loaded_model_size

    if _model is not None and _loaded_model_size == model_size:
        return _model

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from e

    logger.info("Loading Whisper model '%s' (CPU, int8)...", model_size)

    # device="cpu", compute_type="int8" is the standard CPU-only setup.
    # int8 quantization cuts memory usage and speeds up inference with
    # negligible accuracy loss for the word-level timing we need.
    _model = WhisperModel(model_size, device="cpu", compute_type="int8")
    _loaded_model_size = model_size
    logger.info("Whisper model loaded.")
    return _model


def transcribe(
    audio_path: str,
    language: Optional[str] = None,
    model_size: Optional[str] = None,
) -> List[TranscriptSegment]:
    """
    Run faster-whisper on audio_path and return a list of TranscriptSegments.

    Each segment has the recognized text, a start time, and an end time in
    seconds. Segments roughly correspond to sentences or short phrases.

    language: ISO 639-1 code (e.g. 'ru', 'en'). None means auto-detect.
    model_size: overrides config.WHISPER_MODEL_SIZE for this call.

    Raises TranscriptionError if the model fails to load or transcription
    raises an unexpected exception.
    """
    if model_size is None:
        model_size = config.WHISPER_MODEL_SIZE
    if language is None:
        language = config.WHISPER_LANGUAGE

    try:
        model = _get_model(model_size)
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper model: {e}") from e

    logger.info("Transcribing: %s", audio_path)

    try:
        # word_timestamps=True gives per-word timing. We don't use it directly
        # but it improves segment boundary accuracy for short segments.
        segments_iter, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,      # skip silent regions, speeds up processing
        )
        logger.info(
            "Detected language: %s (%.0f%% confident)",
            info.language,
            info.language_probability * 100,
        )
    except Exception as e:
        raise TranscriptionError(f"Transcription failed: {e}") from e

    segments: List[TranscriptSegment] = []
    try:
        for seg in segments_iter:
            segments.append(
                TranscriptSegment(
                    text=seg.text.strip(),
                    start_sec=seg.start,
                    end_sec=seg.end,
                )
            )
    except Exception as e:
        raise TranscriptionError(f"Error while reading transcription output: {e}") from e

    logger.info("Transcription complete: %d segments", len(segments))
    return segments
