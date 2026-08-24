"""
e2e_test.py - End-to-end smoke test for the full pipeline.

Uses a short YouTube video that has burned-in English captions.
We pick a line we know appears in the video and verify the pipeline
finds it (or reports Not Found cleanly with no crash).

This test downloads a real video and runs real OCR so it takes a few
minutes. It is NOT in the pytest suite (no test_ prefix on the file).
Run manually: python e2e_test.py

Target: "Big Buck Bunny" trailer (Creative Commons) - has hard-coded
title card text we can search for.
"""
import sys, os, json, subprocess

sys.path.insert(0, ".")

# Short video with visible text: Big Buck Bunny title card
# Use a very short clip - we'll search for the title text
URL = "https://www.youtube.com/watch?v=YE7VzlLtp-4"   # ~30s BBB trailer
TARGET = "creative commons"   # appears as title card text early in the video

print("=" * 60)
print("End-to-end pipeline test")
print(f"URL:    {URL}")
print(f"Target: '{TARGET}'")
print("=" * 60)

result = subprocess.run(
    [sys.executable, "-m", "dialogue_finder", URL, TARGET,
     "--output-dir", "output", "--verbose", "--json"],
    capture_output=True, text=True, timeout=600,
    cwd=os.path.dirname(os.path.abspath(__file__))
)

print("STDOUT:")
print(result.stdout[:3000] if result.stdout else "(empty)")
print("\nSTDERR (last 30 lines):")
stderr_lines = result.stderr.strip().splitlines()
print("\n".join(stderr_lines[-30:]) if stderr_lines else "(empty)")
print(f"\nExit code: {result.returncode}")

if result.stdout.strip():
    try:
        data = json.loads(result.stdout)
        print(f"\nParsed result:")
        print(f"  found:      {data.get('found')}")
        print(f"  confidence: {data.get('confidence')}")
        print(f"  frame:      {data.get('frame_number')}")
        print(f"  timestamp:  {data.get('timestamp_sec')}")
        print(f"  score:      {data.get('match_score')}")
        print(f"  ocr_text:   {data.get('ocr_text', '')[:80]}")
        print(f"  frame_path: {data.get('frame_image_path')}")
    except Exception as e:
        print(f"Could not parse JSON: {e}")
