"""
cli.py - Command-line entry point.

Usage:
    python -m dialogue_finder <URL> <"target dialogue line"> [options]

or after pip install:
    dialogue-finder <URL> <"target dialogue"> [options]

The CLI is intentionally thin: it parses args, calls run_pipeline(),
prints the result, and exits with 0 on success or 1 on failure.
All real logic is in pipeline.py.
"""

import argparse
import json
import logging
import sys

from dialogue_finder.pipeline import run_pipeline
from dialogue_finder.downloader import DownloadError
from dialogue_finder.transcriber import TranscriptionError
from dialogue_finder.audio import AudioExtractionError
from dialogue_finder.ocr import OCRError


def build_parser():
    p = argparse.ArgumentParser(
        prog="dialogue-finder",
        description="Find the first video frame where a dialogue line is visible on screen.",
    )
    p.add_argument("url", help="Video URL (OK.ru, YouTube, or any yt-dlp-supported site)")
    p.add_argument("target", help="Dialogue line to search for (quoted string)")
    p.add_argument(
        "--output-dir", default="output",
        help="Directory to save the result frame PNG (default: output/)"
    )
    p.add_argument(
        "--work-dir", default=None,
        help="Directory for temporary download/audio files. Cleaned up unless specified."
    )
    p.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Print result as JSON instead of human-readable text"
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show pipeline stage logs"
    )
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        result = run_pipeline(
            url=args.url,
            target=args.target,
            output_dir=args.output_dir,
            work_dir=args.work_dir,
        )
    except FileNotFoundError as e:
        _error(str(e), args.as_json)
        return 1
    except DownloadError as e:
        _error(f"Download failed: {e}", args.as_json)
        return 1
    except AudioExtractionError as e:
        _error(f"Audio extraction failed: {e}", args.as_json)
        return 1
    except TranscriptionError as e:
        _error(f"Transcription failed: {e}", args.as_json)
        return 1
    except OCRError as e:
        _error(f"OCR failed: {e}", args.as_json)
        return 1
    except Exception as e:
        _error(f"Unexpected error: {e}", args.as_json)
        return 1

    if args.as_json:
        print(json.dumps({
            "found": result.found,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "frame_number": result.frame_number,
            "timestamp_sec": result.timestamp_sec,
            "timestamp_hms": _fmt_ts(result.timestamp_sec) if result.timestamp_sec is not None else None,
            "ocr_text": result.ocr_text,
            "frame_image_path": result.frame_image_path,
            "match_score": result.match_score,
        }, indent=2))
    else:
        _print_human(result)

    return 0 if result.found else 1


def _fmt_ts(sec: float) -> str:
    """Convert seconds to HH:MM:SS.sss"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _print_human(result):
    if not result.found:
        print(f"\nNot Found")
        print(f"Confidence : {result.confidence}")
        print(f"Reason     : {result.reasoning}")
        return

    print(f"\nTimestamp : {_fmt_ts(result.timestamp_sec)}")
    print(f"Frame     : {result.frame_number}")
    print(f"Text      : \"{result.ocr_text}\"")
    print(f"Image     : {result.frame_image_path}")
    print(f"")
    print(f"Match score : {result.match_score:.1f}/100")
    print(f"Confidence  : {result.confidence}")
    print(f"Reason      : {result.reasoning}")


def _error(msg, as_json):
    if as_json:
        import json
        print(json.dumps({"error": msg}), file=sys.stderr)
    else:
        print(f"Error: {msg}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
