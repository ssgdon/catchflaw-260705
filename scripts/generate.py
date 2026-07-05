# -*- coding: utf-8 -*-
"""캐치플로 정적 사이트 생성기 — data-src/*.json → docs/
사용: python scripts/generate.py
"""
import json, os, shutil, sys, html, re, time
from collections import defaultdict

BUILD = str(int(time.time()))  # 에셋 캐시버스터

sys.path.insert(0, os.path.dirname(__file__))
from scoring import compute, CATS, SUBS, SUB_KEYWORDS, MIN_REVIEWS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data-src')
OUT = os.path.join(ROOT, 'docs')

# ───────────────────────── 도시 설정 (변수화 — 신규 도시는 여기만 추가) ─────────────────────────
CITY = {'code': 'fukuoka', 'ko': '후쿠오카', 'en': 'Fukuoka', 'data_asof': '2026년 3월'}
UNSUPPORTED_KEYWORDS = ['도쿄', 'tokyo', '오사카', 'osaka', '교토', 'kyoto', '삿포로', 'sapporo',
    '나고야', 'nagoya', '오키나와', 'okinawa', '서울', 'seoul', '부산', 'busan', '제주', 'jeju',
    '방콕', 'bangkok', '다낭', 'danang', '나트랑', '타이베이', 'taipei', '싱가포르', 'singapore',
    '홍콩', 'hongkong', 'hong kong', '괌', 'guam', '세부', 'cebu', '파리', 'paris', '런던', 'london']

CAT_ICON = {'위생 경보': '🧼', '오감 지옥': '👂', '시설 사기단': '🏚️', '동선 파괴자': '🗺️', '불친절 레이더': '💬', '안전 그림자': '🔒'}
BAND_KO = {'danger': '위험', 'warning': '주의', 'safe': '양호'}
GAUGE_MAX = 40.0  # 실망확률 게이지 상한(%)

# ── 인기 지역 (한국인 자주 검색, 좌표+반경km) — 신규 지역은 여기만 추가 ──
AREAS = [
    {'code': 'hakata', 'ko': '하카타역', 'lat': 33.5897, 'lng': 130.4207, 'r': 1.3},
    {'code': 'tenjin', 'ko': '텐진', 'lat': 33.5914, 'lng': 130.3986, 'r': 1.2},
    {'code': 'nakasu', 'ko': '나카스·캐널시티', 'lat': 33.5930, 'lng': 130.4085, 'r': 1.0},
    {'code': 'gion', 'ko': '기온·오호리', 'lat': 33.5915, 'lng': 130.4120, 'r': 1.0},
]

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

def load():
    J = lambda f: json.load(open(os.path.join(SRC, f), encoding='utf-8'))
    hotels_meta = {h['place_id']: h for h in J('hotels.json')}
    # 자체 호스팅 이미지 (scripts/fetch_images.py 로 다운로드된 것만) + 가격 파싱
    for pid, m in hotels_meta.items():
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
    return hotels_meta, quotes, stars

# ───────────────────────── 공통 조각 ─────────────────────────
def head(title, depth=0):
    p = '../' * depth
    return f'''<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0, user-scalable=yes">
    <title>{E(title)}</title>
    <link rel="stylesheet" href="{p}css/tokens.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/common.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/layout.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/swiper.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/uplift.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/mvp.css?v={BUILD}">
    <script src="{p}js/backnav.js?v={BUILD}"></script>
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="{p}js/swiper.js"></script>
    <script>window.CF_SB={{url:'{SUPABASE_URL}',key:'{SUPABASE_ANON}'}};window.CF_AREAS={json.dumps(AREAS, ensure_ascii=False)};</script>
    <script src="{p}js/engage.js?v={BUILD}" defer></script>
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
            <h1 class="logo"><a href="{p}index.html"><img src="{p}img/logo.svg" alt="CATCHFLAW"></a></h1>
        </div></div>
    </header>'''

def badge_html(h):
    if not h['scored']:
        return '<div class="badge-item badge-collect">리뷰 수집중</div>'
    band, label = h['badge']
    return (f'<div class="badge-item badge-{band}">{label}</div>'
            f'<div class="badge-item badge-down">실망 확률 {pct(h["p_crit"])}%</div>')

