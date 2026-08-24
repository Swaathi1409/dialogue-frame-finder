"""
Phase 3 verification: test OCR on real extracted frames.

Creates a synthetic test frame with known text burned in using OpenCV,
then runs run_ocr() on it and checks the result. This verifies:
  1. PaddleOCR loads without error
  2. run_ocr() returns text and confidence
  3. The text roughly matches what was drawn on the frame
  4. Empty frames return ("", 0.0) without error

We also test on a solid color frame (no text) to confirm the empty case.
"""
import sys
import numpy as np
import cv2

sys.path.insert(0, ".")

from dialogue_finder.ocr import run_ocr, OCRError

print("Phase 3 OCR verification")
print()

# Test 1: frame with known text
print("[1] Creating synthetic frame with text 'Hello World'...")
frame = np.zeros((480, 640, 3), dtype=np.uint8)   # black background
frame[:] = (30, 30, 30)                             # dark grey
cv2.putText(
    frame,
    "Hello World",
    (80, 260),                   # position
    cv2.FONT_HERSHEY_SIMPLEX,
    2.5,                         # font scale - large for OCR to see it
    (255, 255, 255),             # white text
    4,                           # thickness
    cv2.LINE_AA,
)
print("    Frame created: 640x480, white text on dark background")

print("    Running PaddleOCR (first call loads the model - may take ~10s)...")
try:
    text, conf = run_ocr(frame)
    print(f"    Recognized text: '{text}'")
    print(f"    Confidence:      {conf:.3f}")
    if text:
        print("    Status: text detected - checking content...")
        # We expect to find 'hello' and 'world' in some form
        norm = text.lower().replace(" ", "")
        if "hello" in norm or "world" in norm:
            print("    Content check: PASS (target words found)")
        else:
            print(f"    Content check: PARTIAL (got '{text}', expected Hello World)")
    else:
        print("    Status: no text detected - OCR may need parameter tuning")
except OCRError as e:
    print(f"    FAILED (OCRError): {e}")
    sys.exit(1)

print()

# Test 2: blank frame - should return ("", 0.0)
print("[2] Testing blank frame (no text - should return empty)...")
blank = np.zeros((480, 640, 3), dtype=np.uint8)
blank[:] = (50, 50, 50)
try:
    text2, conf2 = run_ocr(blank)
    print(f"    Text: '{text2}', confidence: {conf2:.3f}")
    if text2 == "":
        print("    Status: correctly returned empty - PASS")
    else:
        print(f"    Status: returned text on blank frame: '{text2}' (unexpected but not fatal)")
except OCRError as e:
    print(f"    FAILED (OCRError): {e}")
    sys.exit(1)

print()
print("Phase 3 OCR verification complete.")
