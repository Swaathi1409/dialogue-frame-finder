"""
pipeline.py - Orchestrates all pipeline stages end to end.

Accepts either a URL (any yt-dlp-supported site) or a local file path.
If the input is an existing local file, the download stage is skipped.

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


def _looks_like_file(path: str) -> bool:
    """True if the input looks like a local file path rather than a URL."""
    if path.startswith(("http://", "https://", "ftp://", "rtmp://")):
        return False
    # If it has a video extension or no scheme at all, treat as local
    VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v")
    return any(path.lower().endswith(e) for e in VIDEO_EXTS) or "://" not in path


def _run(url, target, output_dir, work_dir):
    # 1. Download (skip if input is a local file path)
    if _looks_like_file(url):
        if not os.path.isfile(url):
            raise FileNotFoundError(
                f"Local file not found: '{url}'\n"
                f"Tip: download the video first with:\n"
                f"  yt-dlp \"<URL>\" -o \"{url}\""
            )
        logger.info("Stage 1: Using local file: %s", url)
        video_path = url
    else:
        logger.info("Stage 1: Downloading video from %s", url)
        video_path = download_video(url, work_dir)
    logger.info("Video: %s", video_path)

    # 2. Video metadata
    logger.info("Stage 2: Reading video metadata")
    video_info = get_video_info(video_path)
    logger.info("fps=%.4f  frames=%d  duration=%.1fs",
                video_info.fps, video_info.total_frames, video_info.duration_sec)

    # 3. Audio extraction + 4. ASR - both optional
    # If the video has no audio track or transcription fails, we fall
    # through to the full-video fallback scan. This is not an error.
    segments = []
    try:
        logger.info("Stage 3: Extracting audio")
        audio_path = os.path.join(work_dir, "audio.wav")
        extract_audio(video_path, audio_path)

        logger.info("Stage 4: Transcribing audio with Whisper")
        segments = transcribe(audio_path)
        logger.info("%d segments transcribed", len(segments))
    except Exception as e:
        logger.warning("Audio/ASR stage failed (%s) - using full-video fallback", e)

    # 5. Localization
    logger.info("Stage 5: Finding search window")
    window = find_asr_window(segments, target, video_info.duration_sec)
    if window is None:
        logger.info("ASR found no match, using full-video fallback")
        window = fallback_window(video_info.duration_sec)
    logger.info("Search window: %.1f-%.1fs (source=%s)", window.start_sec, window.end_sec, window.source)

    # 6. Frame search (OCR-based)
    logger.info("Stage 6: Scanning frames with OCR")
    candidate = search_frames(video_path, video_info, window, target, run_ocr)

    if candidate is None:
        # OCR found no on-screen text matching the target.
        # If ASR matched strongly, the dialogue is spoken on screen (no burned-in
        # subtitles). Return the frame at the midpoint of the ASR segment.
        # This is the correct answer for "on-screen dialogue" = spoken by a
        # character visible in the frame.
        if (
            window.source == "asr"
            and window.asr_segment is not None
            and window.asr_score >= config.ASR_MATCH_THRESHOLD
        ):
            seg = window.asr_segment
            mid_sec = (seg.start_sec + seg.end_sec) / 2.0
            frame_number = int(mid_sec * video_info.fps)
            logger.info(
                "OCR found nothing - using ASR segment midpoint frame %d (%.1fs)",
                frame_number, mid_sec,
            )
            frame_img = extract_frame(video_path, frame_number)
            os.makedirs(output_dir, exist_ok=True)
            frame_path = os.path.join(output_dir, f"frame_{frame_number}.png")
            save_frame(frame_img, frame_path)
            return FinderResult(
                found=True,
                confidence="Low",
                reasoning=(
                    f"no on-screen text found by OCR, but ASR matched the spoken "
                    f"dialogue at {seg.start_sec:.1f}-{seg.end_sec:.1f}s "
                    f"(score {window.asr_score:.0f}/100). "
                    f"Frame is at the midpoint of the spoken segment."
                ),
                frame_number=frame_number,
                timestamp_sec=mid_sec,
                ocr_text=seg.text.strip(),
                frame_image_path=frame_path,
                match_score=window.asr_score,
            )

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

