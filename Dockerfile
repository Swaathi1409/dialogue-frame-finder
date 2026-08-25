# Dialogue Frame Finder - Docker Image
# CPU-only, no Compose needed.
#
# What this image contains:
#   - Python 3.11 slim base
#   - All system dependencies: ffmpeg, libgl (for OpenCV), libgomp (for PaddlePaddle)
#   - All Python packages from requirements.txt including Flask for the web UI
#   - Playwright Chromium browser (for OK.ru TLS bypass fallback)
#   - PaddleOCR and Whisper models pre-downloaded at build time
#     so the container works offline after pull
#
# Build:
#   docker build -t dialogue-frame-finder .
#
# Run the CLI:
#   docker run --rm -v "$PWD/output:/app/output" dialogue-frame-finder \
#     "https://youtu.be/Pae6tjZ2jxs" "so happy you are here today"
#
# Run the Web UI:
#   docker run --rm -p 5000:5000 dialogue-frame-finder web
#   Then open http://localhost:5000

FROM python:3.11-slim

# ------- System dependencies -------
# ffmpeg       : video/audio processing
# libgl1       : OpenCV needs libGL.so.1 even in headless mode
# libglib2.0-0 : OpenCV dependency
# libgomp1     : OpenMP runtime required by PaddlePaddle CPU kernels
# wget, ca-certificates : needed by Playwright browser installer
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ------- Working directory -------
WORKDIR /app

# ------- Python dependencies -------
# Copy requirements first so Docker layer cache is used when only code changes.
COPY requirements.txt .

# Install everything. PaddlePaddle is CPU-only by default on non-GPU images.
RUN pip install --no-cache-dir -r requirements.txt

# Force-reinstall pyclipper to avoid a zlib decompression error that can
# occur when the compiled extension (.so) gets corrupted during the initial
# pip install in certain Docker environments.
RUN pip install --no-cache-dir --force-reinstall pyclipper

# ------- Playwright Chromium -------
# Install the Chromium browser used for the OK.ru TLS bypass fallback.
# This bakes the ~300MB browser into the image so it works offline.
RUN playwright install chromium --with-deps

# ------- Pre-download AI models -------
# Bake the Whisper tiny model into the image at build time.
# Without this, the first run would need internet access to fetch it.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8')"

# Pre-download PaddleOCR models (English, detection + recognition).
# PaddleOCR downloads to ~/.paddleocr on first use; we trigger it here.
# The '|| true' makes this a soft step: if the model CDN is unreachable
# during build, the container still works - models download on first run.
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=False, lang='en', use_gpu=False, show_log=False)" || true

# ------- Copy application code -------
# Done after model download so code changes do not bust the model cache layer.
COPY . .

# ------- Output directory -------
# The CLI and web UI write frame PNGs here. Mount a volume to persist them.
RUN mkdir -p output

# ------- Entrypoint -------
# Default: run the CLI.
# Pass "web" as first argument to start the Flask web server instead.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
