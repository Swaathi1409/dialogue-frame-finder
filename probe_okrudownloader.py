"""
Use curl_cffi to impersonate Chrome's TLS fingerprint and access OK.ru directly.
This bypasses the JA3 fingerprint block that rejects Python/curl/PowerShell.
"""
import re, json
from curl_cffi import requests as cffi_requests

OK_URL = "https://ok.ru/video/248244667877"

session = cffi_requests.Session(impersonate="chrome120")
session.headers.update({
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

print("Fetching OK.ru page with Chrome impersonation...")
try:
    r = session.get(OK_URL, timeout=30)
    print(f"Status: {r.status_code}, Length: {len(r.text)}")

    if r.status_code == 200:
        html = r.text
        # Extract video URLs from embedded metadata
        hls_hits = re.findall(r'hlsMasterPlaylistUrl":"([^"]+)"', html)
        mp4_hits = re.findall(r'"(?:url|src)"\s*:\s*"(https?://[^"]+\.(?:mp4|m3u8)[^"]*)"', html)
        
        # Also look for the JSON data block
        data_blocks = re.findall(r'data-options="([^"]+)"', html)
        
        print(f"\nhls urls: {hls_hits[:2]}")
        print(f"mp4 urls: {mp4_hits[:2]}")
        print(f"data blocks found: {len(data_blocks)}")
        print(f"\nPage title: {re.findall(r'<title>([^<]+)</title>', html)[:1]}")
    else:
        print(f"Non-200: {r.text[:500]}")

except Exception as e:
    print(f"Failed: {type(e).__name__}: {e}")
