# -*- coding: utf-8 -*-
"""관리자 페이지 검사 (ADMIN-DESIGN §7-5·§8) — 빌드 산출물 + VM 집계 JSON(admin.json) 규격. 하나라도 어긋나면 exit 1.

사용
  python scripts/check_admin.py                       # 빌드 산출물만(docs/admin·robots·sitemap·slugs·changes.json)
  python scripts/check_admin.py sample.json           # + admin_export.py 결과 규격(§4)
  python scripts/check_admin.py sample.json --to-docs # 통과하면 docs/admin/sample.json으로 복사(로컬 프리뷰용 — .gitignore, 커밋 안 함)

산출 쪽 검사
  1. docs/admin/index.html: noindex · h1 1개 · GA4/Clarity 태그 없음 · admin.js·chart.js 로드
  2. robots.txt에 Disallow: /admin/ · sitemap.xml에 /admin 없음 · _headers에 /admin/* no-store
  3. docs/admin/site.json 필수 키, hotels 수 = counts.detail = docs/hotels/*.html 수 = docs/data/slugs.json 수
  4. scripts/changes.json: changes(date·commit·title·watch) 형식, 날짜 내림차순, pending(title·from·why·needs)
JSON 쪽 검사(파일을 줬을 때)
  5. 최상위 키 · ga.days 창 3개(7·28·90) 각 필수 키 · hotels 행 수 = 상세 수 · daily 90일
  6. clarity·ops(sync_jobs ≤ 10·health·backup·price_sample·crontab)·db(hotels·reviews_site) — dry-run이면 null 허용(경고)
  7. changes.before_after가 changes.json 커밋을 덮는지 · watch 지표 이름이 METRICS에 있는지 · 크기 300KB 이하
"""
import json, os, re, shutil, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
errs, warns = [], []


def E(m): errs.append(m)
def W(m): warns.append(m)


def need(obj, keys, where):
    if not isinstance(obj, dict):
        E(f'{where}: 객체가 아님({type(obj).__name__})')
        return False
    miss = [k for k in keys if k not in obj]
    if miss:
        E(f'{where}: 키 없음 {miss}')
    return not miss


def read(p):
    return open(p, encoding='utf-8').read()


# ── 산출물 ──
idx = os.path.join(DOCS, 'admin', 'index.html')
site = None
if not os.path.exists(idx):
    E('docs/admin/index.html 없음 — generate.py 빌드 먼저')
else:
    h = read(idx)
    if 'name="robots" content="noindex' not in h: E('admin/index.html: noindex 없음')
    if len(re.findall(r'<h1\b', h)) != 1: E('admin/index.html: h1이 1개가 아님')
    if 'googletagmanager' in h or 'clarity.ms' in h: E('admin/index.html: GA4·Clarity 태그가 실림(운영자 방문이 지표에 섞임)')
    if '/js/admin.js' not in h or 'chart.js@4.4.1' not in h: E('admin/index.html: admin.js 또는 chart.js 4.4.1 로드 없음')
    for k in ('home', 'ux', 'chg', 'ops'):
        if f'id="ad-{k}"' not in h: E(f'admin/index.html: 탭 영역 ad-{k} 없음')
rb = os.path.join(DOCS, 'robots.txt')
if not os.path.exists(rb) or 'Disallow: /admin/' not in read(rb): E('robots.txt: Disallow: /admin/ 없음')
sm = os.path.join(DOCS, 'sitemap.xml')
if os.path.exists(sm) and '/admin' in read(sm): E('sitemap.xml에 /admin 주소가 있음')
hd = os.path.join(DOCS, '_headers')
if os.path.exists(hd) and '/admin/*' not in read(hd): E('_headers: /admin/* 캐시 금지 없음')

sp = os.path.join(DOCS, 'admin', 'site.json')
n_detail_files = len([f for f in os.listdir(os.path.join(DOCS, 'hotels')) if f.endswith('.html')]) if os.path.isdir(os.path.join(DOCS, 'hotels')) else None
if not os.path.exists(sp):
    E('docs/admin/site.json 없음')
