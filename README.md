# Dialogue Frame Finder

Find the exact video frame where a dialogue line is spoken or displayed, given a video URL and the target text.

## What it does

Given a video URL (OK.ru, YouTube, or any yt-dlp-supported site) and a target dialogue line, the tool returns:

- The frame number and timestamp (`HH:MM:SS.sss`)
- A PNG of the frame
- The extracted dialogue text (from OCR or speech recognition)
- A confidence level: **High**, **Low**, or **Not Found**

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Requires **Python 3.10+** and **Node.js** (for YouTube extraction).  
No system ffmpeg or Tesseract needed — ffmpeg is bundled.

> **Note:** PaddleOCR is pinned to `2.7.3` + `paddlepaddle==2.6.2`. Do not upgrade — PaddleOCR 3.x crashes on Windows CPU. See `prompts.txt` for details.

---

### 2a. Web UI (recommended)

```bash
python app.py
```

Open **http://localhost:5000** in your browser. Enter the video URL and dialogue, click Analyze.

---

### 2b. Command line

```bash
# OK.ru (auto-fallback downloader built in)
python -m dialogue_finder "https://ok.ru/video/248244667877" "My mind rebels at stagnation"

# YouTube (requires cookies.txt — see below)
python -m dialogue_finder "https://youtu.be/HAnw168huqA" "might draw a few of you here"

# Local file
python -m dialogue_finder sherlock.mp4 "My mind rebels at stagnation"

# Verbose output
python -m dialogue_finder "https://ok.ru/video/248244667877" "My mind rebels at stagnation" --verbose
```

Options:
```
--output-dir DIR    Where to save the result PNG (default: output/)
--work-dir DIR      Temp dir for download/audio (auto-cleaned if not set)
--json              Print result as JSON
--verbose           Show pipeline stage logs
```

---

## YouTube authentication (cookies.txt)

YouTube requires a logged-in session to download many videos. To enable this:

1. Install **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** in Chrome
2. Log into YouTube in Chrome, then go to [youtube.com](https://youtube.com)
3. Click the extension icon → **Export**
4. Save the file as **`cookies.txt`** in this project's root folder

The tool detects `cookies.txt` automatically. You only need to do this once.

> `cookies.txt` is in `.gitignore` and will not be committed.

---

## Example output

```
Timestamp : 00:05:28.990
Frame     : 7887
Text      : "My mind rebels its stagnation. Give me problems. Give me work."
Image     : output\frame_7887.png

Match score : 92.9/100
Confidence  : Low
Reason      : no on-screen text found by OCR, but ASR matched the spoken dialogue
              at 325.1-332.8s (score 93/100). Frame is at the midpoint of the
              spoken segment.
```

---

## How it works

See [APPROACH.md](APPROACH.md) for the full algorithm.

1. **Download** — yt-dlp fetches the video (with ok.ru fallback via okrudownloader.top API)
2. **Audio** — ffmpeg extracts 16kHz mono WAV
3. **ASR** — faster-whisper transcribes speech to timestamped segments
4. **Locate** — fuzzy-match target against transcript → search window
5. **OCR scan** — PaddleOCR scans frames in the window for burned-in text
6. **Fallback** — if no on-screen text found, uses ASR segment midpoint frame

---

## Running tests

```bash
python -m pytest tests/ -v
```

All 49 tests run without a real video or network access.

---

## OK.ru note

OK.ru uses TLS fingerprint filtering that blocks Python's SSL stack from some IPs. The tool automatically falls back to the `okrudownloader.top` API to get direct CDN URLs. If the fallback also fails (IP-locked CDN URLs), download the video manually in Chrome and pass the local file path instead.
