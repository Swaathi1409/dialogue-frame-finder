# Dialogue Frame Finder

Find the exact video frame where a dialogue line is visually displayed as a burned-in caption, given a video URL and the target text.

## What it does

Given a video URL (OK.ru, YouTube, or any yt-dlp-supported site) and a target dialogue line, the tool returns:

- The frame number and timestamp (in seconds, using real fps)
- A PNG of the frame
- The OCR-recognized text from the frame
- A confidence level: **High**, **Low**, or **Not Found**

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.10+. No system ffmpeg or Tesseract needed — ffmpeg is bundled via `imageio-ffmpeg`.

> **Note:** PaddleOCR is pinned to `2.7.3` + `paddlepaddle==2.6.2`. PaddleOCR 3.x has breaking API changes and crashes on Windows CPU at inference time. See `prompts.txt` for the full explanation.

## Usage

```bash
python -m dialogue_finder "https://ok.ru/video/..." "she said I am going home"
```

Options:
```
--output-dir DIR    Where to save the result PNG (default: output/)
--work-dir DIR      Temp dir for download/audio (auto-cleaned if not set)
--json              Print result as JSON
--verbose           Show pipeline stage logs
```

## Example output

```
Timestamp : 00:04:03.000
Frame     : 5832
Text      : "My mind rebels at stagnation"
Image     : output/frame_5832.png

Match score : 95.0/100
Confidence  : High
Reason      : match score 95.0 >= 90 and confirmed across neighboring frames
```

## How it works

See [APPROACH.md](APPROACH.md) for the full algorithm description.

Short version:
1. Download video with yt-dlp
2. Extract 16kHz mono audio, transcribe with faster-whisper
3. Fuzzy-match target against transcript to find a search window
4. Coarse OCR scan inside the window, then bisect to the exact first frame
5. Confirm with persistence check (consecutive frames must also match)

## Running tests

```bash
python -m pytest tests/ -v
```

All tests run without a real video or model (fake OCR injected).

## OK.ru note

The Odnoklassniki extractor is present in yt-dlp and works correctly. Direct connections to ok.ru from some IPs produce a `ConnectionResetError` (IP/region block by OK.ru, not a code bug). The tool raises `DownloadError` with a clear message in that case.
