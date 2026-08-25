# APPROACH.md - Algorithm and Design Decisions

## Problem

Given a video and a target dialogue line (as burned-in caption text), find
the *first* frame where that text is visually visible on screen, and report
the exact frame number, timestamp, OCR text, and a confidence rating.

## Algorithm

The pipeline runs in three coarse-to-fine stages.

### Stage 1: Coarse temporal localization via ASR

We transcribe the full audio with faster-whisper (Whisper `base` model, CPU,
int8 quantization). This gives timestamped text segments at roughly
sentence granularity.

We fuzzy-match the target line against every segment using RapidFuzz
`partial_ratio`. If the best match clears `ASR_MATCH_THRESHOLD` (default 60),
we take that segment's time range and pad it:

```
window_start = max(0, segment.start - ASR_PAD_BEFORE_SEC)
window_end   = min(duration, segment.end + ASR_PAD_AFTER_SEC)
```

Padding (3s before, 8s after) accounts for the common case where on-screen
captions lag the spoken line by several seconds.

If ASR finds nothing above the threshold, we fall back to a full-video scan
at `FALLBACK_SCAN_INTERVAL_SEC` (1.5s). This is slower but guarantees coverage.

### Stage 2: Coarse OCR scan

Within the search window, we sample frames every `COARSE_SAMPLE_INTERVAL_SEC`
(0.5s). For each frame, PaddleOCR reads the text and we score it against the
target with the same `partial_ratio` matcher. We stop at the first frame that
clears `LOW_CONF_THRESHOLD` (70).

We record the last non-matching frame before this hit — we need it for
bisection.

### Stage 3: Bisection + local sequential scan

Binary search between last_no_match and first_coarse_match narrows the
candidate to within `BISECT_MIN_FRAMES` (1) frames. We stop there because
individual-frame OCR results are not perfectly monotonic: a frame can
score high while its immediate neighbors score lower (subtitle fade-in
effects, compression artifacts, partial rendering). Bisection alone would
land on the wrong frame.

After bisection, we scan every frame in a small local window (3 frames
before, 5 frames after the bisection result) to find the true first
matching frame.

### Stage 4: Persistence check

After identifying the candidate frame, we check that `PERSISTENCE_FRAMES`
(2) consecutive frames after it also clear `LOW_CONF_THRESHOLD`. This rules
out single-frame OCR noise.

A match that passes persistence is labeled **High** confidence if the score
also clears `HIGH_CONF_THRESHOLD` (90). Otherwise it is **Low**. A match
that does not survive the persistence check is also **Low**.

## Text matching

`matcher.normalize()` lowercases text and strips punctuation before scoring.
`partial_ratio` is used instead of `ratio` because:
- Captions often contain multiple lines; the target may appear as a substring
- OCR sometimes adds extra characters at box boundaries

## Design decisions and tradeoffs

