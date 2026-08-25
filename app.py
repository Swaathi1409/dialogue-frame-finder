"""
app.py - Web interface for Dialogue Frame Finder.

Provides a REST + SSE API that the browser UI consumes:
  POST /api/analyze          -> start a job, returns {job_id}
  GET  /api/stream/<job_id>  -> SSE stream of progress events
  GET  /api/frame/<job_id>   -> serve the saved frame image
  GET  /                     -> serve the UI

Pipeline stages are mapped to user-friendly labels.
Internal paths, model names, and implementation details are
not forwarded to the frontend.
"""

import json
import logging
import os
import queue
import threading
import uuid

from flask import Flask, Response, jsonify, render_template, request, send_file

from dialogue_finder.pipeline import run_pipeline

app = Flask(__name__)

_JOBS: dict = {}

_STAGE_MAP = [
    ("Stage 1",               "downloading",  "Downloading video..."),
    ("ok.ru fallback",        "downloading",  "Trying alternative download source..."),
    ("Using cookies file",    "downloading",  "Using saved YouTube cookies..."),
    ("Stage 2",               "metadata",     "Reading video metadata..."),
    ("Stage 3",               "audio",        "Extracting audio track..."),
    ("Audio/ASR stage failed","audio",        "Audio extraction skipped - continuing..."),
    ("Stage 4",               "transcribing", "Transcribing speech with AI..."),
    ("Transcription complete","transcribing", "Transcription complete"),
    ("Stage 5",               "locating",     "Locating dialogue in transcript..."),
    ("Best ASR match",        "locating",     "Dialogue found in audio"),
    ("Stage 6",               "scanning",     "Scanning frames for on-screen text..."),
    ("Coarse scan",           "scanning",     "Performing coarse frame scan..."),
    ("Fine scan",             "scanning",     "Refining frame match..."),
    ("OCR found nothing",     "scanning",     "No subtitle overlay - using audio timestamp"),
    ("Saved frame",           "complete",     "Frame captured"),
]


class _PipelineHandler(logging.Handler):
    def __init__(self, q):
        super().__init__()
        self._q = q

    def emit(self, record):
        msg = self.format(record)
        for substring, stage_id, label in _STAGE_MAP:
            if substring in msg:
                self._q.put({"type": "stage", "stage": stage_id, "message": label})
                return


def _fmt_ts(sec):
    if sec is None:
        return None
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _run_job(job_id, url, target):
    q = _JOBS[job_id]["queue"]
    handler = _PipelineHandler(q)
    handler.setLevel(logging.DEBUG)
    root_logger = logging.getLogger("dialogue_finder")
    root_logger.addHandler(handler)
    out_dir = os.path.join("output", "web", job_id)
    try:
        result = run_pipeline(url=url, target=target, output_dir=out_dir)
        _JOBS[job_id]["frame_path"] = result.frame_image_path
        payload = {"found": result.found}
        if result.found:
            payload.update({
                "timestamp":   _fmt_ts(result.timestamp_sec),
                "frame":       result.frame_number,
                "text":        result.ocr_text,
                "confidence":  result.confidence,
                "match_score": round(result.match_score, 1) if result.match_score else None,
                "reasoning":   result.reasoning,
                "has_image":   bool(result.frame_image_path and os.path.exists(result.frame_image_path)),
            })
        q.put({"type": "done", "result": payload})
    except Exception as exc:
        user_msg = str(exc)[:300]
        q.put({"type": "error", "message": user_msg})
    finally:
        root_logger.removeHandler(handler)
        _JOBS[job_id]["done"] = True


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    url    = (data.get("url") or "").strip()
    target = (data.get("dialogue") or "").strip()
    if not url:
        return jsonify({"error": "Video URL is required"}), 400
    if not target:
        return jsonify({"error": "Dialogue text is required"}), 400
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"queue": queue.Queue(), "frame_path": None, "done": False}
    threading.Thread(target=_run_job, args=(job_id, url, target), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/stream/<job_id>")
def stream(job_id):
    if job_id not in _JOBS:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        q = _JOBS[job_id]["queue"]
        while True:
            try:
                event = q.get(timeout=90)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


@app.route("/api/frame/<job_id>")
def get_frame(job_id):
    if job_id not in _JOBS:
        return jsonify({"error": "Job not found"}), 404
    path = _JOBS[job_id].get("frame_path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "Frame image not available"}), 404
    return send_file(path, mimetype="image/png")


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(debug=False, host=host, port=port, threaded=True)

