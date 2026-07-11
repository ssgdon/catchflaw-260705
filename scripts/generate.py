# -*- coding: utf-8 -*-
"""캐치플로 정적 사이트 생성기 — data-src/*.json → docs/
사용: python scripts/generate.py
"""
import json, os, shutil, sys, html, re, time, math
from collections import defaultdict
from urllib.parse import quote as urlquote

BUILD = str(int(time.time()))  # 에셋 캐시버스터

sys.path.insert(0, os.path.dirname(__file__))
from scoring import compute, CATS, SUBS, SUB_KEYWORDS, RARE_SUBS, MIN_REVIEWS

# ── 카테고리 표시명 (TAXONOMY v4: 명칭이 이미 중립적이라 순화층 불요). cat_ko는 identity로 유지해 호출부 보존. ──
def cat_ko(c): return c
CONTACT_EMAIL = 'fibinc8967@gmail.com'   # 정정·이의제기 창구 (LEGAL-SOFTEN §2-a)

def mask_name(s):
    """리뷰어 실명 마스킹 (LEGAL-SOFTEN §3): 첫 글자 + '**'. 빈값은 '투숙객'."""
    s = str(s or '').strip()
    return (s[0] + '**') if s else '투숙객'

# 클라이언트 JS 표시용 매핑 주입값 (내부키 → 표시명). head()에서 window.CAT_KO 로 주입.
CAT_KO_JSON = json.dumps({c: cat_ko(c) for c in CATS}, ensure_ascii=False)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data-src')
OUT = os.path.join(ROOT, 'docs')

# ───────────────────────── 도시 설정 (변수화 — 신규 도시는 여기만 추가) ─────────────────────────
CITY = {'code': 'fukuoka', 'ko': '후쿠오카', 'en': 'Fukuoka', 'data_asof': '2026년 3월', 'asof': None}

# ── SEO 기반 상수 ──
BASE = 'https://catchflaw.com'   # canonical 기준 도메인 (apex). www/pages.dev 금지.
DEFAULT_OG = f'{BASE}/img/search_bg.jpg'   # 대표 이미지 없는 페이지용 기본 OG
# 검색엔진 소유확인 메타 (전 페이지 head 공통 삽입). 구글은 Cloudflare DNS로 자동확인됨 → 태그 불요.
VERIFY_META = '<meta name="naver-site-verification" content="9b59c2e0175c1673a6091cbb5627e67a25b136e5" />'

R2_PUB = 'https://pub-33003031288947c5a134ef8d12819213.r2.dev'  # 폴백: 현행 R2 공개 버킷(리뷰 전체 JSON fetch 베이스)
def _load_asof():
    """data-src/meta.json(export_pg 생성)의 기준일로 data_asof 갱신 — 하드코딩 제거. 없으면 기존값.
    r2 공개베이스도 함께 읽어 리뷰 전체 더보기 fetch URL 조립에 사용(REVIEW-LAZYLOAD §C)."""
    global R2_PUB
    try:
        d = json.load(open(os.path.join(SRC, 'meta.json'), encoding='utf-8'))
        y, m, _ = str(d['asof']).split('-')
        CITY['data_asof'] = f'{int(y)}년 {int(m)}월'
        CITY['asof'] = str(d['asof'])   # 트렌드 차트 월 축 생성용 (YYYY-MM-DD)
        if d.get('r2'):
            R2_PUB = str(d['r2']).rstrip('/')
    except Exception:
        pass
_load_asof()
UNSUPPORTED_KEYWORDS = ['도쿄', 'tokyo', '오사카', 'osaka', '교토', 'kyoto', '삿포로', 'sapporo',
    '나고야', 'nagoya', '오키나와', 'okinawa', '서울', 'seoul', '부산', 'busan', '제주', 'jeju',
    '방콕', 'bangkok', '다낭', 'danang', '나트랑', '타이베이', 'taipei', '싱가포르', 'singapore',
    '홍콩', 'hongkong', 'hong kong', '괌', 'guam', '세부', 'cebu', '파리', 'paris', '런던', 'london']

CAT_ICON = {'위생': '', '냄새': '', '소음': '', '시설': '', '불친절': '', '위치·안전': ''}
BAND_KO = {'danger': '위험', 'warning': '주의', 'safe': '양호'}
GAUGE_MAX = 40.0  # 실망확률 게이지 상한(%)

# ── 인기 지역 (한국인 자주 검색, 좌표+반경km) — 신규 지역은 여기만 추가 ──
AREAS = [
    {'code': 'hakata', 'ko': '하카타역', 'lat': 33.5897, 'lng': 130.4207, 'r': 1.3},
    {'code': 'tenjin', 'ko': '텐진', 'lat': 33.5914, 'lng': 130.3986, 'r': 1.2},
    {'code': 'nakasu', 'ko': '나카스·캐널시티', 'lat': 33.5930, 'lng': 130.4085, 'r': 1.0},
    {'code': 'gion', 'ko': '기온·오호리', 'lat': 33.5915, 'lng': 130.4120, 'r': 1.0},
]

# ── 역 좌표 (역거리 계산 — HUB-NORMALIZE §2). AREAS 좌표 재사용 + 역 보정. ──
STATIONS = [
    {'code': 'hakata', 'ko': '하카타역', 'lat': 33.5897, 'lng': 130.4207},
    {'code': 'tenjin', 'ko': '텐진역', 'lat': 33.5914, 'lng': 130.3989},
    {'code': 'nakasu', 'ko': '나카스카와바타역', 'lat': 33.5946, 'lng': 130.4064},
    {'code': 'gion', 'ko': '기온역', 'lat': 33.5924, 'lng': 130.4157},
]

# ── 시설 표준키 → 한글 칩 라벨 (허브 카드 텍스트 칩용, 이모지 금지) ──
AMENITY_LABEL = {
    'breakfast': '조식', 'pool': '수영장', 'spa_bath': '온천·사우나', 'parking': '주차',
    'kitchen': '주방', 'fitness': '피트니스', 'laundry': '세탁', 'bar': '바',
    'restaurant': '레스토랑', 'room_service': '룸서비스', 'aircon': '에어컨',
    'airport_shuttle': '공항셔틀', 'wheelchair': '휠체어', 'kids_ok': '유아동반',
    'nonsmoking': '금연', 'pet': '반려동물',
}
AMENITY_CHIP_ORDER = ['breakfast', 'pool', 'spa_bath', 'kitchen', 'parking', 'fitness',
                      'restaurant', 'room_service', 'laundry', 'airport_shuttle']

def nearest_station(lat, lng):
    """호텔 좌표 → (역이름, 도보분, 직선m). 좌표 없으면 None. 도보분 = ceil(거리m/67)."""
    if lat is None or lng is None:
        return None
    try:
        la, lo = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    best = None
    for s in STATIONS:
        d = haversine_km(la, lo, s['lat'], s['lng']) * 1000.0    # m
        if best is None or d < best[1]:
            best = (s['ko'], d)
    ko, dist_m = best
    walk = max(1, math.ceil(dist_m / 67.0))
    return (ko, walk, int(round(dist_m)))

def station_line(meta):
    """상세/허브용 역거리 1줄 텍스트. 예: '하카타역 도보 약 7분(직선 450m)'. 없으면 ''."""
    ns = nearest_station(meta.get('latitude'), meta.get('longitude'))
    if not ns:
        return ''
    ko, walk, dist_m = ns
    return f'{ko} 도보 약 {walk}분(직선 {dist_m}m)'

def amenity_chips(meta, k=3):
    """호텔 amenities → 텍스트 칩 라벨 리스트(최대 k). amenities 부재/빈값이면 []."""
    am = meta.get('amenities') or {}
    if not isinstance(am, dict):
        return []
    out = []
    for key in AMENITY_CHIP_ORDER:
        if key in am and am[key] and key in AMENITY_LABEL:
            out.append(AMENITY_LABEL[key])
        if len(out) >= k:
            break
    return out

# ── 피드백 저장 (Supabase anon key: 공개용, INSERT 전용 RLS) ──
SUPABASE_URL = 'https://iixztaazwpjvxnpgegod.supabase.co'
SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlpeHp0YWF6d3BqdnhucGdlZ29kIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk3NTM2MzQsImV4cCI6MjA4NTMyOTYzNH0.SJSDMieyC7CLMowW04ArmFcaQxGhG2gzPi5b3FQzpmg'

# ── 가격 (스크랩 시점 1박 요금, 통화 혼재 → 원화 환산 후 밴드) ──
FX = {'US$': 1400, '£': 1750, '€': 1500, 'SCR': 100, '₩': 1, '¥': 9.5}
PRICE_BANDS = [
    ('b1', '10만원 미만', 0, 100_000),
    ('b2', '10~20만원', 100_000, 200_000),
    ('b3', '20만원 이상', 200_000, 10**10),
]

def parse_price(price_str):
    """'US$98' → (원화 int, '약 14만원') / 파싱 불가 → (None, '')"""
    if not price_str: return None, ''
    m = re.match(r'^([^\d]*)([\d,\.]+)', str(price_str).strip())
    if not m: return None, ''
    cur = m.group(1).strip() or 'US$'
    try: val = float(m.group(2).replace(',', ''))
    except ValueError: return None, ''
    rate = FX.get(cur)
    if rate is None: return None, ''
    krw = int(val * rate)
    man = max(1, round(krw / 10_000))
    return krw, f'약 {man}만원'

def price_band(krw):
    if krw is None: return None
    for code, label, lo, hi in PRICE_BANDS:
        if lo <= krw < hi: return code, label
    return None

E = lambda s: html.escape(str(s or ''), quote=True)

def emph(s):
    """리뷰 인용문의 **강조** → <span> (퍼블리싱 표준: 보라+굵게). 남는 ** 는 제거."""
    t = html.escape(str(s or ''), quote=True)
    t = re.sub(r'\*\*(.+?)\*\*', r'<span>\1</span>', t)
    return t.replace('**', '')

def pct(x): return round(x * 100)

def josa_eun(word):
    """받침 유무로 '은'/'는' 선택 (F13). 한글 음절 종성 기준. 예: 냄새→는, 위생/소음/시설/불친절/위치·안전→은."""
    w = str(word or '').rstrip()
    if not w:
        return '은'
    ch = w[-1]
    if '가' <= ch <= '힣':
        return '은' if (ord(ch) - 0xAC00) % 28 else '는'
    return '은'

def load():
    J = lambda f: json.load(open(os.path.join(SRC, f), encoding='utf-8'))
    hotels_meta = {h['place_id']: h for h in J('hotels.json')}
    # rec_excluded(러브호텔·넷카페·북카페)는 사이트 전면 제외 — 상세 미생성·검색·자동완성·지도·목록 전부 (DETAIL-FIXES-260706 §5)
    hotels_meta = {pid: m for pid, m in hotels_meta.items() if not m.get('rec_excluded')}
    # R2 호스팅 이미지 (images.py 로 수확) + 로컬 폴백 + 가격 파싱
    imgs = {r['place_id']: r for r in (J('images.json') if os.path.exists(os.path.join(SRC, 'images.json')) else [])}
    for pid, m in hotels_meta.items():
        im = imgs.get(pid, {})
        m['r2_imgs'] = im.get('imgs') or []          # R2 전체 사진 배열(seq순)
        m['r2_img'] = m['r2_imgs'][0] if m['r2_imgs'] else None
        m['local_img'] = os.path.exists(os.path.join(ROOT, 'assets', 'hotels', f'{pid}.jpg'))
        m['krw'], m['price_txt'] = parse_price(m.get('price'))
        m['band'] = price_band(m['krw'])
    quotes = defaultdict(list)
    for q in J('quotes.json'):
        quotes[(q['place_id'], q['mcat'])].append(q)
    stars = defaultdict(lambda: {'dist': {i: 0 for i in range(1, 6)}, 'total': 0, 'low_1y': 0, 'total_1y': 0})
    for s in J('stars.json'):
        st = stars[s['place_id']]
        st['dist'][int(s['stars'])] = s['n']
        st['total'] += s['n']
        st['total_1y'] += s['n_1y']
        if int(s['stars']) <= 2: st['low_1y'] += s['n_1y']
    kr = {}
    for r in (J('kr_stats.json') if os.path.exists(os.path.join(SRC, 'kr_stats.json')) else []):
        kr[(r['place_id'], r['period'])] = r
    # 월별 심각/주의 흐름 (트렌드 차트). 파일 없으면 빈 dict — 빌드 깨지지 않게.
    def _i(x):
        try: return int(float(x))
        except (TypeError, ValueError): return 0
    monthly = defaultdict(dict)   # {pid: {ym: (n, n_crit, n_warn)}}
    if os.path.exists(os.path.join(SRC, 'monthly.json')):
        for r in J('monthly.json'):
            monthly[r['place_id']][r['ym']] = (_i(r.get('n')), _i(r.get('n_crit')), _i(r.get('n_warn')))
    # 카테고리×월별 심각/주의 흐름 (아코디언 트렌드 차트). 파일 없으면 빈 dict — 빌드 안전.
    monthly_cat = defaultdict(dict)   # {pid: {(ym, cat): (n_crit, n_warn)}}
    if os.path.exists(os.path.join(SRC, 'monthly_cat.json')):
        for r in J('monthly_cat.json'):
            monthly_cat[r['place_id']][(r['ym'], r['cat'])] = (_i(r.get('n_crit')), _i(r.get('n_warn')))
    # B층 FAQ (faq_extract → export_pg). 파일 없으면 빈 dict — 빌드 안전(§3-d).
    faq = {}
    if os.path.exists(os.path.join(SRC, 'faq.json')):
        try: faq = json.load(open(os.path.join(SRC, 'faq.json'), encoding='utf-8')) or {}
        except Exception: faq = {}
    # 소셜 콘텐츠 (fetch_social — 네이버 블로그·유튜브 후기). 없으면 빈 dict → 섹션 미노출 (SOCIAL).
    social = {}
    if os.path.exists(os.path.join(SRC, 'social.json')):
        try: social = json.load(open(os.path.join(SRC, 'social.json'), encoding='utf-8')) or {}
        except Exception: social = {}
    return hotels_meta, quotes, stars, kr, monthly, monthly_cat, faq, social

# ───────────────────────── 공통 조각 ─────────────────────────
# Microsoft Clarity (히트맵·세션 리플레이). f-string 아님 — JS 중괄호 리터럴 보존.
CLARITY = '''<script type="text/javascript">
    (function(c,l,a,r,i,t,y){
        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window, document, "clarity", "script", "xi5o022ef1");
</script>'''

# Google Analytics 4 (전 페이지 head). gtag 로드 + 자동 페이지뷰.
GA4_ID = 'G-4M1BGXJZYQ'
GA4 = f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA4_ID}');
</script>'''

def head(title, depth=0, description=None, canonical=None, og_image=None, extra_head=''):
    p = '../' * depth
    seo = []
    d = None
    if description:
        d = description if len(description) <= 150 else description[:149].rstrip() + '…'
        seo.append(f'<meta name="description" content="{E(d)}">')
    if canonical:
        seo.append(f'<link rel="canonical" href="{canonical}">')
        seo.append(f'<meta property="og:title" content="{E(title)}">')
        if d:
            seo.append(f'<meta property="og:description" content="{E(d)}">')
        seo.append(f'<meta property="og:url" content="{canonical}">')
        seo.append('<meta property="og:type" content="website">')
        seo.append('<meta property="og:site_name" content="캐치플로">')
        seo.append(f'<meta property="og:image" content="{og_image or DEFAULT_OG}">')
        seo.append('<meta name="twitter:card" content="summary_large_image">')
    seo_block = '\n    '.join(seo)
    return f'''<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0, user-scalable=yes">
    <title>{E(title)}</title>
    {seo_block}
    {VERIFY_META}
    {GA4}
    {CLARITY}
    {extra_head}
    <link rel="icon" type="image/svg+xml" href="{p}img/favicon.svg">
    <link rel="apple-touch-icon" href="{p}img/favicon.svg">
    <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
    <link rel="stylesheet" href="{p}css/tokens.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/common.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/layout.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/swiper.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/uplift.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/mvp.css?v={BUILD}">
    <script src="{p}js/backnav.js?v={BUILD}"></script>
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="{p}js/swiper.js"></script>
    <script>window.CF_SB={{url:'{SUPABASE_URL}',key:'{SUPABASE_ANON}'}};window.CF_AREAS={json.dumps(AREAS, ensure_ascii=False)};window.CAT_KO={CAT_KO_JSON};</script>
    <script src="{p}js/engage.js?v={BUILD}" defer></script>
    <script src="{p}js/recommend.js?v={BUILD}"></script>
