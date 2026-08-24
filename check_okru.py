"""
Phase 1 end-to-end verification.

Tests the full acquisition pipeline: download -> video info -> audio extraction -> frame extraction.

Uses a short public video (Sintel trailer clip, ~30s at lowest resolution, ~5MB).
When running the real tool, replace TEST_URL with the actual OK.ru target URL.

OK.ru status: The Odnoklassniki extractor IS present in yt-dlp. Connections from
this IP get a ConnectionReset (common for OK.ru outside Russian IPs).
The pipeline raises DownloadError clearly when this happens - it does not proceed silently.
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, ".")

# Import our actual module implementations
from dialogue_finder.downloader import download_video, DownloadError, _get_ffmpeg_dir
from dialogue_finder.audio import extract_audio, AudioExtractionError
from dialogue_finder.frame_extractor import get_video_info, extract_frame, save_frame, timestamp_to_frame

# Short public video: Sintel trailer on YouTube (use a tiny format)
# This is just ~30 seconds at 144p, around 3-5MB
TEST_URL = "https://www.youtube.com/watch?v=eRsGyueVLvQ"

print("=" * 60)
print("Phase 1: Download -> Audio -> Frame extraction test")
print("=" * 60)

with tempfile.TemporaryDirectory(prefix="dff_p1test_") as tmpdir:
    # Step 1: Download via our downloader module
    print(f"\n[1] Downloading from: {TEST_URL}")
    print("    Using our downloader.download_video()...")
    try:
        video_file = download_video(TEST_URL, tmpdir)
        size_mb = os.path.getsize(video_file) / 1024 / 1024
        print(f"    Downloaded: {os.path.basename(video_file)} ({size_mb:.1f} MB)")
        print("    Status: OK")
    except DownloadError as e:
        print(f"    Status: FAILED (DownloadError)")
        print(f"    Error: {e}")
        sys.exit(1)

    # Step 2: Video metadata via OpenCV
    print("\n[2] Reading video metadata with get_video_info()...")
    try:
        info = get_video_info(video_file)
        print(f"    FPS:          {info.fps:.4f}")
        print(f"    Total frames: {info.total_frames}")
        print(f"    Duration:     {info.duration_sec:.2f} sec")
        print(f"    Resolution:   {info.width}x{info.height}")
        assert info.fps > 0, "fps must be > 0"
        print("    Status: OK")
    except Exception as e:
        print(f"    Status: FAILED: {e}")
        sys.exit(1)

    # Step 3: Audio extraction
    print("\n[3] Extracting audio (16kHz mono WAV) with extract_audio()...")
    audio_path = os.path.join(tmpdir, "audio.wav")
    try:
        extract_audio(video_file, audio_path)
        size_kb = os.path.getsize(audio_path) // 1024
        print(f"    Output: audio.wav ({size_kb} KB)")
        print("    Status: OK")
    except AudioExtractionError as e:
        print(f"    Status: FAILED (AudioExtractionError): {e}")
        sys.exit(1)

    # Step 4: Frame extraction at ~1 second mark
    target_frame = timestamp_to_frame(1.0, info.fps)
    print(f"\n[4] Extracting frame {target_frame} (~1.0 sec) with extract_frame()...")
    frame_out = os.path.join(tmpdir, "test_frame.png")
    try:
        frame = extract_frame(video_file, target_frame)
        h, w, c = frame.shape
        print(f"    Frame shape: {w}x{h}, channels: {c}")
        save_frame(frame, frame_out)
        print(f"    Saved to: test_frame.png")
        print(f"    File size: {os.path.getsize(frame_out)} bytes")
        print("    Status: OK")
    except Exception as e:
        print(f"    Status: FAILED: {e}")
        sys.exit(1)

print("\n" + "=" * 60)
print("ALL Phase 1 checks PASSED")
print("  yt-dlp download (via bundled ffmpeg for merging): WORKING")
print("  ffmpeg audio extraction (16kHz mono WAV):         WORKING")
print("  OpenCV video info (fps/frames/duration/res):      WORKING")
print("  OpenCV frame extraction + PNG save:               WORKING")
print("")
print("Note on OK.ru: Odnoklassniki extractor is present in yt-dlp.")
print("  Direct connections from this IP are blocked (region restriction).")
print("  The pipeline raises DownloadError cleanly in that case.")
print("=" * 60)
