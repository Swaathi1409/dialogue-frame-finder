"""
debug_frame.py - Download the YouTube video, extract frame at ~23s, run OCR,
show exactly what OCR sees. This tells us if the problem is no on-screen text
or an OCR failure.
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from dialogue_finder.downloader import download_video
from dialogue_finder.frame_extractor import extract_frame, get_video_info
from dialogue_finder.ocr import run_ocr
import cv2

URL = "https://youtu.be/HAnw168huqA"
TARGET_SEC = 23.0   # ASR found speech here

work = tempfile.mkdtemp(prefix="dff_debug_")
try:
    print(f"Downloading {URL} ...")
    vpath = download_video(URL, work)
    info = get_video_info(vpath)
    print(f"fps={info.fps}, frames={info.total_frames}, size={info.width}x{info.height}")

    # Extract frames from 20-28s
    for t in [20, 22, 23, 24, 25, 26, 28]:
        fn = int(t * info.fps)
        frame = extract_frame(vpath, fn)
        if frame is None:
            print(f"  t={t}s frame={fn}: could not extract")
            continue

        text, conf = run_ocr(frame)
        print(f"  t={t}s frame={fn}: OCR text='{text}' conf={conf:.2f}")

        # Save frame so we can look at it
        out = f"debug_frame_{t}s.png"
        cv2.imwrite(out, frame)
        print(f"    saved: {out}")

finally:
    shutil.rmtree(work, ignore_errors=True)
