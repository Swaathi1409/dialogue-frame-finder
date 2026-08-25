"""
make_test_video.py - Creates a short synthetic .mp4 with the target
dialogue burned in as white text on dark background, starting at ~3s.
Simulates how real burned-in subtitles look.
"""
import cv2
import numpy as np
import os

TARGET = "My mind rebels at stagnation"
OUT = "test_video_sherlock.mp4"
FPS = 24
DURATION_SEC = 10
W, H = 1280, 720

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(OUT, fourcc, FPS, (W, H))

for frame_idx in range(DURATION_SEC * FPS):
    t = frame_idx / FPS
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:] = (20, 20, 20)   # dark background

    # Put caption text from 3s to 7s (72 to 168 frames)
    if 3.0 <= t < 7.0:
        # semi-transparent subtitle bar at bottom
        bar = img.copy()
        cv2.rectangle(bar, (0, H - 90), (W, H), (0, 0, 0), -1)
        img = cv2.addWeighted(bar, 0.6, img, 0.4, 0)

        cv2.putText(
            img, TARGET,
            (40, H - 35),
            cv2.FONT_HERSHEY_DUPLEX, 1.1,
            (255, 255, 255), 2, cv2.LINE_AA,
        )

    writer.write(img)

writer.release()
print(f"Created {OUT}: {DURATION_SEC}s @ {FPS}fps, text at 3-7s")
print(f"Size: {os.path.getsize(OUT) // 1024} KB")