else:
    site = json.load(open(sp, encoding='utf-8'))
    if need(site, ['built_at', 'build', 'commit', 'asof', 'counts', 'hotels', 'deploys', 'changes', 'pending'], 'site.json'):
        c = site['counts']
        need(c, ['detail', 'scored', 'affiliate', 'affiliate_detail', 'active', 'watch'], 'site.json counts')
        if len(site['hotels']) != c.get('detail'): E(f'site.json: hotels {len(site["hotels"])}곳 ≠ counts.detail {c.get("detail")}')
        if n_detail_files is not None and c.get('detail') != n_detail_files: E(f'site.json counts.detail {c.get("detail")} ≠ docs/hotels/*.html {n_detail_files}')
        bad = [p for p, v in site['hotels'].items() if not (isinstance(v, list) and len(v) == 5)]
        if bad: E(f'site.json hotels 행 형식(이름·슬러그·제휴·점수·상태 5칸) 아님: {bad[:3]}')
        if c.get('affiliate_detail', 0) > c.get('detail', 0): E('site.json: 제휴 링크 상세 수 > 상세 수')
        if not site['deploys']: W('site.json deploys 비었음(git 없이 빌드?)')
slp = os.path.join(DOCS, 'data', 'slugs.json')
if not os.path.exists(slp):
    E('docs/data/slugs.json 없음 — VM admin_export가 /hotels/{slug} → pid 매핑에 쓴다')
elif site:
    sl = json.load(open(slp, encoding='utf-8'))
    if set(sl) != set(site['hotels']): E(f'data/slugs.json {len(sl)}곳 ≠ site.json hotels {len(site["hotels"])}곳')
    if any(sl[p] != site['hotels'][p][1] for p in sl if p in site['hotels']): E('data/slugs.json 슬러그가 site.json과 다름')

chp = os.path.join(ROOT, 'scripts', 'changes.json')
changes = []
try:
    cj = json.load(open(chp, encoding='utf-8'))
    changes = cj.get('changes', [])
    for i, c in enumerate(changes):
        if need(c, ['date', 'commit', 'title', 'watch'], f'changes.json changes[{i}]'):
            try: date.fromisoformat(c['date'])
            except ValueError: E(f'changes.json changes[{i}] date 형식 아님: {c["date"]}')
            if not re.fullmatch(r'[0-9a-f]{7,40}', c['commit']): E(f'changes.json changes[{i}] commit 형식 아님: {c["commit"]}')
            if not c['watch']: W(f'changes.json {c["commit"]}: watch 비었음')
    ds = [c.get('date', '') for c in changes]
    if ds != sorted(ds, reverse=True): E('changes.json changes: 최신이 맨 위(날짜 내림차순)가 아님')
    if len({c.get('commit') for c in changes}) != len(changes): E('changes.json: 같은 커밋이 두 번 있음')
    for i, p in enumerate(cj.get('pending', [])):
        need(p, ['title', 'from', 'why', 'needs'], f'changes.json pending[{i}]')
    if site and [c.get('commit') for c in site.get('changes', [])] != [c.get('commit') for c in changes]:
        E('site.json changes가 scripts/changes.json과 다름 — 다시 빌드')
except FileNotFoundError:
    E('scripts/changes.json 없음')
except json.JSONDecodeError as e:
    E(f'scripts/changes.json JSON 오류: {e}')

