"""
pipeline.py - Orchestrates all pipeline stages end to end.

run_pipeline() is the single function callers use. It:
  1. Downloads the video (downloader.py)
  2. Extracts 16kHz mono audio (audio.py)
  3. Reads video metadata - fps, frame count (frame_extractor.py)
  4. Transcribes audio to timestamped segments (transcriber.py)
  5. Fuzzy-matches target against transcript to get a SearchWindow
     (localizer.py) - falls back to full-video scan if ASR fails
  6. Scans frames inside the window with OCR (frame_search.py + ocr.py)
  7. Assigns a confidence bucket (matcher.py)
  8. Saves the frame PNG and returns a FinderResult

All exceptions from each stage bubble up with their own typed error
(DownloadError, TranscriptionError, OCRError, etc.). The caller in
cli.py handles them and prints a plain message to stderr.
"""

import logging
import os
import tempfile

from dialogue_finder import config
from dialogue_finder.downloader import download_video
from dialogue_finder.audio import extract_audio
from dialogue_finder.frame_extractor import get_video_info, extract_frame, save_frame
from dialogue_finder.transcriber import transcribe
from dialogue_finder.localizer import find_asr_window, fallback_window
from dialogue_finder.frame_search import search_frames
from dialogue_finder.ocr import run_ocr
from dialogue_finder.matcher import confidence_bucket
from dialogue_finder.models import FinderResult

logger = logging.getLogger(__name__)


def run_pipeline(
    url: str,
    target: str,
    output_dir: str = None,
    work_dir: str = None,
) -> FinderResult:
    """
    Full pipeline: URL + target dialogue → FinderResult.

    output_dir: where to save the output PNG. Defaults to config.OUTPUT_DIR.
    work_dir: temp directory for downloaded video and audio.
              If None, a system temp dir is created and cleaned up on exit.
    """
    if output_dir is None:
        output_dir = config.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    _cleanup = work_dir is None
    if _cleanup:
        work_dir = tempfile.mkdtemp(prefix="dff_work_")
    try:
        return _run(url, target, output_dir, work_dir)
    finally:
        if _cleanup:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)


def _run(url, target, output_dir, work_dir):
    # 1. Download
    logger.info("Stage 1: Downloading video from %s", url)
    video_path = download_video(url, work_dir)
    logger.info("Video: %s", video_path)

    # 2. Video metadata
    logger.info("Stage 2: Reading video metadata")
    video_info = get_video_info(video_path)
    logger.info("fps=%.4f  frames=%d  duration=%.1fs",
                video_info.fps, video_info.total_frames, video_info.duration_sec)

    # 3. Audio extraction
    logger.info("Stage 3: Extracting audio")
    audio_path = os.path.join(work_dir, "audio.wav")
    extract_audio(video_path, audio_path)

    # 4. ASR transcription
    logger.info("Stage 4: Transcribing audio with Whisper")
    segments = transcribe(audio_path)
    logger.info("%d segments transcribed", len(segments))

    # 5. Localization
    logger.info("Stage 5: Finding search window")
    window = find_asr_window(segments, target, video_info.duration_sec)
    if window is None:
        logger.info("ASR found no match, using full-video fallback")
        window = fallback_window(video_info.duration_sec)
    logger.info("Search window: %.1f-%.1fs (source=%s)", window.start_sec, window.end_sec, window.source)

    # 6. Frame search
    logger.info("Stage 6: Scanning frames with OCR")
    candidate = search_frames(video_path, video_info, window, target, run_ocr)

    if candidate is None:
        label, reasoning = confidence_bucket(0.0, False)
        return FinderResult(found=False, confidence=label, reasoning=reasoning)

    # 7. Confidence
    label, reasoning = confidence_bucket(candidate.match_score, candidate.persists)

    # 8. Save frame
    frame_img = extract_frame(video_path, candidate.frame_number)
    os.makedirs(output_dir, exist_ok=True)
    frame_path = os.path.join(output_dir, f"frame_{candidate.frame_number}.png")
    save_frame(frame_img, frame_path)
    logger.info("Saved frame: %s", frame_path)

    return FinderResult(
        found=True,
        confidence=label,
        reasoning=reasoning,
        frame_number=candidate.frame_number,
        timestamp_sec=candidate.timestamp_sec,
        ocr_text=candidate.ocr_text,
        frame_image_path=frame_path,
        match_score=candidate.match_score,
    )