def img_path(pid, meta, depth=0):
    p = '../' * depth
    return f'{p}img/hotels/{pid}.jpg' if meta.get('local_img') else f'{p}img/placeholder.svg'

def fmt_score(v):
    try: return f'{float(v):.1f}'
    except (TypeError, ValueError): return '-'

def hotel_card(pid, meta, h, depth=0):
    p = '../' * depth
    star_w = round(float(meta.get('total_score') or 0) / 5 * 100)
    return f'''<li class="swiper-slide">
        <a href="{p}hotels/{pid}.html" class="item">
            <div class="thumb">
                <div class="badge">{badge_html(h)}</div>
                <div class="image"><img src="{img_path(pid, meta, depth)}" alt="{E(meta['title'])}" loading="lazy"></div>
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
def build_index(hotels_meta, H, quotes):
    scored = [p for p in H if H[p]['scored'] and p in hotels_meta]

    def worst_by_sub(mcat, scat, k=8):
        cand = [p for p in scored if H[p]['cats'][mcat]['subs'][scat]['count'] >= 5]
        return sorted(cand, key=lambda p: -H[p]['cats'][mcat]['subs'][scat]['score'])[:k]

    best = sorted(scored, key=lambda p: H[p]['p_crit'])[:8]
    cur1 = worst_by_sub('위생 경보', '해충/곰팡이')
    cur2 = worst_by_sub('오감 지옥', '악취 역류')

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

    html_out = head('캐치플로 — 그 호텔, 최악의 리뷰는요?') + f'''
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
                        <div class="tit">잠깐, 그 호텔 <br><span>최악의 리뷰</span>는요?</div>
                        <div class="txt">AI가 {CITY['ko']} 호텔 리뷰 4만 8천 개를 분석해 <br><span>치명적인 단점</span>만 찾아냅니다.</div>
                    </div>
                    <form class="input" action="./search.html" method="get" autocomplete="off">
                        <input type="text" name="q" id="hero-q" placeholder="{CITY['ko']} 호텔명 또는 구글맵 링크 붙여넣기">
                        <button type="submit"><img src="./img/search.svg" alt="검색"></button>
                        <div class="ac-box" id="ac-box" hidden></div>
                    </form>
                    <div class="scope-note">현재 <b>{CITY['ko']}</b> 호텔 {len(scored)}곳 분석 완료 · 다른 도시는 준비 중이에요</div>
                </div>
            </article>
            <article class="section sec-map">
                <div class="home-map init">
                    <div class="head"><div class="title">지도로 한눈에 보기</div>
                    <div class="desc">마커 색은 캐치플로 등급이에요 · 눌러서 실망 확률을 확인하세요</div></div>
                    <div class="map-wrap"><div id="map"></div>
                        <div class="map-legend">
                            <span class="lg safe">양호</span><span class="lg warning">주의</span><span class="lg danger">위험</span><span class="lg none">수집중</span>
                        </div>
                    </div>
                    <div class="map-more"><a href="./search.html">가격·지역·등급으로 딱 맞는 호텔 찾기 →</a></div>
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
    </main>
    <script src="./data/index.js?v={BUILD}"></script>
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
                + '<a class="pop-link" href="./hotels/' + h.id + '.html">캐치플로 분석 보기 →</a></div>');
            pts.push([h.lat, h.lng]);
        }});
        if (pts.length) map.fitBounds(pts, {{padding: [24, 24], maxZoom: 14}});
    }});

    // ───── 메인 검색: 자동완성 + 구글맵 URL 인식 ─────
    $(function(){{
        var $q = $('#hero-q'), $box = $('#ac-box');
        function norm(s){{ return (s||'').toLowerCase().replace(/\\s+/g,''); }}

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

        function render(list){{
            if (!list.length) {{ $box.prop('hidden', true); return; }}
            $box.prop('hidden', false).html(list.map(function(h){{
                var chip = h.p != null ? '<span class="ac-p">실망 ' + h.p + '%</span>' : '<span class="ac-p dim">수집중</span>';
                return '<a class="ac-item" href="./hotels/' + h.id + '.html"><span class="ac-name">' + h.name + '</span>' + chip + '</a>';
            }}).join(''));
        }}

        // 인기 지역 (입력 전 포커스 시 노출)
        function showAreas(){{
            var areas = window.CF_AREAS || [];
            if (!areas.length) {{ $box.prop('hidden', true); return; }}
            $box.prop('hidden', false).html(
                '<div class="ac-section">🔥 후쿠오카 인기 지역</div>' +
                areas.map(function(a){{
                    return '<a class="ac-area" href="./search.html?area=' + a.code + '">'
                        + '<span class="ac-emoji">📍</span><span>' + a.ko + '</span>'
                        + '<span class="ac-sub">이 지역 호텔 보기</span></a>';
                }}).join(''));
        }}
        $q.on('focus', function(){{ if (!$q.val().trim()) showAreas(); }});

        $q.on('input', function(){{
            var v = $q.val().trim();
            if (!v) {{ showAreas(); return; }}
            if (/^https?:\\/\\//.test(v) || v.indexOf('maps.app.goo.gl') >= 0 || v.indexOf('google.') >= 0) {{
                var hit = resolveUrl(v);
                if (hit) {{ render([hit]); }}
                else {{
                    $box.prop('hidden', false).html('<div class="ac-none">링크에서 호텔을 찾지 못했어요. 호텔 이름으로 검색해 보세요!</div>');
                }}
                return;
            }}
            var nq = norm(v);
            render(HOTELS.filter(function(h){{
                return norm(h.name).indexOf(nq) >= 0 || norm(h.en).indexOf(nq) >= 0;
            }}).slice(0, 6));
        }});
        $(document).on('click', function(e){{
            if (!$(e.target).closest('.input').length) $box.prop('hidden', true);
        }});
        $q.closest('form').on('submit', function(e){{
            var v = $q.val().trim();
            if (/^https?:\\/\\//.test(v)) {{
                e.preventDefault();
                var hit = resolveUrl(v);
                if (hit) location.href = './hotels/' + hit.id + '.html';
                else location.href = './search.html?q=' + encodeURIComponent(v);
            }}
        }});
    }});
    </script>''' + FOOT
    return html_out

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
            'img': f'img/hotels/{pid}.jpg' if meta.get('local_img') else '',
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

def build_search(city_avg_pct):
    kw = json.dumps(UNSUPPORTED_KEYWORDS, ensure_ascii=False)
    cats_js = json.dumps([{'ko': c, 'ico': CAT_ICON[c]} for c in CATS], ensure_ascii=False)
    area_chips = ''.join(
        f'<button type="button" class="f-chip" data-area="{a["code"]}">{a["ko"]}</button>' for a in AREAS)
    return head('캐치플로 — 검색') + f'''
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <main id="container">
        <section id="title">
            <div class="back"><a href="./index.html" class="btn-back"><img src="./img/back_b.svg" alt="뒤로가기"></a></div>
            <div class="search">
                <button type="button" id="btn-search"><img src="./img/search_g.svg" alt="검색"></button>
                <input type="text" id="q" placeholder="{CITY['ko']} 호텔명 검색 또는 구글맵 링크">
            </div>
        </section>
        <section id="search">
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
                    <button type="button" class="f-more" id="open-catfilter">⚙ 항목별 필터</button>
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
                        <button type="button" data-sort="cat:위생 경보">🧼 위생 안심순</button>
                        <button type="button" data-sort="cat:오감 지옥">👂 오감 안심순</button>
                        <button type="button" data-sort="cat:시설 사기단">🏚️ 시설 안심순</button>
                        <button type="button" data-sort="cat:동선 파괴자">🗺️ 동선 안심순</button>
                        <button type="button" data-sort="cat:불친절 레이더">💬 불친절 안심순</button>
                        <button type="button" data-sort="cat:안전 그림자">🔒 안전 안심순</button>
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
        var CAT_ICON = {{'위생 경보':'🧼','오감 지옥':'👂','시설 사기단':'🏚️','동선 파괴자':'🗺️','불친절 레이더':'💬','안전 그림자':'🔒'}};
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
        setTimeout(function(){{ map.invalidateSize(); if (baseList.length) {{ drawMap(baseList, true); }} }}, 80);
        $(window).on('load', function(){{ map.invalidateSize(); }});

        function popupHtml(h){{
            var col = h.band ? BAND_COLOR[h.band] : '#9CA3AF';
            var chip = h.p != null ? '<span class="pop-p" style="background:'+col+'">실망 확률 '+h.p+'%</span>'
                                   : '<span class="pop-p" style="background:#9CA3AF">리뷰 수집중</span>';
            return '<div class="map-pop"><b>'+h.name+'</b>'
                + '<div class="pop-meta">★ '+(h.g?h.g.toFixed(1):'-')+' ('+h.rc.toLocaleString()+')'
                + (h.pt?' · 1박 '+h.pt:'')+'</div>'+chip
                + '<a class="pop-link" href="./hotels/'+h.id+'.html">캐치플로 분석 보기 →</a></div>';
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
            var img = h.img ? './'+h.img : './img/placeholder.svg';
            var price = h.pt ? '<span class="price">1박 <b>'+h.pt+'</b></span>' : '';
            return '<li><div class="item">'
                + '<div class="thumb"><a href="./hotels/'+h.id+'.html"><img src="'+img+'" loading="lazy"></a></div>'
                + '<div class="cont">'
                + '<div class="info">'
                + '<div class="name"><a href="./hotels/'+h.id+'.html">'+h.name+'</a></div>'
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
                '<div class="notice-card"><div class="notice-emoji">🙏</div>'
                + '<div class="notice-tit">아직 <b>'+CITY_KO+'</b>만 지원해요</div>'
                + '<div class="notice-txt">&ldquo;'+q+'&rdquo; 지역은 준비 중이에요.<br>'+CITY_KO+' 호텔은 전부 분석되어 있으니 먼저 둘러보세요!</div>'
                + '<a class="notice-btn" href="./search.html">'+CITY_KO+' 호텔 전체 보기</a></div>');
            $res.html('');
        }}

        function run(){{
            var q = $q.val().trim();
            $notice.hide();
            var pool = HOTELS.filter(passFilters);
            if (q){{
                var nq = norm(q);
                if (OTHER.some(function(k){{ return nq.indexOf(norm(k)) >= 0; }})) {{ unsupported(q); drawMap(HOTELS.filter(passFilters), true); return; }}
                pool = pool.filter(function(h){{ return norm(h.name).indexOf(nq)>=0 || norm(h.en).indexOf(nq)>=0; }});
                if (!pool.length) {{ unsupported(q); drawMap(HOTELS.filter(passFilters), true); return; }}
                $total.html('&ldquo;<span>'+q+'</span>&rdquo; 검색 결과 <span class="highlight">'+pool.length+'건</span>'+filterLabel());
            }} else {{
                $total.html(CITY_KO+' 호텔 <span class="highlight">'+pool.length+'곳</span>'+filterLabel()+' · 도시 평균 실망확률 '+CITY_AVG+'%');
            }}
            baseList = pool;
            drawMap(pool, true);   // fitBounds → moveend → renderVisible
            renderVisible();
        }}

        // ───── 이벤트 ─────
        map.on('moveend', function(){{ if (syncMap) renderVisible(); }});

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
            return '<button type="button" class="cft-chip" data-cat="'+c.ko+'"><span class="cft-ico">'+c.ico+'</span>'+c.ko+'</button>';
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
            $('#open-catfilter').toggleClass('active', fCats.length>0).text(fCats.length ? '⚙ 항목 '+fCats.length : '⚙ 항목별 필터');
            CFNav.pop(); run();
        }});

        $('#btn-search').on('click', run);
        $q.on('keyup', function(e){{ if(e.key==='Enter') run(); }});
        $q.on('input', function(){{ if(!$q.val().trim()) run(); }});

        // URL 파라미터: ?area= / ?q=
        var sp = new URLSearchParams(location.search);
        var initArea = sp.get('area'), initQ = sp.get('q');
        if (initArea){{ fArea = initArea; $('#f-area .f-chip').removeClass('on'); $('#f-area .f-chip[data-area="'+initArea+'"]').addClass('on'); }}
        if (initQ){{ $q.val(initQ); }}
        run();
    }})();
    </script>''' + FOOT

# ───────────────────────── detail ─────────────────────────
def gauge_html(p_crit, city_crit):
    """원본 퍼블리싱 게이지 구조 그대로 — 중앙 = 도시 평균, 좌 우수 / 우 위험"""
    if p_crit <= city_crit:
        pos = 50.0 * p_crit / city_crit
    else:
        pos = 50.0 + 50.0 * min((p_crit - city_crit) / (2 * city_crit), 1.0)
    return f'''<div class="gauge">
        <div class="bar">
            <div class="pointer" style="left:calc({pos:.1f}% - 5px)"><div class="arrow"></div><span class="dot"></span></div>
        </div>
        <div class="label">
            <span>우수</span>
            <span class="analysis">평균 {pct(city_crit)}%</span>
            <span>위험</span>
        </div>
    </div>'''

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
        <div class="text">모든 카테고리가 <span>{CITY['ko']} 평균 수준 이하</span>로 <br>관리되고 있는 호텔이에요 👍</div>
        <div class="tags">{tags}</div>
    </div>'''

