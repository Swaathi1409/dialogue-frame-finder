# Dialogue Frame Finder

🚀 **Live Demo:** [https://dialogue-frame-finder.onrender.com](https://dialogue-frame-finder.onrender.com)

Find the exact video frame where a dialogue line is spoken or displayed, given a video URL and the target text.

## What it does

Given a video URL (OK.ru, YouTube, or any yt-dlp-supported site) and a target dialogue line, the tool returns:

- The frame number and timestamp (`HH:MM:SS.sss`)
- A PNG of the frame
- The extracted dialogue text (from OCR or speech recognition)
- A confidence level: **High**, **Low**, or **Not Found**

---

## Complete Setup Guide (Local Machine)

> **Also available as a Word document:** [`SETUP_GUIDE.docx`](SETUP_GUIDE.docx) — printable and shareable.

### Prerequisites

Before starting, install:
- **Python 3.10+** → [python.org/downloads](https://www.python.org/downloads/) *(check "Add to PATH" on Windows)*
- **Git** → [git-scm.com](https://git-scm.com/downloads)
- **Google Chrome** → needed only for YouTube cookie export

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/Swaathi1409/dialogue-frame-finder.git
cd dialogue-frame-finder
```

---

### Step 2 — Create a virtual environment *(recommended)*

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

---

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

> ⚠ **Do NOT upgrade PaddleOCR or paddlepaddle.** They are pinned to `2.7.3` / `2.6.2`. Upgrading crashes the tool on CPU-only machines.

---

### Step 4 — Install the Playwright browser *(for OK.ru videos)*

```bash
playwright install chromium
```

---

### Step 5 — Set up YouTube cookies *(for YouTube videos)*

YouTube blocks script-based downloads (bot detection). Each person must export **their own** cookies from their own logged-in Chrome browser — once. After that, YouTube downloads work permanently on your machine.

1. Install **[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** in Chrome
2. Make sure you are **logged into YouTube** in Chrome
3. Go to **[youtube.com](https://youtube.com)** (homepage — not a video). Accept any consent banner.
4. Click the extension icon → **Export**
5. Save the file as **`cookies.txt`** in the project root folder (same folder as `app.py`)

> `cookies.txt` is in `.gitignore` and will never be committed to GitHub.  
> ⚠ **Each person who clones this repo must export their OWN cookies** — cookies are tied to a specific YouTube account and cannot be shared.

---

### Step 6 — Run

**Web UI (recommended):**
```bash
python app.py
```
Open **http://localhost:5000** in your browser.

**Command line:**
```bash
python -m dialogue_finder "https://youtu.be/VIDEO_ID" "dialogue to find"
```

---

## Supported video sources

| Source | Works locally? | Works on live site? |
|---|---|---|
| YouTube | ✅ Yes (with cookies.txt) | ⚠ Needs server-side cookies |
| Instagram | ✅ Yes | ✅ Yes |
| OK.ru | ✅ Yes (via Playwright) | ✅ Yes |
| Local MP4 | ✅ Yes | ❌ No |

---

## Common errors & fixes

**`Sign in to confirm you're not a bot`** → Export a fresh `cookies.txt` from Chrome (Step 5 above).

**`pyclipper` / `zlib` crash** → Run: `pip install --force-reinstall pyclipper`

**`No module named playwright`** → Run: `pip install playwright && playwright install chromium`

---

## Command line options

```
--output-dir DIR    Where to save the result PNG (default: output/)
--work-dir DIR      Temp dir for download/audio (auto-cleaned if not set)
--json              Print result as JSON
--verbose           Show pipeline stage logs
```

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
3. **ASR** — faster-whisper transcribes speech to timestamped segments (using `tiny` model for CPU speed)
4. **Locate** — fuzzy-match target against transcript → search window (padded by a few seconds)
5. **OCR scan** — PaddleOCR scans frames in the window for burned-in text at 1.0s intervals
6. **Fallback** — if no on-screen text found, uses ASR segment midpoint frame

---

## Running tests

```bash
python -m pytest tests/ -v
```

All 50+ tests run without a real video or network access.

---

## Docker Deployment

You can run both the CLI and Web UI via Docker without installing any Python or system dependencies on your machine. The image comes with PaddleOCR, Whisper, and Playwright Chromium pre-baked.

### Build the image

```bash
# This takes 10-15 minutes on the first run (bakes AI models and headless browser)
docker build --network=host -t dialogue-frame-finder .
```

### Run the CLI

Mount an output directory to save the extracted frame:

```bash
mkdir -p output
docker run --rm -v "${PWD}/output:/app/output" dialogue-frame-finder "https://youtu.be/Pae6tjZ2jxs" "so happy you are here today"
```

### Run the Web UI

Run the container in detached mode (`-d`) and map port 5000:

```bash
docker run -d -p 5001:5000 --name dff-web dialogue-frame-finder web
```

Then visit **http://localhost:5001** in your browser.

---

## Cloud Deployment (Render.com)

The project includes a `render.yaml` file for 1-click deployment to [Render](https://render.com/).

1. Push this code to a repository on GitHub.
2. Sign up for Render and click **New+** -> **Blueprint**.
3. Connect your GitHub repository.
4. Render will automatically read `render.yaml`, build the Docker image, and deploy the web UI to a public URL.

*(Note: The build process takes 10-15 minutes because it downloads PaddleOCR and Whisper models into the container).*

---

## OK.ru note

OK.ru uses TLS/JA3 fingerprint filtering that actively blocks Python's SSL/network stack from most IPs, making standard `yt-dlp` fail.

To bypass this network block, the tool automatically falls back to **Playwright**. It will launch a genuine headless Chromium instance, navigate to the video page, intercept the direct CDN stream URL, and download it using the browser's own trusted network context. If headless mode gets blocked by the firewall, it will automatically retry in a visible headed browser (for local testing).

Because Playwright is used, you must run `playwright install chromium` once during setup.