</head>
<body>
<div id="wrapper">'''

FOOT = '''</div>
</body>
</html>'''

def header_nav(depth=0):
    p = '../' * depth
    return f'''
    <header id="header">
        <div class="header"><div class="inner">
            <div class="logo"><a href="{p or "./"}"><img src="{p}img/logo.svg" alt="CATCHFLAW"></a></div>
        </div></div>
    </header>'''

def build_footer(depth=0):
    """공통 미니 푸터 (LEGAL-SOFTEN §2-b). 전 생성 페이지에 삽입. about·정정창구 링크."""
    p = '../' * depth
    return f'''
    <footer id="site-foot">
        <div class="foot-note">캐치플로의 실망 확률·위험도는 공개된 투숙객 리뷰를 AI로 분석한 <b>참고용 통계 의견</b>이며, 특정 업소의 객관적 품질을 단정하지 않습니다.</div>
        <div class="foot-links"><a href="{p or './'}about">캐치플로 소개·산출 방법</a> · <a href="mailto:{CONTACT_EMAIL}">정정·이의제기</a></div>
        <div class="foot-copy">ⓒ 2026 CATCHFLAW</div>
    </footer>'''

def site_header(depth=1, back=None):
    """F36+F40: 공통 사이트 헤더(좌 back·중앙 로고·우 햄버거)+드로어 4링크 — 상세·recent 공유. sticky는 CSS."""
    p = '../' * depth
    home = p or './'
    back_href = back or home
    return f'''<div class="det-header">
                <a class="dh-back" href="{back_href}" aria-label="뒤로가기"><img src="{p}img/back_b.svg" alt="뒤로가기"></a>
                <a class="dh-logo" href="{home}" aria-label="CATCHFLAW 홈"><img src="{p}img/logo.svg" alt="CATCHFLAW"></a>
                <button type="button" class="dh-menu" aria-label="전체메뉴"><span></span><span></span><span></span></button>
            </div>
            <div class="det-drawer" hidden>
                <div class="dd-dim"></div>
                <div class="dd-panel">
                    <button type="button" class="dd-close" aria-label="닫기">✕</button>
                    <nav class="dd-nav">
                        <a href="{home}">홈</a>
                        <a href="{p}search">호텔 검색</a>
                        <a href="{p}recent">최근 본 호텔</a>
                        <a href="{p}about">산출 방법</a>
                    </nav>
                </div>
            </div>
            <script>
            $(function(){{
                var $drawer = $('.det-drawer');
                function drawerClose(){{ $drawer.removeClass('is-open'); setTimeout(function(){{ $drawer.prop('hidden', true); }}, 300); }}
                $('.dh-menu').on('click', function(e){{ e.preventDefault(); $drawer.prop('hidden', false); $drawer[0].offsetWidth; $drawer.addClass('is-open'); }});
                $drawer.on('click', '.dd-dim, .dd-close', function(e){{ e.preventDefault(); drawerClose(); }});
                $(document).on('keydown', function(e){{ if (e.key === 'Escape' && $drawer.hasClass('is-open')) drawerClose(); }});
            }});
            </script>'''

def badge_html(h):
    if not h['scored']:
        return '<div class="badge-item badge-collect">리뷰 수집중</div>'
    band, label = h['badge']
    return (f'<div class="badge-item badge-{band}">{label}</div>'
            f'<div class="badge-item badge-down">실망 확률 {pct(h["p_crit"])}%</div>')

def img_path(pid, meta, depth=0):
    p = '../' * depth
    if meta.get('r2_img'):
        return meta['r2_img']                       # R2 절대 URL
    if meta.get('local_img'):
        return f'{p}img/hotels/{pid}.jpg'
    return f'{p}img/placeholder.svg'

def fmt_score(v):
    try: return f'{float(v):.1f}'
    except (TypeError, ValueError): return '-'

def hotel_card(pid, meta, h, depth=0):
    p = '../' * depth
    star_w = round(float(meta.get('total_score') or 0) / 5 * 100)
    return f'''<li class="swiper-slide">
        <a href="{p}hotels/{pid}" class="item">
            <div class="thumb">
                <div class="badge">{badge_html(h)}</div>
                <div class="image"><img src="{img_path(pid, meta, depth)}" alt="{E(meta['title'])}" width="600" height="400" loading="lazy"></div>
            </div>
            <div class="info">
                <h3 class="name">{E(meta['title'])}</h3>
                <div class="eng">{E(meta.get('sub_title') or CITY['en'])}</div>
                <div class="star"><i style="width:{star_w}%"></i></div>
                <div class="text">구글 {fmt_score(meta.get('total_score'))} · 리뷰 {meta.get('reviews_count') or 0:,}개</div>
                <div class="price-line">{('1박 <b>' + meta['price_txt'] + '</b>') if meta.get('price_txt') else '&nbsp;'}</div>
            </div>
        </a>
    </li>'''

# ───────────────────────── index ─────────────────────────
def build_index(hotels_meta, H, quotes, col_index=()):
    scored = [p for p in H if H[p]['scored'] and p in hotels_meta]  # hotels_meta가 rec_excluded 제외 → scored도 자동 제외
    _total = sum(r['n'] for r in json.load(open(os.path.join(SRC, 'agg_denom.json'), encoding='utf-8')))
    total_reviews_txt = f"{round(_total/10000)}만"   # 동적: 분석 대상 리뷰 총수 (예: 6만)

    def worst_by_sub(mcat, scat, k=8):
        cand = [p for p in scored if H[p]['cats'][mcat]['subs'][scat]['count'] >= 5]
        return sorted(cand, key=lambda p: -H[p]['cats'][mcat]['subs'][scat]['score'])[:k]

    best = sorted(scored, key=lambda p: H[p]['p_crit'])[:8]
    cur1 = worst_by_sub('위생', '해충/곰팡이')
    cur2 = worst_by_sub('냄새', '화장실·곰팡 악취')

    def slider(title, desc, pids):
        cards = '\n'.join(hotel_card(p, hotels_meta[p], H[p]) for p in pids)
        return f'''<div class="hotel-list init">
            <div class="head"><div class="title">{title}</div><div class="desc">{desc}</div></div>
            <div class="list hotel-slider"><ul class="swiper-wrapper">{cards}</ul></div>
        </div>'''

    # 가격대별 만족도: 각 밴드에서 실망 확률 낮은 순
    price_parts = []
    for code, label, lo, hi in PRICE_BANDS:
        pids = sorted((p for p in scored if hotels_meta[p].get('band') and hotels_meta[p]['band'][0] == code),
                      key=lambda p: H[p]['p_crit'])[:8]
        if len(pids) >= 3:
            price_parts.append(slider(f'{label} · 추천 숙소',
                f'1박 {label} 가격대에서 실망 확률이 가장 낮은 숙소예요 (가격 {CITY["data_asof"]} 기준)', pids))
    price_sliders = ''.join(price_parts)

    # 지역·테마별 컬렉션 칩 그리드 (생성된 컬렉션만 노출 — HUB §3-d)
    col_chips = ''
    if col_index:
        chips = ''.join(f'<a class="hub-home-chip" href="./{E(slug)}">{E(name)}</a>' for slug, name in col_index)
        col_chips = f'''<article class="section sec-collections">
                <div class="home-collections init">
                    <div class="head"><div class="title">지역·테마별 보기</div>
                    <div class="desc">찾는 조건에 맞는 호텔을 리뷰 위험도 순으로 모았어요</div></div>
                    <div class="hub-home-chips">{chips}</div>
                </div>
            </article>'''

    n_live = sum(1 for pid in hotels_meta if pid in H)   # 상세 생성되는 호텔 수
    home_ld = _jsonld({'@context':'https://schema.org','@type':'WebSite','name':'캐치플로','alternateName':'CATCHFLAW',
        'url':f'{BASE}/', 'potentialAction':{'@type':'SearchAction',
        'target':{'@type':'EntryPoint','urlTemplate':f'{BASE}/search?q={{search_term_string}}'},
        'query-input':'required name=search_term_string'}})
    html_out = head('캐치플로 — 후쿠오카 호텔 리뷰 위험도·실망 확률 분석',
        description=f'{CITY["ko"]} 호텔 {n_live}곳의 실제 리뷰를 AI로 분석해 실망 확률을 알려드립니다. '
                    '위생·소음·시설·동선·서비스·안전 6개 항목의 위험도를 예약 전에 확인하세요.',
        canonical=f'{BASE}/', extra_head=home_ld) + f'''
    <link rel="preload" as="image" href="./img/search_bg.jpg?v={BUILD}" fetchpriority="high">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">''' + header_nav() + f'''
    <main id="container">
        <section id="main">
            <article class="section sec-1">
                <div class="search-box init">
                    <div class="text"><ul>
                        <li><div class="subject">직원이 불친절해요</div><div class="star"><i style="width:20%"></i></div></li>
                        <li><div class="subject">너무 시끄러워요</div><div class="star"><i style="width:40%"></i></div></li>
                        <li><div class="subject">침대에서 벌레가 나왔어요</div><div class="star"><i style="width:40%"></i></div></li>
                    </ul></div>
                    <div class="title">
                        <h1 class="tit">잠깐, 그 호텔 <br><span>최악의 리뷰</span>는요?</h1>
                        <div class="txt">AI가 {CITY['ko']} 호텔 리뷰 {total_reviews_txt} 개를 분석해 <br><span>치명적인 단점</span>만 찾아냅니다.</div>
                    </div>
                    <form class="input" action="./search" method="get" autocomplete="off">
                        <input type="text" name="q" id="hero-q" placeholder="{CITY['ko']} 호텔명 또는 구글맵 링크 붙여넣기">
                        <button type="submit"><img src="./img/search.svg" alt="검색"></button>
                        <div class="ac-box" id="ac-box" hidden></div>
                    </form>
                    <div class="scope-note">현재 <b>{CITY['ko']}</b> 호텔 {len(scored)}곳 분석 완료 · 다른 도시는 준비 중이에요</div>
                </div>
            </article>
            {col_chips}
            <article class="section sec-map">
                <div class="home-map init">
                    <div class="head"><div class="title">지도로 한눈에 보기</div>
                    <div class="desc">마커 색은 캐치플로 등급이에요 · 눌러서 실망 확률을 확인하세요</div></div>
                    <div class="map-wrap"><div id="map"></div>
                        <div class="map-legend">
                            <span class="lg safe">양호</span><span class="lg warning">주의</span><span class="lg danger">위험</span><span class="lg none">수집중</span>
                        </div>
                    </div>
                    <div class="map-more"><a href="./search">가격·지역·등급으로 딱 맞는 호텔 찾기 →</a></div>
                </div>
            </article>
            <article class="section sec-2">
                {price_sliders}
                {slider(f'{CITY["ko"]} 추천 숙소', f'{CITY["ko"]}에서 실망 확률이 가장 낮은 숙소 순이에요', best)}
                {slider('벌레·곰팡이 언급 숙소', f'리뷰에 해충·곰팡이 언급이 많은 {CITY["ko"]} 숙소입니다', cur1)}
                {slider('악취 언급 숙소', f'리뷰에 냄새 관련 언급이 많은 {CITY["ko"]} 숙소입니다', cur2)}
                <script>
                    $(function(){{
                        $('.hotel-slider').each(function(i, el){{
                            new Swiper(el, {{slidesPerView:'auto', spaceBetween:10, observer:true, observeParents:true}});
                        }});
                    }});
                </script>
            </article>
        </section>
        <section id="float">
            <div class="float">
                <a href="javascript:;" class="btn-airec"><span>AI 추천받기</span></a>
            </div>
        </section>
    </main>
    <script src="./data/index.js?v={BUILD}"></script>
    <script defer src="./data/search_index.js?v={BUILD}"></script>
    <script src="./js/search-key.js?v={BUILD}"></script>
    <script src="./js/search-ac.js?v={BUILD}"></script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    // ───── 메인: 지도 (한국어 라벨 타일) ─────
    $(function(){{
        var BAND_COLOR = {{safe:'#5EA5E7', warning:'#F0A028', danger:'#FA5252'}};
        var map = L.map('map', {{scrollWheelZoom: false}}).setView([33.5902, 130.4017], 13);
        L.tileLayer('https://{{s}}.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&hl=ko',
            {{maxZoom: 19, subdomains: ['mt0','mt1','mt2','mt3'], attribution: '&copy; Google'}}).addTo(map);
        map.on('click', function(){{ map.scrollWheelZoom.enable(); }});
        var pts = [];
        HOTELS.forEach(function(h){{
            if (h.lat == null) return;
            var col = h.band ? BAND_COLOR[h.band] : '#9CA3AF';
            var mk = L.circleMarker([h.lat, h.lng], {{radius: 8, color: '#fff', weight: 2, fillColor: col, fillOpacity: 0.95}}).addTo(map);
            var chip = h.p != null
                ? '<span class="pop-p" style="background:' + col + '">실망 확률 ' + h.p + '%</span>'
                : '<span class="pop-p" style="background:#9CA3AF">리뷰 수집중</span>';
            mk.bindPopup('<div class="map-pop"><b>' + h.name + '</b>'
                + '<div class="pop-meta">★ ' + (h.g ? h.g.toFixed(1) : '-') + ' (' + h.rc.toLocaleString() + ')'
                + (h.pt ? ' · 1박 ' + h.pt : '') + '</div>' + chip
                + '<a class="pop-link" href="./hotels/' + h.id + '">캐치플로 분석 보기 →</a></div>');
            pts.push([h.lat, h.lng]);
        }});
        if (pts.length) map.fitBounds(pts, {{padding: [24, 24], maxZoom: 14}});
    }});

    // ───── 메인 검색: 자동완성(CFAutocomplete) + 구글맵 URL 인식 ─────
    $(function(){{
        var $q = $('#hero-q'), $box = $('#ac-box');
        function norm(s){{ return (s||'').toLowerCase().replace(/\\s+/g,''); }}
        function isUrl(v){{ return /^https?:\\/\\//.test(v) || v.indexOf('maps.app.goo.gl') >= 0 || v.indexOf('google.') >= 0; }}

        function resolveUrl(input){{
            // 구글맵 URL → place_id / 좌표 / 장소명으로 우리 호텔 매칭
            var m = input.match(/place_id[:=]([A-Za-z0-9_-]+)/) || input.match(/(ChIJ[A-Za-z0-9_-]{{10,}})/);
            if (m) {{
                var hit = HOTELS.filter(function(h){{ return h.id === m[1]; }})[0];
                if (hit) return hit;
            }}
            var c = input.match(/@(-?\\d+\\.\\d+),(-?\\d+\\.\\d+)/) || input.match(/[?&]q=(-?\\d+\\.\\d+),(-?\\d+\\.\\d+)/);
            if (c) {{
                var la = parseFloat(c[1]), lo = parseFloat(c[2]), best = null, bd = 1e9;
                HOTELS.forEach(function(h){{
                    if (h.lat == null) return;
                    var d = Math.pow(h.lat - la, 2) + Math.pow(h.lng - lo, 2);
                    if (d < bd) {{ bd = d; best = h; }}
                }});
                if (best && bd < 0.00001) return best;   // 약 300m 이내
            }}
            var pm = input.match(/\\/place\\/([^\\/@?]+)/);
            if (pm) {{
                var name = norm(decodeURIComponent(pm[1]).replace(/\\+/g, ' '));
                var hit2 = HOTELS.filter(function(h){{
                    return norm(h.name).indexOf(name) >= 0 || name.indexOf(norm(h.name)) >= 0
                        || (h.en && (norm(h.en).indexOf(name) >= 0 || name.indexOf(norm(h.en)) >= 0));
                }})[0];
                if (hit2) return hit2;
            }}
            return null;
        }}

        // 공용 자동완성 엔진 연결 (별칭 인덱스 매칭 · 키보드 · 미매칭 요청행)
        if (window.CFAutocomplete) {{
            window.CFAutocomplete.attach($q.get(0), {{ hrefPrefix: './hotels/', areaHref: './search?area=', isUrl: isUrl }});
        }}

        // URL 입력 시엔 자동완성 대신 링크 해석 안내
        $q.on('input', function(){{
            var v = $q.val().trim();
            if (isUrl(v)) {{
                var hit = resolveUrl(v);
                if (hit) {{
                    $box.prop('hidden', false).html('<div class="ac-section">호텔</div><a class="ac-item" href="./hotels/' + hit.id + '"><span class="ac-main"><span class="ac-name">' + hit.name + '</span></span></a>');
                }} else {{
                    $box.prop('hidden', false).html('<div class="ac-none">링크에서 호텔을 찾지 못했어요. 호텔 이름으로 검색해 보세요!</div>');
                }}
            }}
        }});

        $q.closest('form').on('submit', function(e){{
            var v = $q.val().trim();
            if (isUrl(v)) {{
                e.preventDefault();
                var hit = resolveUrl(v);
                if (hit) location.href = './hotels/' + hit.id;
                else location.href = './search?q=' + encodeURIComponent(v);
            }}
        }});
    }});
    </script>''' + build_footer(0) + FOOT
    return html_out

# ───────────────────────── 404 ─────────────────────────
def build_404():
    """soft-404 해소용 독립 404 페이지. canonical/description 없이 noindex.
       링크는 절대경로(어느 깊이에서도 서빙되므로 상대경로 금지)."""
    return head('페이지를 찾을 수 없어요 — 캐치플로', depth=0,
        extra_head='<meta name="robots" content="noindex">') + header_nav() + f'''
    <main id="container"><section id="search" style="padding:60px 20px">
        <div class="notice-card">
            <div class="notice-tit">페이지를 찾을 수 없어요</div>
            <div class="notice-txt">주소가 바뀌었거나 없는 페이지예요.<br>{CITY['ko']} 호텔 분석은 아래에서 계속 볼 수 있어요.</div>
            <a class="notice-btn" href="/">캐치플로 홈으로</a>
            <a class="notice-btn" href="/search" style="margin-left:8px;background:var(--ink)">호텔 전체 보기</a>
        </div>
    </section></main>''' + build_footer(0) + FOOT

# ───────────────────────── recent (F40) ─────────────────────────
def build_recent(hotels_meta, H):
    """F40-c: 최근 본 호텔 — localStorage(cf_recent, 최신순 pid 배열·기록은 js/engage.js) 기반 개인화 페이지.
       카드 = hotel_card 동일 마크업(빌드시 전 호텔 숨김 풀 프리렌더 → JS가 기록 순서로 노출, 최대 20). sitemap 제외·noindex."""
    pool = '\n'.join(hotel_card(p, hotels_meta[p], H[p], depth=0) for p in hotels_meta if p in H)
    return head('최근 본 호텔 | 캐치플로', depth=0,
        extra_head='<meta name="robots" content="noindex">') + f'''
    <main id="container">
        <section id="main">
            {site_header(0, back='./')}
            <div class="hotel-list recent-list">
                <div class="head"><div class="title">최근 본 호텔</div></div>
                <div class="list"><ul id="recent-list"></ul></div>
            </div>
            <div class="recent-empty" id="recent-empty" hidden>
                <div class="re-txt">아직 본 호텔이 없어요</div>
                <a class="re-btn" href="./search">호텔 검색하기</a>
            </div>
            <ul id="recent-pool" hidden>{pool}</ul>
        </section>
    </main>
    <script>
    $(function(){{
        var ids = [];
        try {{ ids = JSON.parse(localStorage.getItem('cf_recent') || '[]'); }} catch (e) {{}}
        if (!Array.isArray(ids)) ids = [];
        var $list = $('#recent-list'), n = 0;
        ids.slice(0, 20).forEach(function(pid){{
            var $a = $('#recent-pool a[href="hotels/' + String(pid).replace(/[^\\w-]/g, '') + '"]');
            if ($a.length) {{ $list.append($a.closest('li')); n++; }}
        }});
        $('#recent-pool').remove();
        if (!n) {{ $('#recent-empty').prop('hidden', false); $('.recent-list').hide(); }}
    }});
    </script>''' + build_footer(0) + FOOT

# ───────────────────────── search ─────────────────────────
def build_search_index(hotels_meta, H):
    items = []
    for pid, meta in hotels_meta.items():
        h = H.get(pid)
        if not h: continue
        # 카테고리별 등급/점수 (필터·정렬용): {대분류: band}, {대분류: 위험도점수}
        cb, cs = {}, {}
        if h['scored']:
            for c in CATS:
                cb[c] = h['cats'][c]['band']
                cs[c] = round(h['cats'][c]['score'])
        items.append({
            'id': pid, 'name': meta['title'], 'en': meta.get('sub_title') or '',
            'stars': meta.get('hotel_stars') or '', 'g': float(meta.get('total_score') or 0),
            'rc': meta.get('reviews_count') or 0,
            'img': meta.get('r2_img') or (f'img/hotels/{pid}.jpg' if meta.get('local_img') else ''),
            'scored': h['scored'],
            'p': pct(h['p_crit']) if h['scored'] else None,
            'band': h['badge'][0] if h['scored'] else None,
            'label': h['badge'][1] if h['scored'] else '리뷰 수집중',
            'lat': float(meta['latitude']) if meta.get('latitude') else None,
            'lng': float(meta['longitude']) if meta.get('longitude') else None,
            'pb': meta['band'][0] if meta.get('band') else None,
            'pt': meta.get('price_txt') or '',
            'krw': meta.get('krw'),
            'cb': cb, 'cs': cs,
        })
    return items

def build_search_ac_index(hotels_meta, H):
    """자동완성용 슬림 인덱스 (§7-a): hotels_index.json(별칭키) + 계산된 실망확률/밴드.
       항목당 {id,t,p,band,krn,pop,keys(≤40),cho(≤10)}. closed/미노출 제외. window.CF_IDX 로 노출."""
    src = os.path.join(SRC, 'hotels_index.json')
    if not os.path.exists(src):
        return '[]'
    raw = json.load(open(src, encoding='utf-8'))
    out = []
    for r in raw:
        pid = r['id']
        if r.get('st') == 'closed':
            continue
        h = H.get(pid)
        meta = hotels_meta.get(pid)
        if not h or not meta:            # 사이트 미노출(상세 페이지 없음) 제외
            continue
        # 짧은 키 우선 보존(브랜드/초성 축약형이 매칭에 가장 유용) 후 상한 절단
        keys = sorted(r.get('keys') or [], key=lambda s: (len(s), s))[:40]
        cho = sorted(r.get('cho') or [], key=lambda s: (len(s), s))[:10]
        if not keys and not cho:
            continue
        out.append({
            'id': pid,
            't': meta['title'],
            'p': pct(h['p_crit']) if h['scored'] else None,
            'band': h['badge'][0] if h['scored'] else None,
            'krn': r.get('krn') or 0,
            'pop': r.get('pop') or 0,
            'keys': keys,
            'cho': cho,
        })
    out.sort(key=lambda x: -x['pop'])
    return json.dumps(out, ensure_ascii=False, separators=(',', ':'))

def build_search(city_avg_pct):
    kw = json.dumps(UNSUPPORTED_KEYWORDS, ensure_ascii=False)
    cats_js = json.dumps([{'ko': c, 'ico': CAT_ICON[c]} for c in CATS], ensure_ascii=False)
    area_chips = ''.join(
        f'<button type="button" class="f-chip" data-area="{a["code"]}">{a["ko"]}</button>' for a in AREAS)
    return head('캐치플로 — 검색',
        description=f'{CITY["ko"]} 호텔 전체를 실망 확률 순으로 비교하세요. '
                   f'도시 평균 실망 확률 {city_avg_pct}% 기준, 지역·가격대·위험 항목별 필터 제공.',
        canonical=f'{BASE}/search') + f'''
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <main id="container">
        <section id="title">
            <div class="back"><a href="./" class="btn-back"><img src="./img/back_b.svg" alt="뒤로가기"></a></div>
            <div class="search">
                <button type="button" id="btn-search"><img src="./img/search_g.svg" alt="검색"></button>
                <input type="text" id="q" placeholder="{CITY['ko']} 호텔명 검색 또는 구글맵 링크" autocomplete="off">
                <div class="ac-box" id="ac-box" hidden></div>
            </div>
        </section>
        <section id="search">
            <div class="rec-header" id="rec-header" style="display:none"></div>
            <div class="filters">
                <div class="f-row" id="f-city">
                    <span class="f-label">도시</span>
                    <button type="button" class="f-chip city-on" data-v="fukuoka">{CITY['ko']}</button>
                    <button type="button" class="f-chip disabled" title="준비 중">도쿄</button>
                    <button type="button" class="f-chip disabled" title="준비 중">오사카</button>
                    <button type="button" class="f-chip disabled" title="준비 중">교토</button>
                </div>
                <div class="f-row" id="f-area">
                    <span class="f-label">지역</span>
                    <button type="button" class="f-chip on" data-area="">전체</button>
                    {area_chips}
                </div>
                <div class="f-row" id="f-price">
                    <span class="f-label">가격</span>
                    <button type="button" class="f-chip on" data-v="">전체</button>
                    <button type="button" class="f-chip" data-v="b1">10만원 미만</button>
                    <button type="button" class="f-chip" data-v="b2">10~20만원</button>
                    <button type="button" class="f-chip" data-v="b3">20만원 이상</button>
                    <button type="button" class="f-more" id="open-catfilter">항목별 필터</button>
                </div>
            </div>
            <div class="map-wrap"><div id="map"></div>
                <div class="map-legend">
                    <span class="lg safe">양호</span><span class="lg warning">주의</span><span class="lg danger">위험</span><span class="lg none">수집중</span>
                </div>
            </div>
            <div class="map-hint" id="map-hint"></div>
            <div class="total" id="total"></div>
            <div class="notice" id="notice" style="display:none"></div>
            <div class="list-head" id="list-head" style="display:none">
                <div class="lh-count" id="lh-count"></div>
                <div class="lh-sort" id="lh-sort">
                    <button type="button" class="lh-sort-btn" id="lh-sort-btn">실망 확률 낮은 순</button>
                    <div class="lh-sort-box">
                        <button type="button" class="on" data-sort="p">실망 확률 낮은 순</button>
                        <button type="button" data-sort="price">1박 가격 낮은 순</button>
                        <button type="button" data-sort="rc">구글 리뷰 많은 순</button>
                        <button type="button" data-sort="g">구글 평점 높은 순</button>
                        <div class="lh-sort-sep">카테고리 안심순</div>
                        <button type="button" data-sort="cat:위생">위생 안심순</button>
                        <button type="button" data-sort="cat:냄새">냄새 안심순</button>
                        <button type="button" data-sort="cat:소음">소음 안심순</button>
                        <button type="button" data-sort="cat:시설">시설 안심순</button>
                        <button type="button" data-sort="cat:불친절">불친절 안심순</button>
                        <button type="button" data-sort="cat:위치·안전">위치·안전 안심순</button>
                    </div>
                </div>
            </div>
            <div class="list"><ul id="results"></ul></div>
        </section>
    </main>

    <div class="cf-modal" id="cf-catfilter">
        <div class="cf-modal-dim"></div>
        <div class="cf-modal-card">
            <div class="cft-tit">걱정되는 항목을 골라주세요</div>
            <div class="cft-txt">선택한 항목이 <b>&lsquo;위험&rsquo; 등급</b>인 호텔을 결과에서 빼드려요. (여러 개 선택 가능)</div>
            <div class="cft-grid" id="cft-grid"></div>
            <div class="cf-modal-btns">
                <button type="button" class="cf-btn cf-btn-ghost" data-act="reset">초기화</button>
                <button type="button" class="cf-btn cf-btn-primary" data-act="apply">적용하기</button>
            </div>
        </div>
    </div>

    <script src="./data/index.js?v={BUILD}"></script>
    <script defer src="./data/search_index.js?v={BUILD}"></script>
    <script src="./js/search-key.js?v={BUILD}"></script>
    <script src="./js/search-ac.js?v={BUILD}"></script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    (function(){{
        var CITY_KO = '{CITY['ko']}', CITY_AVG = {city_avg_pct};
        var OTHER = {kw};
        var CATS = {cats_js};
        var AREAS = window.CF_AREAS || [];
        var $q = $('#q'), $res = $('#results'), $total = $('#total'), $notice = $('#notice');
        var $lhead = $('#list-head'), $lcount = $('#lh-count'), $hint = $('#map-hint');
        var fPrice = '', fBand = '', fArea = '', fCats = [], sortBy = 'p', sortCat = '';
        var CAT_ICON = {{'위생':'','냄새':'','소음':'','시설':'','불친절':'','위치·안전':''}};
        var baseList = [];       // 검색+지역+가격+카테고리 필터 결과 (지도 뷰포트 제외)
        var syncMap = true;      // 지도 이동 시 리스트 연동 on/off

        function norm(s){{ return (s||'').toLowerCase().replace(/\\s+/g,''); }}
        function km(a1,o1,a2,o2){{ var R=6371,p1=a1*Math.PI/180,p2=a2*Math.PI/180,dp=(a2-a1)*Math.PI/180,dl=(o2-o1)*Math.PI/180;
            var x=Math.sin(dp/2)*Math.sin(dp/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2); return 2*R*Math.asin(Math.sqrt(x)); }}

        // ───── 지도 ─────
        var BAND_COLOR = {{safe:'#5EA5E7', warning:'#F0A028', danger:'#FA5252'}};
        var map = L.map('map', {{scrollWheelZoom:false}}).setView([33.5902,130.4017], 13);
        L.tileLayer('https://{{s}}.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}&hl=ko',
            {{maxZoom:19, subdomains:['mt0','mt1','mt2','mt3'], attribution:'&copy; Google'}}).addTo(map);
        map.on('click', function(){{ map.scrollWheelZoom.enable(); }});
        var markers = L.layerGroup().addTo(map);
        // 컨테이너 레이아웃 완료 후 크기 재계산 (초기 0폭 방지) + 리스트 재동기화
        // §6: 지역(fArea) 선택 진입 시엔 fitBounds(전체 뷰)로 되돌아가지 않고 지역 중심 줌 15 유지
        setTimeout(function(){{
            map.invalidateSize();
            if (recMode) return;              // rec 모드는 drawRecMap이 별도 처리
            if (!baseList.length) return;
            var a = fArea ? AREAS.filter(function(x){{ return x.code === fArea; }})[0] : null;
            if (a) {{ map.setView([a.lat, a.lng], 15, {{animate:false}}); drawMap(baseList, false); renderVisible(); }}
            else {{ drawMap(baseList, true); }}
        }}, 80);
        $(window).on('load', function(){{ map.invalidateSize(); }});

        function popupHtml(h){{
            var col = h.band ? BAND_COLOR[h.band] : '#9CA3AF';
            var chip = h.p != null ? '<span class="pop-p" style="background:'+col+'">실망 확률 '+h.p+'%</span>'
                                   : '<span class="pop-p" style="background:#9CA3AF">리뷰 수집중</span>';
            return '<div class="map-pop"><b>'+h.name+'</b>'
                + '<div class="pop-meta">★ '+(h.g?h.g.toFixed(1):'-')+' ('+h.rc.toLocaleString()+')'
                + (h.pt?' · 1박 '+h.pt:'')+'</div>'+chip
                + '<a class="pop-link" href="./hotels/'+h.id+'">캐치플로 분석 보기 →</a></div>';
        }}
        function drawMap(list, fit){{
            markers.clearLayers();
            var pts = [];
            list.forEach(function(h){{
                if (h.lat == null) return;
                var col = h.band ? BAND_COLOR[h.band] : '#9CA3AF';
                var mk = L.circleMarker([h.lat,h.lng], {{radius:8, color:'#fff', weight:2, fillColor:col, fillOpacity:0.95}});
                mk.bindPopup(popupHtml(h));
                markers.addLayer(mk);
                pts.push([h.lat,h.lng]);
            }});
            if (fit && pts.length) {{ syncMap = false; map.once('moveend', function(){{ syncMap = true; renderVisible(); }}); map.fitBounds(pts, {{padding:[28,28], maxZoom:15}}); }}
        }}

        // ───── 정렬 ─────
        var BAND_KO = {{safe:'양호', warning:'주의', danger:'위험'}};
        function sortList(arr){{
            var a = arr.slice();
            if (sortCat){{  // 카테고리 안심순 (해당 카테고리 위험도 낮은 순)
                a.sort(function(x,y){{
                    var sx = (x.cs && x.cs[sortCat] != null) ? x.cs[sortCat] : 999;
                    var sy = (y.cs && y.cs[sortCat] != null) ? y.cs[sortCat] : 999;
                    return sx - sy;
                }});
            }} else if (sortBy === 'price') a.sort(function(x,y){{ return (x.krw==null)-(y.krw==null) || (x.krw||0)-(y.krw||0); }});
            else if (sortBy === 'rc') a.sort(function(x,y){{ return (y.rc||0)-(x.rc||0); }});
            else if (sortBy === 'g') a.sort(function(x,y){{ return (y.g||0)-(x.g||0); }});
            else a.sort(function(x,y){{ return (x.p==null)-(y.p==null) || (x.p||0)-(y.p||0); }});  // 실망확률 낮은순(기본)
            return a;
        }}

        // ───── 리스트 렌더 ─────
        function bandChip(h){{
            if(!h.scored) return '<span class="badge-item badge-collect">리뷰 수집중</span>';
            return '<span class="badge-item badge-'+h.band+'">'+h.label+'</span>'
                 + '<span class="badge-item badge-down">실망 확률 '+h.p+'%</span>';
        }}
        function catChip(h){{  // 카테고리 정렬 시 해당 카테고리 등급을 카드에 표시
            if (!sortCat || !h.scored || !h.cb || h.cb[sortCat]==null) return '';
            var band = h.cb[sortCat];
            return '<div class="cat-row is-'+band+'"><span class="ci">'+(CAT_ICON[sortCat]||'')+'</span>'
                + '<span class="cn">'+sortCat+'</span>'
                + '<span class="cbadge">'+BAND_KO[band]+' · 위험도 '+h.cs[sortCat]+'</span></div>';
        }}
        function row(h){{
            var img = h.img ? (h.img.indexOf('http')===0 ? h.img : './'+h.img) : './img/placeholder.svg';
            var price = h.pt ? '<span class="price">1박 <b>'+h.pt+'</b></span>' : '';
            return '<li><div class="item">'
                + '<div class="thumb"><a href="./hotels/'+h.id+'"><img src="'+img+'" width="200" height="200" loading="lazy"></a></div>'
                + '<div class="cont">'
                + '<div class="info">'
                + '<div class="name"><a href="./hotels/'+h.id+'">'+h.name+'</a></div>'
                + '<div class="meta"><span>'+CITY_KO+', JP</span>'+(h.stars?'<span>'+h.stars+'</span>':'')+price+'</div></div>'
                + '<div class="bottom">'
                + '<div class="grade"><div class="ico"><img src="./img/star.svg"></div>'
                + '<div class="num">'+(h.g?h.g.toFixed(1):'-')+'</div><div class="txt">('+h.rc.toLocaleString()+')</div></div>'
                + '<div class="badge">'+bandChip(h)+'</div></div>'
                + catChip(h)
                + '</div></div></li>';
        }}
        function renderRows(list){{
            if (!list.length) {{ $res.html('<li class="sub-head">이 조건에 맞는 호텔이 없어요. 필터를 조정해 보세요.</li>'); return; }}
            $res.html(sortList(list).map(row).join(''));
        }}

        // 지도 뷰포트 안의 호텔만 리스트에 (C-3)
        function renderVisible(){{
            var b = map.getBounds();
            var vis = baseList.filter(function(h){{ return h.lat != null && b.contains([h.lat, h.lng]); }});
            $lcount.text('지도 영역 내 ' + vis.length + '곳');
            $lhead.toggle(baseList.length > 0);
            renderRows(vis);
            $hint.html(baseList.length ? '지도를 움직이면 <b>보이는 영역</b>의 호텔만 아래 목록에 나와요' : '');
        }}

        // ───── 필터 적용 ─────
        function passFilters(h){{
            if (fPrice && h.pb !== fPrice) return false;
            if (fBand && h.band !== fBand) return false;
            if (fArea){{
                var a = AREAS.filter(function(x){{ return x.code === fArea; }})[0];
                if (a){{ if (h.lat == null) return false; if (km(a.lat,a.lng,h.lat,h.lng) > a.r) return false; }}
            }}
            if (fCats.length){{
                for (var i=0;i<fCats.length;i++){{ if (h.cb && h.cb[fCats[i]] === 'danger') return false; }}
            }}
            return true;
        }}
        function filterLabel(){{
            var t = [];
            if (fArea){{ var a=AREAS.filter(function(x){{return x.code===fArea;}})[0]; if(a) t.push(a.ko); }}
            if (fPrice) t.push($('#f-price .f-chip[data-v="'+fPrice+'"]').text());
            if (fBand) t.push($('#f-band .f-chip[data-v="'+fBand+'"]').text());
            if (fCats.length) t.push(fCats.length + '개 항목 안심');
            return t.length ? ' · ' + t.join(' · ') : '';
        }}
        function unsupported(q){{
            $total.html(''); $lhead.hide(); $hint.html('');
            $notice.show().html(
                '<div class="notice-card">'
                + '<div class="notice-tit">아직 <b>'+CITY_KO+'</b>만 지원해요</div>'
                + '<div class="notice-txt">&ldquo;'+q+'&rdquo; 지역은 준비 중이에요.<br>'+CITY_KO+' 호텔은 전부 분석되어 있으니 먼저 둘러보세요!</div>'
                + '<a class="notice-btn" href="./search">'+CITY_KO+' 호텔 전체 보기</a></div>');
            $res.html('');
        }}

        function run(){{
            var q = $q.val().trim();
            $notice.hide();
            var pool = HOTELS.filter(passFilters);
            if (q){{
                var nq = norm(q);
                // 1) 별칭 인덱스(CF_IDX) 매칭 우선 — 이름 변형 검색을 목록에도 적용 (§7-d)
                var idSet = null;
                if (window.CFAutocomplete && window.CF_IDX) {{
                    var ids = window.CFAutocomplete.matchIds(q);
                    idSet = {{}}; ids.forEach(function(id){{ idSet[id] = 1; }});
                }}
                var matched = idSet
                    ? pool.filter(function(h){{ return idSet[h.id]; }})
                    : pool.filter(function(h){{ return norm(h.name).indexOf(nq)>=0 || norm(h.en).indexOf(nq)>=0; }});
                // 인덱스 매칭 실패 시 부분 문자열 폴백 (인덱스에 없는 신규명 대비)
                if (idSet && !matched.length) {{
                    matched = pool.filter(function(h){{ return norm(h.name).indexOf(nq)>=0 || norm(h.en).indexOf(nq)>=0; }});
                }}
                // 2) 매칭 0건일 때만 타도시 안내 발동 (§7-d)
                if (!matched.length) {{ unsupported(q); drawMap(HOTELS.filter(passFilters), true); return; }}
                pool = matched;
                $total.html('&ldquo;<span>'+q+'</span>&rdquo; 검색 결과 <span class="highlight">'+pool.length+'건</span>'+filterLabel());
            }} else {{
                $total.html(CITY_KO+' 호텔 <span class="highlight">'+pool.length+'곳</span>'+filterLabel()+' · 도시 평균 실망확률 '+CITY_AVG+'%');
            }}
            baseList = pool;
            // 지역이 선택돼 있으면 지역 중심으로 고정 줌 (fitBounds는 가장자리 호텔로 뷰가 넓어짐)
            var area = fArea ? AREAS.filter(function(x){{ return x.code === fArea; }})[0] : null;
            if (area) {{
                map.setView([area.lat, area.lng], 15, {{animate:false}});  // 애니메이션 setView는 프로그래밍 호출 시 무시됨
                drawMap(pool, false);
            }} else {{
                drawMap(pool, true);   // 전체일 때만 fitBounds
            }}
            renderVisible();
        }}

        // ───── 이벤트 ─────
        map.on('moveend', function(){{ if (syncMap && !recMode) renderVisible(); }});

        $('#f-area').on('click', '.f-chip', function(){{
            var $c = $(this); $('#f-area .f-chip').removeClass('on'); $c.addClass('on');
            fArea = $c.data('area') || ''; run();
        }});
        $('#f-price').on('click', '.f-chip', function(){{
            var $c = $(this); $('#f-price .f-chip').removeClass('on'); $c.addClass('on');
            fPrice = $c.data('v') || ''; run();
        }});
        $('#f-city').on('click', '.f-chip.disabled', function(){{
            alert('아직 '+CITY_KO+'만 지원해요. 다른 도시는 준비 중이에요!');
        }});

        // 정렬 드롭다운 (일반 + 카테고리 안심순)
        $('#lh-sort-btn').on('click', function(e){{ e.stopPropagation(); $('#lh-sort').toggleClass('open'); }});
        $('#lh-sort .lh-sort-box button').on('click', function(){{
            var v = String($(this).data('sort'));
            if (v.indexOf('cat:') === 0) {{ sortCat = v.slice(4); sortBy = 'p'; }}
            else {{ sortCat = ''; sortBy = v; }}
            $('#lh-sort .lh-sort-box button').removeClass('on'); $(this).addClass('on');
            $('#lh-sort-btn').text($(this).text());
            $('#lh-sort').removeClass('open');
            renderVisible();
        }});
        $(document).on('click', function(){{ $('#lh-sort').removeClass('open'); }});

        // 카테고리 위험 필터 시트
        var $cft = $('#cf-catfilter');
        $('#cft-grid').html(CATS.map(function(c){{
            var koDisp = (window.CAT_KO && window.CAT_KO[c.ko]) || c.ko;   // data-cat은 내부키(c.ko), 표시만 순화
            return '<button type="button" class="cft-chip" data-cat="'+c.ko+'"><span class="cft-ico">'+c.ico+'</span>'+koDisp+'</button>';
        }}).join(''));
        function openCatFilter(){{
            $('#cft-grid .cft-chip').each(function(){{ $(this).toggleClass('on', fCats.indexOf($(this).data('cat'))>=0); }});
            $cft.addClass('is-open'); $('body').css('overflow','hidden');
            CFNav.push(function(){{ $cft.removeClass('is-open'); $('body').css('overflow',''); }});
        }}
        $('#open-catfilter').on('click', openCatFilter);
        $cft.on('click', '.cft-chip', function(){{ $(this).toggleClass('on'); }});
        $cft.find('.cf-modal-dim').on('click', function(){{ CFNav.pop(); }});
        $cft.find('[data-act="reset"]').on('click', function(){{ $('#cft-grid .cft-chip').removeClass('on'); }});
        $cft.find('[data-act="apply"]').on('click', function(){{
            fCats = $('#cft-grid .cft-chip.on').map(function(){{ return $(this).data('cat'); }}).get();
            $('#open-catfilter').toggleClass('active', fCats.length>0).text(fCats.length ? '항목 '+fCats.length : '⚙ 항목별 필터');
            CFNav.pop(); run();
        }});

        $('#btn-search').on('click', run);
        $q.on('keyup', function(e){{ if(e.key==='Enter') run(); }});
        $q.on('input', function(){{ if(!$q.val().trim()) run(); }});

        // 공용 자동완성 (별칭 인덱스 드롭다운). 선택 시 상세로 이동, 미매칭 시 분석 요청행.
        if (window.CFAutocomplete) {{
            window.CFAutocomplete.attach($q.get(0), {{ hrefPrefix: './hotels/', areaHref: './search?area=' }});
        }}

        // ═════════ AI 맞춤 추천 (rec) 모드 ═════════
        var recMode = false;
        var RC = (window.CFRec && window.CFRec.byCode) || {{}};   // code → {{ko,label,chip}}
        function bayes(g, rc){{ return (g*rc + 4.0*100) / (rc + 100); }}   // 베이지안 평점(사전 4.0, 100건)
        function norm35_46(x){{ return Math.max(0, Math.min(100, (x - 3.5) / (4.6 - 3.5) * 100)); }}
        function matchScore(h, pr){{
            var w = pr.length===1 ? [1.0] : pr.length===2 ? [0.6,0.4] : [0.5,0.3,0.2];
            var prio = 0;
            for (var i=0;i<pr.length;i++){{
                var ko = (RC[pr[i]]||{{}}).ko;
                var risk = (h.cs && ko && h.cs[ko]!=null) ? h.cs[ko] : 50;
                prio += (100 - risk) * w[i];
            }}
            var safe = 100 - Math.min(h.p==null?20:h.p, 40) / 40 * 100;
            var trust = norm35_46(bayes(h.g||3.8, h.rc||0));
            return prio*0.60 + safe*0.25 + trust*0.15;
        }}
        function recWord(c){{ var s=(RC[c]||{{}}).chip||''; var a=s.split(' '); return a.length>1 ? a.slice(1).join(' ') : s; }}
        function recReason(h, pr){{
            var parts = [];
            var first = RC[pr[0]], w = recWord(pr[0]);
            if (first && h.cb && h.cb[first.ko] === 'safe'){{
                parts.push('선택하신 <b>'+w+'</b> 걱정이 적은 곳이에요');
            }} else if (first){{
                parts.push('<b>'+w+'</b> 조건을 고려해 골랐어요');
            }}
            if (h.p != null && h.p <= CITY_AVG) parts.push('실망 확률 '+h.p+'%');
            if (h.pt) parts.push('1박 '+h.pt);
            return parts.join(' · ');
        }}
        function recRow(h, rank, pr){{
            var img = h.img ? (h.img.indexOf('http')===0 ? h.img : './'+h.img) : './img/placeholder.svg';
            var medal = rank<=3 ? '<span class="rec-medal">'+rank+'</span>' : '<span class="rec-num">'+rank+'</span>';
            var price = h.pt ? '<span class="price">1박 <b>'+h.pt+'</b></span>' : '';
            return '<li><div class="item">'
                + '<div class="thumb"><a href="./hotels/'+h.id+'"><img src="'+img+'" width="200" height="200" loading="lazy"></a></div>'
                + '<div class="cont">'
                + '<div class="rec-rankline">'+medal+'<div class="name" style="margin:0"><a href="./hotels/'+h.id+'">'+h.name+'</a></div></div>'
                + '<div class="meta"><span>'+CITY_KO+', JP</span>'+(h.stars?'<span>'+h.stars+'</span>':'')+price+'</div>'
                + '<div class="bottom"><div class="grade"><div class="ico"><img src="./img/star.svg"></div>'
                + '<div class="num">'+(h.g?h.g.toFixed(1):'-')+'</div><div class="txt">('+h.rc.toLocaleString()+')</div></div>'
                + '<div class="badge">'+bandChip(h)+'</div></div>'
                + '<div class="rec-reason">'+recReason(h, pr)+'</div>'
                + '</div></div></li>';
        }}
        function drawRecMap(top){{
            markers.clearLayers();
            var pts = [];
            top.forEach(function(h, i){{
                if (h.lat == null) return;
                var rank = i+1, big = rank<=3;
                var icon = L.divIcon({{className:'', html:'<div class="rec-marker '+(big?'big':'small')+'">'+rank+'</div>',
                    iconSize:[big?32:26, big?32:26], iconAnchor:[big?16:13, big?16:13]}});
                var mk = L.marker([h.lat,h.lng], {{icon:icon, zIndexOffset: (11-rank)*10}});
                mk.bindPopup('<div class="map-pop"><b>'+rank+'위'+' '+h.name+'</b>'
                    + '<div class="pop-meta">★ '+(h.g?h.g.toFixed(1):'-')+' ('+h.rc.toLocaleString()+')'+(h.pt?' · 1박 '+h.pt:'')+'</div>'
                    + '<a class="pop-link" href="./hotels/'+h.id+'">캐치플로 분석 보기 →</a></div>');
                markers.addLayer(mk); pts.push([h.lat,h.lng]);
            }});
            var a = recArea ? AREAS.filter(function(x){{return x.code===recArea;}})[0] : null;
            if (a) map.setView([a.lat,a.lng], 15, {{animate:false}});
            else if (pts.length) map.fitBounds(pts, {{padding:[30,30], maxZoom:15}});
        }}
        var recPr = [], recBud = '', recArea = '';
        function recCandidates(){{
            return HOTELS.filter(function(h){{
                if (!h.scored) return false;
                if (recBud && h.pb !== recBud) return false;
                if (recArea){{ var a=AREAS.filter(function(x){{return x.code===recArea;}})[0];
                    if (a){{ if (h.lat==null) return false; if (km(a.lat,a.lng,h.lat,h.lng) > a.r) return false; }} }}
                return true;
            }});
        }}
        function renderRecHeader(){{
            var chips = recPr.map(function(c, i){{ return '<span class="rh-chip"><span class="rh-rank">'+(i+1)+'</span>'+((RC[c]||{{}}).chip||'')+'</span>'; }});
            if (recBud){{ var b=(window.CFRec.BUDGETS||[]).filter(function(x){{return x.code===recBud;}})[0]; if(b) chips.push('<span class="rh-chip">'+b.label+'</span>'); }}
            if (recArea){{ var a=AREAS.filter(function(x){{return x.code===recArea;}})[0]; if(a) chips.push('<span class="rh-chip">'+a.ko+'</span>'); }}
            return '<div class="rh-tit">내 조건 맞춤 추천</div>'
                + '<div class="rh-sub" id="rh-sub"></div>'
                + '<div class="rh-chips">'+chips.join('')+'</div>'
                + '<a href="javascript:;" class="rh-reset rec-reset">조건 다시 설정 ↻</a>';
        }}
        function initRec(){{
            recMode = true;
            recPr = (sp.get('pr')||'').split(',').filter(function(c){{ return RC[c]; }});
            recBud = sp.get('bud')||''; recArea = sp.get('area')||'';
            window.CF_REC_PRESET = {{pr:recPr, bud:recBud, area:recArea}};
            $('.filters, #list-head, #map-hint, #total').hide();
            $('#rec-header').html(renderRecHeader()).show();
            var cands = recCandidates();
            cands.sort(function(a,b){{ var d=matchScore(b,recPr)-matchScore(a,recPr); if(d) return d;
                return (a.p==null)-(b.p==null) || (a.p||0)-(b.p||0) || (b.rc||0)-(a.rc||0); }});
            var top = cands.slice(0, 10);
            $('#rh-sub').text('선택하신 조건으로 '+cands.length+'곳 중에서 골랐어요');
            if (cands.length < 3){{
                var relax = '';
                if (recBud) relax += '<a class="notice-btn" href="'+recUrl({{bud:''}})+'">예산 넓혀 다시 보기</a> ';
                if (recArea) relax += '<a class="notice-btn" href="'+recUrl({{area:''}})+'">지역 넓혀 다시 보기</a>';
                $('#results').html('<div class="notice-card" style="margin:16px 0">'
                    + '<div class="notice-tit">조건에 딱 맞는 곳이 '+cands.length+'곳뿐이에요</div>'
                    + '<div class="notice-txt">예산이나 지역을 넓히면 더 보여드릴 수 있어요</div>'
                    + '<div style="margin-top:14px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">'+relax+'</div></div>');
            }} else {{
                $('#results').html(top.map(function(h,i){{ return recRow(h, i+1, recPr); }}).join(''));
            }}
            setTimeout(function(){{ map.invalidateSize(); drawRecMap(top); }}, 80);
        }}
        function recUrl(over){{
            var pr = over.pr!==undefined ? over.pr : recPr.join(',');
            var bud = over.bud!==undefined ? over.bud : recBud;
            var area = over.area!==undefined ? over.area : recArea;
            var qs = 'rec=1&pr='+pr; if(bud) qs+='&bud='+bud; if(area) qs+='&area='+area;
            return './search?'+qs;
        }}

        // URL 파라미터: ?rec= / ?area= / ?q=
        var sp = new URLSearchParams(location.search);
        if (sp.get('rec')){{ initRec(); }}
        else {{
            var initArea = sp.get('area'), initQ = sp.get('q');
            if (initArea){{ fArea = initArea; $('#f-area .f-chip').removeClass('on'); $('#f-area .f-chip[data-area="'+initArea+'"]').addClass('on'); }}
            if (initQ){{ $q.val(initQ); }}
            run();
        }}
    }})();
    </script>''' + build_footer(0) + FOOT

# ───────────────────────── detail ─────────────────────────
def gauge_html(rank_pct, avg_rank_pct, city_crit, tone='safe'):
    """F37: 백분위(상대순위) 축 게이지 — 마커 위치 = crit_rank_pct(좌 0=우수, 우 100=최악).
    평균 마커 = city_crit이 실제로 위치하는 백분위(실계산, 50 고정 아님). 말풍선은 마커와 동일 좌표(축 일치)."""
    pos = min(max(float(rank_pct if rank_pct is not None else 50), 0.0), 100.0)
    avg_pos = min(max(float(avg_rank_pct if avg_rank_pct is not None else 50), 8.0), 92.0)  # 끝 라벨(우수/위험)과 겹침 방지 클램프
    rank_html = ''
    if rank_pct:
        txt = (f'{CITY["ko"]} 상위 {rank_pct}%' if rank_pct <= 50 else f'{CITY["ko"]} 하위 {100 - rank_pct}%')
        clamp = ' is-clamp-l' if pos <= 18 else (' is-clamp-r' if pos >= 82 else '')
        rank_html = f'<span class="g-rank is-{tone}{clamp}" style="left:{pos:.1f}%">{E(txt)}</span>'
    return f'''<div class="gauge">
        <div class="bar">
            {rank_html}
            <div class="pointer" style="left:calc({pos:.1f}% - 5px)"><div class="arrow"></div><span class="dot"></span></div>
        </div>
        <div class="label">
            <span>우수</span>
            <span class="analysis" style="left:{avg_pos:.1f}%">평균 {pct(city_crit)}%</span>
            <span>위험</span>
        </div>
    </div>'''

def city_crit_rank_pct(H, city_crit):
    """F37-b: 도시 평균 실망확률(city_crit)이 scored 호텔 p_crit 분포에서 차지하는 백분위(실계산)."""
    vals = [h['p_crit'] for h in H.values() if h['scored']]
    if not vals: return 50.0
    return 100.0 * sum(1 for v in vals if v < city_crit) / len(vals)

def ratio_from_score(score):
    return score / 50.0 if score <= 50 else 1.0 + (score - 50.0) / 25.0

def insight_card(h):
    """원본 .disappear .result 카드 — 최악 카테고리 인사이트 + 태그"""
    worst = sorted(CATS, key=lambda c: -h['cats'][c]['score'])
    top = [c for c in worst if h['cats'][c]['score'] >= 60][:2]
    if top:
        names = '·'.join(t.split(' ')[0] for t in top)
        ratio = ratio_from_score(h['cats'][top[0]]['score'])
        subs = []
        for c in top:
            subs += sorted(h['cats'][c]['subs'].items(), key=lambda kv: -kv[1]['score'])
        tags = ''.join(f'<div class="tags-item">#{E(s)}</div>' for s, d in subs[:4] if d['count'] >= 3)
        return f'''<div class="result">
            <div class="text">이 호텔은 <span>{E(names)}</span> 관련 불만이 <br>{CITY['ko']} 평균보다 <span>{ratio:.1f}배</span> 많아요!</div>
            <div class="tags">{tags}</div>
        </div>'''
    best_subs = sorted(((s, d) for c in CATS for s, d in h['cats'][c]['subs'].items()),
                       key=lambda kv: kv[1]['score'])[:4]
    tags = ''.join(f'<div class="tags-item">#{E(s)} 양호</div>' for s, _ in best_subs)
    return f'''<div class="result">
        <div class="text">모든 카테고리가 <span>{CITY['ko']} 평균 수준 이하</span>로 <br>관리되고 있는 호텔이에요</div>
        <div class="tags">{tags}</div>
    </div>'''

LANG_KO = {'ko': '한국어', 'ja': '일본어', 'en': '영어'}
def lang_label(lang):
    """리뷰 언어 라벨 (§5-a). zh* → 중국어, 그외 → 대문자코드, null → None(표기 생략)."""
    if not lang: return None
    l = str(lang).lower()
    if l in LANG_KO: return LANG_KO[l]
    if l.startswith('zh'): return '중국어'
    return str(lang).upper()

def quote_cards(qlist, limit=6):
    out = []
    for q in qlist[:limit]:
        star = ''
        if q.get('stars'):
            star = f'<div class="star"><i style="width:{int(q["stars"]) * 20}%"></i></div>'
        origin = E(q.get('review_origin') or 'Google')
        gband = 'danger' if q['grade'] == '심각' else 'warning'
        lang = (q.get('lang') or '').lower()
        llabel = lang_label(lang)
        lang_chip = f'<span class="q-lang">{E(llabel)}</span>' if llabel else ''
        out.append(f'''<li class="swiper-slide"><div class="item">
            <div class="item-top">
                <div class="name">{E(mask_name(q.get('reviewer_name')))}</div>
                <div class="status"><div class="status-item {gband}">{E(q['grade'])}</div></div>
            </div>
            <div class="item-info">{star}<div class="web">{origin}</div>{lang_chip}</div>
            <div class="item-bottom">
                <div class="text">{emph(q.get('quote') or q.get('summary'))}</div>
                <div class="date">{E((q.get('pub') or '')[:10].replace('-', '. '))} · {E(q.get('scat') or '')}</div>
            </div>
        </div></li>''')
    return '\n'.join(out)

def haversine_km(a1, o1, a2, o2):
    import math
    R = 6371.0
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, do = math.radians(a2 - a1), math.radians(o2 - o1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(do / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

def similar_hotels(pid, hotels_meta, H, k=8):
    """추천: 같은 가격대 우선 + 가까울수록 + 실망 확률 낮을수록"""
    me = hotels_meta.get(pid, {})
    my_band = me.get('band')
    cands = []
    for p, m in hotels_meta.items():
        if p == pid or p not in H or not H[p]['scored']: continue
        rank = H[p]['p_crit'] * 100.0                       # 실망 확률(%p 단위)
        if my_band and m.get('band') and m['band'][0] != my_band[0]:
            rank += 8.0                                     # 다른 가격대 페널티
        if me.get('latitude') and m.get('latitude'):
            d = haversine_km(float(me['latitude']), float(me['longitude']),
                             float(m['latitude']), float(m['longitude']))
            rank += min(d, 5.0) * 1.5                       # 5km까지 거리 페널티
        cands.append((rank, p))
    return [p for _, p in sorted(cands)[:k]]

def kr_rank_map(kr_stats):
    """kr_n≥10인 호텔들의 kr_ratio('all') 백분위 순위 계산 (§2-a). {pid: pct_top} 반환.
       pct_top = round(100 * (해당보다 kr_ratio 큰 호텔 수 + 1) / 대상수) — 작을수록 상위."""
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    pool = []
    for (pid, period), r in kr_stats.items():
        if period != 'all': continue
        if int(num(r.get('kr_n')) or 0) < 10: continue
        pool.append((pid, num(r.get('kr_ratio')) or 0.0))
    n = len(pool)
    rank = {}
    for pid, ratio in pool:
        bigger = sum(1 for _, o in pool if o > ratio)
        rank[pid] = max(1, round(100 * (bigger + 1) / n)) if n else None
    return rank


def kr_ratio_dist(kr_stats):
    """kr_n≥10 호텔들의 kr_ratio('all') 오름차순 리스트 — 분포 막대 차트(§2-a)용."""
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    vals = [num(r.get('kr_ratio')) or 0.0
            for (pid, period), r in kr_stats.items()
            if period == 'all' and int(num(r.get('kr_n')) or 0) >= 10]
    return sorted(vals)


def _complete_months(asof, k=12):
    """asof 기준 완전월 k개 → [(ym 'YYYY-MM', '<N>월'), ...] 오름차순 (오래된→최신).
    asof 일자 < 28이면 asof월은 부분월로 보고 제외하고 그 앞 k개월을 사용 (CAT-TREND C-4)."""
    try:
        y, m, d = (int(x) for x in str(asof).split('-')[:3])
    except (ValueError, IndexError):
        return []
    end_y, end_m = y, m
    if d < 28:                      # asof월은 부분월 → 제외, 직전월을 마지막 완전월로
        end_m -= 1
        if end_m <= 0:
            end_m += 12; end_y -= 1
    out = []
    for off in range(k - 1, -1, -1):
        yy, mm = end_y, end_m - off
        while mm <= 0:
            mm += 12; yy -= 1
        out.append((f'{yy:04d}-{mm:02d}', f'{mm}월'))
    return out


def overall_trend_html(pid, monthly, monthly_cat, asof, city_avg=None):
    """전체 통합 월별 위험 리뷰 흐름 (누적 스택 트렌드). 카테고리 차트와 동일 형태·데이터 가공.
    .sect.disappear 안 게이지 아래·인사이트 카드 위에 배치. 데이터 부족 시(합<10) 미노출.
    반환: (html, trendc_all_or_None). trendc_all은 window.TRENDC['all'] 주입용."""
    cmonths = _complete_months(asof, 12) if (monthly and asof) else []
    if not cmonths:
        return '', None
    mdata = (monthly or {}).get(pid) or {}
    pw, pc, pa = [], [], []      # 주의%, 심각%, 도시평균% (완전월 12개)
    sum_flag = 0
    for ym, _lbl in cmonths:
        n, nc, nw = mdata.get(ym, (0, 0, 0))
        pw.append(round(nw / n * 100, 1) if n else 0.0)
        pc.append(round(nc / n * 100, 1) if n else 0.0)
        pa.append((city_avg or {}).get(ym, 0.0))
        sum_flag += nc + nw
    if sum_flag < 10:                        # 가드(R-6): 저표본 차트 생략
        return '', None
    labels = [lbl for _ym, lbl in cmonths]
    trendc_all = {'m': labels, 'w': pw, 'c': pc, 'a': pa}
    tot = round(pw[-1] + pc[-1], 1)          # 합계 = 주의+심각 (배타이므로 합집합 비율)
    now_txt = f'{labels[-1]} {tot}% · 평균 {pa[-1]}%'
    dt = round((pw[-1] + pc[-1]) - (pw[-2] + pc[-2]), 1)
    if abs(dt) < 0.05:
        delta_txt = '지난 달과 비슷한 수준이에요'
    else:
        delta_txt = f'지난 달 대비 {dt:+.1f}p {"증가했어요" if dt > 0 else "줄었어요"}'
    # 기본 접힘(F7): 토글 버튼만 노출, 탭 시 차트 펼침(Chart.js는 펼칠 때 지연 초기화 — 0폭 canvas 함정 회피)
    html = (f'<div class="trend-fold">'
        f'<button type="button" class="trend-fold-btn"><span class="tf-tit">월별 위험 흐름 보기</span><span class="tf-arrow"></span></button>'
        f'<div class="trend-fold-body">'
        f'<div class="cat-trend cat-trend-all">'
        f'<div class="ct-head"><span class="ct-tit">월별 위험 리뷰 흐름</span>'
        f'<span class="ct-now">{E(now_txt)}</span></div>'
        f'<div class="ct-canvas"><canvas id="cat-trend-all"></canvas></div>'
        f'<div class="ct-delta">{E(delta_txt)}</div></div>'
        f'</div></div>')
    return html, trendc_all


def kr_pyramid(top_pct):
    """한국인 비중 순위 피라미드 — 전체 삼각형은 회색 외곽선(라운드 조인), 이 호텔 위치는 보라 선으로.
       위치 높이 = apex(상위)로부터 순위 백분위(상위=위쪽, 하위=아래쪽). 채우지 않음."""
    n = max(1.0, min(float(top_pct), 99.0))
    t = n / 100.0                                  # apex로부터 높이비율 = 순위 백분위
    ay, by, cx, bh = 12.0, 108.0, 80.0, 62.0       # apex y, base y, center x, base half-width
    cy = ay + (by - ay) * t                        # 위치선 y
    hw = bh * t
    lx, rx = cx - hw, cx + hw
    return (
        '<svg class="kp-svg" viewBox="0 0 160 120" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="한국인 비중 순위 피라미드">'
        f'<polygon points="{cx},{ay} 146,{by} 14,{by}" '
        'style="fill:none;stroke:#D3D7DE;stroke-width:2.5;stroke-linejoin:round"/>'
        f'<line x1="{lx - 2:.1f}" y1="{cy:.1f}" x2="{rx + 2:.1f}" y2="{cy:.1f}" '
        'style="stroke:var(--primary);stroke-width:2.5;stroke-linecap:round"/>'
        f'<circle cx="{cx}" cy="{cy:.1f}" r="3.5" style="fill:var(--primary)"/>'
        '</svg>')

def kr_dist_bars(this_ratio, dist):
    """한국인 비중 분포 막대 차트 — 전체 호텔의 kr_ratio를 오름차순 정렬해 N개 막대로 샘플하고
       이 호텔 위치 막대만 강조색(--primary)으로. 캡처(지니계수 분포)와 같은 톤, 사이트 토큰 사용."""
    import bisect
    if not dist:
        return ''
    N = 20
    n = len(dist)
    mx = max(dist) or 1.0
    pos = bisect.bisect_left(dist, this_ratio) / max(n - 1, 1)   # 분포 내 위치 0~1
    hl = min(N - 1, max(0, round(pos * (N - 1))))
    bars = []
    for i in range(N):
        src = round(i / (N - 1) * (n - 1))
        v = this_ratio if i == hl else dist[src]
        h = max(v / mx, 0.08) * 100                              # 막대 높이(%), 0값도 최소 8%
        if i == hl:
            lab = f'<span class="kd-val">{round(this_ratio * 100)}%</span>'
            bars.append(f'<div class="kd-bar is-hl" style="height:{h:.0f}%">{lab}</div>')
        else:
            bars.append(f'<div class="kd-bar" style="height:{h:.0f}%"></div>')
    return (f'<div class="kd-chart" role="img" '
            f'aria-label="후쿠오카 호텔 한국인 비중 분포에서 이 호텔 위치">{"".join(bars)}</div>')


def korean_card(kr, city, kr_rank_pct=None, kr_1y=None, kr_dist=None):
    """한국인 리뷰 현황 카드 (LLM-ANALYSIS §7.3 + DETAIL-UI-REVAMP §2). 표본 10건 미만이면 미노출."""
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    if not kr or int(num(kr.get('kr_n')) or 0) < 10:
        return ''
    kr_n, all_n = int(num(kr['kr_n'])), int(num(kr['all_n']))
    ratio = round((num(kr.get('kr_ratio')) or 0) * 100)
    kr_st, all_st = num(kr.get('kr_stars')), num(kr.get('all_stars'))
    # §2-a 신규 지표: 심각·주의 리뷰 비율(kr_risk/all_risk). 구 kr_stats.json엔 부재 → None 가드.
    kr_rk_raw = num(kr.get('kr_risk'))
    all_rk_raw = num(kr.get('all_risk'))
    has_risk = kr_rk_raw is not None and all_rk_raw is not None
    kr_rk_pct = (kr_rk_raw * 100) if kr_rk_raw is not None else None
    all_rk_pct = (all_rk_raw * 100) if all_rk_raw is not None else None
    small = kr_n < 30

    # 임계 (§2-c): 별점차 ±0.15, 위험비율차 ±1.5%p
    d_st = (kr_st - all_st) if (kr_st and all_st) else None
    # 인사이트 d_dp = 심각·주의 비율차(%p). risk 부재 시 실망확률(심각-only)로 폴백해 카드가 깨지지 않게.
    if has_risk:
        d_dp = kr_rk_pct - all_rk_pct
    else:
        d_dp = ((num(kr.get('kr_disappoint')) or 0) - (num(kr.get('all_disappoint')) or 0)) * 100
    ST_TH, DP_TH = 0.15, 1.5
    # §2-c 인사이트 4케이스 (별점+위험비율 조합), 별점 없으면 위험비율축만 2케이스
    if d_st is not None:
        if d_st >= ST_TH and d_dp <= -DP_TH:
            insight = '한국 리뷰어가 다른 나라 리뷰어보다 <b>만족</b>스러워 했어요'
        elif d_st >= ST_TH and d_dp >= DP_TH:
            insight = '별점은 후하지만, <b>심각·주의 언급은 더 많았어요</b>'
        elif d_st <= -ST_TH and d_dp <= -DP_TH:
            insight = '별점은 박한 편이지만, <b>심각·주의 언급은 적었어요</b>'
        elif d_st <= -ST_TH and d_dp >= DP_TH:
            insight = '한국 리뷰어의 만족도가 다른 나라 리뷰어보다 <b>낮았어요</b>'
        else:
            insight = '한국인과 전체 리뷰어의 평가가 비슷한 호텔이에요'
    else:
        if d_dp <= -DP_TH:
            insight = '한국 리뷰어의 심각·주의 언급이 다른 나라보다 <b>적었어요</b>'
        elif d_dp >= DP_TH:
            insight = '한국 리뷰어의 심각·주의 언급이 다른 나라보다 <b>많았어요</b>'
        else:
            insight = '한국인과 전체 리뷰어의 평가가 비슷한 호텔이에요'

    # §2-d 심각 언급 문장 — 최근 1y 표본(≥10건) 있을 때만 노출.
    # 전기간 폴백은 kr-rows의 실망 확률과 동어반복(중복 표기)이라 제거.
    def num1(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    serious_block = ''
    if kr_1y and int(num1(kr_1y.get('kr_n')) or 0) >= 10:
        n_serious = round((num1(kr_1y.get('kr_disappoint')) or 0) * 100)
        if n_serious == 0:
            serious_txt = '최근 1년 한국인 리뷰에선 심각한 문제 언급이 없었어요'
        else:
            serious_txt = f'최근 1년 기준, 한국인 리뷰의 <b>{n_serious}%</b>가 심각한 문제를 언급했어요'   # F25: "100명 중 N명" 비유 제거(사이트 전역)
        serious_block = f'<div class="kr-serious">{serious_txt}</div>'

    # §2-b 비교 — 지표당 세로 막대 2개(한국인 primary vs 전체 회색), 값은 막대 위(목업①② 스타일).
    def vcol(role, frac, val_txt, is_ko):
        vcls = ' kv-val-ko' if is_ko else ''
        fcls = ' kv-fill-ko' if is_ko else ''
        h = max(min(frac, 1.0), 0.04) * 100        # 막대 높이(%), 0값도 최소 4% 보이게
        return (f'<div class="kv-col"><div class="kv-val{vcls}">{val_txt}</div>'
                f'<div class="kv-track"><span class="kv-fill{fcls}" style="height:{h:.0f}%"></span></div>'
                f'<div class="kv-lab">{role}</div></div>')
    def vgroup(tit, ko_frac, all_frac, ko_txt, all_txt):
        return (f'<div class="kv-group"><div class="kv-tit">{tit}</div>'
                f'<div class="kv-bars">{vcol("한국인", ko_frac, ko_txt, True)}'
                f'{vcol("전체", all_frac, all_txt, False)}</div></div>')
    vbars = ''
    if kr_st and all_st:
        vbars += vgroup('구글 평균 별점', kr_st / 5, all_st / 5, f'{kr_st:.1f}', f'{all_st:.1f}')
    footnote = ''
    if has_risk:
        # 스케일: 둘 다 작아도 막대가 보이게 max(kr,all,10%)로 정규화(상한 100%).
        norm = max(kr_rk_pct, all_rk_pct, 10.0)
        vbars += vgroup('심각·주의 리뷰 비율', kr_rk_pct / norm, all_rk_pct / norm,
                        f'{round(kr_rk_pct)}%', f'{round(all_rk_pct)}%')
        footnote = ('<div class="kr-foot">비율 = 심각·주의 언급 리뷰 ÷ 전체 리뷰'
                    '(별점만 남긴 리뷰 포함)</div>')

    # §2-a 한국인 비중 순위 — 분포 막대 차트(전체 호텔 중 이 호텔 위치 강조) + 평이한 부연설명.
    # 50% 초과는 '하위 M%'로 뒤집어 직관화. 부연: 상위 33% 이내=많은 편 / 하위 33%=적은 편 / 그 외=보통.
    dist_block = ''
    if kr_rank_pct:
        rank_txt = f'상위 {kr_rank_pct}%' if kr_rank_pct <= 50 else f'하위 {100 - kr_rank_pct}%'
        if kr_rank_pct <= 33:
            level = '<b>많은 편</b>이에요'
        elif kr_rank_pct >= 67:
            level = '<b>적은 편</b>이에요'
        else:
            level = '<b>보통</b> 수준이에요'
        sub = f'{CITY["ko"]} 호텔 중 한국인 투숙객이 {level}'
        this_ratio = num(kr.get('kr_ratio')) or 0.0
        chart = kr_dist_bars(this_ratio, kr_dist) if kr_dist else kr_pyramid(kr_rank_pct)
        dist_block = (f'<div class="kr-dist">{chart}'
                      f'<div class="kp-cap">한국인 비중 <b>{CITY["ko"]} {rank_txt}</b></div>'
                      f'<div class="kp-sub">{sub}</div></div>')

    count_txt = f'<b>{kr_n:,}</b>건 · 전체 {ratio}%{" · 참고용" if small else ""}'
    return f'''
        <div class="sect kr-card">
            <div class="head kr-head">
                <div class="title">한국인 리뷰 현황</div>
                <div class="kr-count">{count_txt}</div>
            </div>
            {dist_block}
            <div class="kr-vbars">{vbars}</div>
            {footnote}
            <div class="kr-insight">{insight}</div>
            {serious_block}
        </div>'''


def gallery_html(meta, name, fallback):
    """상세 히어로: 사진 2장+면 Swiper 갤러리(점 표시·스와이프), 아니면 단일 이미지."""
    imgs = meta.get('r2_imgs') or []
    if len(imgs) < 2:
        return f'<div class="visual"><img src="{E(imgs[0] if imgs else fallback)}" alt="{E(name)}" width="800" height="600"></div>'
    # 히어로 갤러리: 첫 장 즉시(LCP), 나머지는 lazy 대신 그냥 로드(Swiper 오프스크린+native lazy 충돌 회피)
    slides = ''.join(
        f'<div class="swiper-slide"><img src="{E(u)}" alt="{E(name)}" width="800" height="600"'
        + (' fetchpriority="high"' if i == 0 else ' decoding="async"') + '></div>'
        for i, u in enumerate(imgs))
    return (f'<div class="visual"><div class="swiper hotel-gallery">'
            f'<div class="swiper-wrapper">{slides}</div>'
            f'<div class="swiper-pagination"></div>'
            f'<div class="gallery-count">1 / {len(imgs)}</div>'
            f'</div></div>')


def crit_rank_map(H):
    """scored 호텔의 p_crit 오름차순 백분위. {pid: pct_top} — 작을수록 실망확률이 낮은(안전한) 상위."""
    scored = [(h['p_crit'], pid) for pid, h in H.items() if h['scored']]
    n = len(scored)
    if not n: return {}
    return {pid: round(100 * (sum(1 for v, _ in scored if v < p) + 1) / n) for p, pid in scored}

def _jsonld(obj):
    """JSON-LD script 태그. </script> 조기 종료 방지를 위해 </ 이스케이프."""
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')
            + '</script>')

def jsonld_detail(pid, meta):
    url = f'{BASE}/hotels/{pid}'
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    hotel = {
        '@context': 'https://schema.org', '@type': 'Hotel',
        'name': meta['title'], 'url': url,
        'address': {'@type': 'PostalAddress',
                    'streetAddress': meta.get('address') or '',
                    'addressLocality': 'Fukuoka', 'addressCountry': 'JP'},
    }
    img = meta.get('r2_img') or (f'{BASE}/img/hotels/{pid}.jpg' if meta.get('local_img') else None)
    if img: hotel['image'] = img
    lat, lng = num(meta.get('latitude')), num(meta.get('longitude'))
    if lat and lng:
        hotel['geo'] = {'@type': 'GeoCoordinates', 'latitude': lat, 'longitude': lng}
    if meta.get('price_txt'):
        hotel['priceRange'] = meta['price_txt']
    m = re.match(r'(\d)성급', meta.get('hotel_stars') or '')
    if m:
        hotel['starRating'] = {'@type': 'Rating', 'ratingValue': int(m.group(1))}
    g, rc = num(meta.get('total_score')), meta.get('reviews_count') or 0
    if g and rc > 0:   # 구글 정책: 페이지에 실제 노출되는 평점만. 없으면 통째로 생략(허위 별점 금지)
        hotel['aggregateRating'] = {'@type': 'AggregateRating', 'ratingValue': g,
                                    'reviewCount': int(rc), 'bestRating': 5, 'worstRating': 1}
    crumbs = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': '캐치플로', 'item': f'{BASE}/'},
            {'@type': 'ListItem', 'position': 2, 'name': f'{CITY["ko"]} 호텔', 'item': f'{BASE}/search'},
            {'@type': 'ListItem', 'position': 3, 'name': meta['title'], 'item': url},
        ],
    }
    return _jsonld(hotel) + '\n' + _jsonld(crumbs)

# ── B층 FAQ 섹션 (TAXONOMY-V4 §3-d). faq = [{t,g,q,a,c:[chips],e:[{q,d,st,o}],n}] 또는 None ──
FAQ_GROUP_ORDER = ['가족·인원', '시설·어메니티', '서비스·정책', '위치']

def _faq_date(d):
    """근거 날짜 YY.MM.DD (예 26.02.19)."""
    d = str(d or '')[:10]
    return d[2:].replace('-', '.') if len(d) == 10 else d.replace('-', '.')

# F23: 토픽별 ko 키워드 — **정본은 pipeline/faq_topics.py TOPICS** (pipeline/은 gitignored라 프론트 빌드용 복제.
# faq_topics 변경 시 여기도 동기화). 인용 하이라이트 전용 — 원문 글자는 변형하지 않고 <b>로 감싸기만 한다.
FAQ_KO_KW = {
    'family': ['아이', '아기', '유아', '애기', '가족', '키즈'],
    'beds': ['엑스트라베드', '침대 추가', '트윈', '더블', '소파베드', '침대'],
    'bath': ['대욕장', '온천', '사우나', '스파', '목욕탕'],
    'breakfast': ['조식', '아침식사', '뷔페'],
    'kitchen': ['냉장고', '전자레인지', '주방', '세탁', '런드리', '인덕션'],
    'luggage': ['짐 보관', '짐을 맡', '캐리어 보관', '수하물', '짐 맡', '짐'],
    'checkout': ['레이트 체크아웃', '얼리 체크인', '일찍 체크인', '늦은 체크아웃', '체크아웃', '체크인'],
    'parking': ['주차'],
    'elevator': ['엘리베이터', '엘베', '계단'],
    'access': ['역에서', '도보', '걸어서', '공항에서'],
}
_FAQ_NUM_RX = r'\d[\d,]*\s?(?:분|엔|층)|무료|유료'

def faq_hl(text, topic):
    """근거 인용 결정적 하이라이트(F23): 토픽 ko 키워드 + 숫자단위(N분|N엔|N층|무료|유료)만 <b> 래핑.
    원문 무변형 — escape 후 감싸기만. 창작·의역 아님."""
    t = E(str(text or ''))
    kws = sorted((k for k in FAQ_KO_KW.get(topic, []) if k), key=len, reverse=True)
    pats = [re.escape(E(k)) for k in kws] + [_FAQ_NUM_RX]
    return re.sub('(' + '|'.join(pats) + ')', r'<b>\1</b>', t)

def faq_answer_html(a):
    """답변 렌더(F23): emph(**→primary span) 후 문장 종결('다. '/'요. ')마다 줄바꿈."""
    return re.sub(r'(?<=[다요])\.\s+', '.<br>', emph(a or ''))

def orig_link_label(o):
    """F32+F39: 원문 링크 라벨 통일 — 목적지 URL은 현행 그대로(변형 금지)."""
    return '리뷰 원문 보기 ↗'

def _faq_ev_preview(ev, topic=''):
    """FAQ 카드 내 리뷰 근거 미니카드 — 고객 id(마스킹) 우선, 출처는 보조, 별점 있으면 별점(§7: 별 0개 금지)."""
    st = ev.get('st')
    try: stw = int(float(st)) * 20
    except (TypeError, ValueError): stw = 0
    star = f'<span class="star"><i style="width:{stw}%"></i></span>' if stw else ''
    d = _faq_date(ev.get('d'))
    iso = str(ev.get('d') or '')[:10]
    # F27: 날짜 옆 상대시간 뱃지 자리(fe-rel) — 클라이언트 JS가 채움(빌드시점 고정 아님)
    date_html = (f'<span class="fe-date">{d}</span><span class="rel-badge" data-d="{E(iso)}"></span>'
                 if d else '')
    meta = (f'<span class="fe-name">{E(mask_name(ev.get("rn")))}</span>'
            f'<span class="fe-src">{E(ev.get("o") or "Google")}</span>{star}{date_html}')
    # F32: 근거 미니카드 원문 링크 (url 빈값이면 미출력, 저장값 그대로)
    u = ev.get('u') or ''
    link = (f'<a class="fe-link" href="{E(u)}" target="_blank" rel="noopener">{orig_link_label(ev.get("o") or "Google")}</a>'
            if u else '')
    return (f'<li class="fe-item"><div class="fe-meta">{meta}</div>'
            f'<div class="fe-q">"{faq_hl(ev.get("q") or "", topic)}"</div>{link}</li>')

def faq_section(faq):
    """F12+F18: 필터 탭 + 컴팩트 리스트(접힘=Q+칩 / 펼침=답변→근거 3개→더보기 시트). e 최대 8."""
    if not faq: return ''
    by_g = defaultdict(list)
    for item in faq:
        by_g[item.get('g') or '기타'].append(item)
    present = [g for g in FAQ_GROUP_ORDER if by_g.get(g)]
    if not present: return ''
    tabs = ['<button type="button" class="faq-tab is-on" data-g="">전체</button>']
    tabs += [f'<button type="button" class="faq-tab" data-g="{E(g)}">{E(g)}</button>' for g in present]
    cards = []
    faqevid = {}
    for g in present:
        for it in sorted(by_g[g], key=lambda x: -(x.get('n') or 0)):
            t = str(it.get('t') or '')
            evlist = [ev for ev in (it.get('e') or []) if ev.get('q')]
            chips = ''.join(f'<span class="faq-chip">{E(c)}</span>' for c in (it.get('c') or [])[:4] if c)
            chips_html = f'<div class="faq-chips">{chips}</div>' if chips else ''
            ev_block = ''
            if evlist:
                prev = ''.join(_faq_ev_preview(ev, t) for ev in evlist[:3])
                more = ''
                # FAQ-LAZYLOAD: 라벨 N = nt(최근1년 매칭 총수, export_faq_reviews.py) — 없거나 근거수 이하면 근거수 폴백
                try: nt = int(it.get('nt') or 0)
                except (TypeError, ValueError): nt = 0
                n_label = nt if nt > len(evlist) else len(evlist)
                if n_label > 3:
                    # 시트용 evidence(R2 fetch 실패 시 폴백): rn은 마스킹된 n으로만 내보냄(실명 금지 — LEGAL §3). qh=하이라이트 HTML(F23). u/l/tf=F28 동형화용
                    faqevid[t] = [{'q': ev.get('q') or '', 'qh': faq_hl(ev.get('q') or '', t),
                                   'd': ev.get('d') or '', 'st': ev.get('st'),
                                   'o': ev.get('o') or 'Google', 'n': mask_name(ev.get('rn')),
                                   'u': ev.get('u') or '', 'l': ev.get('l') or '', 'tf': ev.get('tf') or ''}
                                  for ev in evlist]
                    more = (f'<button type="button" class="faq-more-btn" data-topic="{E(t)}" '
                            f'data-q="{E(it.get("q") or "")}">리뷰 {n_label}개 모두 보기</button>')
                ev_block = (f'<div class="faq-ev-head">실제 투숙객 리뷰</div>'
                            f'<ul class="faq-ev">{prev}</ul>{more}')
            # F18: 접힘(기본) = Q.질문+칩 한 덩어리 / 펼침 = 답변·근거(.faq-body)
            cards.append(f'''<div class="faq-card" id="faq-{E(t)}" data-group="{E(g)}">
                <button type="button" class="faq-q"><span class="q-pre">Q.</span><span class="q-txt">{E(it.get('q') or '')}</span><span class="faq-arrow"></span></button>
                {chips_html}
                <div class="faq-body">
                    <p class="faq-a">{faq_answer_html(it.get('a'))}</p>
                    {ev_block}
                </div>
            </div>''')
    evid_script = (f'<script>window.FAQEVID={json.dumps(faqevid, ensure_ascii=False)};</script>'
                   if faqevid else '')
    return f'''<div class="sect faq" id="hotel-faq">
            <div class="head"><div class="title">리뷰로 확인한 실전 정보</div>
            <div class="desc">투숙객 리뷰에서 추출했어요 · 최신 정책은 호텔에 확인하세요</div></div>
            <div class="faq-tabs">{''.join(tabs)}</div>
            <div class="faq-cards">{''.join(cards)}</div>
        </div>{evid_script}'''

def social_section(soc, name):
    """소셜 후기 (SOCIAL) — 네이버 블로그 후기 top3 + 유튜브 후기 영상.
    블로그: 카드(제목·블로거·썸네일) → 바텀시트 iframe(원본 그대로, 이탈 없음).
    영상: lite-embed(썸네일 → 탭 시 인페이지 재생, 쇼츠는 세로 카드). 콘텐츠 없으면 미노출."""
    if not soc: return ''
    blogs = soc.get('b') or []
    vids = soc.get('v') or []
    out = []
    if blogs:
        cards = []
        for b in blogs:
            img = (f'<img src="{E(b["img"])}" alt="" loading="lazy" onerror="this.parentNode.classList.add(\'no-img\')">'
                   if b.get('img') else '')
            d = str(b.get('d') or '')
            dd = f'{d[:4]}. {d[4:6]}. {d[6:8]}' if len(d) == 8 else d
            meta = ' · '.join(x for x in [b.get('by') or '', dd] if x)
            cards.append(f'''<button type="button" class="nb-card" data-url="{E(b['u'])}" data-title="{E(b['t'])}">
                <span class="nb-main"><span class="nb-tit">{E(b['t'])}</span>
                <span class="nb-meta">{E(meta)}</span></span>
                <span class="nb-thumb{'' if img else ' no-img'}">{img}</span>
            </button>''')
        out.append(f'''<div class="sect social-blog">
            <div class="head"><div class="title">네이버 블로그 후기</div>
            <div class="desc">네이버 "{E(name)} 후기" 상위 글이에요 · 탭하면 여기서 바로 읽을 수 있어요</div></div>
            <div class="nb-list">{''.join(cards)}</div>
        </div>''')
    if vids:
        slides = []
        for v in vids:
            scls = ' is-shorts' if v.get('s') else ''
            badge = '<span class="yt-badge">Shorts</span>' if v.get('s') else ''
            slides.append(f'''<li class="swiper-slide yt-slide{scls}">
                <div class="yt-card" data-vid="{E(v['id'])}" data-title="{E(v['t'])}">
                    <div class="yt-thumb"><img src="https://i.ytimg.com/vi/{E(v['id'])}/hqdefault.jpg" alt="" loading="lazy"><span class="yt-play"></span>{badge}</div>
                    <div class="yt-tit">{E(v['t'])}</div>
                    <div class="yt-ch">{E(v.get('ch') or '')}</div>
                </div>
            </li>''')
        out.append(f'''<div class="sect social-video">
            <div class="head"><div class="title">관련 영상</div>
            <div class="desc">유튜브 "{E(name)} 후기" 영상 · 탭하면 바로 재생돼요</div></div>
            <div class="yt-slider"><ul class="swiper-wrapper">{''.join(slides)}</ul></div>
        </div>''')
    return '\n'.join(out)


BLOG_SHEET_HTML = '''<div class="review-sheet blog-sheet" id="blog-sheet" hidden>
            <div class="sheet-dim"></div>
            <div class="sheet-panel">
                <div class="sheet-head">
                    <div class="sheet-grab"></div>
                    <div class="bs-title" id="bs-tit"></div>
                    <button type="button" class="sheet-close" aria-label="닫기">✕</button>
                </div>
                <div class="bs-body"><iframe id="bs-frame" src="about:blank" referrerpolicy="no-referrer-when-downgrade"></iframe></div>
                <div class="bs-foot"><a id="bs-link" href="#" target="_blank" rel="noopener">네이버에서 보기 ↗</a></div>
            </div>
        </div>'''


def faq_jsonld(faq):
    """FAQPage 스키마 (answer = ** 제거 평문 + chips 포함). 항목 없으면 None."""
    if not faq: return None
    entries = []
    for it in faq:
        q = (it.get('q') or '').strip()
        a_plain = re.sub(r'\*\*(.+?)\*\*', r'\1', it.get('a') or '').replace('**', '').strip()
        chips = [c for c in (it.get('c') or []) if c]
        if chips:
            a_plain = (a_plain + ' (' + ', '.join(chips) + ')').strip()
        if q and a_plain:
            entries.append({'@type': 'Question', 'name': q,
                            'acceptedAnswer': {'@type': 'Answer', 'text': a_plain}})
    if not entries: return None
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': entries}

def build_detail(pid, meta, h, quotes, stars, city, hotels_meta, H, kr=None, kr_rank_pct=None, kr_1y=None, monthly=None, monthly_cat=None, city_avg=None, city_cat_avg=None, crit_rank_pct=None, hotel_cols=(), kr_dist=None, faq=None, social=None):
    name = meta['title']
    img = img_path(pid, meta, depth=1)
    gmap = ('https://www.google.com/maps/search/?api=1'
            f'&query={urlquote(name, safe="")}&query_place_id={pid}')
    hstars = E(meta.get('hotel_stars') or '')

    lat, lng = meta.get('latitude'), meta.get('longitude')
    map_block = ''
    if lat and lng:
        # ── 위치 정보 칩 (F9: 사실 기반만 — 역거리 실계산 + 권역. 리뷰 유래 칩은 FAQ 섹션이 전담) ──
        _loc = []
        _ns = nearest_station(meta.get('latitude'), meta.get('longitude'))
        if _ns:
            _loc.append(f'<span class="lc-chip">{E(_ns[0])} 도보 {_ns[1]}분 · {_ns[2]}m</span>')
        for _a in AREAS:
            if _in_area(meta, _a):
                _loc.append(f'<span class="lc-chip">{E(_a["ko"].split("·")[0].rstrip("역"))}권</span>')
                break
        loc_chips = f'<div class="loc-chips">{"".join(_loc[:2])}</div>' if _loc else ''
        addr_html = (f'<div class="loc-addr">{E(meta.get("address") or "")}</div>'
                     if meta.get('address') else '')
        map_block = f'''<div class="sect location">
            <div class="head"><div class="title">위치</div></div>
            {addr_html}
            {loc_chips}
            <div class="map"><iframe src="https://maps.google.com/maps?q={lat},{lng}&z=16&hl=ko&output=embed"
                loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="{E(name)} 지도"></iframe></div>
        </div>'''

    # ── 딜브레이커 발동 계산 (경고 스트립·점프칩·verdict 공용): 희소·고위험 최근 1년 심각 ≥3건 — 캘리브레이션 고정 ──
    db_data = []          # [(cat, strip_label, chip_label, n), ...] — 발동(≥3)분만 (점프칩 fj-risk·verdict 공용, F35로 스트립은 삭제)
    rare_crit = {}        # {scat: 최근1년 심각 건수} — 발동 여부 무관 원시 카운트 (F8 verdict A① 판정용)
    rare_cascade = {}     # F33: {scat: (label, tone)} — 희소 칩 최신성 캐스케이드(최근 3달 → 최근 1년 → 심각 리뷰 없음)
    cut_1y = None         # 최근 1년 컷 날짜 문자열 (F8 case C 재사용)
    if CITY['asof']:
        from datetime import date as _date, timedelta as _td
        _y, _m, _d = map(int, CITY['asof'].split('-'))
        cut_1y = str(_date(_y, _m, _d) - _td(days=365))
        cut_3m = str(_date(_y, _m, _d) - _td(days=90))
        for _cat, _scat, _slabel, _clabel in (('위생', '해충/곰팡이', '벌레·곰팡이', '벌레 리뷰'),   # F43: 신고→리뷰
                                              ('위치·안전', '치안·안심', '치안·안심', '치안 리뷰')):
            _sev = [str(q.get('pub') or '')[:10] for q in quotes.get((pid, _cat), [])
                    if (q.get('scat') or '') == _scat and q.get('grade') == '심각']
            _n = sum(1 for p in _sev if p >= cut_1y)          # 최근 1년 심각
            _n3 = sum(1 for p in _sev if p >= cut_3m)          # 최근 3달 심각
            rare_crit[_scat] = _n
            if _n >= 3:
                db_data.append((_cat, _slabel, _clabel, _n))
            # F33 캐스케이드: 최근 3달 심각 ≥1 → 최근 1년 심각 ≥1 → 둘 다 0(심각 리뷰 없음 — F43 워딩)
            if _n3 >= 1:
                rare_cascade[_scat] = (f'최근 3달 심각 {_n3}건', 'alert')
            elif _n >= 1:
                rare_cascade[_scat] = (f'최근 1년 심각 {_n}건', 'alert')
            else:
                rare_cascade[_scat] = ('최근 1년 심각 리뷰 없음', 'clear')

    # ── 진입점 점프 칩 (info-cont 마지막 줄): 위험 칩(딜브레이커) + FAQ 질문형 칩(primary) + 전체 (최대 4칩) ──
    FAQ_CHIP_Q = [('bath', '대욕장 있나요?'), ('luggage', '짐 맡아주나요?'), ('breakfast', '조식 어때요?'),
                  ('family', '아이동반 되나요?'), ('parking', '주차 되나요?')]
    faq_jump_html = ''
    if h['scored'] and (faq or db_data):
        _chips = []
        for _cat, _sl, _cl, _n in db_data:
            _chips.append(f'<button type="button" class="fj-btn fj-risk" data-target="risk-{CATS.index(_cat)}">{_cl} {_n}건</button>')
        if faq:
            _tset = {it.get('t') for it in faq}
            _slots = max(0, 3 - len(db_data))      # 위험 칩 1개면 질문 칩 2개, 없으면 3개 (총 4칩 상한: 위험+질문+전체)
            for _key, _lbl in FAQ_CHIP_Q:
                if _slots <= 0: break
                if _key in _tset:
                    _chips.append(f'<button type="button" class="fj-btn fj-q" data-target="faq-{_key}">{_lbl}</button>')
                    _slots -= 1
            _chips.append(f'<button type="button" class="fj-btn fj-all" data-target="hotel-faq">실전정보 {len(faq)}개 전체보기</button>')
        # F14: 우측 화이트 페이드(스크롤 어포던스) 래퍼 · F19: 칩 위 마이크로 타이틀(칩 없으면 미출력)
        faq_jump_html = (f'<div class="fj-title">리뷰에서 찾아봤어요</div>'
                         f'<div class="faq-jump-wrap"><div class="faq-jump">{"".join(_chips)}</div></div>')

    # 이 호텔이 속한 컬렉션 칩 (지역 1 + 테마 매칭, 최대 3 — HUB §3-d)
    col_chip_block = ''
    if hotel_cols:
        chips = ''.join(f'<a class="det-col-chip" href="../{E(slug)}">{E(name)} 리포트</a>' for slug, name in hotel_cols)
        col_chip_block = f'''<div class="sect hub-detail-cols">
            <div class="head"><div class="title">이 호텔이 속한 컬렉션</div>
            <div class="desc">같은 조건의 다른 호텔과 위험도를 비교해 보세요</div></div>
            <div class="det-col-chips">{chips}</div>
        </div>'''

    sim = similar_hotels(pid, hotels_meta, H)
    similar_block = ''
    if sim:
        sim_cards = '\n'.join(hotel_card(p, hotels_meta[p], H[p], depth=1) for p in sim)
        similar_block = f'''<div class="sect hotel">
            <div class="head"><div class="title">이런 호텔은 어떠세요?</div>
            <div class="desc">비슷한 가격대·가까운 위치에서 실망 확률이 낮은 순이에요</div></div>
            <div class="list hotel-slider"><ul class="swiper-wrapper">{sim_cards}</ul></div>
        </div>'''

    if not h['scored']:
        body_scored = f'''<div class="sect"><div class="head">
            <div class="title">아직 분석 리뷰가 부족해요</div>
            <div class="desc">이 호텔은 분석된 리뷰가 {h['analyzed']}건이라 신뢰할 수 있는 확률을 내기 어려워요 (최소 {MIN_REVIEWS}건). 데이터가 쌓이면 공개할게요.</div>
        </div></div>'''
    else:
        v = pct(h['p_crit']); avg = pct(city['crit'])
        ratio = h['p_crit'] / city['crit']
        radar_vals = [round(h['cats'][c]['score']) for c in CATS]
        radar_max = max(65, min(100, (max(radar_vals) // 10 + 2) * 10))  # 동적 상한(폴리곤이 안 눌리게, 50은 항상 노출)

        # ── F8+F15+F25: 4-CASE verdict 헤드라인 + 근거 2줄(핵심 숫자 <b>) — 숫자는 전부 실측, 비유("100명 중") 금지 ──
        # F25: 최근 1년 심각 실측 카운트 — sev_by_cat(카테고리별 심각 finding 수) · crit_reviews_1y(고유 리뷰 union)
        sev_by_cat = {}
        crit_reviews_1y = 0
        if cut_1y:
            _seen = set()
            for _c in CATS:
                _k = 0
                for q in quotes.get((pid, _c), []):
                    if q.get('grade') == '심각' and str(q.get('pub') or '')[:10] >= cut_1y:
                        _k += 1
                        _seen.add((q.get('reviewer_name'), str(q.get('pub'))[:10], q.get('review_origin')))
                if _k:
                    sev_by_cat[_c] = _k
            crit_reviews_1y = len(_seen)
        _worst = max(CATS, key=lambda c: h['cats'][c]['score'])
        _worst_sc = h['cats'][_worst]['score']
        _all_safe = all(h['cats'][c]['band'] == 'safe' for c in CATS)
        if ratio <= 0.8:                              # A
            v_head, v_tone = '까다롭게 봐도 통과', 'safe'
            if rare_crit and all(n == 0 for n in rare_crit.values()):   # 스트립 발동 시 자동 배제(카운트>0)
                v_why = f'최근 1년 내 <b>{h["analyzed"]:,}건</b>을 분석했지만,<br>벌레·치안 심각 리뷰는 <b>0건</b>이었어요'
            elif _all_safe:
                v_why = f'최근 1년 내 <b>{h["analyzed"]:,}건</b>을 분석한 결과,<br>6개 항목 모두 평균보다 안전했어요'
            else:
                v_why = f'최근 1년 심각 언급 비율 <b>{v}%</b>,<br>{CITY["ko"]} 평균(<b>{avg}%</b>)보다 낮아요'
        elif ratio < 1.15:                            # B
            v_head, v_tone = '무난하게 통과', 'safe'
            if h['cats'][_worst]['band'] in ('warning', 'danger'):
                v_why = (f'다만 <b>{E(cat_ko(_worst))}</b>({round(_worst_sc)}){josa_eun(cat_ko(_worst))} '
                         f'평균보다 높아요,<br>아래 상세에서 확인하세요')
            else:
                v_why = '튀는 위험 항목 없이 고른 수준이에요'
        elif ratio < 1.5:                             # C
            v_head, v_tone = '예약 전 확인이 필요해요', 'warning'
            _warns = sorted((c for c in CATS if h['cats'][c]['band'] in ('warning', 'danger')),
                            key=lambda c: -h['cats'][c]['score'])[:2] or [_worst]
            _names = '·'.join(cat_ko(c) for c in _warns)
            _k = sum(sev_by_cat.get(c, 0) for c in _warns)
            if _k:
                v_why = f'<b>{E(_names)}</b> 불만이 집중돼요,<br>최근 1년 심각 <b>{_k}건</b>이 확인됐어요'
            else:
                v_why = f'<b>{E(_names)}</b> 불만이 집중돼요'
        else:                                         # D — F25: 실측 카운트(고유 리뷰 수 + 최다 카테고리)
            v_head, v_tone = '실망 위험이 높은 호텔이에요', 'danger'
            _top_sev = max(sev_by_cat, key=sev_by_cat.get) if sev_by_cat else None
            if crit_reviews_1y and _top_sev:
                v_why = (f'최근 1년 리뷰 <b>{h["analyzed"]:,}건</b> 중 <b>{crit_reviews_1y}건</b>에서 심각한 문제가 확인됐어요,<br>'
                         f'특히 <b>{E(cat_ko(_top_sev))}</b> 불만이 <b>{sev_by_cat[_top_sev]}건</b>으로 가장 많았어요')
            elif crit_reviews_1y:
                v_why = f'최근 1년 리뷰 <b>{h["analyzed"]:,}건</b> 중 <b>{crit_reviews_1y}건</b>에서 심각한 문제가 확인됐어요'
            else:   # 가드(빈값): 실측 비율만
                v_why = f'최근 1년 심각 언급 비율 <b>{v}%</b>,<br>{CITY["ko"]} 평균(<b>{avg}%</b>)보다 높아요'
        # F41: 히어로 줄 = %+판정 같은 줄·같은 케이스색(verdict 별도 줄 흡수). 근거(why)는 게이지 아래 유지
        verdict_why_html = f'<div class="verdict-why">{v_why}</div>'

        # F35: 딜브레이커 경고 스트립 삭제(db_data 계산은 점프칩 fj-risk·verdict용으로 유지)
        radar_labels = json.dumps([cat_ko(c) for c in CATS], ensure_ascii=False)  # 표시 라벨만 순화(순서=CATS 고정)

        # 카테고리 × 소분류 — 아코디언(§4) + 리뷰 시트 데이터. 위험도 내림차순 정렬(§4-d).
        groups = []
        sheet_data = {}
        sheet_total = {}     # {cat: {'t': 전체 카드수, 's': {scat: 건수}}} — 팝업 실제 총건수(임베드 40 아님). REVIEW-LAZYLOAD §C
        trendc = {}          # {ci: {'m':[..'N월'], 'w':[..pw], 'c':[..pc]}} — 차트 있는 카테고리만 (CAT-TREND)
        axis = '''<div class="stat-axis"><span class="ax safe">양호</span><span class="ax avg">평균 50</span><span class="ax danger">위험</span></div>'''
        cats_sorted = sorted(CATS, key=lambda c: -h['cats'][c]['score'])  # 나쁜 것부터
        # 카테고리 트렌드용 완전월 12개 + 월별 분석 리뷰 수 n(monthly 재사용 — 분모 정합)
        cmonths = _complete_months(CITY['asof'], 12) if (monthly_cat and CITY['asof']) else []
        mcat_data = (monthly_cat or {}).get(pid) or {}
        m_n = {ym: nvals[0] for ym, nvals in ((monthly or {}).get(pid) or {}).items()}  # {ym: n}
        radar_chips = []
        for order, c in enumerate(cats_sorted):
            ci = CATS.index(c)                 # 카테고리 고정 인덱스 (칩 data-target ↔ id="risk-{ci}")
            cat = h['cats'][c]
            band = cat['band']
            cscore = round(cat['score'])
            qlist = quotes.get((pid, c), [])
            sheet_data[c] = [{'s': q.get('scat') or '', 'g': q['grade'], 'q': q.get('quote') or q.get('summary') or '',
                              'd': (q.get('pub') or '')[:10], 'n': mask_name(q.get('reviewer_name')),
                              'st': q.get('stars'), 'o': q.get('review_origin') or 'Google',
                              'u': q.get('review_url') or '', 'tf': q.get('tfull') or '', 'of': q.get('ofull') or '',
                              'l': (q.get('lang') or '').lower()} for q in qlist]
            # 실제 총건수(소분류 건수 = 아코디언 표기와 동일 출처). R2 전체 파일의 카드 수와 일치.
            sub_cnt = {s: cat['subs'][s]['count'] for s in SUBS[c] if cat['subs'][s]['count'] > 0}
            sheet_total[c] = {'t': sum(sub_cnt.values()), 's': sub_cnt}
            rows = []
            # 소분류 정렬: 점수 내림차순, 단 RARE_SUBS(칩 렌더·점수 아님)는 항상 마지막 고정
            sub_order = (sorted((s for s in SUBS[c] if s not in RARE_SUBS),
                                key=lambda s: -cat['subs'][s]['score'])
                         + [s for s in SUBS[c] if s in RARE_SUBS])
            for s in sub_order:
                sub = cat['subs'][s]
                sc = round(sub['score'])
                cnt = sub['count']
                cnt_html = (f'<button type="button" class="stat-count has-reviews" data-cat="{E(c)}" data-sub="{E(s)}">{cnt}건</button>'
                            if cnt > 0 else '<span class="stat-count zero">0건</span>')
                if s in RARE_SUBS:
                    # §3-c 희소·고위험: 점수 막대 대신 칩 (점수는 내부 계산 유지, 화면만 미노출) — F33 최신성 캐스케이드
                    _clabel, _ctone = rare_cascade.get(s, ('최근 1년 심각 리뷰 없음', 'clear'))
                    rdot = 'danger' if _ctone == 'alert' else 'safe'
                    chip = f'<div class="rare-chip is-{_ctone}">{E(_clabel)}</div>'
                    rare_btn = cnt_html if cnt > 0 else ''      # 우측 "N건" 전체보기 링크 현행 유지
                    rows.append(f'''<li class="stat-row is-rare">
                    <div class="stat-info"><div class="factor"><span class="sub-dot is-{rdot}"></span>{E(s)}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, ''))}</div></div>
                    {chip}
                    {rare_btn}
                </li>''')
                    continue
                # F34+F38: 소분류 행 최근 1년 비율 캡션 — "최근 1년 리뷰의 P%"(P=1y finding/analyzed·소수1자리), 우측 건수 링크 아래 우측정렬. 희소 칩 행은 F33이 대체.
                n1y = sub.get('count_1y', 0)
                cap_1y = (f'최근 1년 리뷰의 {round(n1y / h["analyzed"] * 100, 1)}%'
                          if n1y > 0 and h['analyzed'] else '최근 1년 없음')
                rows.append(f'''<li class="stat-row is-{sub['band']}">
                    <div class="stat-info"><div class="factor"><span class="sub-dot is-{sub['band']}"></span>{E(s)}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, ''))}</div></div>
                    <div class="stat-track"><div class="stat-fill" style="width:{sc}%"><i class="bubble">{sc}</i></div></div>
                    {cnt_html}
                    <div class="sub-1y">{E(cap_1y)}</div>
                </li>''')
            qc = quote_cards(qlist)
            total_q = len(qlist)
            more_btn = (f'''<div class="more"><button type="button" class="more-btn" data-cat="{E(c)}"><strong>{E(cat_ko(c))}</strong> 리뷰 전체보기 ({sheet_total[c]['t']}건)</button></div>'''
                        if total_q > 0 else '')
            quotes_block = (f'''<div class="review"><div class="list review-slider"><ul class="swiper-wrapper">{qc}</ul></div></div>{more_btn}'''
                            if qc else '<div class="no-quote">이 카테고리는 문제 언급 리뷰가 거의 없어요</div>')
            pctl_txt = f"{'하위 ' + str(cat['pctl_worse']) if cat['pctl_worse'] <= 50 else '상위 ' + str(100 - cat['pctl_worse'])}%"
            is_open = ' is-open' if order == 0 else ''      # 1위만 초기 펼침(§4-c)

            # ── 카테고리별 월별 위험 리뷰 흐름 (CAT-TREND). 최상단(axis 앞) 삽입 ──
            cat_trend = ''
            if cmonths:
                pw, pc, pa = [], [], []      # 주의%, 심각%, 도시 카테고리 평균% (완전월 12개)
                sum_flag = 0
                for ym, _lbl in cmonths:
                    nc, nw = mcat_data.get((ym, c), (0, 0))
                    n = m_n.get(ym, 0)
                    pw.append(round(nw / n * 100, 1) if n else 0.0)
                    pc.append(round(nc / n * 100, 1) if n else 0.0)
                    pa.append((city_cat_avg or {}).get((ym, c), 0.0))
                    sum_flag += nc + nw
                if sum_flag >= 8:                            # 가드(C-5): 저표본 차트 생략
                    labels = [lbl for _ym, lbl in cmonths]
                    trendc[ci] = {'m': labels, 'w': pw, 'c': pc, 'a': pa}
                    tot = round(pw[-1] + pc[-1], 1)          # 합계 = 주의+심각 (배타)
                    now_txt = f'{labels[-1]} {tot}% · 평균 {pa[-1]}%'
                    dt = round((pw[-1] + pc[-1]) - (pw[-2] + pc[-2]), 1)
                    # 델타 문구(C-8): ±0.05p 미만은 "비슷", 그 외 합계 기준 증감
                    if abs(dt) < 0.05:
                        delta_txt = '지난 달과 비슷한 수준이에요'
                    else:
                        delta_txt = f'지난 달 대비 {dt:+.1f}p {"증가했어요" if dt > 0 else "줄었어요"}'
                    # F24: 기본 접힘 — 토글 줄에 현재값 요약 유지(정보 손실 방지), 차트는 펼칠 때 지연 렌더
                    cat_trend = (f'<div class="trend-fold ct-fold" data-ci="{ci}">'
                        f'<button type="button" class="trend-fold-btn"><span class="tf-tit">월별 위험 흐름 보기</span>'
                        f'<span class="tf-now">{E(now_txt)}</span><span class="tf-arrow"></span></button>'
                        f'<div class="trend-fold-body">'
                        f'<div class="cat-trend" data-ci="{ci}">'
                        f'<div class="ct-canvas"><canvas id="cat-trend-{ci}"></canvas></div>'
                        f'<div class="ct-delta">{E(delta_txt)}</div></div>'
                        f'</div></div>')

            groups.append(f'''<div class="risk-acc-item{is_open}" id="risk-{ci}" data-order="{order}">
                <button type="button" class="risk-acc-head">
                    <span class="risk-dot is-{band}"></span>
                    <span class="cat-name">{E(cat_ko(c))}</span>
                    <span class="cat-score is-{band}">위험도 {cscore}<span class="pctl"> · {pctl_txt}</span></span>
                    <span class="risk-arrow"></span>
                </button>
                <div class="risk-acc-body">
                    {cat_trend}
                    {axis}
                    <ul class="stat-list">{''.join(rows)}</ul>
                    {quotes_block}
                </div>
            </div>''')
            # §3-b 레이더 카테고리 칩 (동일 순서)
            radar_chips.append(
                f'<button type="button" class="radar-cat is-{band}" data-target="risk-{ci}">'
                f'<span class="risk-dot is-{band}"></span><span class="rc-name">{E(cat_ko(c))}</span>'
                f'<span class="rc-score">{cscore}</span></button>')
        radar_cats_html = f'<div class="radar-cats">{"".join(radar_chips)}</div>'

        # ── 전체 통합 월별 흐름 라인차트 (게이지 아래·인사이트 앞) ──
        overall_trend, trendc_all = overall_trend_html(pid, monthly, monthly_cat, CITY['asof'], city_avg)
        if trendc_all is not None:
            trendc['all'] = trendc_all

        st = stars.get(pid)
        stars_block = ''
        if st and st['total'] > 0:
            bars = []
            for i in range(1, 6):
                w = round(st['dist'][i] / st['total'] * 100)
                bars.append(f'''<li><div class="num">{i}점</div><div class="bar"><i style="width:{w}%"></i></div><div class="per">{w}%</div></li>''')
            low_share = round(st['low_1y'] / st['total_1y'] * 100) if st['total_1y'] else 0
            stars_block = f'''<div class="sect recent">
                <div class="head"><div class="title">구글 별점 분포</div>
                <div class="desc">최근 1년 <b>2점 이하 리뷰 비율은 {low_share}%</b> 입니다.</div>
                <div class="count">총 {st['total']:,}건</div></div>
                <div class="list"><ul>{''.join(bars)}</ul></div>
            </div>'''

        body_scored = f'''
        <div class="sect disappear">
            <div class="head">
                <div class="eyebrow">이 호텔에서 실망할 확률<button type="button" class="basis-toggle" aria-label="산출 기준"><i class="bt-q">?</i></button></div>
                <div class="pct">{v}%</div>
                <div class="vh is-{v_tone}">{E(v_head)}</div>
            </div>
            {gauge_html(crit_rank_pct, city_crit_rank_pct(H, city['crit']), city['crit'], v_tone)}
            {verdict_why_html}
            {overall_trend}
            <div class="basis-fold">
                <div class="basis">
                    <p>최근 리뷰일수록 높은 가중치로 반영됩니다</p>
                    <p>분석 리뷰 {h['analyzed']:,}건 · 기준 {CITY['data_asof']}</p>
                    <p class="basis-note">공개 리뷰 기반의 참고용 의견으로, 실제 경험과 다를 수 있습니다 · <a href="../about">산출 방법</a></p>
                </div>
            </div>
        </div>
        <div class="sect risk">
            <div class="head"><div class="title">카테고리별 위험도</div>
            <div class="desc">{CITY['ko']} 평균 = 50</div></div>
            <div class="chart">
                <div class="radar-box"><canvas id="radar"></canvas></div>
                <div class="custom-legend">
                    <div class="legend-item legend-hotel"><span class="legend-symbol"></span><span class="hotel-text">{E(name)}</span></div>
                    <div class="legend-item legend-average"><span class="legend-symbol"></span><span class="hotel-text">{CITY['ko']} 평균</span></div>
                </div>
            </div>
            <script>
            document.addEventListener('DOMContentLoaded', function(){{
                var ctx = document.getElementById('radar').getContext('2d');
                new Chart(ctx, {{
                    type: 'radar',
                    data: {{
                        labels: {radar_labels},
                        datasets: [
                            {{label: '{E(name)}', data: {radar_vals}, fill: true,
                              backgroundColor: 'rgba(141,91,253,0.13)', borderColor: '#8D5BFD', borderWidth: 2,
                              pointBackgroundColor: '#fff', pointBorderColor: '#8D5BFD', pointBorderWidth: 2,
                              pointRadius: 3.5, pointHoverRadius: 4, tension: 0}},
                            {{label: '{CITY['ko']} 평균', data: [50,50,50,50,50,50], fill: false,
                              borderColor: '#B0B4BB', borderDash: [4,4], pointRadius: 0, borderWidth: 1.5}}
                        ]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        layout: {{padding: 2}},
                        plugins: {{legend: {{display: false}}, tooltip: {{enabled: false}}}},
                        scales: {{r: {{
                            min: 0, max: {radar_max},
                            angleLines: {{color: '#F1F2F4'}},
                            grid: {{color: '#EEEFF3', circular: false}},
                            ticks: {{stepSize: 25, backdropColor: 'transparent', showLabelBackdrop: false, color: '#B0B4BB', font: {{size: 10}}}},
                            pointLabels: {{font: {{size: 12.5, weight: '700'}}, color: '#4B5057', padding: 12}}
                        }}}}
                    }}
                }});
            }});
            </script>
            {radar_cats_html}
        </div>
        <div class="sect analysis" id="risk-detail">
            <div class="head"><div class="title">리스크 상세 분석</div>
            <div class="desc">위험도 0~100 · {CITY['ko']} 평균이 50이에요<br>100에 가까울수록 같은 불만이 많다는 뜻 (100 = 평균의 3배 이상)</div></div>
            <div class="risk-acc">{''.join(groups)}</div>
            {('<script>window.TRENDC=' + json.dumps(trendc, ensure_ascii=False) + ';</script>') if trendc else ''}
            <div class="stat-legend">
                <span class="lg is-danger">위험 70+</span><span class="lg is-warning">주의 45~70</span><span class="lg is-safe">양호 ~45</span>
                <span class="note">불만 리뷰 5건 미만 소분류는 위험 등급을 붙이지 않아요</span>
                <span class="note">인용문은 리뷰 원문 발췌입니다</span>
                <span class="note">벌레·치안처럼 드물지만 치명적인 항목은 점수 대신 리뷰 건수로 보여드려요</span>
            </div>
        </div>
        {faq_section(faq)}
        {social_section(social, name)}
        {stars_block}
        {korean_card(kr, city, kr_rank_pct, kr_1y, kr_dist)}
        <div class="review-sheet" id="review-sheet" hidden>
            <div class="sheet-dim"></div>
            <div class="sheet-panel">
                <div class="sheet-head">
                    <div class="sheet-grab"></div>
                    <div class="sheet-title">
                        <button type="button" class="sheet-nav" id="sheet-prev" aria-label="이전 카테고리">‹</button>
                        <span class="tit"><span id="sheet-cat"></span> 리뷰 <span class="cnt" id="sheet-cnt"></span></span>
                        <button type="button" class="sheet-nav" id="sheet-next" aria-label="다음 카테고리">›</button>
                    </div>
                    <button type="button" class="sheet-close" aria-label="닫기">✕</button>
                    <div class="sheet-chips" id="sheet-chips"></div>
                    <div class="sheet-tools">
                        <div class="sheet-sort">심각도 · 최신순</div>
                        <button type="button" class="sheet-kr" id="sheet-kr">한국인 리뷰만</button>
                    </div>
                </div>
                <ul class="sheet-list" id="sheet-list"></ul>
            </div>
        </div>
        {BLOG_SHEET_HTML if (social or {}).get('b') else ''}
        <script>
        window.QDATA = {json.dumps(sheet_data, ensure_ascii=False)};
        window.QTOTAL = {json.dumps(sheet_total, ensure_ascii=False)};
        window.QSUBS = {json.dumps({c: SUBS[c] for c in CATS}, ensure_ascii=False)};
        window.QFULL = {json.dumps(f'{R2_PUB}/quotes/{pid}.json')};
        window.CF_FAQR = {json.dumps(f'{R2_PUB}/faq_reviews/{pid}.json')};
        window.CF_PID = {json.dumps(pid)};
        window.CF_GREVIEWS = 'https://search.google.com/local/reviews?placeid={pid}';
        </script>'''

    canonical = f'{BASE}/hotels/{pid}'
    og_img = meta.get('r2_img') or (f'{BASE}/img/hotels/{pid}.jpg' if meta.get('local_img') else None)
    if h['scored']:
        _v = pct(h['p_crit']); _avg = pct(city['crit'])
        rank_txt = (f' 실망 확률이 낮은 순으로 {CITY["ko"]} 상위 {crit_rank_pct}%.'
                    if crit_rank_pct and crit_rank_pct <= 50 else '')
        seo_title = f'{name} 리뷰 위험도 · 실망확률 {_v}% | 캐치플로'
        seo_desc = (f'{name} 실망 확률 {_v}% ({CITY["ko"]} 평균 {_avg}%).{rank_txt} '
                    '위생·냄새·소음·시설·불친절·위치안전 6개 항목의 리뷰 위험도를 예약 전에 확인하세요.')
    else:
        seo_title = f'{name} 리뷰 위험도 분석 | 캐치플로'
        seo_desc = (f'{name}의 리뷰를 수집·분석하고 있습니다. 위치·가격·구글 평점과 '
                    '주변의 실망 확률 낮은 추천 호텔을 캐치플로에서 확인하세요.')
    _faqld = faq_jsonld(faq) if h['scored'] else None
    _extra_head = jsonld_detail(pid, meta) + (('\n' + _jsonld(_faqld)) if _faqld else '')
    return head(seo_title, depth=1, description=seo_desc, canonical=canonical,
                og_image=og_img, extra_head=_extra_head) + f'''
    <script>window.CF_HOTEL={{pid:{json.dumps(pid)},name:{json.dumps(name)},gmap:{json.dumps(gmap)}}};</script>
    <main id="container">
        <section id="detail">
            {site_header(1, back='../search')}
            <div class="content">
                {gallery_html(meta, name, img)}
                <div class="sect information">
                    <div class="info-top"><div class="badge">{badge_html(h)}</div></div>
                    <div class="info-cont">
                        <div class="name">
                            <h1 class="name-ko">{E(name)}</h1>
                            <p class="name-en">{E(meta.get('sub_title') or '')}</p>
                        </div>
                        <div class="meta"><span>{CITY['ko']}, JP</span>{f'<span>{hstars}</span>' if hstars else ''}{f"<span class='price'>1박 <b>{meta['price_txt']}</b></span>" if meta.get('price_txt') else ''}</div>
                    </div>
                    <div class="info-bottom">
                        <a class="btn-link btn-google" href="{E(gmap)}" target="_blank" rel="noopener">
                            <span class="ico"><img src="../img/google.svg" alt=""></span>
                            <span class="txt"><span class="label">구글 평점 {fmt_score(meta.get('total_score'))}</span><span class="count">({meta.get('reviews_count') or 0:,}개)</span></span>
                        </a>
                        <a class="btn-link btn-audit" href="#risk-detail">
                            <span class="ico"><img src="../img/audit.svg" alt=""></span>
                            <span class="txt"><span class="label">분석 리뷰 {h['analyzed']:,}개</span><span class="count">AI 분석 리포트</span></span>
                        </a>
                    </div>
                    {faq_jump_html}
                </div>
                {map_block}
                {body_scored}
                {col_chip_block}
                {similar_block}
            </div>
            <div class="button"><a class="btn-reservate" href="{E(gmap)}" target="_blank" rel="noopener">실시간 최저가 확인</a></div>
        </section>
        <section id="float">
            <div class="float">
                <a href="javascript:;" class="btn-share" aria-label="공유하기"><img src="../img/b_share.svg" alt="공유하기"></a>
                <a href="javascript:;" class="btn-top" aria-label="맨 위로"><img src="../img/b_top.svg" alt="맨 위로"></a>
            </div>
        </section>
    </main>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
        $(function(){{
            $('.hotel-gallery').each(function(i, el){{
                var cnt = el.querySelector('.gallery-count'), total = el.querySelectorAll('.swiper-slide').length;
                new Swiper(el, {{slidesPerView:1, spaceBetween:0, loop:true,
                    pagination:{{el: el.querySelector('.swiper-pagination'), clickable:true}},
                    observer:true, observeParents:true,
                    on:{{slideChange:function(){{ if(cnt) cnt.textContent=(this.realIndex+1)+' / '+total; }}}}
                }});
            }});
            $('.review-slider, #detail .hotel-slider, .yt-slider').each(function(i, el){{
                new Swiper(el, {{slidesPerView:'auto', spaceBetween:10, observer:true, observeParents:true}});
            }});

            // F36 드로어 JS는 site_header() 공통 컴포넌트에 포함 (상세·recent 공유)

            // ───── 플로팅: 공유 / 맨 위로 ─────
            $(window).on('scroll', function(){{
                $('#float').toggleClass('is-active', $(window).scrollTop() > 50);
            }});
            $('.btn-top').on('click', function(e){{
                e.preventDefault();
                $('html, body').stop().animate({{scrollTop: 0}}, 400);
            }});
            // 공유(.btn-share)는 js/engage.js 에서 처리 (OS 공유시트 + 카카오 인앱 폴백)

            // F16+F21+F31: 산출 기준(basis) ? 토글 — 가드 없는 블록에서 바인딩(항상 실행). 모바일 탭 확실성 위해 preventDefault
            $('#detail').on('click', '.basis-toggle', function(e){{
                e.preventDefault();
                $('.disappear .basis-fold').toggleClass('is-open');
            }});

            // F27: 상대시간 뱃지 — 클라이언트 계산(로드 시점 기준, 빌드 고정 아님). <7일 N일 전 / <35일 N주 전 / <12개월 N개월 전 / 그 외 N년 전
            window.CF_rel = function(iso){{
                if (!iso) return '';
                var t = Date.parse(iso.length > 10 ? iso : iso + 'T00:00:00');
                if (isNaN(t)) return '';
                var days = Math.floor((Date.now() - t) / 86400000);
                if (days < 0) days = 0;
                if (days < 7) return (days || 0) + '일 전';
                if (days < 35) return Math.floor(days / 7) + '주 전';
                var mon = Math.floor(days / 30);
                if (mon < 12) return mon + '개월 전';
                return Math.floor(days / 365) + '년 전';
            }};
            // 서버 렌더된 FAQ 미리보기 뱃지 채우기 (동적 시트 카드는 렌더 시 inline 처리)
            $('.rel-badge[data-d]').each(function(){{ var s = window.CF_rel($(this).data('d')); if (s) $(this).text(s); }});

            // ───── 리뷰 바텀시트 (심각도>최신순 정렬 데이터, 소분류 칩 필터) ─────
            if (!window.QDATA) return;
            var $sheet = $('#review-sheet'), curCat = null, curSub = null, krOnly = false;
            var qfull = false, qloading = false;   // R2 전체 인용문 로드 상태 (REVIEW-LAZYLOAD §C)

            function toast(msg){{
                var t = document.createElement('div'); t.className = 'cf-toast'; t.textContent = msg;
                document.body.appendChild(t);
                requestAnimationFrame(function(){{ t.classList.add('show'); }});
                setTimeout(function(){{ t.classList.remove('show'); setTimeout(function(){{ t.remove(); }}, 300); }}, 1800);
            }}
            // 첫 '더보기'/한국인필터 시 호텔 전체 인용문 JSON을 R2에서 1회 fetch → QDATA 교체(이후 탭 전환 즉시)
            function loadFull(cb){{
                if (qfull || !window.QFULL) {{ cb && cb(); return; }}
                if (qloading) return;
                qloading = true; render();
                fetch(window.QFULL, {{cache: 'force-cache'}})
                    .then(function(r){{ return r.ok ? r.json() : Promise.reject(r.status); }})
                    .then(function(j){{ window.QDATA = j; qfull = true; qloading = false; cb && cb(); }})
                    .catch(function(){{ qloading = false; render(); toast('전체 리뷰를 불러오지 못했어요'); }});
            }}

            function esc(s){{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
            function emph(s){{ return esc(s).replace(/\\*\\*(.+?)\\*\\*/g, '<span>$1</span>').replace(/\\*\\*/g, ''); }}
            function langLabel(l){{
                if (!l) return '';
                var M = {{ko:'한국어', ja:'일본어', en:'영어'}};
                if (M[l]) return M[l];
                if (l.indexOf('zh') === 0) return '중국어';
                return l.toUpperCase();
            }}

            function card(q){{
                var star = q.st ? '<div class="star"><i style="width:' + (q.st*20) + '%"></i></div>' : '';
                var band = q.g === '심각' ? 'danger' : 'warning';
                var hasFull = !!(q.tf || q.of);
                var full = '';
                if (hasFull) {{
                    full = '<div class="full" hidden>'
                        + (q.tf ? '<div class="full-tit">전체 리뷰 (번역)</div><div class="full-txt">' + esc(q.tf) + '</div>' : '')
                        + (q.of && q.of !== q.tf ? '<div class="full-tit">원문</div><div class="full-txt">' + esc(q.of) + '</div>' : '')
                        + '</div>';
                }}
                var foot = '<div class="item-foot">'
                    + origLink(q.o, q.u)
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '')
                    + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(q.n) + '</div>'
                    + '<div class="status"><div class="status-item ' + band + '">' + q.g + '</div></div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(q.o) + '</div>' + (langLabel(q.l) ? '<span class="q-lang">' + langLabel(q.l) + '</span>' : '') + '</div>'
                    + '<div class="item-bottom"><div class="text clamp">' + emph(q.q) + '</div>'
                    + '<div class="date">' + esc((q.d||'').replace(/-/g,'. ')) + (q.s ? ' · ' + esc(q.s) : '') + relSpan(q.d) + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }}
            // F32+F39: 원문 링크 — 라벨 통일 "리뷰 원문 보기", 목적지는 저장 URL 그대로. URL 빈값이면 미출력
            function origLink(o, u){{
                if (!u) return '<span></span>';
                return '<a class="orig-link" href="' + esc(u) + '" target="_blank" rel="noopener">리뷰 원문 보기 ↗</a>';
            }}
            // F27: 시트 카드 날짜 옆 상대 뱃지 (동적 렌더 — 로드시점 계산)
            function relSpan(d){{ var s = window.CF_rel ? window.CF_rel(String(d||'').slice(0,10)) : ''; return s ? '<span class="rel-badge">' + s + '</span>' : ''; }}

            function render(){{
                var T = (window.QTOTAL && window.QTOTAL[curCat]) || null;
                var base = (window.QDATA[curCat] || []);
                var list = krOnly ? base.filter(function(q){{ return q.l === 'ko'; }}) : base;
                var filtered = curSub ? list.filter(function(q){{ return q.s === curSub; }}) : list;
                // 건수: 전체언어 & 미로드 상태면 실제 총건수(QTOTAL), 그 외(로드완료·한국인필터)는 현재 리스트 기준
                var useReal = (!qfull && !krOnly && T);
                function cnt(sub){{
                    if (useReal) return sub ? (T.s[sub] || 0) : T.t;
                    return (sub ? list.filter(function(q){{ return q.s === sub; }}) : list).length;
                }}
                $('#sheet-cat').text((window.CAT_KO && window.CAT_KO[curCat]) || curCat);   // 표시만 순화, curCat은 내부키 유지
                $('#sheet-cnt').text(cnt(curSub) + '건');
                var cards = filtered.map(card).join('');
                // 더보기: 아직 전체 로드 전이고 임베드가 실제 총건보다 적으면 리스트 하단에 노출
                var more = '';
                if (!qfull && T && base.length < T.t) {{
                    var remain = cnt(curSub) - filtered.length;
                    more = '<li class="sheet-more"><button type="button" class="sheet-more-btn"' + (qloading ? ' disabled' : '') + '>'
                         + (qloading ? '불러오는 중…' : '리뷰 전체 보기' + (remain > 0 ? ' (+' + remain + '건)' : '')) + '</button></li>';
                }}
                $('#sheet-list').html((cards ||
                    '<li class="sheet-empty">' + (krOnly ? '이 카테고리엔 한국어 리뷰가 없어요' : '이 소분류의 인용 리뷰가 없어요') + '</li>') + more);
                var subs = window.QSUBS[curCat] || [];
                var chips = ['<button type="button" class="sheet-chip' + (!curSub ? ' on' : '') + '" data-sub="">전체 ' + cnt(null) + '</button>'];
                subs.forEach(function(s){{
                    var n = cnt(s);
                    if (!n) return;
                    chips.push('<button type="button" class="sheet-chip' + (curSub === s ? ' on' : '') + '" data-sub="' + esc(s) + '">' + esc(s) + ' ' + n + '</button>');
                }});
                $('#sheet-chips').html(chips.join(''));
                $('#sheet-list').scrollTop(0);
                $('#sheet-kr').toggleClass('is-on', krOnly);
            }}

            function closeVisual(){{
                $sheet.removeClass('is-open faq-mode');
                $('body').css('overflow', '');
                setTimeout(function(){{ $sheet.prop('hidden', true); }}, 300);
            }}
            // F28: FAQ 시트 카드 = 리스크 시트 카드 동형(이름·별점·출처·언어칩·인용·날짜+상대뱃지·원문링크·tf 토글). grade만 미해당→생략.
            function faqCard(e){{
                var stw = parseInt(e.st, 10) || 0;
                var star = stw ? '<div class="star"><i style="width:' + (stw*20) + '%"></i></div>' : '';
                var d = String(e.d||'').slice(2,10).replace(/-/g,'.');   // YY.MM.DD
                var hasFull = !!e.tf;
                var full = hasFull ? '<div class="full" hidden><div class="full-tit">전체 리뷰 (번역)</div><div class="full-txt">' + esc(e.tf) + '</div></div>' : '';
                var foot = '<div class="item-foot">' + origLink(e.o, e.u)
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '') + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(e.n || '투숙객') + '</div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(e.o || 'Google') + '</div>' + (langLabel(e.l) ? '<span class="q-lang">' + langLabel(e.l) + '</span>' : '') + '</div>'
                    + '<div class="item-bottom"><div class="text clamp">' + (e.qh || emph(e.q)) + '</div>'   // qh = 서버 하이라이트 HTML(F23)
                    + '<div class="date">' + esc(d) + relSpan(e.d) + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }}
            // FAQ-LAZYLOAD: 더보기 시트 소스 = R2 faq_reviews/{{pid}}.json (토픽별 최근1년 매칭 전체, 토픽당 최대 60건).
            // 전체 JSON 1회 fetch 후 캐싱(토픽 전환 시 재요청 없음). 실패/CORS 시 인라인 FAQEVID 폴백 — 빈 시트 금지.
            var faqFull = null, faqFetchP = null, faqSeq = 0;
            function maskName(s){{
                s = String(s || '').trim();
                return s ? Array.from(s)[0] + '**' : '투숙객';
            }}
            // R2 카드(rn 원명) → faqCard 입력형 변환. rn은 반드시 마스킹(LEGAL §3). qh 없음 → faqCard가 emph(q)로 렌더.
            function faqNorm(r){{
                return {{n: maskName(r.rn), st: r.st, o: r.o || 'Google', u: r.u || '',
                        l: r.l || '', q: r.q || '', d: r.d || '', tf: r.tf || ''}};
            }}
            function faqFetch(){{
                if (faqFetchP) return faqFetchP;
                if (!window.CF_FAQR) return Promise.reject();
                faqFetchP = fetch(window.CF_FAQR, {{cache: 'force-cache'}})
                    .then(function(r){{ return r.ok ? r.json() : Promise.reject(r.status); }})
                    .then(function(j){{ faqFull = j; return j; }})
                    .catch(function(e){{ faqFetchP = null; return Promise.reject(e); }});
                return faqFetchP;
            }}
            function faqList(topic, q, cnt, cards){{
                $('#sheet-cat').text(q || '');
                $('#sheet-cnt').text(cnt ? cnt + '건' : '');
                $('#sheet-list').html(cards || '<li class="sheet-empty">리뷰 근거가 없어요</li>');
                $('#sheet-list').scrollTop(0);
            }}
            function faqRender(topic, q){{
                var t = faqFull && faqFull[topic];
                if (t && t.r && t.r.length) {{
                    faqList(topic, q, t.n || t.r.length, t.r.map(faqNorm).map(faqCard).join(''));
                }} else {{
                    var list = (window.FAQEVID && window.FAQEVID[topic]) || [];   // 폴백: 인라인 근거 8개(현행)
                    faqList(topic, q, list.length, list.map(faqCard).join(''));
                }}
            }}
            function faqOpen(topic, q){{
                $sheet.addClass('faq-mode');
                $('#sheet-chips').empty();
                $sheet.prop('hidden', false);
                requestAnimationFrame(function(){{ $sheet.addClass('is-open'); }});
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);
                var seq = ++faqSeq;   // 로딩 중 토픽 전환/재오픈 시 낡은 응답 렌더 방지
                if (faqFull) {{ faqRender(topic, q); return; }}
                faqList(topic, q, 0, '<li class="sheet-loading">리뷰를 불러오는 중…</li>');
                faqFetch()
                    .then(function(){{ if (seq === faqSeq) faqRender(topic, q); }})
                    .catch(function(){{ if (seq === faqSeq) faqRender(topic, q); }});
            }}
            $(document).on('click', '.faq-more-btn', function(){{ faqOpen($(this).data('topic'), $(this).data('q')); }});
            function open(cat, sub){{
                curCat = cat; curSub = sub || null; krOnly = false;
                render();
                $sheet.prop('hidden', false);
                requestAnimationFrame(function(){{ $sheet.addClass('is-open'); }});
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);  // 뒤로가기로 시트만 닫힘
            }}
            function close(){{ if (window.CFNav) CFNav.pop(); else closeVisual(); }}

            $(document).on('click', '.stat-count.has-reviews', function(){{
                open($(this).data('cat'), $(this).data('sub'));
            }});
            $(document).on('click', '.more-btn', function(){{ open($(this).data('cat')); }});
            $sheet.on('click', '.sheet-more-btn', function(){{ loadFull(render); }});
            $(document).on('click', '.sheet-chip', function(){{
                curSub = $(this).data('sub') || null; render();
            }});
            // 한국인 리뷰만: 정확한 한국어 총건 위해 미로드 상태면 전체 먼저 로드
            $sheet.on('click', '#sheet-kr', function(){{
                krOnly = !krOnly;
                if (krOnly && !qfull) loadFull(render); else render();
            }});
            var CATLIST = Object.keys(window.QSUBS);
            function shift(dir){{
                var i = (CATLIST.indexOf(curCat) + dir + CATLIST.length) % CATLIST.length;
                curCat = CATLIST[i]; curSub = null; render();
            }}
            $('#sheet-prev').on('click', function(){{ shift(-1); }});
            $('#sheet-next').on('click', function(){{ shift(1); }});
            $sheet.on('click', '.expand-btn', function(){{
                var $b = $(this), $full = $b.closest('.item').find('.full');
                var opened = !$full.prop('hidden');
                $full.prop('hidden', opened);
                $b.toggleClass('is-open', !opened);
                $b.closest('.item').find('.text').toggleClass('clamp', opened);
            }});
            $sheet.on('click', '.sheet-close, .sheet-dim', close);
            $(document).on('keydown', function(e){{ if (e.key === 'Escape') close(); }});
        }});

        // ───── 소셜 후기 (SOCIAL): 네이버 블로그 바텀시트 + 유튜브 lite-embed ─────
        $(function(){{
            // 블로그: 카드 탭 → 바텀시트 iframe (원본 그대로, X·딤·뒤로가기로 즉시 복귀)
            var $bs = $('#blog-sheet');
            function bsCloseVisual(){{
                $bs.removeClass('is-open');
                $('body').css('overflow', '');
                setTimeout(function(){{ $bs.prop('hidden', true); $('#bs-frame').attr('src', 'about:blank'); }}, 300);
            }}
            $(document).on('click', '.nb-card', function(){{
                if (!$bs.length) return;
                var u = $(this).data('url'), t = $(this).data('title');
                if (typeof gtag === 'function') {{
                    var hh = window.CF_HOTEL || {{}};
                    gtag('event', 'blog_open', {{hotel_name: hh.name || '', hotel_id: hh.pid || '', blog_url: u}});
                }}
                $('#bs-tit').text(t);
                $('#bs-link').attr('href', u);
                $('#bs-frame').attr('src', u);
                $bs.prop('hidden', false);
                void $bs[0].offsetHeight;               // 강제 reflow — hidden 해제가 transition에 반영되도록 (rAF는 백그라운드 탭에서 안 불림)
                $bs.addClass('is-open');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(bsCloseVisual);
            }});
            $bs.on('click', '.sheet-close, .sheet-dim', function(){{
                if (window.CFNav) CFNav.pop(); else bsCloseVisual();
            }});

            // 유튜브: 썸네일 탭 → 그 자리에서 플레이어 교체(자동재생, 이탈 없음)
            $(document).on('click', '.yt-card', function(){{
                var $c = $(this);
                if ($c.hasClass('is-playing')) return;
                var vid = $c.data('vid');
                if (typeof gtag === 'function') {{
                    var hh2 = window.CF_HOTEL || {{}};
                    gtag('event', 'video_play', {{hotel_name: hh2.name || '', hotel_id: hh2.pid || '', video_id: vid, video_title: $c.data('title') || ''}});
                }}
                $c.addClass('is-playing');
                $c.find('.yt-thumb').html('<iframe src="https://www.youtube-nocookie.com/embed/' + vid
                    + '?autoplay=1&playsinline=1&rel=0" title="YouTube" frameborder="0" '
                    + 'allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>');
            }});
        }});

        // ───── 리스크 아코디언 + 레이더 칩 + 한국인 필터 (§2-e·§3-b·§4·§5) ─────
        $(function(){{
            var $sect = $('#risk-detail');
            if (!$sect.length) return;

            // ── 월별 위험 흐름 라인차트 공통 생성 헬퍼 (카테고리·전체 공용) ──
            function makeTrendChart(canvasId, d){{
                var el = document.getElementById(canvasId); if (!el || !window.Chart || !d) return;
                var ctx = el.getContext('2d');
                var gW = ctx.createLinearGradient(0,0,0,130); gW.addColorStop(0,'rgba(240,160,40,.22)'); gW.addColorStop(1,'rgba(240,160,40,.02)');
                var gC = ctx.createLinearGradient(0,0,0,130); gC.addColorStop(0,'rgba(250,82,82,.22)'); gC.addColorStop(1,'rgba(250,82,82,.02)');
                var n = d.m.length, pr = Array(n).fill(0); pr[n-1] = 3;
                new Chart(ctx, {{type:'line', data:{{labels:d.m, datasets:[
                    {{label:'심각', data:d.c, borderColor:'#FA5252', backgroundColor:gC, fill:'origin', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#FA5252', stack:'risk'}},
                    {{label:'주의', data:d.w, borderColor:'#F0A028', backgroundColor:gW, fill:'-1', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#F0A028', stack:'risk'}},
                    {{label:'후쿠오카 평균', data:d.a, borderColor:'#B0B4BB', borderDash:[4,4], borderWidth:1.5, pointRadius:0, fill:false, tension:.35, stack:'avg'}}]}},
                  options:{{responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}},
                    plugins:{{legend:{{display:false}}, tooltip:{{displayColors:false, backgroundColor:'#fff', titleColor:'#232323', bodyColor:'#555B63',
                        borderColor:'#E8E9ED', borderWidth:1, cornerRadius:10, padding:10, footerColor:'#232323', footerFont:{{weight:'bold'}},
                        callbacks:{{label:function(t){{return t.dataset.label+' '+t.parsed.y.toFixed(1)+'%';}},
                            footer:function(items){{var s=0; items.forEach(function(it){{if(it.dataset.stack==='risk') s+=it.parsed.y;}}); return '합계 '+s.toFixed(1)+'%';}}}}}}}},
                    scales:{{x:{{grid:{{display:false}}, ticks:{{font:{{size:10}}, color:'#8B9097', maxRotation:0, autoSkip:true, maxTicksLimit:7}}}},
                            y:{{beginAtZero:true, stacked:true, grid:{{color:'#efefef'}}, border:{{display:false}},
                               ticks:{{font:{{size:10}}, color:'#8B9097', maxTicksLimit:4, callback:function(v){{return v+'%';}}}}}}}}}}}});
            }}


            // F7+F24: 월별 트렌드 폴드(전체·카테고리 공용) — 기본 접힘, 펼칠 때 1회 지연 렌더(0폭 canvas 함정 회피)
            var allTrendInited = false;
            var trendInited = {{}};
            $('#detail').on('click', '.trend-fold-btn', function(){{
                var $fold = $(this).closest('.trend-fold');
                $fold.toggleClass('is-open');
                if (!$fold.hasClass('is-open') || !window.TRENDC || !window.Chart) return;
                if ($fold.find('#cat-trend-all').length) {{
                    if (!allTrendInited && TRENDC['all']) {{ allTrendInited = true; makeTrendChart('cat-trend-all', TRENDC['all']); }}
                    return;
                }}
                var ci = $fold.data('ci');
                if (ci !== undefined && !trendInited[ci] && TRENDC[ci]) {{
                    trendInited[ci] = 1; makeTrendChart('cat-trend-'+ci, TRENDC[ci]);
                }}
            }});

            // 아코디언 재오픈 시: 이미 펼쳐둔 폴드가 있는데 차트 미생성이면 보완 초기화 (F24 가드)
            function initCatTrend($item){{
                var $fold = $item.find('.trend-fold.is-open'); if (!$fold.length) return;
                var ci = $fold.data('ci'); if (ci === undefined || trendInited[ci] || !window.TRENDC || !window.Chart || !TRENDC[ci]) return;
                trendInited[ci] = 1;
                makeTrendChart('cat-trend-'+ci, TRENDC[ci]);
            }}

            // 아코디언 토글 (헤더 클릭). sticky 스택은 CSS가 담당.
            $sect.on('click', '.risk-acc-head', function(){{
                var $item = $(this).closest('.risk-acc-item');
                $item.toggleClass('is-open');
                if ($item.hasClass('is-open')) initCatTrend($item);   // 펼칠 때만 init
            }});

            // F12 FAQ 필터 탭: 그룹별 카드 표시 토글 (전체=data-g 빈값)
            $('#hotel-faq').on('click', '.faq-tab', function(){{
                var g = String($(this).data('g') || '');
                $('#hotel-faq .faq-tab').removeClass('is-on');
                $(this).addClass('is-on');
                $('#hotel-faq .faq-card').each(function(){{
                    $(this).toggle(!g || $(this).data('group') === g);
                }});
            }});
            // F18 FAQ 카드 접힘/펼침 — Q줄 클릭은 토글(펼침 상태에서 접기 가능)
            $('#hotel-faq').on('click', '.faq-q', function(e){{
                $(this).closest('.faq-card').toggleClass('is-open');
                e.stopPropagation();   // 카드 레벨 핸들러 중복 방지
            }});
            // F29 접힘 상태 = 카드 박스 전체가 클릭 영역. 펼친 상태에선 내부 인터랙션(더보기·링크) 보존
            $('#hotel-faq').on('click', '.faq-card', function(){{
                if (!$(this).hasClass('is-open')) $(this).addClass('is-open');
            }});

            // 특정 카테고리 열고 그 위치로 스크롤 (칩·캔버스 공용)
            function openAndScroll(id){{
                var $item = $('#' + id);
                if (!$item.length) return;
                $item.addClass('is-open');
                initCatTrend($item);
                // 스택 헤더 높이만큼 보정해서 헤더가 바로 보이도록
                var top = $item.offset().top - 8;
                $('html, body').stop().animate({{scrollTop: top}}, 350);
            }}
            $('.radar-cats').on('click', '.radar-cat', function(){{
                openAndScroll($(this).data('target'));
            }});
            // 점프 칩(진입점·위치 섹션 공용): risk-* → 아코디언 오픈, faq-* → 해당 카드로 스크롤, hotel-faq → 섹션 앵커
            $('#detail').on('click', '.fj-btn', function(){{
                var t = String($(this).data('target') || '');
                if (t.indexOf('risk-') === 0) {{ openAndScroll(t); return; }}
                if (t.indexOf('faq-') === 0) $('#hotel-faq .faq-tab[data-g=""]').trigger('click');  // 전체 탭으로 카드 노출 보장
                var $el = $('#' + t); if (!$el.length) return;
                if ($el.hasClass('faq-card')) $el.addClass('is-open');   // F18: 점프 진입 시 답변까지 펼침
                $('html, body').stop().animate({{scrollTop: $el.offset().top - 8}}, 350);
            }});

            // 레이더 캔버스 클릭 → nearest 카테고리 아코디언 열기
            var chartEl = document.getElementById('radar');
            if (chartEl && window.Chart) {{
                chartEl.addEventListener('click', function(e){{
                    var ch = (Chart.getChart && Chart.getChart(chartEl)) || null;
                    if (!ch) return;
                    var pts = ch.getElementsAtEventForMode(e, 'nearest', {{intersect:false}}, true);
                    if (!pts || !pts.length) return;
                    var idx = pts[0].index;                 // CATS 원본 인덱스와 동일 순서
                    openAndScroll('risk-' + idx);
                }});
            }}

            // 초기 열림(1위) 카테고리 차트 즉시 init
            initCatTrend($sect.find('.risk-acc-item.is-open'));
        }});
    </script>''' + build_footer(1) + FOOT

# ───────────────────────── 컬렉션 허브 (HUB-NORMALIZE §3) ─────────────────────────
# 지역 3 + 테마 5. slug=URL(무확장), kind, H1, min N 가드. 선정 로직은 collection_members().
COLLECTIONS = [
    {'slug': 'area/tenjin', 'kind': 'area', 'area': 'tenjin', 'min': 10,
     'name': '텐진', 'h1': '후쿠오카 텐진 호텔 — 리뷰 위험도로 고른 안심 숙소',
     'title': '후쿠오카 텐진 호텔 TOP | 캐치플로'},
    {'slug': 'area/hakata', 'kind': 'area', 'area': 'hakata', 'min': 10,
     'name': '하카타역', 'h1': '하카타역 숙소 — 리뷰 위험도로 고른 안심 호텔',
     'title': '하카타역 호텔 TOP | 캐치플로'},
    {'slug': 'area/nakasu', 'kind': 'area', 'area': 'nakasu', 'min': 10,
     'name': '나카스·캐널시티', 'h1': '나카스·캐널시티 호텔 — 리뷰 위험도 비교',
     'title': '나카스·캐널시티 호텔 TOP | 캐치플로'},
    {'slug': 'best/value', 'kind': 'value', 'min': 8,
     'name': '가성비', 'h1': '후쿠오카 가성비 숙소 TOP — 가격대별 실망 확률 최저',
     'title': '후쿠오카 가성비 호텔 TOP | 캐치플로'},
    {'slug': 'best/capsule', 'kind': 'capsule', 'min': 3,
     'name': '캡슐호텔', 'h1': '후쿠오카 캡슐호텔 전부 비교 — 리뷰 위험도 순',
     'title': '후쿠오카 캡슐호텔 비교 | 캐치플로'},
    {'slug': 'best/pool', 'kind': 'pool', 'min': 3,
     'name': '수영장', 'h1': '후쿠오카 수영장 호텔 전부 비교 — 리뷰 위험도 순',
     'title': '후쿠오카 수영장 호텔 비교 | 캐치플로'},
    {'slug': 'best/family', 'kind': 'family', 'min': 8,
     'name': '가족여행', 'h1': '후쿠오카 가족여행 안심 호텔 — 방음·위생·안전 기준',
     'title': '후쿠오카 가족 호텔 TOP | 캐치플로'},
    {'slug': 'best/luxury', 'kind': 'luxury', 'min': 8,
     'name': '4·5성급', 'h1': '후쿠오카 4·5성급 호텔 — 고급 호텔 위험도 비교',
     'title': '후쿠오카 고급 호텔 TOP | 캐치플로'},
]
# 가족 안심 기준 카테고리 (위생, 방음=소음, 위치·안전) — TAXONOMY v4
FAMILY_CATS = ['위생', '소음', '위치·안전']

def _area_by_code(code):
    for a in AREAS:
        if a['code'] == code:
            return a
    return None

def _in_area(meta, area):
    lat, lng = meta.get('latitude'), meta.get('longitude')
    if not lat or not lng:
        return False
    return haversine_km(float(lat), float(lng), area['lat'], area['lng']) <= area['r']

def _is_capsule(pid, meta):
    """캡슐 매칭: 분류(hotel_stars) 정본 + 이름·부제 폴백.
       실측: 후쿠오카 캡슐 5곳은 '캡슐' 문자열이 아니라 캐빈/나인아워스 계열 명명 + 분류 '캡슐 호텔'."""
    if (meta.get('hotel_stars') or '') == '캡슐 호텔':
        return True
    title = (meta.get('title') or '') + ' ' + (meta.get('sub_title') or '')
    t = title.lower()
    if any(k in title for k in ('캡슐', '캐빈', '나인아워스', 'カプセル')) or 'capsule' in t or 'cabin' in t or 'nine hours' in t:
        return True
    am = meta.get('amenities') or {}
    etc = am.get('_etc') or [] if isinstance(am, dict) else []
    return any('캡슐' in str(x) or 'capsule' in str(x).lower() for x in etc)

def _has_pool(meta):
    am = meta.get('amenities') or {}
    return bool(isinstance(am, dict) and am.get('pool'))

def _stars_num(meta):
    m = re.match(r'(\d)성급', meta.get('hotel_stars') or '')
    return int(m.group(1)) if m else None

def collection_members(col, hotels_meta, H):
    """컬렉션 소속 scored 호텔 pid 리스트를 랭킹 순으로 반환. 데이터 부족 시 None(스킵).
       수집중(unscored)·rec_excluded(hotels_meta에서 이미 제외)는 랭킹에서 뺀다."""
    scored = [p for p in hotels_meta if p in H and H[p]['scored']]
    kind = col['kind']

    if kind == 'area':
        area = _area_by_code(col['area'])
        if not area:
            return None
        cand = [p for p in scored if _in_area(hotels_meta[p], area)]
        cand.sort(key=lambda p: H[p]['p_crit'])
        return cand

    if kind == 'value':
        # 하위 2밴드(b1·b2) × p_crit 낮은순
        cand = [p for p in scored if hotels_meta[p].get('band') and hotels_meta[p]['band'][0] in ('b1', 'b2')]
        cand.sort(key=lambda p: H[p]['p_crit'])
        return cand

    if kind == 'capsule':
        cand = [p for p in scored if _is_capsule(p, hotels_meta[p])]
        cand.sort(key=lambda p: H[p]['p_crit'])
        return cand

    if kind == 'pool':
        # amenities 의존 — 데이터 없으면 매칭 0 → 가드에서 스킵됨
        if not any(isinstance(hotels_meta[p].get('amenities'), dict) for p in hotels_meta):
            return None                      # amenities 컬럼 자체가 아직 없음 → 스킵
        cand = [p for p in scored if _has_pool(hotels_meta[p])]
        cand.sort(key=lambda p: H[p]['p_crit'])
        return cand

    if kind == 'family':
        # 방음·위생·안전 3개 카테고리 band != danger & scored, 그 3개 평균점수 낮은순
        cand = [p for p in scored
                if all(H[p]['cats'][c]['band'] != 'danger' for c in FAMILY_CATS)]
        cand.sort(key=lambda p: sum(H[p]['cats'][c]['score'] for c in FAMILY_CATS) / len(FAMILY_CATS))
        return cand

    if kind == 'luxury':
        cand = [p for p in scored if (_stars_num(hotels_meta[p]) or 0) >= 4]
        cand.sort(key=lambda p: H[p]['p_crit'])
        return cand

    return None

def collection_stats(pids, hotels_meta, H, city):
    """컬렉션 집계 수치: N곳·리뷰 M건·평균 실망확률%·최다 불만 카테고리·카테고리 편차 상위.
       반환 dict. reviews M = Σ analyzed."""
    n = len(pids)
    reviews = sum(H[p]['analyzed'] for p in pids)
    avg_p = pct(sum(H[p]['p_crit'] for p in pids) / n) if n else 0
    city_p = pct(city['crit'])
    # 카테고리 프로파일: 컬렉션 평균 카테고리 점수 vs 도시평균(=50). 편차 상위 2~3개.
    cat_avg = {c: sum(H[p]['cats'][c]['score'] for p in pids) / n for c in CATS} if n else {c: 50 for c in CATS}
    devs = sorted(((c, cat_avg[c] - 50.0) for c in CATS), key=lambda kv: -abs(kv[1]))
    top_dev = [(c, d) for c, d in devs if abs(d) >= 3.0][:3]   # 의미 있는 편차만
    worst_cat = max(CATS, key=lambda c: cat_avg[c]) if n else CATS[0]
    return {'n': n, 'reviews': reviews, 'avg_p': avg_p, 'city_p': city_p,
            'cat_avg': cat_avg, 'top_dev': top_dev, 'worst_cat': worst_cat}

def _col_href(slug, depth=0):
    """컬렉션 상대경로 링크 — 사이트 전역 무확장 규칙(canonical·sitemap과 동일 표기)."""
    return f'{"../" * depth}{slug}'

def hub_card(pid, meta, h, rank, depth=1):
    """허브 랭킹 카드 — 검색 리스트 카드와 픽셀 동일한 구조/클래스 재사용(#hub .hub-list 셀렉터 병기).
       고유 요소: 순위 배지(썸네일 좌상단)·역거리 1줄·시설 칩만 추가."""
    p_root = '../' * depth
    href = f'{p_root}hotels/{pid}'
    img = img_path(pid, meta, depth)
    name = E(meta['title'])
    st = station_line(meta)
    st_html = f'<div class="hub-station">{E(st)}</div>' if st else ''
    meta_html = f'<span>{E(meta.get("hotel_stars"))}</span>' if meta.get('hotel_stars') else ''
    chips = amenity_chips(meta, 3)
    chip_html = ''.join(f'<span class="hub-chip">{E(c)}</span>' for c in chips)
    chip_block = f'<div class="hub-chips">{chip_html}</div>' if chip_html else ''
    band, label = h['badge']
    return f'''<li class="hub-row">
        <div class="item">
            <div class="thumb">
                <span class="hub-rank">{rank}</span>
                <a href="{href}"><img src="{img}" alt="{name}" width="120" height="120" loading="lazy"></a>
            </div>
            <div class="cont">
                <div class="info">
                    <div class="name"><a href="{href}">{name}</a></div>
                    <div class="meta">{meta_html}</div>
                    {st_html}
                </div>
                <div class="bottom">
                    <div class="grade">
                        <div class="ico"><img src="{p_root}img/star.svg" alt=""></div>
                        <div class="num">{fmt_score(meta.get('total_score'))}</div>
                        <div class="txt">(리뷰 {meta.get('reviews_count') or 0:,}개)</div>
                    </div>
                    <div class="badge">
                        <div class="badge-item badge-{band}">{label}</div>
                        <div class="badge-item badge-down">실망 확률 {pct(h['p_crit'])}%</div>
                    </div>
                </div>
                {chip_block}
            </div>
        </div>
    </li>'''

def build_collection(col, pids, hotels_meta, H, city, monthly, monthly_cat, city_avg, other_cols):
    """컬렉션 허브 1페이지. pids=랭킹 순 소속 호텔(scored). other_cols=상호링크용 [(slug,name), ...]."""
    depth = 1                      # docs/area/x.html · docs/best/x.html → 루트까지 ../
    slug = col['slug']
    canonical = f'{BASE}/{slug}'
    stats = collection_stats(pids, hotels_meta, H, city)
    n, reviews, avg_p, city_p = stats['n'], stats['reviews'], stats['avg_p'], stats['city_p']
    worst_first = stats['worst_cat'].split(' ')[0]
    cmp_word = '낮아요' if avg_p <= city_p else '높아요'

    # ── 1. breadcrumb + H1 + 요약 2문장 ──
    summary = (f'{CITY["ko"]} {col["name"]} 지역 호텔 {n}곳의 리뷰 {reviews:,}건을 AI로 분석했어요. '
               if col['kind'] == 'area' else
               f'{col["h1"].split(" — ")[0]}, 총 {n}곳의 리뷰 {reviews:,}건을 AI로 분석했어요. ')
    summary2 = (f'평균 실망 확률은 {avg_p}%로 {CITY["ko"]} 평균({city_p}%)보다 {cmp_word}. '
                f'가장 많이 지적된 항목은 {worst_first}이에요.')
    summary_full = summary + summary2

    # ── 2. 리스크 리포트 카드 ──
    dev_rows = []
    for c, d in stats['top_dev']:
        word = c.split(' ')[0]
        sign = '높아요' if d > 0 else '낮아요'
        dev_rows.append(f'<li class="hub-dev is-{"up" if d>0 else "down"}"><span class="hd-cat">{E(word)}</span>'
                        f'<span class="hd-val">도시 평균 대비 {abs(round(d))}점 {sign}</span></li>')
    dev_html = f'<ul class="hub-devs">{"".join(dev_rows)}</ul>' if dev_rows else \
               '<div class="hub-dev-none">카테고리별로 도시 평균과 큰 차이가 없어요</div>'
    p_cmp_cls = 'is-good' if avg_p <= city_p else 'is-bad'
    risk_card = f'''<div class="hub-risk">
        <div class="hub-risk-top">
            <div class="hr-block"><span class="hr-label">이 컬렉션 평균 실망 확률</span><span class="hr-num {p_cmp_cls}">{avg_p}%</span></div>
            <div class="hr-block"><span class="hr-label">{CITY['ko']} 평균</span><span class="hr-num">{city_p}%</span></div>
        </div>
        <div class="hub-risk-prof">
            <div class="hr-prof-tit">카테고리 프로파일</div>
            {dev_html}
        </div>
    </div>'''

    # ── 3. 랭킹 리스트 TOP 10~15 ──
    is_all = col['kind'] in ('capsule', 'pool')     # 전부 비교 컬렉션
    top = pids if is_all else pids[:15]
    rank_cards = '\n'.join(hub_card(p, hotels_meta[p], H[p], i + 1, depth) for i, p in enumerate(top))
    rank_note = '조건에 맞는 곳을 전부 실망 확률 낮은 순으로 보여드려요' if is_all else \
                '실망 확률이 낮은 순이에요 (리뷰 수집중 호텔 제외)'
    rank_block = f'''<div class="hub-sect">
        <div class="hub-h2">실망 확률 낮은 순 TOP {len(top)}</div>
        <div class="hub-sub">{rank_note}</div>
        <ul class="hub-list">{rank_cards}</ul>
        <a class="hub-more" href="{'../' * depth}search{('?area=' + col['area']) if col['kind']=='area' else ''}">{CITY['ko']} 호텔 전체 검색 →</a>
    </div>'''

    # ── 4. 가격대별 베스트 (지역 컬렉션만) ──
    price_block = ''
    if col['kind'] == 'area':
        parts = []
        for code, label, lo, hi in PRICE_BANDS:
            band_pids = [p for p in pids if hotels_meta[p].get('band') and hotels_meta[p]['band'][0] == code][:2]
            if band_pids:
                items = ''.join(
                    f'<li class="hub-pb-item"><a href="{"../" * depth}hotels/{p}">'
                    f'<span class="pb-name">{E(hotels_meta[p]["title"])}</span>'
                    f'<span class="pb-p">실망 {pct(H[p]["p_crit"])}%</span></a></li>'
                    for p in band_pids)
                parts.append(f'<div class="hub-pb-band"><div class="pb-label">{E(label)}</div><ul>{items}</ul></div>')
        if parts:
            price_block = f'''<div class="hub-sect">
                <div class="hub-h2">가격대별 안심 숙소</div>
                <div class="hub-sub">가격대마다 실망 확률이 가장 낮은 곳이에요</div>
                <div class="hub-pb">{''.join(parts)}</div>
            </div>'''

    # ── 5. 조심 구간 ──
    n_danger = sum(1 for p in pids if H[p]['badge'][0] == 'danger')
    caution_block = ''
    if n_danger:
        caution_block = f'''<div class="hub-caution">
            <div class="hc-tit">이 중 위험 등급 {n_danger}곳</div>
            <div class="hc-txt">공통적으로 <b>{E(worst_first)}</b> 관련 불만이 많아요. 호텔명은 검색에서 확인하세요.</div>
            <a class="hc-link" href="{'../' * depth}search{('?area=' + col['area']) if col['kind']=='area' else ''}">검색에서 확인하기 →</a>
        </div>'''

    # ── 6. FAQ (FAQPage JSON-LD) ──
    faqs = build_collection_faq(col, stats, pids, hotels_meta, H, city)
    faq_items = ''.join(
        f'<div class="hub-faq-item"><div class="hf-q">{E(q)}</div><div class="hf-a">{a}</div></div>'
        for q, a, _ in faqs)
    faq_block = f'''<div class="hub-sect">
        <div class="hub-h2">자주 묻는 질문</div>
        <div class="hub-faqs">{faq_items}</div>
    </div>'''

    # ── 7. 다른 컬렉션 카드 (상호 링크) + 방법론 ──
    link_cards = ''.join(
        f'<a class="hub-xlink" href="{_col_href(s, depth)}">{E(nm)}</a>'
        for s, nm in other_cols if s != slug)
    xlink_block = f'''<div class="hub-sect">
        <div class="hub-h2">다른 컬렉션도 보기</div>
        <div class="hub-xlinks">{link_cards}</div>
        <div class="hub-method">실망 확률 = 심각 태그 리뷰의 최신성 가중 비율 · 리뷰 6만 건 분석 · 기준 {CITY['data_asof']}</div>
    </div>'''

    # ── 메타·JSON-LD ──
    og_img = hotels_meta[pids[0]].get('r2_img') if pids else None
    itemlist = {'@context': 'https://schema.org', '@type': 'ItemList', 'name': col['h1'],
                'itemListElement': [
                    {'@type': 'ListItem', 'position': i + 1, 'name': hotels_meta[p]['title'],
                     'url': f'{BASE}/hotels/{p}'}
                    for i, p in enumerate(top)]}
    faqpage = {'@context': 'https://schema.org', '@type': 'FAQPage',
               'mainEntity': [{'@type': 'Question', 'name': q,
                               'acceptedAnswer': {'@type': 'Answer', 'text': a_plain}}
                              for q, _a, a_plain in faqs]}
    crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList',
              'itemListElement': [
                  {'@type': 'ListItem', 'position': 1, 'name': '캐치플로', 'item': f'{BASE}/'},
                  {'@type': 'ListItem', 'position': 2, 'name': f'{CITY["ko"]} 호텔', 'item': f'{BASE}/search'},
                  {'@type': 'ListItem', 'position': 3, 'name': col['name'], 'item': canonical}]}
    ld = _jsonld(itemlist) + '\n' + _jsonld(faqpage) + '\n' + _jsonld(crumbs)

    return head(col['title'], depth=depth, description=summary_full, canonical=canonical,
                og_image=og_img, extra_head=ld) + header_nav(depth) + f'''
    <main id="container">
        <section id="hub">
            <nav class="hub-crumb"><a href="{'../' * depth}">캐치플로</a> › <a href="{'../' * depth}search">{CITY['ko']} 호텔</a> › <span>{E(col['name'])}</span></nav>
            <h1 class="hub-h1">{E(col['h1'])}</h1>
            <p class="hub-summary">{E(summary_full)}</p>
            <div class="hub-stat-strip">
                <span class="hs-item"><b>{n}</b>곳 분석</span>
                <span class="hs-item"><b>{reviews:,}</b>건 리뷰</span>
                <span class="hs-item">평균 실망 <b>{avg_p}%</b></span>
            </div>
            {risk_card}
            {rank_block}
            {price_block}
            {caution_block}
            {faq_block}
            {xlink_block}
        </section>
    </main>''' + build_footer(1) + FOOT

def build_collection_faq(col, stats, pids, hotels_meta, H, city):
    """컬렉션 FAQ 3문 (§3-e). 반환 [(질문, 답변HTML, 답변plain), ...]."""
    n, reviews, avg_p, city_p = stats['n'], stats['reviews'], stats['avg_p'], stats['city_p']
    name = col['name']
    kind = col['kind']
    faqs = []

    # (1) 분석 규모
    q1 = f'{name} 호텔은 몇 곳을 분석했나요?'
    a1p = f'{CITY["ko"]} {name} 관련 호텔 {n}곳, 리뷰 {reviews:,}건을 AI로 분석했어요. 평균 실망 확률은 {avg_p}%예요.'
    faqs.append((q1, E(a1p), a1p))

    # (2) 컬렉션 고유 질문
    if kind == 'area':
        # 지역: ○○ vs 하카타 비교 (하카타 평균과 대조)
        other = 'hakata' if col['area'] != 'hakata' else 'tenjin'
        other_area = _area_by_code(other)
        other_ko = other_area['ko'] if other_area else '하카타'
        other_pids = [p for p in hotels_meta if p in H and H[p]['scored'] and _in_area(hotels_meta[p], other_area)] if other_area else []
        other_p = pct(sum(H[p]['p_crit'] for p in other_pids) / len(other_pids)) if other_pids else None
        q2 = f'{name} vs {other_ko}, 어디에 잡을까요?'
        if other_p is not None:
            cmp_w = '더 낮아' if avg_p < other_p else ('더 높아' if avg_p > other_p else '비슷해')
            a2p = f'{name} 평균 실망 확률은 {avg_p}%, {other_ko}는 {other_p}%예요. {name}가 {cmp_w} {"안심할 만해요" if avg_p<=other_p else "조금 더 주의가 필요해요"}. 역·번화가 접근성도 함께 보고 고르세요.'
        else:
            a2p = f'{name} 평균 실망 확률은 {avg_p}%예요. 지역별 편차가 있으니 개별 호텔 리포트를 함께 확인하세요.'
        faqs.append((q2, E(a2p), a2p))
    elif kind in ('capsule', 'pool'):
        typ = '캡슐호텔' if kind == 'capsule' else '수영장 있는 호텔'
        q2 = f'{CITY["ko"]}에 {typ}은 총 몇 곳인가요?'
        a2p = f'캐치플로가 분석한 {CITY["ko"]} {typ}은 총 {n}곳이에요. 이 페이지에서 전부 실망 확률 순으로 비교할 수 있어요.'
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'value':
        best_pid = pids[0] if pids else None
        q2 = '10만원 이하에서 실망 확률이 가장 낮은 곳은?'
        if best_pid:
            a2p = f'현재 기준 {E(hotels_meta[best_pid]["title"])}가 실망 확률 {pct(H[best_pid]["p_crit"])}%로 가장 낮아요. 가격은 스크랩 시점 기준이라 실제 예약가는 확인이 필요해요.'
            faqs.append((q2, f'현재 기준 <b>{E(hotels_meta[best_pid]["title"])}</b>가 실망 확률 {pct(H[best_pid]["p_crit"])}%로 가장 낮아요. 가격은 스크랩 시점 기준이라 실제 예약가는 확인이 필요해요.', a2p))
        else:
            a2p = '가격대별 실망 확률이 가장 낮은 곳을 위 랭킹에서 확인하세요.'
            faqs.append((q2, E(a2p), a2p))
    elif kind == 'family':
        q2 = '가족여행 호텔은 뭘 봐야 하나요?'
        a2p = '아이와 함께라면 방음(옆방·복도 소음), 위생(침구·해충), 안전(보안·프라이버시) 3가지가 특히 중요해요. 이 페이지는 세 항목이 모두 위험 등급이 아닌 곳만 골라 평균 점수가 낮은 순으로 보여드려요.'
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'luxury':
        # 비싼 호텔이 실망확률도 낮은가 — 럭셔리 평균 vs 도시평균
        q2 = '비싼 호텔은 실망 확률도 낮나요?'
        rel = '낮은 편이에요' if avg_p < city_p else ('오히려 높은 편이에요' if avg_p > city_p else '도시 평균과 비슷해요')
        a2p = f'4·5성급 {n}곳의 평균 실망 확률은 {avg_p}%로 {CITY["ko"]} 평균({city_p}%)보다 {rel}. 등급이 높아도 개별 편차가 크니 리포트를 꼭 확인하세요.'
        faqs.append((q2, E(a2p), a2p))

    # (3) 데이터 기준일
    q3 = '데이터는 언제 기준인가요?'
    a3p = f'리뷰 데이터는 주간 단위로 갱신돼요. 현재 페이지는 {CITY["data_asof"]} 기준으로 집계했어요.'
    faqs.append((q3, E(a3p), a3p))
    return faqs

# ───────────────────────── about (LEGAL-SOFTEN §2-c) ─────────────────────────
def build_about(hotels_meta, H, city):
    """서비스 소개·방법론·한계·정정창구·제휴고지. E-E-A-T 겸용. sitemap priority 0.5."""
    n_live = sum(1 for p in hotels_meta if p in H)
    try:
        _total = sum(r['n'] for r in json.load(open(os.path.join(SRC, 'agg_denom.json'), encoding='utf-8')))
        reviews_txt = f'{_total:,}건'
    except Exception:
        reviews_txt = '수만 건'
    asof = CITY['data_asof']
    avg_pct = pct(city['crit'])
    desc = (f'{CITY["ko"]} 호텔 {n_live}곳의 공개 리뷰를 AI로 분석해 실망 확률을 계산하는 방법과 '
            '데이터 출처·한계, 정정 창구를 안내합니다.')

    def sect(title, body):
        return (f'<div class="sect about-sect"><div class="head"><div class="title">{E(title)}</div></div>'
                f'<div class="about-body">{body}</div></div>')

    s1 = sect('무엇을 하는 서비스인가요',
        f'캐치플로는 {CITY["ko"]} 호텔 {n_live}곳의 공개 리뷰 {reviews_txt}을 AI로 분석해, '
        '심각한 불만이 언급된 비율을 <b>실망 확률</b>로 보여드립니다. '
        '별점에 묻힌 치명적인 단점을 예약 전에 미리 확인하실 수 있어요.')
    s2 = sect('실망 확률은 이렇게 계산해요',
        '<ul class="about-list">'
        '<li>최근 12개월 이내 리뷰에 더 높은 가중치를 둬요</li>'
        f'<li>{CITY["ko"]} 평균을 50으로 두고 상대적인 위험도로 환산해요</li>'
        '<li>분석된 리뷰가 30건 미만이면 신뢰도가 낮아 확률을 공개하지 않아요</li>'
        '<li>불만 표본이 5건 미만인 소분류에는 위험 등급을 붙이지 않아요</li>'
        '</ul>')
    s3 = sect('데이터 출처와 한계',
        '<ul class="about-list">'
        '<li>구글 지도 등 공개 플랫폼의 실제 투숙객 리뷰를 사용해요</li>'
        f'<li>매주 갱신하며, 현재 페이지는 {asof} 기준({CITY["ko"]} 평균 실망 확률 {avg_pct}%)이에요</li>'
        '<li><b>AI 분석은 통계적 의견이며 오류가 있을 수 있고, 실제 이용 경험과 다를 수 있어요</b></li>'
        '<li>예약 판단의 유일한 근거로 삼지 마시고, 개별 리뷰 원문도 함께 확인하세요</li>'
        '</ul>')
    s4 = sect('정정·이의제기',
        f'본인 업소 정보의 사실 오류나 이의가 있으시면 '
        f'<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>로 알려주세요. 확인 후 신속히 반영합니다.')
    s5 = sect('제휴 고지',
        '일부 예약 링크는 제휴 링크일 수 있으며, 예약 시 캐치플로가 수수료를 받을 수 있어요. '
        '수수료는 분석 결과에 영향을 주지 않습니다.')

    return head('캐치플로 소개 — 실망 확률은 이렇게 계산해요', depth=0,
                description=desc, canonical=f'{BASE}/about') + header_nav() + f'''
    <main id="container">
        <section id="about">
            <h1 class="about-h1">캐치플로 소개</h1>
            <p class="about-lead">공개된 투숙객 리뷰를 AI로 분석해, 예약 전에 알아야 할 위험을 알려드려요.</p>
            {s1}{s2}{s3}{s4}{s5}
        </section>
    </main>''' + build_footer(0) + FOOT

# ───────────────────────── main ─────────────────────────
def city_averages(monthly, monthly_cat):
    """빌드타임 도시(후쿠오카) 평균 시리즈 (TREND-V2 §2-a). 전 호텔 monthly 합산 기준
    — rec_excluded 호텔이 hotels_meta에서 빠져도 monthly.json엔 있으므로 도시 평균은 전 호텔 유지.
    반환: (city_n{ym:n}, city_avg{ym:pct}, city_cat_avg{(ym,cat):pct}). 분모는 city_n[ym]."""
    city_n = defaultdict(int)      # {ym: Σ n}
    city_risk = defaultdict(int)   # {ym: Σ (n_crit+n_warn)}  전체 차트용
    for pid, mdata in monthly.items():
        for ym, (n, nc, nw) in mdata.items():
            city_n[ym] += n
            city_risk[ym] += nc + nw
    city_cat_risk = defaultdict(int)  # {(ym,cat): Σ (n_crit+n_warn)}
    for pid, mcdata in monthly_cat.items():
        for (ym, cat), (nc, nw) in mcdata.items():
            city_cat_risk[(ym, cat)] += nc + nw
    city_avg = {ym: round(city_risk[ym] / city_n[ym] * 100, 1) if city_n[ym] else 0.0 for ym in city_n}
    city_cat_avg = {k: round(city_cat_risk[k] / city_n[k[0]] * 100, 1) if city_n.get(k[0]) else 0.0
                    for k in city_cat_risk}
    return city_n, city_avg, city_cat_avg


ROBOTS_TXT = f'''User-agent: *
Allow: /

Sitemap: {BASE}/sitemap.xml
'''

def build_sitemap(detail_pids, collection_slugs=()):
    lastmod = CITY['asof'] or time.strftime('%Y-%m-%d')   # meta.json asof(YYYY-MM-DD), 없으면 빌드일
    rows = [(f'{BASE}/', 'daily', '1.0'),
            (f'{BASE}/search', 'daily', '0.9'),
            (f'{BASE}/about', 'monthly', '0.5'),   # 소개·방법론 (LEGAL-SOFTEN §2-c)
            *[(f'{BASE}/{slug}', 'weekly', '0.9') for slug in collection_slugs],   # 허브 priority 0.9
            *[(f'{BASE}/hotels/{pid}', 'weekly', '0.8') for pid in detail_pids]]
    urls = '\n'.join(
        f'  <url><loc>{E(loc)}</loc><lastmod>{lastmod}</lastmod>'
        f'<changefreq>{cf}</changefreq><priority>{pr}</priority></url>'
        for loc, cf, pr in rows)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'{urls}\n</urlset>\n')


def main():
    city, H = compute(SRC)
    hotels_meta, quotes, stars, kr_stats, monthly, monthly_cat, faq_data, social_data = load()
    city_n, city_avg, city_cat_avg = city_averages(monthly, monthly_cat)

    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, 'hotels'))
    os.makedirs(os.path.join(OUT, 'data'))
    for d in ('css', 'js', 'img'):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(OUT, d))
    hotels_img = os.path.join(ROOT, 'assets', 'hotels')
    if os.path.exists(hotels_img):
        shutil.copytree(hotels_img, os.path.join(OUT, 'img', 'hotels'))

    def W(path, s):
        full = os.path.join(OUT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)   # 하위 디렉토리(area/·best/) 자동 생성
        open(full, 'w', encoding='utf-8').write(s)

    # ── 컬렉션 허브 선정 (index·detail보다 먼저 — 홈 칩·상세 칩이 built_cols 참조) ──
    built_cols = []          # [(col, pids), ...] 가드 통과분
    skipped_cols = []        # [(slug, 사유), ...]
    for col in COLLECTIONS:
        pids = collection_members(col, hotels_meta, H)
        if pids is None:
            skipped_cols.append((col['slug'], '의존 데이터 없음'))
            continue
        if len(pids) < col['min']:
            skipped_cols.append((col['slug'], f'{len(pids)}곳 < 최소 {col["min"]}'))
            continue
        built_cols.append((col, pids))
    col_index = [(c['slug'], c['name']) for c, _ in built_cols]   # 상호링크·홈칩·상세칩 공용

    W('index.html', build_index(hotels_meta, H, quotes, col_index))
    W('search.html', build_search(pct(city['crit'])))
    W('404.html', build_404())
    W('recent.html', build_recent(hotels_meta, H))   # F40: 개인화 페이지 — sitemap 제외
    W('about.html', build_about(hotels_meta, H, city))
    idx = build_search_index(hotels_meta, H)
    W('data/index.js', 'window.HOTELS=' + json.dumps(idx, ensure_ascii=False) + ';')
    W('data/search_index.js', 'window.CF_IDX=' + build_search_ac_index(hotels_meta, H) + ';')
    open(os.path.join(OUT, '.nojekyll'), 'w').close()

    # 상세 컬렉션 칩용: pid → [(slug, name), ...] (지역 1 + 테마 매칭, 최대 3)
    detail_col_map = defaultdict(list)
    for col, pids in built_cols:
        for p in pids:
            detail_col_map[p].append((col['slug'], col['name']))

    krrank = kr_rank_map(kr_stats)
    kr_dist = kr_ratio_dist(kr_stats)
    critrank = crit_rank_map(H)
    written = []
    for pid, meta in hotels_meta.items():
        if pid not in H: continue
        W(f'hotels/{pid}.html', build_detail(pid, meta, H[pid], quotes, stars, city, hotels_meta, H,
            kr_stats.get((pid, 'all')), krrank.get(pid), kr_stats.get((pid, '1y')), monthly, monthly_cat,
            city_avg, city_cat_avg, crit_rank_pct=critrank.get(pid),
            hotel_cols=detail_col_map.get(pid, [])[:3], kr_dist=kr_dist, faq=faq_data.get(pid),
            social=social_data.get(pid)))
        written.append(pid)
    n = len(written)

    # ── 컬렉션 허브 페이지 생성 ──
    for col, pids in built_cols:
        W(f'{col["slug"]}.html', build_collection(col, pids, hotels_meta, H, city,
            monthly, monthly_cat, city_avg, col_index))

    W('robots.txt', ROBOTS_TXT)
    col_slugs = [c['slug'] for c, _ in built_cols]
    W('sitemap.xml', build_sitemap(written, col_slugs))
    scored = sum(1 for p in H if H[p]['scored'])
    sitemap_n = n + 3 + len(col_slugs)   # 홈·검색·about + 허브 + 상세
    print(f'OK: 상세 {n}p (점수 노출 {scored}, 수집중 {n - scored}) · sitemap {sitemap_n} URL · 도시평균 실망확률 {pct(city["crit"])}%')
    print(f'컬렉션 생성 {len(built_cols)}개: ' + ', '.join(f'{c["slug"]}({len(p)})' for c, p in built_cols))
    if skipped_cols:
        print('컬렉션 스킵 ' + str(len(skipped_cols)) + '개: ' + ', '.join(f'{s}({r})' for s, r in skipped_cols))

if __name__ == '__main__':
    main()