def quote_cards(qlist, limit=6):
    out = []
    for q in qlist[:limit]:
        star = ''
        if q.get('stars'):
            star = f'<div class="star"><i style="width:{int(q["stars"]) * 20}%"></i></div>'
        origin = E(q.get('review_origin') or 'Google')
        gband = 'danger' if q['grade'] == '심각' else 'warning'
        out.append(f'''<li class="swiper-slide"><div class="item">
            <div class="item-top">
                <div class="name">{E(q.get('reviewer_name') or '투숙객')}</div>
                <div class="status"><div class="status-item {gband}">{E(q['grade'])}</div></div>
            </div>
            <div class="item-info">{star}<div class="web">{origin}</div></div>
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

def build_detail(pid, meta, h, quotes, stars, city, hotels_meta, H):
    name = meta['title']
    img = img_path(pid, meta, depth=1)
    gmap = f'https://www.google.com/maps/place/?q=place_id:{pid}'
    hstars = E(meta.get('hotel_stars') or '')

    lat, lng = meta.get('latitude'), meta.get('longitude')
    map_block = ''
    if lat and lng:
        band_txt = f" · 1박 {meta['price_txt']} ({meta['band'][1]} 가격대)" if meta.get('price_txt') and meta.get('band') else ''
        map_block = f'''<div class="sect location">
            <div class="head"><div class="title">위치</div>
            <div class="desc">{E(meta.get('address') or '')}{band_txt}</div></div>
            <div class="map"><iframe src="https://maps.google.com/maps?q={lat},{lng}&z=16&hl=ko&output=embed"
                loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="{E(name)} 지도"></iframe></div>
            <a class="map-link" href="{gmap}" target="_blank" rel="noopener">구글 지도 앱에서 열기 ↗</a>
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
        if ratio >= 1.15: level_txt = '주의가 필요한 수준이에요'
        elif ratio <= 0.85: level_txt = '안심할 수 있는 수준이에요'
        else: level_txt = '평균적인 수준이에요'
        radar_vals = [round(h['cats'][c]['score']) for c in CATS]
        radar_labels = json.dumps([c for c in CATS], ensure_ascii=False)

        # 카테고리 × 소분류 전체 나열 (탭 없음) + 리뷰 시트 데이터
        groups = []
        sheet_data = {}
        axis = '''<div class="stat-axis"><span class="ax safe">양호</span><span class="ax avg">평균 50</span><span class="ax danger">위험</span></div>'''
        for c in CATS:
            cat = h['cats'][c]
            qlist = quotes.get((pid, c), [])
            sheet_data[c] = [{'s': q.get('scat') or '', 'g': q['grade'], 'q': q.get('quote') or q.get('summary') or '',
                              'd': (q.get('pub') or '')[:10], 'n': q.get('reviewer_name') or '투숙객',
                              'st': q.get('stars'), 'o': q.get('review_origin') or 'Google',
                              'u': q.get('review_url') or '', 'tf': q.get('tfull') or '', 'of': q.get('ofull') or ''} for q in qlist]
            rows = []
            for s in SUBS[c]:
                sub = cat['subs'][s]
                sc = round(sub['score'])
                cnt_html = (f'<button type="button" class="stat-count has-reviews" data-cat="{E(c)}" data-sub="{E(s)}">{sub["count"]}건</button>'
                            if sub['count'] > 0 else '<span class="stat-count zero">0건</span>')
                rows.append(f'''<li class="stat-row is-{sub['band']}">
                    <div class="stat-info"><div class="factor">{E(s)}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, ''))}</div></div>
                    <div class="stat-track"><div class="stat-fill" style="width:{sc}%"><i class="bubble">{sc}</i></div></div>
                    {cnt_html}
                </li>''')
            qc = quote_cards(qlist)
            total_q = len(qlist)
            more_btn = (f'''<div class="more"><button type="button" class="more-btn" data-cat="{E(c)}"><strong>{E(c)}</strong> 리뷰 전체보기 ({cat['count']}건)</button></div>'''
                        if total_q > 0 else '')
            quotes_block = (f'''<div class="review"><div class="list review-slider"><ul class="swiper-wrapper">{qc}</ul></div></div>{more_btn}'''
                            if qc else '<div class="no-quote">이 카테고리는 문제 언급 리뷰가 거의 없어요 🎉</div>')
            groups.append(f'''<div class="cat-group">
                <div class="cat-head">
                    <div class="cat-name"><span class="ico">{CAT_ICON[c]}</span>{E(c)}</div>
                    <div class="cat-score is-{cat['band']}">{BAND_KO[cat['band']]} · 위험도 {round(cat['score'])}<span class="pctl"> · {CITY['ko']} {'하위 ' + str(cat['pctl_worse']) if cat['pctl_worse'] <= 50 else '상위 ' + str(100 - cat['pctl_worse'])}%</span></div>
                </div>
                {axis}
                <ul class="stat-list">{''.join(rows)}</ul>
                {quotes_block}
            </div>''')

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
                <div class="tit">이 호텔에서 실망할 확률</div>
                <div class="num">{v}%</div>
                <div class="txt">{CITY['ko']} 평균(<span>{avg}%</span>)보다 {level_txt} <br>최근 투숙객 100명 중 <span>{v}명</span>이 심각한 문제를 언급했어요</div>
            </div>
            {gauge_html(h['p_crit'], city['crit'])}
            {insight_card(h)}
            <div class="basis">최근 리뷰일수록 높은 가중치로 반영됩니다 <br>분석 리뷰 {h['analyzed']:,}건 · 기준 {CITY['data_asof']}</div>
        </div>
        <div class="sect risk">
            <div class="head"><div class="title">카테고리별 위험도</div>
            <div class="desc">{CITY['ko']} 평균 = 50 · 3배 나쁘면 100</div></div>
            <div class="chart"><canvas id="radar"></canvas>
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
                              backgroundColor: 'rgba(141,91,253,0.15)', borderColor: '#8D5BFD',
                              pointBackgroundColor: '#8D5BFD', pointRadius: 3, borderWidth: 2}},
                            {{label: '{CITY['ko']} 평균', data: [50,50,50,50,50,50], fill: false,
                              borderColor: '#CCCCCC', borderDash: [4,4], pointRadius: 0, borderWidth: 1}}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{legend: {{display: false}}, tooltip: {{enabled: false}}}},
                        scales: {{r: {{angleLines: {{color: '#efefef'}}, grid: {{color: '#efefef'}},
                            suggestedMin: 0, suggestedMax: 100,
                            ticks: {{stepSize: 25, backdropColor: 'transparent', font: {{size: 10}}}},
                            pointLabels: {{font: {{size: 12, weight: '600'}}, color: '#232323'}}}}}}
                    }}
                }});
            }});
            </script>
        </div>
        <div class="sect analysis" id="risk-detail">
            <div class="head"><div class="title">리스크 상세 분석</div>
            <div class="desc">대분류 6개 · 소분류 20개 전체 — 숫자는 위험도(0~100), {CITY['ko']} 평균이면 50이에요</div></div>
            {''.join(groups)}
            <div class="stat-legend">
                <span class="lg is-danger">위험 70+</span><span class="lg is-warning">주의 45~70</span><span class="lg is-safe">양호 ~45</span>
                <span class="note">불만 리뷰 5건 미만 소분류는 위험 등급을 붙이지 않아요 · 인용문은 리뷰 원문 발췌입니다</span>
            </div>
        </div>
        {stars_block}
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
                    <div class="sheet-sort">심각도 · 최신순</div>
                </div>
                <ul class="sheet-list" id="sheet-list"></ul>
            </div>
        </div>
        <script>
        window.QDATA = {json.dumps(sheet_data, ensure_ascii=False)};
        window.QSUBS = {json.dumps({c: SUBS[c] for c in CATS}, ensure_ascii=False)};
        window.CF_PID = {json.dumps(pid)};
        window.CF_GREVIEWS = 'https://search.google.com/local/reviews?placeid={pid}';
        </script>'''

    return head(f'{name} — 캐치플로', depth=1) + f'''
    <script>window.CF_HOTEL={{pid:{json.dumps(pid)},name:{json.dumps(name)},gmap:{json.dumps(gmap)}}};</script>
    <main id="container">
        <section id="detail">
            <div class="header">
                <div class="back"><a href="../search.html"><img src="../img/back.svg" alt="뒤로가기"></a></div>
            </div>
            <div class="content">
                <div class="visual"><img src="{E(img)}" alt="{E(name)}"></div>
                <div class="sect information">
                    <div class="info-top"><div class="badge">{badge_html(h)}</div></div>
                    <div class="info-cont">
                        <div class="name">
                            <h2 class="name-ko">{E(name)}</h2>
                            <p class="name-en">{E(meta.get('sub_title') or '')}</p>
                        </div>
                        <div class="meta"><span>{CITY['ko']}, JP</span>{f'<span>{hstars}</span>' if hstars else ''}{f"<span class='price'>1박 <b>{meta['price_txt']}</b></span>" if meta.get('price_txt') else ''}</div>
                    </div>
                    <div class="info-bottom">
                        <a class="btn-link btn-google" href="{gmap}" target="_blank" rel="noopener">
                            <span class="ico"><img src="../img/google.svg" alt=""></span>
                            <span class="txt"><span class="label">구글 평점 {fmt_score(meta.get('total_score'))}</span><span class="count">({meta.get('reviews_count') or 0:,}개)</span></span>
                        </a>
                        <a class="btn-link btn-audit" href="#risk-detail">
                            <span class="ico"><img src="../img/audit.svg" alt=""></span>
                            <span class="txt"><span class="label">분석 리뷰 {h['analyzed']:,}개</span><span class="count">AI 분석 리포트</span></span>
                        </a>
                    </div>
                </div>
                {map_block}
                {body_scored}
                {similar_block}
            </div>
            <div class="button"><a class="btn-reservate" href="{gmap}" target="_blank" rel="noopener">구글 지도에서 이 호텔 보기</a></div>
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
            $('.review-slider, #detail .hotel-slider').each(function(i, el){{
                new Swiper(el, {{slidesPerView:'auto', spaceBetween:10, observer:true, observeParents:true}});
            }});

            // ───── 플로팅: 공유 / 맨 위로 ─────
            $(window).on('scroll', function(){{
                $('#float').toggleClass('is-active', $(window).scrollTop() > 50);
            }});
            $('.btn-top').on('click', function(e){{
                e.preventDefault();
                $('html, body').stop().animate({{scrollTop: 0}}, 400);
            }});
            // 공유(.btn-share)는 js/engage.js 에서 처리 (OS 공유시트 + 카카오 인앱 폴백)

            // ───── 리뷰 바텀시트 (심각도>최신순 정렬 데이터, 소분류 칩 필터) ─────
            if (!window.QDATA) return;
            var $sheet = $('#review-sheet'), curCat = null, curSub = null;

            function esc(s){{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
            function emph(s){{ return esc(s).replace(/\\*\\*(.+?)\\*\\*/g, '<span>$1</span>').replace(/\\*\\*/g, ''); }}

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
                // 링크: 구글 origin만 개별 리뷰 원본으로, 그 외(Trip.com·Booking 등)는 전부 호텔 구글 리뷰 페이지로
                // (Trip.com/Booking 원본 URL은 예약페이지로 빠져 리뷰가 안 보임)
                var linkHtml = '<span></span>';
                var isGoogle = (q.o === 'Google') && q.u && q.u.toLowerCase().indexOf('google.') >= 0;
                if (isGoogle) {{
                    linkHtml = '<a class="orig-link" href="' + esc(q.u) + '" target="_blank" rel="noopener">구글 리뷰 보기 ↗</a>';
                }} else if (window.CF_GREVIEWS) {{
                    linkHtml = '<a class="orig-link" href="' + esc(window.CF_GREVIEWS) + '" target="_blank" rel="noopener">구글 리뷰 보기 ↗</a>';
                }}
                var foot = '<div class="item-foot">'
                    + linkHtml
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '')
                    + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(q.n) + '</div>'
                    + '<div class="status"><div class="status-item ' + band + '">' + q.g + '</div></div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(q.o) + '</div></div>'
                    + '<div class="item-bottom"><div class="text clamp">' + emph(q.q) + '</div>'
                    + '<div class="date">' + esc((q.d||'').replace(/-/g,'. ')) + (q.s ? ' · ' + esc(q.s) : '') + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }}

            function render(){{
                var list = (window.QDATA[curCat] || []);
                var filtered = curSub ? list.filter(function(q){{ return q.s === curSub; }}) : list;
                $('#sheet-cat').text(curCat);
                $('#sheet-cnt').text(filtered.length + '건');
                $('#sheet-list').html(filtered.map(card).join('') ||
                    '<li class="sheet-empty">이 소분류의 인용 리뷰가 없어요</li>');
                var subs = window.QSUBS[curCat] || [];
                var chips = ['<button type="button" class="sheet-chip' + (!curSub ? ' on' : '') + '" data-sub="">전체 ' + list.length + '</button>'];
                subs.forEach(function(s){{
                    var n = list.filter(function(q){{ return q.s === s; }}).length;
                    if (!n) return;
                    chips.push('<button type="button" class="sheet-chip' + (curSub === s ? ' on' : '') + '" data-sub="' + esc(s) + '">' + esc(s) + ' ' + n + '</button>');
                }});
                $('#sheet-chips').html(chips.join(''));
                $('#sheet-list').scrollTop(0);
            }}

            function closeVisual(){{
                $sheet.removeClass('is-open');
                $('body').css('overflow', '');
                setTimeout(function(){{ $sheet.prop('hidden', true); }}, 300);
            }}
            function open(cat, sub){{
                curCat = cat; curSub = sub || null;
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
            $(document).on('click', '.sheet-chip', function(){{
                curSub = $(this).data('sub') || null; render();
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
    </script>''' + FOOT

# ───────────────────────── main ─────────────────────────
def main():
    city, H = compute(SRC)
    hotels_meta, quotes, stars = load()

    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, 'hotels'))
    os.makedirs(os.path.join(OUT, 'data'))
    for d in ('css', 'js', 'img'):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(OUT, d))
    hotels_img = os.path.join(ROOT, 'assets', 'hotels')
    if os.path.exists(hotels_img):
        shutil.copytree(hotels_img, os.path.join(OUT, 'img', 'hotels'))

    W = lambda path, s: open(os.path.join(OUT, path), 'w', encoding='utf-8').write(s)

    W('index.html', build_index(hotels_meta, H, quotes))
    W('search.html', build_search(pct(city['crit'])))
    idx = build_search_index(hotels_meta, H)
    W('data/index.js', 'window.HOTELS=' + json.dumps(idx, ensure_ascii=False) + ';')
    open(os.path.join(OUT, '.nojekyll'), 'w').close()

    n = 0
    for pid, meta in hotels_meta.items():
        if pid not in H: continue
        W(f'hotels/{pid}.html', build_detail(pid, meta, H[pid], quotes, stars, city, hotels_meta, H))
        n += 1
    scored = sum(1 for p in H if H[p]['scored'])
    print(f'OK: 상세 {n}p (점수 노출 {scored}, 수집중 {n - scored}) · 도시평균 실망확률 {pct(city["crit"])}%')

if __name__ == '__main__':
    main()