# ── VM 집계 JSON ──
args = [a for a in sys.argv[1:] if not a.startswith('--')]
data_path = args[0] if args else None
if data_path:
    raw = open(data_path, 'rb').read()
    kb = len(raw) / 1024
    if kb > 300: E(f'{data_path}: {kb:.0f}KB — 목표 300KB 이하(§3)')
    d = json.loads(raw.decode('utf-8'))
    dry = d.get('mode') == 'dry-run'
    need(d, ['made_at', 'asof_db', 'ga', 'clarity', 'ops', 'db', 'changes', 'errors'], 'admin.json')
    if d.get('errors'): W(f'admin.json errors {len(d["errors"])}건: {d["errors"][:3]}')
    g = d.get('ga')
    n_detail = site['counts']['detail'] if site else None
    if not g:
        E('admin.json ga 없음(GA4 실패)')
    else:
        days = g.get('days') or {}
        if sorted(days) != ['28', '7', '90']: E(f'ga.days 창이 7·28·90이 아님: {sorted(days)}')
        for w, x in days.items():
            if not need(x, ['sessions', 'users', 'prev_sessions', 'landing', 'channel', 'funnel', 'events', 'hotels', 'search_noresult'], f'ga.days[{w}]'):
                continue
            need(x['funnel'], ['detail_sessions', 'scroll90', 'tab_click', 'cta_click', 'cta_agoda', 'cta_google', 'prev'], f'ga.days[{w}].funnel')
            if n_detail is not None and len(x['hotels']) != n_detail: E(f'ga.days[{w}].hotels {len(x["hotels"])}행 ≠ 상세 수 {n_detail}')
            if site and any(h['pid'] not in site['hotels'] for h in x['hotels']): E(f'ga.days[{w}].hotels에 site.json에 없는 pid')
            for e in x['events'][:3]:
                need(e, ['name', 'count', 'sessions', 'by'], f'ga.days[{w}].events')
            if x['sessions'] <= 0: W(f'ga.days[{w}].sessions = 0')
        daily = g.get('daily') or []
        if len(daily) != 90: E(f'ga.daily {len(daily)}일 ≠ 90일')
        if daily and not need(daily[-1], ['day', 'sessions', 'detail_sessions', 'cta', 'm'], 'ga.daily[]'): pass
        if days.get('7') and days.get('28') and days['7']['sessions'] > days['28']['sessions']: E('ga 7일 세션 > 28일 세션')
    if dry:
        W('dry-run 판 — clarity·ops·db가 null(4탭 중 운영·Clarity 표는 비어 보임)')
    else:
        c = d.get('clarity')
        if need(c, ['days', 'urls', 'pulls_today', 'last_day'], 'clarity') and c['urls']:
            need(c['urls'][0], ['url', 'sessions', 'dead', 'rage', 'quickback', 'scroll', 'engage_sec'], 'clarity.urls[]')
        o = d.get('ops')
        if need(o, ['sync_jobs', 'health', 'backup', 'price_sample', 'crontab'], 'ops'):
            if len(o['sync_jobs']) > 10: E('ops.sync_jobs 10건 초과')
            if not o['sync_jobs']: W('ops.sync_jobs 비었음')
            for j in o['sync_jobs'][:1]:
                need(j, ['job_type', 'started_at', 'completed_at', 'status', 'stats'], 'ops.sync_jobs[]')
            need(o['health'], ['checked_at', 'issues'], 'ops.health')
            need(o['backup'], ['latest_key', 'size_mb', 'at'], 'ops.backup')
            need(o['price_sample'], ['last_run', 'tail'], 'ops.price_sample')
            if not o['crontab']: E('ops.crontab 비었음')
        db = d.get('db')
        if need(db, ['hotels', 'reviews_site', 'analyzed_v5'], 'db'):
            if not db['hotels'].get('active'): E('db.hotels.active 없음')
    ch = d.get('changes')
    if g and need(ch, ['before_after', 'metrics'], 'changes'):
        got = {b['commit'] for b in ch['before_after']}
        for c in changes:
            if c['commit'] not in got:
                W(f'before_after에 {c["commit"]} 없음 — admin_export는 GitHub main의 changes.json을 읽는다(push 뒤 다음 집계에 들어감)')
            unk = [k for k in c.get('watch', []) if k not in ch['metrics']]
            if unk: E(f'changes.json {c["commit"]} watch 지표 이름이 admin_export METRICS에 없음: {unk}')
        for b in ch['before_after']:
            need(b, ['commit', 'date', 'before', 'after', 'days_after', 'final', 'verdict', 'metrics'], 'changes.before_after[]')
    print(f'admin.json {kb:.0f}KB · mode {d.get("mode")} · made_at {d.get("made_at")}')

for w in warns:
    print('  경고 ' + w)
for e in errs:
    print('  오류 ' + e)
if errs:
    print(f'check_admin 실패: 오류 {len(errs)}건')
    sys.exit(1)
print(f'check_admin OK (경고 {len(warns)}건)')
if data_path and '--to-docs' in sys.argv:
    dst = os.path.join(DOCS, 'admin', 'sample.json')
    shutil.copyfile(data_path, dst)
    print(f'  → {os.path.relpath(dst, ROOT)} (로컬 프리뷰용, .gitignore)')
