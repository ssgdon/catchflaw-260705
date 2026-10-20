# -*- coding: utf-8 -*-
"""빌드 산출물(docs/) 링크·주소 검사 — SEO-CRAWL-DESIGN §7. 빌드(scripts/generate.py) 뒤에 돌린다. 하나라도 어긋나면 exit 1.

사용: python scripts/check_links.py

  1. 모든 페이지의 href="…hotels…"(상세·전체 목록, canonical 포함)가 실제 파일(docs/hotels/{slug}.html·docs/hotels.html)로 풀린다
     + 검색·비교·자동완성 데이터(data/index.js·search_index.js·compare.js)의 슬러그 u도 전부 파일로 풀린다
  2. docs/ 안 'hotels/ChIJ'(pid 주소)는 허용 자리뿐: _redirects 옛 주소 · R2 사진 URL · 로컬 사진(img/hotels/) — 페이지 링크엔 0
     + 인라인 JS가 pid로 상세 주소를 만드는 옛 코드('./hotels/' + h.id, hrefPrefix + h.id)가 남지 않았다
  3. 사이트맵 <loc> 수 = 채점 상세(noindex 아닌 것) + 허브 + 정적 5(홈·search·hotels·recommend·about), 모든 loc이 파일로 존재,
     noindex 상세는 사이트맵에 없다
  4. _redirects 줄 수 = 상세 수 + 2(허브 옛 주소), 옛 pid 주소 → 슬러그 대상 파일 존재, 상세마다 정확히 1줄
  5. 상세 전부가 홈·허브·전체 목록 중 어딘가의 서버 렌더 href로 링크된다
  6. 상세마다 .info-answer 정확히 1개, 채점 상세의 description에 호텔명·'실망 확률'
"""
import glob, html, json, os, re, sys
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
BASE = 'https://catchflaw.com'
STATIC = ['/', '/search', '/hotels', '/recommend', '/about']

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def read(p):
    return open(p, encoding='utf-8').read()


def page_url(path):
    """docs 안 파일 → 사이트 URL 경로(확장자 없음). index.html → '/'."""
    rel = os.path.relpath(path, DOCS).replace(os.sep, '/')
    if rel == 'index.html':
        return '/'
    return '/' + (rel[:-5] if rel.endswith('.html') else rel)


def to_file(url_path):
    """사이트 URL 경로 → docs 파일(없으면 None). '/' → index.html, '/x' → x.html(같은 이름 폴더가 있어도 .html 먼저)."""
    p = url_path.split('?')[0].split('#')[0]
    if p in ('', '/'):
        f = os.path.join(DOCS, 'index.html')
    else:
        f = os.path.join(DOCS, *p.strip('/').split('/'))
        if not f.endswith('.html'):
            f += '.html'
    return f if os.path.isfile(f) else None


def norm(s):
    return html.unescape(s).replace(' ', ' ').replace('⁠', '')


def card_name(title):   # = generate.card_name — 뒤에 붙은 영문 괄호 병기 뺌(답 문단·description이 이 이름을 쓴다)
    t = re.sub(r'\s*\([^)]*[A-Za-z][^)]*\)\s*$', '', title).strip()
    return t if len(t) >= 3 else title


pages = sorted(glob.glob(os.path.join(DOCS, '**', '*.html'), recursive=True))
details = sorted(glob.glob(os.path.join(DOCS, 'hotels', '*.html')))
detail_urls = {page_url(f) for f in details}
hubs = sorted(glob.glob(os.path.join(DOCS, 'area', '*.html')) + glob.glob(os.path.join(DOCS, 'best', '*.html')))
results = []


def report(no, title, errs, info=''):
    ok = not errs
    results.append(ok)
    print(f'[{"OK" if ok else "FAIL"}] {no}. {title}' + (f' — {info}' if info else ''))
    for e in errs[:15]:
        print('      ' + e)
    if len(errs) > 15:
        print(f'      … 외 {len(errs) - 15}건')


HREF_RX = re.compile(r'href="([^"]*)"')
HOTELS_RX = re.compile(r'(^|/)hotels(/|$|[?#])')

# ── 1 ──
errs, n = [], 0
for f in pages:
    base = BASE + page_url(f)
    for href in HREF_RX.findall(read(f)):
        if not HOTELS_RX.search(href) or href.startswith('mailto:'):
            continue
        u = urlparse(urljoin(base, html.unescape(href)))
        if u.netloc != 'catchflaw.com':
            continue   # 외부(사진 CDN 등)
        n += 1
        if not to_file(u.path):
            errs.append(f'{os.path.relpath(f, DOCS)}: {href}')
data_u = 0
for name, rx in (('data/index.js', r'"u":"([^"]+)"'), ('data/search_index.js', r'"u":"([^"]+)"'), ('data/compare.js', r'"u":"([^"]+)"')):
    src = read(os.path.join(DOCS, *name.split('/'))).replace('": "', '":"')
    us = re.findall(rx, src)
    if not us:
        errs.append(f'{name}: 슬러그 u 없음')
    for s in us:
        data_u += 1
        if not os.path.isfile(os.path.join(DOCS, 'hotels', s + '.html')):
            errs.append(f'{name}: u={s} 파일 없음')
report(1, '상세·목록 href가 파일로 풀림', errs, f'href {n}개 · 데이터 슬러그 {data_u}개')

