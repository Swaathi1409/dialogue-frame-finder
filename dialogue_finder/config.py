"""
config.py - All tunable constants live here.

If you need to change a threshold, a model size, a sampling rate,
or a timing pad, change it here. No other file should have magic numbers.
"""

# ---------- Model settings ----------

# Whisper model size. "tiny" is fast, "base" is a bit slower but more accurate.
# On CPU "tiny" usually finishes in well under a minute for a 20-minute video.
WHISPER_MODEL_SIZE = "base"

# Language hint for Whisper. None means auto-detect.
WHISPER_LANGUAGE = None

# ---------- ASR search window padding ----------

# When Whisper finds the spoken line at time T seconds, we look for the
# on-screen caption starting this many seconds before T ...
ASR_PAD_BEFORE_SEC = 3.0

# ... and ending this many seconds after T.
ASR_PAD_AFTER_SEC = 8.0

# ---------- Coarse frame sampling inside the search window ----------

# How far apart (in seconds) the coarse OCR samples are spaced.
# 0.5 s gives ~2 frames/sec which is fast enough to catch any visible caption.
COARSE_SAMPLE_INTERVAL_SEC = 0.5

# ---------- Fallback full-video scan ----------

# If ASR finds nothing, scan the whole video at this interval (seconds).
FALLBACK_SCAN_INTERVAL_SEC = 1.5

# ---------- Fuzzy matching thresholds ----------

# RapidFuzz partial_ratio score (0-100) above which we call it a confirmed hit.
HIGH_CONF_THRESHOLD = 90

# Score between this and HIGH_CONF_THRESHOLD => Low confidence hit.
LOW_CONF_THRESHOLD = 70

# ASR fuzzy match threshold: how well the spoken transcript has to match the
# target line before we trust the Whisper-derived window. Below this we fall
# back to the full-video scan.
ASR_MATCH_THRESHOLD = 60

# ---------- Persistence check ----------

# After finding the first matching frame, we verify the match persists for
# at least this many consecutive frames (at native fps) before calling it real.
# Helps rule out single-frame OCR noise.
PERSISTENCE_FRAMES = 2

# ---------- Binary search ----------

# When bisecting between the last non-match and first coarse match, we stop
# when the gap is smaller than this many frames.
BISECT_MIN_FRAMES = 1

# ---------- Output ----------

# Directory where extracted frame PNGs are saved.
OUTPUT_DIR = "output"

# ---------- PaddleOCR settings ----------

# det_db_box_thresh controls how aggressively the detector finds text boxes.
# Lower values catch more text, including faint captions.
PADDLE_DET_DB_BOX_THRESH = 0.3

# drop_score: detections below this PaddleOCR confidence are ignored.
PADDLE_DROP_SCORE = 0.3
