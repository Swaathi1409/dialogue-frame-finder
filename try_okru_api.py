"""
Try OK.ru's internal video metadata API endpoints
"""
import requests, json, warnings
warnings.filterwarnings('ignore')

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://ok.ru/',
    'Origin': 'https://ok.ru',
})

video_id = '248244667877'

# Try several known OK.ru API endpoints
endpoints = [
    f'https://ok.ru/dk?cmd=videoPlayerMetadata&mid={video_id}',
    f'https://ok.ru/api/video/get?entity_id={video_id}&application_key=ANONYMSXA&format=json',
    f'https://ok.ru/video/{video_id}',
]

for url in endpoints:
    try:
        r = session.get(url, timeout=10)
        print(f'\n{url[:80]}')
        print(f'Status: {r.status_code}, Size: {len(r.text)}')
        if r.status_code == 200 and r.text:
            snippet = r.text[:500]
            print(f'Preview: {snippet}')
    except Exception as e:
        print(f'{url[:80]}')
        print(f'Error: {type(e).__name__}: {str(e)[:150]}')
