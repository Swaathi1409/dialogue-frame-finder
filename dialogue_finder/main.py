"""
main.py - Entry point. Wires the full pipeline together.

Parses CLI arguments, calls each stage in order, handles exceptions
from each module, and prints structured output. If any stage raises
a typed exception (DownloadError, TranscriptionError, etc.) it prints
a clear error and exits - never silently continues on a broken state.
"""

# STUB - implemented in Phase 5

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Find the exact video frame where a dialogue line appears on screen."
    )
    p.add_argument("url", help="Video URL (e.g. OK.ru link)")
    p.add_argument("dialogue", help="The dialogue line to search for")
    p.add_argument(
        "--output-dir", default="output", help="Directory to save the result frame PNG"
    )
    p.add_argument(
        "--whisper-model", default=None, help="Whisper model size override (tiny/base/small)"
    )
    p.add_argument(
        "--language", default=None, help="Language hint for Whisper (e.g. 'ru', 'en')"
    )
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    # Full pipeline wired in Phase 5
    print("Phase 0 stub: CLI argument parsing works.")
    print(f"  URL: {args.url}")
    print(f"  Dialogue: {args.dialogue}")


if __name__ == "__main__":
    main()