# ── 2 ──
errs, seen = [], 0
ALLOW_CTX = re.compile(r'(r2\.dev/hotels/|img/hotels/)$')
for f in glob.glob(os.path.join(DOCS, '**', '*'), recursive=True):
    if not os.path.isfile(f) or not f.endswith(('.html', '.js', '.json', '.xml', '.txt')):
        continue
    rel = os.path.relpath(f, DOCS).replace(os.sep, '/')
    txt = read(f)
    for m in re.finditer(r'hotels/ChIJ', txt):
        seen += 1
        pre = txt[max(0, m.start() - 40):m.start() + 7]
        if ALLOW_CTX.search(pre):
            continue
        errs.append(f'{rel}: …{txt[max(0, m.start() - 40):m.end() + 20]}…')
rd = read(os.path.join(DOCS, '_redirects'))
red_pid = len(re.findall(r'^/hotels/ChIJ', rd, re.M))
OLD_JS = re.compile(r"""hotels/['"]\s*\+\s*[\w.]*\bid\b|hrefPrefix\s*\+\s*h\.id\b""")
for f in pages + glob.glob(os.path.join(DOCS, 'js', '*.js')):
    for m in OLD_JS.finditer(read(f)):
        errs.append(f'{os.path.relpath(f, DOCS)}: pid로 상세 주소를 만드는 코드 — {m.group(0)}')
report(2, "'hotels/ChIJ'는 허용 자리뿐", errs, f'R2·로컬 사진 {seen}곳 · _redirects 옛 주소 {red_pid}줄')

# ── 3 ──
errs = []
sm = read(os.path.join(DOCS, 'sitemap.xml'))
locs = re.findall(r'<loc>([^<]+)</loc>', sm)
noindex = {page_url(f) for f in details if 'name="robots" content="noindex' in read(f)}
scored = detail_urls - noindex
want = len(scored) + len(hubs) + len(STATIC)
if len(locs) != want:
    errs.append(f'<loc> {len(locs)}개 ≠ 채점 상세 {len(scored)} + 허브 {len(hubs)} + 정적 {len(STATIC)} = {want}')
if len(set(locs)) != len(locs):
    errs.append('중복 <loc>')
paths = set()
for loc in locs:
    u = urlparse(loc)
    paths.add(u.path or '/')
    if u.netloc != 'catchflaw.com' or not to_file(u.path or '/'):
        errs.append(f'파일 없음: {loc}')
for p in sorted(noindex & paths):
    errs.append(f'noindex 상세가 사이트맵에 있음: {p}')
for p in sorted(scored - paths):
    errs.append(f'채점 상세가 사이트맵에 없음: {p}')
for p in STATIC + [page_url(f) for f in hubs]:
    if p not in paths:
        errs.append(f'사이트맵에 없음: {p}')
report(3, '사이트맵 <loc> 수·파일', errs, f'{len(locs)}개 = 채점 상세 {len(scored)} + 허브 {len(hubs)} + 정적 {len(STATIC)}')

# ── 4 ──
errs = []
lines = [l for l in rd.splitlines() if l.strip()]
if len(lines) != len(details) + 2:
    errs.append(f'_redirects {len(lines)}줄 ≠ 상세 {len(details)} + 2')
targets, sources = {}, set()
for l in lines:
    parts = l.split()
    if len(parts) != 3 or parts[2] != '301':
        errs.append(f'형식: {l}')
        continue
    a, b, _ = parts
    if a in sources:
        errs.append(f'옛 주소 중복: {a}')
    sources.add(a)
    if not to_file(b):
        errs.append(f'대상 파일 없음: {l}')
    if a.startswith('/hotels/'):
        if not re.fullmatch(r'/hotels/ChIJ[\w-]+(\.html)?', a):
            errs.append(f'옛 주소가 pid가 아님: {l}')
        targets[b] = targets.get(b, 0) + 1
for p in sorted(detail_urls):
    if targets.get(p, 0) != 2:   # 무확장 + .html
        errs.append(f'옛 주소 301 {targets.get(p, 0)}줄(2여야): {p}')
report(4, '_redirects 줄 수·대상', errs, f'{len(lines)}줄 = 상세 {len(details)}×2(무확장·.html) + 허브 2')

# ── 5 ──
errs = []
linked = set()
for f in [os.path.join(DOCS, 'index.html'), os.path.join(DOCS, 'hotels.html')] + hubs:
    base = BASE + page_url(f)
    for href in HREF_RX.findall(read(f)):
        u = urlparse(urljoin(base, html.unescape(href)))
        if u.netloc == 'catchflaw.com' and u.path.startswith('/hotels/'):
            linked.add(u.path)
miss = sorted(detail_urls - linked)
for p in miss:
    errs.append(f'홈·허브·목록 어디에도 링크 없음: {p}')
report(5, '상세 전부가 홈·허브·목록에서 링크됨', errs, f'{len(detail_urls & linked)}/{len(detail_urls)}곳')

# ── 6 ──
errs = []
for f in details:
    s = read(f)
    rel = os.path.relpath(f, DOCS)
    k = len(re.findall(r'<p class="info-answer">', s))
    if k != 1:
        errs.append(f'{rel}: .info-answer {k}개')
    if page_url(f) in noindex:
        continue
    m = re.search(r'<meta name="description" content="([^"]*)"', s)
    t = re.search(r'<h1 class="name-ko">(.*?)</h1>', s, re.S)
    d = norm(m.group(1)) if m else ''
    nm = card_name(norm(re.sub(r'<[^>]+>', '', t.group(1)))) if t else ''
    if not nm or nm not in d:
        errs.append(f'{rel}: description에 호텔명 없음 — {nm!r} / {d[:60]!r}')
    if '실망 확률' not in d:
        errs.append(f"{rel}: description에 '실망 확률' 없음")
report(6, "상세 답 문단 1개 · description에 호텔명·'실망 확률'", errs, f'상세 {len(details)}쪽(채점 {len(scored)})')

print(f'\n{sum(results)}/{len(results)} 통과')
sys.exit(0 if all(results) else 1)
