import requests, re, json, warnings, sys
warnings.filterwarnings('ignore')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://ok.ru/',
}

try:
    r = requests.get('https://ok.ru/video/248244667877', headers=headers, verify=False, timeout=15)
    print('Status:', r.status_code)
    html = r.text

    patterns = [
        ('hlsMasterPlaylistUrl', r'hlsMasterPlaylistUrl":"([^"]+)"'),
        ('videoSrc', r'videoSrc":"([^"]+)"'),
        ('m3u8', r'https?://[^\s"\\]+\.m3u8'),
        ('mp4', r'https?://[^\s"\\]+\.mp4'),
    ]
    for name, pat in patterns:
        hits = re.findall(pat, html)
        if hits:
            print(f'{name}: {hits[0][:200]}')
        else:
            print(f'{name}: not found')

    # Check if we got a real page or a block page
    print('\nPage title:', re.findall(r'<title>([^<]+)</title>', html)[:1])
    print('Page length:', len(html))

except Exception as e:
    print('Request failed:', type(e).__name__, str(e)[:300])