**Network Acquisition & TLS/JA3 Filtering (ok.ru)**
OK.ru actively blocks programmatic HTTP clients (like Python's `ssl` stack, `requests`, `curl`, and `yt-dlp`) via TLS/JA3 fingerprint filtering. When yt-dlp attempts to fetch video metadata, the server forcibly resets the connection (`ConnectionResetError`). Proxies like `okrudownloader.top` can fetch metadata, but the direct CDN video URLs they return are IP-bound, meaning if we try to download them via a Python script, the CDN still blocks our non-browser IP footprint.
Streaming the video directly via `ffmpeg` does not fix this, because the block happens at the TLS handshake level before streaming begins.
**Solution:** The pipeline uses a Playwright Chromium fallback for `ok.ru`. It launches a genuine headless Chromium browser context, navigates to the video page, intercepts the CDN stream URL from the network tab, and downloads the stream using the browser's own trusted network context. If headless gets blocked, it retries in headed mode (useful for local development). This is a network condition on the host machine, not a defect in the tool, and the fallback guarantees it works.

**OpenCV instead of ffprobe for VideoInfo**
ffprobe is not included in `imageio-ffmpeg`. OpenCV uses the same
`libavformat` under the hood so values are identical for CFR (constant
frame rate) video. For VFR video the declared fps may not match actual
frame timing — acceptable for broadcast/streaming content like OK.ru.

**PaddleOCR pinned to 2.7.3**
PaddleOCR 3.x has breaking API changes and crashes at inference time on
Windows CPU due to a PIR executor + oneDNN incompatibility in paddlepaddle 3.x.
2.7.3 + paddlepaddle 2.6.2 is the stable, tested combination.

**Confidence thresholds are engineering heuristics**
The values in `config.py` (HIGH=90, LOW=70, ASR=60) were chosen by judgment,
not derived from a statistical study. They should be treated as reasonable
defaults to be tuned against real test cases.

**No Tesseract fallback**
The spec prohibits adding a Tesseract fallback unless it is actually tested.
It was not tested. PaddleOCR is the only OCR engine.

**ASR is for windowing only, not text confirmation**
Whisper transcribes the spoken audio. On-screen captions may use different
wording than what is spoken, or the text may appear before/after it is
spoken. We use Whisper only to find a rough time window, not to confirm
the text. The OCR pass is the only confirmation.

**Multi-language support (Tamil and other non-Latin scripts)**
The pipeline works on Tamil (and other non-Latin languages) provided the
*target dialogue is typed in the native script* (e.g. Tamil Unicode: காலை வணக்கம்),
not as English transliteration (e.g. "kalai vanakkam").

- **Whisper ASR** — faster-whisper with `WHISPER_LANGUAGE = None` (auto-detect)
  correctly transcribes Tamil speech and produces Tamil Unicode transcript segments.
  Matching the Tamil Unicode input against those segments works correctly.
- **PaddleOCR** — the default PaddleOCR model used here (`lang='en'`) reads only
  Latin-script text. Tamil on-screen captions will not be detected by OCR. When
  Tamil captions are not burned in (or are in a non-Latin font), the pipeline
  correctly falls back to the ASR segment midpoint frame and returns Low confidence.
- **English transliteration will NOT match** — typing "kalai vanakkam" (Latin)
  against a Whisper transcript that says "காலை வணக்கம்" (Tamil Unicode) produces
  a 0 fuzzy score because the character sets are completely different.
- **Recommendation:** Always enter the target dialogue in its native script for
  non-English videos.

## All thresholds

All tunable values are in `dialogue_finder/config.py`. No magic numbers
appear in any other file.

| Constant | Default | Purpose |
|---|---|---|
| HIGH_CONF_THRESHOLD | 90 | Score for High confidence |
| LOW_CONF_THRESHOLD | 70 | Score for Low confidence |
| ASR_MATCH_THRESHOLD | 60 | Min score to use ASR window |
| ASR_TIE_THRESHOLD | 5.0 | Score margin within which later ASR segments are preferred |
| ASR_PAD_BEFORE_SEC | 2.0 | Seconds before ASR segment |
| ASR_PAD_AFTER_SEC | 4.0 | Seconds after ASR segment |
| COARSE_SAMPLE_INTERVAL_SEC | 1.0 | OCR sampling interval (ASR window) |
| FALLBACK_SCAN_INTERVAL_SEC | 1.5 | OCR sampling interval (full video) |
| BISECT_MIN_FRAMES | 1 | Stop bisection when gap ≤ this |
| PERSISTENCE_FRAMES | 2 | Consecutive frames required to confirm |
| WHISPER_MODEL_SIZE | tiny | faster-whisper model |
| PLAYWRIGHT_FALLBACK_DOMAINS | ["ok.ru"] | Domains to use Playwright fallback |
| PLAYWRIGHT_TIMEOUT_MS | 60000 | Timeout for Playwright ops |
