# -*- coding: utf-8 -*-
"""IndexNow 알림 — 배포 뒤 사이트맵의 URL을 Bing·Yandex 등(IndexNow 참여 검색엔진)에 한 번에 알린다. (2026-10-10)

구글은 IndexNow를 쓰지 않는다(구글은 Search Console 색인 요청·사이트맵). Bing 색인은 ChatGPT 검색·Copilot 노출에도 쓰인다.
소유 확인 = 사이트 루트의 {INDEXNOW_KEY}.txt (generate.py가 매 빌드 생성). 라이브에 키 파일이 없으면 보내지 않는다.

사용 (배포가 끝나 라이브에 반영된 뒤):
  python scripts/indexnow.py            # docs/sitemap.xml의 모든 URL
  python scripts/indexnow.py --dry-run  # 보낼 목록만 출력
"""
import json, os, re, sys, urllib.request, urllib.error
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from generate import INDEXNOW_KEY, BASE   # noqa: E402  (generate는 import만 하면 빌드하지 않는다)

HOST = BASE.split('//', 1)[1].rstrip('/')
ENDPOINT = 'https://api.indexnow.org/indexnow'
UA = 'Mozilla/5.0 (compatible; catchflaw-indexnow/1.0; +https://catchflaw.com/about)'


def main():
    sm = open(os.path.join(ROOT, 'docs', 'sitemap.xml'), encoding='utf-8').read()
    urls = re.findall(r'<loc>([^<]+)</loc>', sm)
    print(f'[indexnow] {len(urls)} URL · host {HOST}')
    if '--dry-run' in sys.argv:
        print('\n'.join(urls[:10]), '...' if len(urls) > 10 else '')
        return
    key_url = f'{BASE}/{INDEXNOW_KEY}.txt'
    try:
        # Cloudflare가 파이썬 기본 User-Agent를 403으로 막아서 이름을 붙인다(검색엔진 봇은 그대로 통과)
        live = urllib.request.urlopen(urllib.request.Request(key_url, headers={'User-Agent': UA}), timeout=20).read().decode().strip()
    except Exception as e:
        sys.exit(f'[indexnow] 키 파일을 못 읽음({key_url}): {e} — 배포가 라이브에 반영된 뒤 다시 실행')
    if live != INDEXNOW_KEY:
        sys.exit('[indexnow] 라이브 키 파일 내용이 다름 — 배포 반영 후 다시 실행')
    body = json.dumps({'host': HOST, 'key': INDEXNOW_KEY, 'keyLocation': key_url, 'urlList': urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8', 'User-Agent': UA})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        print(f'[indexnow] 전송 완료 HTTP {r.status}')   # 200 = 접수, 202 = 접수(키 확인 대기)
    except urllib.error.HTTPError as e:
        sys.exit(f'[indexnow] 실패 HTTP {e.code}: {e.read()[:200]!r}')


if __name__ == '__main__':
    main()
