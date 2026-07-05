# -*- coding: utf-8 -*-
"""호텔 대표 이미지 다운로드 → assets/hotels/{place_id}.jpg
구글 이미지 URL 중 /p/ 타입(영구)만 사용. gps-cs-s 타입은 세션 만료로 403.
사용: python scripts/fetch_images.py   (이미 받은 파일은 건너뜀)
"""
import json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data-src', 'images_all.json')
OUT = os.path.join(ROOT, 'assets', 'hotels')
SIZE = '=w960-h720-k-no'   # 상세 비주얼까지 커버하는 크기

def pick_url(row):
    urls = row.get('urls') or []
    if isinstance(urls, str): urls = json.loads(urls)
    main = row.get('main_url')
    cand = ([main] if main else []) + list(urls)
    for u in cand:
        if u and '/p/' in u:
            return re.sub(r'=w\d+-h\d+[^ ]*$', SIZE, u)
    return None

def main():
    rows = json.load(open(SRC, encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    ok = skip = miss = fail = 0
    for r in rows:
        pid = r['place_id']
        dst = os.path.join(OUT, f'{pid}.jpg')
        if os.path.exists(dst): skip += 1; continue
        u = pick_url(r)
        if not u: miss += 1; continue
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=15).read()
            open(dst, 'wb').write(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f'FAIL {pid}: {str(e)[:60]}')
    print(f'다운로드 {ok} · 기존 {skip} · URL없음 {miss} · 실패 {fail}')

if __name__ == '__main__':
    main()
