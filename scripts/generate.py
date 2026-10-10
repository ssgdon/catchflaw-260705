# -*- coding: utf-8 -*-
"""캐치플로 정적 사이트 생성기 — data-src/*.json → docs/
사용: python scripts/generate.py
"""
import json, os, shutil, sys, html, re, time, math, statistics
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import quote as urlquote

BUILD = str(int(time.time()))  # 에셋 캐시버스터

sys.path.insert(0, os.path.dirname(__file__))
from scoring import compute, CATS as ALL_CATS, SCORED_CATS, CHIP_ONLY_CATS, SUBS, SUB_KEYWORDS, RARE_SUBS, MIN_REVIEWS, RANK_MIN, rec_scores, bayes_rating, SAFE_MULT
# 분류 v5: 점수로 보여주는 대분류(6)만 CATS로 쓴다. 칩 전용 대분류(안전)는 위험 칩·별도 펼침 항목으로만 표시
CATS = SCORED_CATS
CAT_INDEX = {c: i for i, c in enumerate(ALL_CATS)}   # 펼침 항목 id="risk-{i}" — 점수 대분류는 CATS.index와 같고 안전이 마지막

# ── 카테고리 표시명 (TAXONOMY v4: 명칭이 이미 중립적이라 순화층 불요). cat_ko는 identity로 유지해 호출부 보존. ──
def cat_ko(c): return c
# P1 한눈에 보기 문장 재료: 소분류 → 고객 언어 명사구 (SUBS 21개와 키 동일해야 함 — scoring.py SUBS 변경 시 동기화)
SUB_PHRASE = {
    '벌레': '벌레', '곰팡이': '곰팡이', '머리카락·얼룩': '머리카락·얼룩', '청소 안 됨': '청소 상태',
    '담배 냄새': '담배 냄새', '악취': '방 냄새',
    '실내 소음': '옆방·복도 소음', '바깥 소음': '도로·유흥가 소음',
    '좁은 방': '좁은 객실', '침대·베개': '침대·베개', '낡음·고장': '낡은 시설·고장', '실내 온도': '실내 온도',
    '온수·수압': '온수·수압', '와이파이·TV': '와이파이·TV',
    '불친절': '직원 응대', '대기·지연': '체크인·요청 대기', '대응 미흡': '문제 발생 시 대처',
    '역 거리': '역까지 거리', '주변 편의': '주변 편의시설', '동네 분위기': '밤길·동네 분위기',
    '객실 보안': '객실 보안',
}
assert set(SUB_PHRASE) == {s for v in SUBS.values() for s in v}, 'SUB_PHRASE ↔ scoring.SUBS 불일치'
# P3 누구와 가세요(1단계): 일행 구성별로 관련 깊은 소분류·FAQ 토픽만 모아 보여줌. 구성별 실망 확률은 동행 추출(파이프라인) 후.
# FEEDBACK-2610 §11 개정: 혼자=객실 보안(밤길과 함께 1인의 핵심), 커플=침대·베개, 친구=온수·수압. 동행 허브(best/solo·couple·group)도 이 소분류를 쓴다.
WHO_GROUPS = [
    ('solo', '혼자', ['객실 보안', '동네 분위기', '역 거리'], ['luggage', 'access']),
    ('two', '2인·커플', ['좁은 방', '침대·베개', '실내 소음'], ['beds']),
    ('group', '친구 3인 이상', ['좁은 방', '침대·베개', '온수·수압'], ['beds', 'luggage']),     # 친구: 침대 구성·짐 보관(§11)
    ('kids', '아이 동반', ['머리카락·얼룩', '벌레', '좁은 방'], ['family', 'beds', 'breakfast']),   # 아이: 조식 추가(§11)
]
WHO_FAQ_LABEL = {'luggage': '짐 보관', 'access': '역까지', 'beds': '침대 구성', 'family': '아이 동반', 'breakfast': '조식'}
SUB_CAT = {s: c for c, v in SUBS.items() for s in v}

# 카테고리 결론 라벨 (UI-STANDARDS §13): 위험도 숫자 대신 "평균보다 적은지 많은지"를 먼저 말한다.
# 위험도 = 50·비율(비율≤1) / 50+25·(비율-1) → 비율로 되돌려 사람 말로. 밴드는 grade_band와 동일(양호<45·주의<70·위험).
def cat_ratio(score):
    return score / 50 if score <= 50 else 1 + (score - 50) / 25

def cat_verdict(score):
    """(짧은 라벨, 문장, 밴드). 예) 32 → ('적은 편', '평균보다 적어요', 'safe')."""
    if score < 25: return '거의 없음', '불만이 거의 없어요', 'safe'
    if score < 45: return '적은 편', '평균보다 적어요', 'safe'
    if score < 55: return '평균 수준', '평균과 비슷해요', 'warning'
    if score < 70: return '많은 편', '평균보다 많아요', 'warning'
    return '많음', '평균보다 훨씬 많아요', 'danger'

def ratio_text(score):
    """후쿠오카 평균 대비 한 줄: '평균보다 36% 적어요' · '평균과 비슷해요' · '평균의 1.8배'.
    경계는 cat_verdict와 같다(45·55) — 예전엔 비율 기준(0.95·1.05)이라 '1.2배'인데 '평균 수준'처럼 어긋났다."""
    r = cat_ratio(score)
    if score < 45: return f'평균보다 {round((1 - r) * 100)}% 적어요'
    if score < 55: return '평균과 비슷해요'
    return f'평균의 {max(r, 1.2):.1f}배'

def ratio_html(score):
    """ratio_text의 HTML판 — 핵심 수치('36% 적어요'·'1.1배'·'비슷해요')만 굵게."""
    m = re.match(r'(평균보다 |평균의 |평균과 )(.+)$', ratio_text(score))
    return f'{m.group(1)}<b>{m.group(2)}</b>' if m else ratio_text(score)

def rank_text(pctl_worse):
    """도시 내 위치를 넉넉한 구간 문장으로 (pctl_worse = 위험도가 이 호텔 이상인 호텔 비율%, 리뷰 100개 이상 호텔끼리).
    정밀 백분위('78%보다 많아요')는 순위 오차가 커서 쓰지 않는다(2026-10 표본 공정성). None(리뷰 적음) → 빈 문자열."""
    if pctl_worse is None: return ''
    if pctl_worse >= 90: return f'{CITY["ko"]}에서 가장 적은 편'
    if pctl_worse >= 75: return f'{CITY["ko"]} 호텔 중 적은 편'
    if pctl_worse > 25: return f'{CITY["ko"]} 호텔 중 중간쯤'
    if pctl_worse > 10: return f'{CITY["ko"]} 호텔 중 많은 편'
    return f'{CITY["ko"]}에서 가장 많은 편'
CONTACT_EMAIL = 'fibinc8967@gmail.com'   # 정정·이의제기 창구 (LEGAL-SOFTEN §2-a)

def mask_name(s):
    """리뷰어 실명 마스킹 (LEGAL-SOFTEN §3): 첫 글자 + '**'. 빈값은 '투숙객'."""
    s = str(s or '').strip()
    return (s[0] + '**') if s else '투숙객'

# 클라이언트 JS 표시용 매핑 주입값 (내부키 → 표시명). head()에서 window.CAT_KO 로 주입.
CAT_KO_JSON = json.dumps({c: cat_ko(c) for c in ALL_CATS}, ensure_ascii=False)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data-src')
OUT = os.path.join(ROOT, 'docs')

# ───────────────────────── 도시 설정 (변수화 — 신규 도시는 여기만 추가) ─────────────────────────
CITY = {'code': 'fukuoka', 'ko': '후쿠오카', 'en': 'Fukuoka', 'data_asof': '2026년 3월', 'asof': None, 'crit': 0.0}
# ── 추천순·수요 신호 (2026-10, RECOMMEND-PRICE-DESIGN §4 / HOME-CONCEPT-DESIGN) — main()에서 채움 ──
REC = {}      # pid → rec_score(0~1, scoring.rec_scores). 정렬 전용, 화면에 숫자로 노출 금지
KRN = {}      # pid → 최근 1년 한국인 리뷰 수 (kr_stats 1y kr_n) = 수요 신호
PAIRS = []    # [(pid_a, pid_b)] 카페에서 자주 같이 비교되는 쌍 (scripts/compare_pairs.json)
REC_SORT_DESC = '실망 확률이 낮고, 한국인 리뷰가 많고, 구글 평점이 높은 순'   # '추천순' 툴팁·설명 정본

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

CAT_ICON = {c: '' for c in ALL_CATS}
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

STATION_MAX_WALK = 30   # 도보 30분 넘으면 가까운 역으로 안내하지 않음

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
    if walk > STATION_MAX_WALK:   # 역 목록(STATIONS)에 없는 외곽 호텔 — '텐진역 도보 105분' 같은 의미 없는 표기 대신 미표시
        return None
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

# ── 가격 (2026-10 개편: 날짜별 표본 → 평일 중앙값이 대표, 주말은 따로. 통화 혼재 → 원화 환산 후 밴드) ──
# 표본 = data-src/prices.json (pipeline hotel_prices): 주간 구글 지도 가격(구글이 고른 숙박일 1개) +
#        price_sample.py 날짜 지정 수집(앞으로 8주의 수·토, 2인 1박 원화). 둘 다 2인 기준(같은 날 대조 확인).
# 10/9 수집 실측: 주말(금·토 밤)은 평일의 중앙 2.65배라 둘을 한 범위로 묶으면 '11~42만원'처럼 쓸모없이 넓다.
# 평일 중앙값은 사용자가 직접 찾은 실제 가격 17곳과 배율 0.99(평균 1.04)로 일치 → 대표값·가격대·정렬 = 평일.
# prices.json이 아예 없을 때만 기존 price_raw 한 개로 '약 N만원'. prices.json이 있으면 근거 없는 호텔은 가격 비표시
# (10/9 빌드: 10곳 — 상세·검색 카드는 가격 줄 생략, 비교표·홈 비교 카드는 '정보 없음').
FX = {'US$': 1400, '£': 1750, '€': 1500, 'SCR': 100, '₩': 1, 'KRW': 1, '¥': 9.5}
PRICE_WINDOW_DAYS = 56          # 최근 8주 수집분만 사용
WEEKEND_NIGHTS = (4, 5)         # 금·토 밤 (date.weekday)
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
    """가격대는 화면에 보이는 만원 단위(반올림)로 정한다 — '약 10만원'이 '10만원 미만'에 들어가는 어긋남 방지."""
    if krw is None: return None
    shown = max(1, round(krw / 10_000)) * 10_000
    for code, label, lo, hi in PRICE_BANDS:
        if lo <= shown < hi: return code, label
    return None

def price_stats(rows):
    """한 호텔의 가격 표본(prices.json 행들) → (평일 원화|None, 표시 문구, 확인일 'YYYY-MM-DD', 주말 원화|None) / 근거 없으면 None.
    같은 숙박일은 가장 최근 수집 1건만(같은 날이면 날짜 지정 수집 우선). 대표 = 평일 밤 중앙값('평일 약 13만원').
    평일 근거 = 날짜 지정 수집 1건 이상 또는 평일 표본 2건 이상 — 구글 지도가 고른 연초 비수기 하루뿐인 호텔은
    실제보다 반값으로 보여 제외(몬토레 9만 vs 실측 17만). 평일 근거가 없고 주말만 있으면 '주말 약 N만원'(가격대·정렬 제외)."""
    by_day = {}
    for r in rows:
        rate = FX.get(r['currency'])
        if rate is None or r['stay_date'] < r['observed_on']:
            continue
        rank = (r['observed_on'], r['source'] == 'ghotels')
        if r['stay_date'] not in by_day or rank > by_day[r['stay_date']][0]:
            by_day[r['stay_date']] = (rank, float(r['amount']) * rate)
    if not by_day:
        return None
    seen = max(rank[0] for rank, _ in by_day.values())
    wd = [(rank[1], v) for d, (rank, v) in by_day.items() if date.fromisoformat(d).weekday() not in WEEKEND_NIGHTS]
    we = [v for d, (_, v) in by_day.items() if date.fromisoformat(d).weekday() in WEEKEND_NIGHTS]
    we_mid = int(statistics.median(we)) if we else None
    if wd and (len(wd) >= 2 or any(g for g, _ in wd)):
        mid = statistics.median(v for _, v in wd)
        return int(mid), f'평일 약 {max(1, round(mid / 10_000))}만원', seen, we_mid
    if we_mid:
        return None, f'주말 약 {max(1, round(we_mid / 10_000))}만원', seen, None
    return None

def md_ko(iso):
    """'2026-10-09' → '10월 9일'"""
    d = date.fromisoformat(str(iso)[:10])
    return f'{d.month}월 {d.day}일'

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

def josa_iga(word):
    """받침 유무로 '이'/'가' 선택. 예: 하카타역→이, 텐진→이, 나카스→가."""
    w = str(word or '').rstrip()
    ch = w[-1] if w else ''
    if '가' <= ch <= '힣':
        return '이' if (ord(ch) - 0xAC00) % 28 else '가'
    return '이'

# ── 모바일 줄바꿈 다듬기 (UI-STANDARDS §15) ──
# 좁은 화면에서 "많은 / 편이에요", "4.2% / (3건)", "다른 도시는 / 준비 중이에요"처럼 뜻이 갈리는 줄바꿈을 막는다.
# W()가 모든 .html을 쓰기 직전에 본문 텍스트(스크립트·스타일·속성 제외)에만 적용 → 새 문구도 자동으로 같은 규칙.
NB = ' '                                    # 줄바꿈 없는 공백
DSEP = '<span class="dsep"> · </span>'           # 문장 사이 구분점: 모바일에선 줄바꿈으로(ds.css ⑦)
_GLUE = [
    (re.compile(r'실망 확률'), '실망' + NB + '확률'),
    (re.compile(r'(많은|적은|낮은|높은|좋은) (편|순|곳|숙소|호텔)'), r'\1' + NB + r'\2'),
    (re.compile(r'가장 (많음|적음|낮음|높음|낮은|높은|많은|적은|좋은|가까운)'), '가장' + NB + r'\1'),
    (re.compile(r'(폭|약|총) (\d)'), r'\1' + NB + r'\2'),
    (re.compile(r'침대 폭'), '침대' + NB + '폭'),
    # 띄어쓰기 없는 가운뎃점(냉난방·수압, 리뷰·실전)은 점 뒤에서 끊지 않음 — 단어 결합자(U+2060)
    (re.compile(r'(?<=[^\s\u00a0·])·(?=[^\s\u00a0·])'), '\u2060·\u2060'),
    (re.compile(r'준비 중'), '준비' + NB + '중'),
    (re.compile(r'최근 (\d+)(년|개월)'), '최근' + NB + r'\1\2'),
    (re.compile(r'도보 (약 )?(\d+)분'), lambda m: '도보' + NB + (('약' + NB) if m.group(1) else '') + m.group(2) + '분'),
    (re.compile(r'(\d[\d.,]*%) (\(\d[\d,]*건\))'), r'\1' + NB + r'\2'),
    (re.compile(r'(\d[\d.,]*만?) (건|곳|개|명)(?=[\s.,·)]|$)'), r'\1' + NB + r'\2'),
    # 라벨과 건수는 한 덩어리: "실망 리뷰 / 27건" "벌레 / 2건" 처럼 숫자만 다음 줄로 떨어지지 않게 (360px 상세 근거 줄 실측)
    (re.compile(r'(?<=[가-힣]) (\d[\d,]*건)'), NB + r'\1'),
    # 짧은 괄호 묶음은 통째로: "(직선 199m)" "(가격 2026년 10월 기준)" "(트립닷컴 등은 별점 미제공)"
    (re.compile(r'\(([^()<>]{1,16})\)'), lambda m: '(' + m.group(1).replace(' ', NB) + ')'),
]
_DESC_RE = re.compile(r'(<div class="desc">)(.*?)(</div>)', re.S)
_H1_DASH_RE = re.compile(r'(<h1 class="hub-h1">)(.*?)(</h1>)', re.S)


def _glue(t):
    for rx, rep in _GLUE:
        t = rx.sub(rep, t)
    return t


def polish_breaks(page):
    head, sep, body = page.partition('<body')
    if not sep:
        return page
    parts = re.split(r'(<script\b.*?</script>|<style\b.*?</style>)', body, flags=re.S)
    for i in range(0, len(parts), 2):                     # 짝수 = 스크립트·스타일 밖
        s = parts[i]
        s = _DESC_RE.sub(lambda m: m.group(1) + m.group(2).replace(' · ', DSEP) + m.group(3), s)
        s = _H1_DASH_RE.sub(lambda m: m.group(1) + m.group(2).replace(' — ', '<span class="dsep"> — </span>') + m.group(3), s)
        s = re.sub(r'>([^<>]+)<', lambda m: '>' + _glue(m.group(1)) + '<', s)
        parts[i] = s
    return head + sep + ''.join(parts)


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
        m['price_seen'] = m['price_we'] = None
    # 가격 표본(최근 8주) → 대표값·범위·확인일. 기준 = 표본 중 가장 최근 수집일(빌드가 늦어도 창이 비지 않게)
    psamples = defaultdict(list)
    if os.path.exists(os.path.join(SRC, 'prices.json')):
        prows = J('prices.json')
        if prows:
            cut = str(date.fromisoformat(max(r['observed_on'] for r in prows)) - timedelta(days=PRICE_WINDOW_DAYS))
            for r in prows:
                if r['observed_on'] >= cut:
                    psamples[r['place_id']].append(r)
    for pid, m in hotels_meta.items():
        if psamples:                 # 표본이 있으면 근거 없는 호텔은 숫자 비표시 (옛 단일가로 채우지 않음)
            ps = price_stats(psamples.get(pid, []))
            m['krw'], m['price_txt'], m['price_seen'], m['price_we'] = ps or (None, '', None, None)
        m['band'] = price_band(m['krw'])
    seen = [m['price_seen'] for m in hotels_meta.values() if m['price_seen']]
    CITY['price_seen'] = md_ko(max(seen)) if seen else CITY['data_asof']
    quotes = defaultdict(list)
    for q in J('quotes.json'):
        quotes[(q['place_id'], q['mcat'])].append(q)
    stars = defaultdict(lambda: {'dist': {i: 0 for i in range(1, 6)}, 'dist_1y': {i: 0 for i in range(1, 6)},
                                 'total': 0, 'low_1y': 0, 'total_1y': 0})
    for s in J('stars.json'):
        st = stars[s['place_id']]
        st['dist'][int(s['stars'])] = s['n']
        st['dist_1y'][int(s['stars'])] = s['n_1y']   # 화면 분포는 최근 1년 (다른 숫자와 같은 기간)
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
# P2 상세 섹션 탭: 스크롤 위치로 활성 탭 표시 + 클릭 시 헤더+탭 높이만큼 보정해 이동. f-string 아님(JS 중괄호 보존).
DETAIL_TABS_JS = '''<script>
(function(){
    var nav = document.getElementById('det-tabs'); if (!nav) return;
    var links = [].slice.call(nav.querySelectorAll('a')), ticking = false;
    var hd = document.querySelector('.det-header');
    function top0(){ return (hd ? hd.offsetHeight : 56) + nav.offsetHeight; }   // 헤더 높이: 모바일 56 · PC 64
    function target(a){ return document.getElementById(a.getAttribute('href').slice(1)); }
    function spy(){
        ticking = false;
        var cur = links[0], lim = top0() + 24;
        links.forEach(function(a){ var s = target(a); if (s && s.getBoundingClientRect().top <= lim) cur = a; });
        links.forEach(function(a){ a.classList.toggle('is-on', a === cur); });
    }
    window.addEventListener('scroll', function(){ if (!ticking) { ticking = true; requestAnimationFrame(spy); } }, {passive: true});
    nav.addEventListener('click', function(e){
        var a = e.target.closest('a'); if (!a) return;
        var s = target(a); if (!s) return;
        e.preventDefault();
        window.scrollTo({top: s.getBoundingClientRect().top + window.pageYOffset - top0() + 1, behavior: 'smooth'});
        if (typeof gtag === 'function') gtag('event', 'detail_tab', {tab: a.textContent});
    });
})();
</script>'''

# P3 누구와 가세요: 칩 → 패널 전환 + GA4 who_select. f-string 아님(JS 중괄호 보존).
WHO_JS = '''<script>
(function(){
    var sec = document.getElementById('sec-who'); if (!sec) return;
    sec.addEventListener('click', function(e){
        var b = e.target.closest('.who-chip'); if (!b) return;
        var k = b.getAttribute('data-who');
        sec.querySelectorAll('.who-chip').forEach(function(x){ var on = x === b; x.classList.toggle('is-on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); });
        sec.querySelectorAll('.who-panel').forEach(function(p){ p.hidden = p.getAttribute('data-who') !== k; });
        if (typeof gtag === 'function') gtag('event', 'who_select', {group: k});
    });
})();
</script>'''

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
    <link rel="stylesheet" href="{p}css/ds.css?v={BUILD}">
    <link rel="stylesheet" href="{p}css/pc.css?v={BUILD}">
    <script src="{p}js/backnav.js?v={BUILD}"></script>
    <script src="{p}js/common.js?v={BUILD}" defer></script>
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

def build_footer(depth=0):
    """공통 미니 푸터 (LEGAL-SOFTEN §2-b). 전 생성 페이지에 삽입. about·정정창구 링크."""
    p = '../' * depth
    return f'''
    <footer id="site-foot">
        <div class="foot-note">캐치플로의 실망 확률·위험도는 공개된 투숙객 리뷰를 AI로 분석한 <b>참고용 통계 의견</b>이며, 특정 업소의 객관적 품질을 단정하지 않습니다.</div>
        <div class="foot-links"><a href="{p or './'}about">캐치플로 소개·산출 방법</a> · <a href="mailto:{CONTACT_EMAIL}">정정·이의제기</a></div>
        <div class="foot-copy">ⓒ 2026 CATCHFLAW</div>
    </footer>'''

def site_header(depth=1, back=None, search=True):
    """F36+F40+F45: 전 페이지 공통 헤더(좌 back·중앙 로고·우 햄버거)+드로어 4링크.
    back=None(홈)이면 back 아이콘 대신 스페이서 → 로고 중앙 유지. 드로어 JS는 jQuery 비의존 vanilla."""
    p = '../' * depth
    home = p or './'
    # PC 전용 헤더 검색(pc.css에서만 표시) — 상세·비교·허브 등에서 바로 다른 호텔을 찾게(Tripadvisor·Klook 헤더 패턴)
    dh_search = (f'<form class="dh-search" action="{p}search" method="get" role="search">'
                 f'<input type="search" name="q" placeholder="{CITY["ko"]} 호텔명 검색" aria-label="호텔 검색">'
                 '<button type="submit" aria-label="검색"><svg width="18" height="18" viewBox="0 0 20 20" fill="none"><circle cx="9" cy="9" r="6" stroke="currentColor" stroke-width="1.8"/><path d="m13.5 13.5 3.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button></form>'
                 if search else '')
    back_slot = (f'<a class="dh-back" href="{back}" aria-label="뒤로가기"><img src="{p}img/back_b.svg" alt="뒤로가기"></a>'
                 if back else '<span class="dh-back dh-back-empty" aria-hidden="true"></span>')
    return f'''<div class="det-header">
                {back_slot}
                <a class="dh-logo" href="{home}" aria-label="CATCHFLAW 홈"><img src="{p}img/logo.svg" alt="CATCHFLAW"></a>
                {dh_search}
                <nav class="dh-nav" aria-label="주요 메뉴">
                    <a href="{home}">홈</a>
                    <a href="{p}search">호텔 검색</a>
                    <a href="{p}compare">호텔 비교</a>
                    <a href="{p}recent">최근 본 호텔</a>
                    <a href="{p}about">산출 방법</a>
                </nav>
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
            (function(){{
                var drawer = document.querySelector('.det-drawer'),
                    menu = document.querySelector('.dh-menu');
                if (!drawer || !menu) return;
                function open(){{ drawer.hidden = false; void drawer.offsetWidth; drawer.classList.add('is-open'); }}
                function close(){{ drawer.classList.remove('is-open'); setTimeout(function(){{ drawer.hidden = true; }}, 300); }}
                menu.addEventListener('click', function(e){{ e.preventDefault(); open(); }});
                drawer.addEventListener('click', function(e){{
                    if (e.target.closest('.dd-dim') || e.target.closest('.dd-close')) {{ e.preventDefault(); close(); }}
                }});
                document.addEventListener('keydown', function(e){{
                    if (e.key === 'Escape' && drawer.classList.contains('is-open')) close();
                }});
            }})();
            </script>'''

def kr_n_map(kr_stats):
    """pid → 최근 1년 한국인 리뷰 수 (수요 신호). 없으면 0."""
    out = {}
    for (pid, period), r in kr_stats.items():
        if period != '1y': continue
        try: out[pid] = int(float(r.get('kr_n') or 0))
        except (TypeError, ValueError): pass
    return out

def man_txt(krw):
    """원화 → '약 34만원' (표시 만원 반올림). None이면 ''."""
    return f'약 {max(1, round(krw / 10_000))}만원' if krw else ''

def price_line_html(meta, weekend_first=False):
    """카드 가격 줄 정본 (FEEDBACK-2610 §1): '1박 <b>평일 약 13만원</b> <span class="seg">· 주말 약 34만원</span>'.
    평일만 있으면 평일만, 주말만('주말 약 …')이면 그대로. 근거 없으면 ''. 주말 값은 굵게 안 함(.pl-we, --ink-2).
    홈 카드·허브 카드·비교 카드가 공용, 검색 statLine(JS)은 같은 규칙(pt·ptw)."""
    pt = meta.get('price_txt') or ''
    if not pt: return ''
    we = man_txt(meta.get('price_we')) if meta.get('price_we') and pt.startswith('평일') else ''
    if not we: return f'1박 <b>{E(pt)}</b>'
    return f'1박 <b>{E(pt)}</b> <span class="seg pl-we">· 주말 {we}</span>'

def area_tag(meta):
    """지역 태그 (FEEDBACK-2610 §1): AREAS 반경 안에 드는 지역 중 중심이 가장 가까운 곳의 짧은 이름
    (하카타역·텐진·나카스·기온). 반경 밖이면 ''."""
    lat, lng = meta.get('latitude'), meta.get('longitude')
    if not lat or not lng: return ''
    best = None
    for a in AREAS:
        d = haversine_km(float(lat), float(lng), a['lat'], a['lng'])
        if d <= a['r'] and (best is None or d < best[0]):
            best = (d, a['ko'].split('·')[0])
    return best[1] if best else ''

def station_short(meta):
    """카드용 역 도보 문구 '텐진역 도보 3분'. 도보 30분 초과·좌표 없음이면 ''."""
    ns = nearest_station(meta.get('latitude'), meta.get('longitude'))
    return f'{ns[0]} 도보 {ns[1]}분' if ns else ''

def area_line_html(meta, station=None):
    """카드 지역 줄: '<span class="area-tag">텐진</span><span class="seg">텐진역 도보 3분</span>'.
    태그도 역도 없으면 '' (줄 생략). station에 다른 문구(허브의 '도보 약 7분(직선 450m)')를 넘길 수 있다."""
    tag = area_tag(meta)
    st = station_short(meta) if station is None else station
    if not tag and not st: return ''
    return (f'<span class="area-tag">{E(tag)}</span>' if tag else '') + (f'<span class="seg">{E(st)}</span>' if st else '')

def worst_cat_of(h):
    """주의·위험 구간인 최다 불만 대분류(점수형 6개 중). 없으면 None."""
    c = max(SCORED_CATS, key=lambda c: h['cats'][c]['score'])
    return c if h['cats'][c]['band'] in ('warning', 'danger') else None

def why_line(pid, h, cls='why'):
    """카드 사유줄 (HOME-CONCEPT §2.2 · FEEDBACK-2610 §1): '한국인 리뷰 N건'(N≥10) + 평균의 1.2배 이상이면 '주로 소음 불만'.
       평균 대비 말('평균의 절반 이하' 등)은 쓰지 않는다(사용자 피드백). 실망 확률 숫자는 배지가 이미 보여준다."""
    if not h.get('scored'): return ''
    parts = []
    n = KRN.get(pid, 0)
    if n >= 10: parts.append(f'<span class="seg">한국인 리뷰 {n}건</span>')
    c = CITY.get('crit') or 0
    wc = worst_cat_of(h) if (c and h['p_crit'] / c >= 1.2) else None
    if wc: parts.append(f'<span class="seg">주로 {E(cat_ko(wc))} 불만</span>')
    if not parts: return ''
    return f'<div class="{cls}">{DSEP.join(parts[:2])}</div>'

def short_name(title):
    """칩·비교 카드용 짧은 이름: 앞 '호텔 '·뒤 ' 호텔'·도시명 제거 (3자 미만이 되면 원래 이름)."""
    t = re.sub(r'^호텔\s+', '', str(title or ''))
    t2 = re.sub(r'\s*' + re.escape(CITY['ko']) + r'\s*', ' ', t).strip()
    t2 = re.sub(r'\s+호텔$', '', t2).strip()
    return t2 if len(t2) >= 3 else t

def load_pairs():
    f = os.path.join(ROOT, 'scripts', 'compare_pairs.json')
    try: return json.load(open(f, encoding='utf-8'))['pairs']
    except Exception: return []

def resolve_pairs(hotels_meta, H):
    """compare_pairs.json의 정규식 쌍 → [(pid_a, pid_b)] (둘 다 채점 호텔). 순서 유지·중복 제거."""
    out, seen = [], set()
    def find(rx):
        for p, m in hotels_meta.items():
            if p in H and H[p]['scored'] and re.search(rx, m['title']): return p
        return None
    for a, b in load_pairs():
        pa, pb = find(a), find(b)
        if pa and pb and pa != pb and (pa, pb) not in seen:
            seen.add((pa, pb)); out.append((pa, pb))
    return out

def vs_verdict(pa, pb, hotels_meta, H):
    """비교 카드 결론 1줄 (HOME-CONCEPT §2.1 · FEEDBACK-2610 §2.2): 둘 다 위험 → '두 곳 다 평균보다 실망이 잦아요',
    차이 < 평균의 0.3배면 '비슷해요', 1.5배 이상이면 'N배 낮아요'. 반환 (문구 HTML, 낮은 쪽 pid|None)."""
    a, b = H[pa]['p_crit'], H[pb]['p_crit']
    c = CITY.get('crit') or 1e-9
    if H[pa]['badge'][0] == 'danger' and H[pb]['badge'][0] == 'danger':
        return '두 곳 다 평균보다 실망이 잦아요', None
    if abs(a - b) < 0.3 * c:
        return '두 곳 실망 확률이 비슷해요', None
    lo = pa if a <= b else pb
    r = max(a, b) / max(min(a, b), 1e-9)
    name = E(short_name(hotels_meta[lo]['title']))
    if r >= 1.5:
        return f'<span class="seg">{name}{josa_iga(name)}</span> <span class="seg">실망 확률 {r:.1f}배 낮아요</span>', lo
    return f'<span class="seg">{name}{josa_iga(name)}</span> <span class="seg">실망 확률이 낮아요</span>', lo

def vs_sub(pa, pb, win, hotels_meta, H):
    """비교 카드 결론 상자의 보조 문장과 상자 톤 (FEEDBACK-2610 §2.2). 반환 (문장 HTML, 'ok'|'bad')."""
    c = CITY.get('crit') or 1e-9
    ha, hb = H[pa], H[pb]
    def nm(p): return E(short_name(hotels_meta[p]['title']))
    def worst(p): return worst_cat_of(H[p])
    if ha['badge'][0] == 'danger' and hb['badge'][0] == 'danger':
        cats = [x for x in dict.fromkeys([worst(pa), worst(pb)]) if x]
        return (f'주로 {"·".join(E(cat_ko(x)) for x in cats)} 불만이에요' if cats else ''), 'bad'
    if win is None:                                    # 차이가 평균의 0.3배 미만 — 비슷해요
        if ha['p_crit'] <= SAFE_MULT * c and hb['p_crit'] <= SAFE_MULT * c:
            return '둘 다 평균보다 실망이 적어요', 'ok'
        if ha['p_crit'] >= 1.2 * c and hb['p_crit'] >= 1.2 * c:   # 가정: 둘 다 평균보다 높으면 '평균 수준'이라 쓰지 않는다
            return '둘 다 평균보다 실망이 많은 편이에요', 'ok'
        return f'둘 다 {CITY["ko"]} 평균 수준이에요', 'ok'
    lose = pb if win == pa else pa
    ln, wc = nm(lose), worst(lose)
    if H[lose]['badge'][0] == 'danger':                # 한쪽만 위험 — 상자는 이긴 쪽 기준(ok), 진 쪽 주의 안내
        return (f'<span class="seg">{ln}{josa_eun(ln)} 주의가 필요해요</span>'
                + (f'{DSEP}<span class="seg">주로 {E(cat_ko(wc))} 불만</span>' if wc else '')), 'ok'
    if wc:
        return f'<span class="seg">{ln}{josa_eun(ln)}</span> <span class="seg">주로 {E(cat_ko(wc))} 불만이에요</span>', 'ok'
    if H[lose]['p_crit'] <= SAFE_MULT * c:
        return f'<span class="seg">{ln}도</span> <span class="seg">평균보다 실망이 적어요</span>', 'ok'
    return f'<span class="seg">{ln}도</span> <span class="seg">평균 수준이에요</span>', 'ok'

def vs_topic(pa, pb, hotels_meta):
    """비교 카드 주제 한 줄: 두 호텔의 지역(같으면 '텐진', 다르면 '하카타역 vs 텐진') + 같은 가격대면 밴드."""
    def area_of(p):
        m = hotels_meta[p]
        for a in AREAS:
            if _in_area(m, a): return a['ko'].split('·')[0]
        return None
    a, b = area_of(pa), area_of(pb)
    if a and b and a != b: return f'{a} vs {b}'                 # 지역이 다르면 그 자체가 주제
    area = a or b
    ba, bb = hotels_meta[pa].get('band'), hotels_meta[pb].get('band')
    band = ba[1] if (ba and bb and ba[0] == bb[0]) else None
    parts = [x for x in (area, band) if x]
    return (' · '.join(parts) + ' 숙소') if parts else '숙소 비교'

VS_ICON_OK = ('<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="currentColor"/>'
              '<path d="m6 10.2 2.6 2.6L14 7.4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
VS_ICON_BAD = ('<svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="currentColor"/>'
               '<path d="M10 5.5v5.5" stroke="white" stroke-width="2.2" stroke-linecap="round"/><circle cx="10" cy="14.3" r="1.3" fill="white"/></svg>')

def vs_card(pa, pb, hotels_meta, H, depth=0):
    """홈 비교 카드 1장 (FEEDBACK-2610 §2.2): 주제 칩 · 사진 2장 + VS · 이름·평점 2열 · 실망 확률 / 한국인 리뷰 / 1박 평일 행
    (A값 | 라벨 | B값) · 결론 상자(아이콘 + 굵은 결론 + 보조 문장) → compare 프리셋 링크. 색 면은 결론 상자에만."""
    root = '../' * depth
    verdict, win = vs_verdict(pa, pb, hotels_meta, H)
    sub, tone = vs_sub(pa, pb, win, hotels_meta, H)
    def w(p): return ' is-win' if p == win else ''
    def pic(p):
        m = hotels_meta[p]
        return f'<span class="vs-pic"><img src="{img_path(p, m, depth)}" alt="{E(m["title"])}" width="300" height="225" loading="lazy"></span>'
    def col(p):
        m = hotels_meta[p]
        return (f'<span class="vs-col"><span class="vs-n{w(p)}">{E(short_name(m["title"]))}</span>'
                f'<span class="vs-g"><img src="{root}img/star.svg" alt="" width="14" height="14">{fmt_score(m.get("total_score"))} ({m.get("reviews_count") or 0:,})</span></span>')
    def val(p, kind):
        h, m = H[p], hotels_meta[p]
        if kind == 'p': return f'<b class="vs-v vs-p{w(p)}">{pct(h["p_crit"])}%</b>'
        if kind == 'kr':
            n = KRN.get(p, 0)
            return f'<span class="vs-v{w(p)}">{n}건</span>' if n >= 10 else '<span class="vs-v vs-none">리뷰 10건 미만</span>'
        pt = m.get('price_txt') or ''
        if not pt: return '<span class="vs-v vs-none">가격 정보 없음</span>'
        return f'<span class="vs-v{w(p)}">{E(pt[3:] if pt.startswith("평일 ") else pt)}</span>'
    def row(label, kind):
        return f'<div class="vs-r">{val(pa, kind)}<span class="vs-k">{label}</span>{val(pb, kind)}</div>'
    box_cls = 'is-bad' if tone == 'bad' else 'is-ok'
    icon = VS_ICON_BAD if tone == 'bad' else VS_ICON_OK
    return f'''<a class="vs-card" href="{root}compare?ids={pa},{pb}">
        <div class="vs-topic">{E(vs_topic(pa, pb, hotels_meta))}</div>
        <div class="vs-pics">{pic(pa)}<span class="vs-x">VS</span>{pic(pb)}</div>
        <div class="vs-heads">{col(pa)}{col(pb)}</div>
        <div class="vs-rows">
            {row('실망 확률', 'p')}
            {row('한국인 리뷰', 'kr')}
            {row('1박 평일', 'pr')}
        </div>
        <div class="vs-box {box_cls}"><span class="vs-ico">{icon}</span><span class="vs-bt"><b class="vs-verdict">{verdict}</b>{f'<span class="vs-sub">{sub}</span>' if sub else ''}</span></div>
    </a>'''

def stars_label(meta):
    """카드용 성급 표기: '3성급 호텔'·'캡슐 호텔'만. 구글이 그냥 '호텔'로 준 12곳은 빈 값(카드에 '· 호텔'이 떠서 어색)."""
    st = str(meta.get('hotel_stars') or '')
    return st if (any(ch.isdigit() for ch in st) or '캡슐' in st) else ''

def badge_html(h):
    if not h['scored']:
        return '<div class="badge-item badge-collect">분석 준비 중</div>'
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

def hotel_card(pid, meta, h, depth=0, extra=''):
    """extra: info 하단 추가 HTML (상세 '약점 맞춤 대안'의 비교 줄 등). 기본 빈값 = 기존 카드 그대로."""
    p = '../' * depth
    star_w = round(float(meta.get('total_score') or 0) / 5 * 100)
    al = area_line_html(meta)
    pl = price_line_html(meta)
    return f'''<li class="swiper-slide">
        <a href="{p}hotels/{pid}" class="item">
            <div class="thumb">
                <div class="badge">{badge_html(h)}</div>
                <div class="image"><img src="{img_path(pid, meta, depth)}" alt="{E(meta['title'])}" width="600" height="400" loading="lazy"></div>
            </div>
            <div class="info">
                <h3 class="name">{E(meta['title'])}</h3>
                {f'<div class="area-line">{al}</div>' if al else ''}
                <div class="star"><i style="width:{star_w}%"></i></div>
                <div class="text">구글 평점 {fmt_score(meta.get('total_score'))} ({meta.get('reviews_count') or 0:,})</div>
                <div class="price-line">{pl or '&nbsp;'}</div>
                {why_line(pid, h)}
                {extra}
            </div>
        </a>
    </li>'''

# ───────────────────────── index ─────────────────────────
def ai_reviews_total():
    """AI가 실제로 읽은 글 리뷰 수(agg_reviewlevel.analyzed 합) — 'AI가 N건 분석' 문구용. 별점만 리뷰는 제외."""
    return sum(r['analyzed'] for r in json.load(open(os.path.join(SRC, 'agg_reviewlevel.json'), encoding='utf-8')))

def build_index(hotels_meta, H, quotes, col_index=()):
    scored = [p for p in H if H[p]['scored'] and p in hotels_meta]  # hotels_meta가 rec_excluded 제외 → scored도 자동 제외
    ranked = [p for p in scored if H[p]['ranked']]   # 추천·랭킹 모수 = 최근 1년 리뷰 RANK_MIN 이상 (2026-10 표본 공정성)
    _total = sum(r['n'] for r in json.load(open(os.path.join(SRC, 'agg_denom.json'), encoding='utf-8')))
    total_reviews_txt = f"{round(_total/10000)}만"   # 동적: 수집 리뷰 총수 (별점만 리뷰 포함, 예: 6만)
    ai_reviews_txt = f"{round(ai_reviews_total()/10000)}만"   # AI가 읽은 글 리뷰 수 (예: 3만) — 'AI가 분석' 문구는 이 값

    def worst_by_sub(mcat, scat, k=8):
        cand = [p for p in ranked if H[p]['cats'][mcat]['subs'][scat]['count_1y'] >= 5]   # 점수와 같은 최근 1년 기준
        return sorted(cand, key=lambda p: -H[p]['cats'][mcat]['subs'][scat]['score'])[:k]

    # 추천순(rec_score) — 실망 확률 단독 정렬은 한국인이 안 가는 조용한 호텔을 1위에 올렸다(RECOMMEND-PRICE-DESIGN §2.4).
    rec_pool = sorted((p for p in ranked if p in REC), key=lambda p: -REC[p])
    best = [p for p in rec_pool if H[p]['badge'][0] != 'danger'][:8]              # 홈 추천은 위험 배지 제외
    gems = [p for p in rec_pool if KRN.get(p, 0) < 50 and H[p]['p_crit'] <= SAFE_MULT * (CITY.get('crit') or 0)
            and bayes_rating(hotels_meta[p].get('total_score'), hotels_meta[p].get('reviews_count')) >= 4.2][:8]   # 조용히 좋은 곳(인기 가중 상쇄)
    hot = sorted((p for p in scored), key=lambda p: -KRN.get(p, 0))[:6]           # 히어로 칩: 판정 진입이라 위험도 포함
    cur1 = worst_by_sub('청결', '벌레')
    cur2 = worst_by_sub('냄새', '악취')

    def slider(title, desc, pids):
        cards = '\n'.join(hotel_card(p, hotels_meta[p], H[p]) for p in pids)
        return f'''<div class="hotel-list init">
            <div class="head"><div class="title">{title}</div><div class="desc">{desc}</div></div>
            <div class="list hotel-slider"><ul class="swiper-wrapper">{cards}</ul></div>
        </div>'''

    # 가격대별 만족도: 각 밴드에서 실망 확률 낮은 순
    price_parts = []
    for code, label, lo, hi in PRICE_BANDS:
        pids = sorted((p for p in ranked if hotels_meta[p].get('band') and hotels_meta[p]['band'][0] == code),
                      key=lambda p: -REC.get(p, 0))[:8]
        if len(pids) >= 3:
            price_parts.append(slider(f'<em>{label}</em> 추천',
                f'2인 1박 평일 가격 기준 ({CITY["price_seen"]} 확인)', pids))
    price_sliders = ''.join(price_parts)

    # 동네·동행·테마별 허브 칩 (FEEDBACK-2610 §3): 3줄(라벨 + 가로 스크롤 칩), 홈 마지막 블록. 생성된 허브만 노출 — 순서는 COLLECTIONS
    col_chips = ''
    if col_index:
        rows = []
        for row, label in COL_ROWS:
            items = [(slug, name) for slug, name in col_index if COL_BY_SLUG.get(slug, {}).get('row') == row]
            if not items: continue
            chips = ''.join(f'<a class="hub-home-chip" href="./{E(slug)}">{E(COL_BY_SLUG[slug].get("chip") or name)}</a>' for slug, name in items)
            rows.append(f'<div class="hub-home-row"><span class="hh-label">{label}</span><div class="hub-home-chips">{chips}</div></div>')
        col_chips = f'''<article class="section sec-collections">
                <div class="home-collections init">
                    <div class="head"><div class="title"><em>동네</em>·<em>동행</em>별로 보기</div>
                    <div class="desc">같은 조건끼리 추천순으로 모았어요</div></div>
                    {''.join(rows)}
                </div>
            </article>'''

    # 블록 2: 지금 한국인이 가장 많이 고민하는 비교 (카페 'A vs B' 151/1000건) — HOME-CONCEPT §2.1
    # 카페 최다 비교 4쌍은 그대로, 보여주는 순서만 '실망 확률 차이가 큰 쌍 먼저' — '비슷해요' 카드가 앞에 오면 비교할 거리가 없어 보임
    _gap = lambda pr: max(H[pr[0]]['p_crit'], H[pr[1]]['p_crit']) / max(min(H[pr[0]]['p_crit'], H[pr[1]]['p_crit']), 1e-6)
    vs_cards = ''.join(vs_card(pa, pb, hotels_meta, H) for pa, pb in sorted(PAIRS[:4], key=_gap, reverse=True))
    vs_block = f'''<article class="section sec-vs">
                <div class="home-vs init">
                    <div class="head"><div class="title"><em>한국인</em>이 가장 많이 <em>비교</em>하는 숙소</div>
                    </div>
                    <div class="vs-list">{vs_cards}</div>
                </div>
            </article>''' if vs_cards else ''
    hero_chips = ''.join(f'<a class="hero-chip" href="./hotels/{p}">{E(short_name(hotels_meta[p]["title"]))}</a>' for p in hot)
    hero_chips_html = (f'<div class="hero-chips"><span class="hc-label">많이 찾는 호텔</span>{hero_chips}</div>'
                       if hero_chips else '')
    gems_slider = slider('<em>숨겨진 보석</em> 같은 곳', '한국인 리뷰는 적지만 실망 확률 낮고 평점 높아요', gems) if len(gems) >= 3 else ''

    n_live = sum(1 for pid in hotels_meta if pid in H)   # 상세 생성되는 호텔 수
    home_ld = _jsonld({'@context':'https://schema.org','@type':'WebSite','name':'캐치플로','alternateName':'CATCHFLAW',
        'url':f'{BASE}/', 'potentialAction':{'@type':'SearchAction',
        'target':{'@type':'EntryPoint','urlTemplate':f'{BASE}/search?q={{search_term_string}}'},
        'query-input':'required name=search_term_string'}})
    html_out = head('캐치플로 — 후쿠오카 호텔 리뷰 위험도·실망 확률 분석',
        description=f'{CITY["ko"]} 호텔 {n_live}곳의 실제 리뷰를 AI로 분석해 실망 확률을 알려드립니다. '
                    '청결·냄새·소음·객실·직원·위치 6개 항목과 안전 신호를 예약 전에 확인하세요.',
        canonical=f'{BASE}/', extra_head=home_ld) + f'''
    <link rel="preload" as="image" href="./img/home_bg.jpg" media="(max-width:1099px)" fetchpriority="high">
    <link rel="preload" as="image" href="./img/home_bg_pc.jpg" media="(min-width:1100px)" fetchpriority="high">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">''' + site_header(0, search=False) + f'''
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
                        <div class="txt">AI가 {CITY['ko']} 호텔 리뷰 {ai_reviews_txt} 개를 분석해 <br><span>치명적인 단점</span>만 찾아냅니다.</div>
                    </div>
                    <form class="input" action="./search" method="get" autocomplete="off">
                        <input type="text" name="q" id="hero-q" placeholder="{CITY['ko']} 호텔명 또는 구글맵 링크 붙여넣기">
                        <button type="submit"><img src="./img/search.svg" alt="검색"></button>
                        <div class="ac-box" id="ac-box" hidden></div>
                    </form>
                    {hero_chips_html}
                </div>
            </article>
            <div class="trust-band"><span class="tb-i">추천 순서에 광고·수수료 없음</span><span class="tb-i">{CITY['data_asof']} 기준</span></div>
            {vs_block}
            <article class="section sec-2 sec-rec">
                {slider('<em>한국인</em>이 찾고 <em>실망</em>은 적은 숙소', '한국인 리뷰 많고 평점 높고 실망 확률 낮은 순', best)}
            </article>
            <article class="section sec-map">
                <div class="home-map init">
                    <div class="head"><div class="title"><em>지도</em>로 한눈에</div>
                    <div class="desc">마커 색 = 등급 · 누르면 실망 확률</div></div>
                    <div class="map-wrap"><div id="map"></div>
                        <div class="map-legend">
                            <span class="lg safe">양호</span><span class="lg warning">주의</span><span class="lg danger">위험</span><span class="lg none">준비 중</span>
                        </div>
                    </div>
                    <div class="map-more"><button type="button" class="map-more-btn btn-airec">딱 맞는 호텔 찾기</button></div>
                </div>
            </article>
            <article class="section sec-2">
                {price_sliders}
                {gems_slider}
                {slider('<em>벌레</em> 언급 많은 숙소', '예약 전에 꼭 확인하세요', cur1)}
                {slider('<em>냄새</em> 언급 많은 숙소', '하수구·곰팡내 언급이 많아요', cur2)}
                <script>
                    $(function(){{
                        $('.hotel-slider').each(function(i, el){{
                            new Swiper(el, {{slidesPerView:'auto', spaceBetween:10, observer:true, observeParents:true}});
                        }});
                    }});
                </script>
            </article>
            {col_chips}
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
            var col = (h.band && BAND_COLOR[h.band]) || '#8B95A1';
            var mk = L.circleMarker([h.lat, h.lng], {{radius: 8, color: '#fff', weight: 2, fillColor: col, fillOpacity: 0.95}}).addTo(map);
            var chip = h.p != null
                ? '<span class="pop-p" style="background:' + col + '">실망 확률 ' + h.p + '%</span>'
                : '<span class="pop-p" style="background:var(--ink-3)">분석 준비 중</span>';
            mk.bindPopup('<div class="map-pop"><b>' + h.name + '</b>'
                + '<div class="pop-meta">★ ' + (h.g ? h.g.toFixed(1) : '-') + ' (' + h.rc.toLocaleString() + ')'
                + (h.pt ? ' · 1박 ' + h.pt : '') + '</div>' + chip
                + '<a class="pop-link" href="./hotels/' + h.id + '">상세 보기 →</a></div>');
            pts.push([h.lat, h.lng]);
        }});
        // 화면 맞춤은 도심 기준: 중앙값에서 5km 밖 외곽 호텔은 맞춤에서만 제외(마커는 그대로) — 검색 지도와 동일
        var med = function(a){{ a = a.slice().sort(function(x, y){{ return x - y; }}); return a[Math.floor(a.length / 2)]; }};
        var mLat = med(pts.map(function(p){{ return p[0]; }})), mLng = med(pts.map(function(p){{ return p[1]; }}));
        var core = pts.filter(function(p){{ return Math.abs(p[0] - mLat) * 111 <= 5 && Math.abs(p[1] - mLng) * 93 <= 5; }});
        var fit = core.length >= pts.length * 0.8 ? core : pts;
        if (fit.length) map.fitBounds(fit, {{padding: [24, 24], maxZoom: 14}});
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

        // 홈 블록별 클릭 측정 (HOME-CONCEPT §6: 2주 뒤 블록 순서 재조정 근거)
        $(document).on('click', '.hero-chip, .hero-cmp, .vs-card, .hotel-list .item, .hub-home-chip', function(){{
            if (typeof gtag !== 'function') return;
            var pl = this.classList.contains('hero-chip') ? 'hero_chip' : this.classList.contains('hero-cmp') ? 'hero_compare'
                   : this.classList.contains('vs-card') ? 'vs_card' : this.classList.contains('hub-home-chip') ? 'collection_chip' : 'home_card';
            var blk = $(this).closest('.hotel-list, .home-vs, .search-box, .home-collections').find('.title, .tit').first().text().trim();
            gtag('event', 'home_click', {{placement: pl, block: blk.slice(0, 40), link_url: this.getAttribute('href') || ''}});
        }});
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
        extra_head='<meta name="robots" content="noindex">') + site_header(0, back='./') + f'''
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

def abs_img(pid, meta):
    """페이지 깊이와 무관한 썸네일 URL (비교함 localStorage 공유용): R2 절대 → 루트 기준 로컬 → 빈값."""
    if meta.get('r2_img'): return meta['r2_img']
    if meta.get('local_img'): return f'/img/hotels/{pid}.jpg'
    return ''

def top_complaint(h):
    """P1과 같은 기준의 대표 불만 1개: 주의·위험 소분류 & 최근 1년 3건+ & 비율 2%+ 중 위험도 최고.
       반환 (소분류, band, 최근1년건수) 또는 None."""
    best = None
    for c in CATS:
        for s in SUBS[c]:
            sb = h['cats'][c]['subs'][s]
            n1 = sb.get('count_1y', 0)
            if (s not in RARE_SUBS and sb['band'] in ('warning', 'danger') and n1 >= 3
                    and h['analyzed'] and n1 / h['analyzed'] >= 0.02):
                if best is None or sb['score'] > best[0]:
                    best = (sb['score'], s, sb['band'], n1)
    return best[1:] if best else None

def card_tags(h):
    """P6 검색 카드 태그(최대 2): 가장 안전한 양호 카테고리 + 대표 불만. [[tone, text], ...] — 실측만."""
    if not h['scored'] or not h['ranked']: return []   # 리뷰 적은 호텔은 '불만 적음' 같은 비교형 태그 생략
    tags = []
    tc = top_complaint(h)
    tc_cat = next((c for c in CATS if tc and tc[0] in SUBS[c]), None)
    safe = sorted((c for c in CATS if h['cats'][c]['band'] == 'safe' and c != tc_cat),
                  key=lambda c: h['cats'][c]['score'])
    if safe: tags.append(['safe', f'{cat_ko(safe[0])} 불만 적음'])
    if tc: tags.append([tc[1], f'{SUB_PHRASE[tc[0]]} 불만'])
    return tags

# ── '1년 안에 한 번도 없어야' 조건 (FEEDBACK-2610 §6.1) — 검색 인덱스 x·검색 필터·AI 추천이 같은 숫자를 쓴다 ──
ROACH_RX = re.compile(r'바퀴|cockroach|roach|ゴキブリ|蟑螂', re.I)
NO_KEYS = [('roach', '바퀴벌레'), ('bug', '벌레 전부'), ('safe', '객실 보안·밤길')]   # URL no= 키 → 화면 라벨

def rare_counts(pid, h, quotes):
    """최근 1년 심각 리뷰 건수 3종: bug = 벌레 소분류 심각(scoring crit_1y), safe = 객실 보안 + 동네 분위기 심각,
    roach = 벌레 심각 인용(quotes.json, 호텔·카테고리별 40건 상한 — 하한값이지만 벌레 심각이 40건 넘는 호텔은 없다) 중
    본문에 바퀴벌레 언급. 채점 안 된 호텔은 None."""
    if not h.get('scored'): return None
    def crit(s): return int(h['cats'][SUB_CAT[s]]['subs'][s].get('crit_1y', 0) or 0)
    cut = str(date.fromisoformat(CITY['asof']) - timedelta(days=365)) if CITY.get('asof') else ''
    roach = 0
    for q in quotes.get((pid, SUB_CAT['벌레']), []):
        if q.get('scat') != '벌레' or q.get('grade') != '심각' or str(q.get('pub') or '') < cut: continue
        if any(ROACH_RX.search(str(q.get(k) or '')) for k in ('quote', 'summary', 'tfull', 'ofull')):
            roach += 1
    bug = crit('벌레')
    return {'bug': bug, 'roach': min(roach, bug) if bug else roach, 'safe': crit('객실 보안') + crit('동네 분위기')}

# ───────────────────────── compare (P5) ─────────────────────────
CMP_FAQ = [('luggage', '짐 보관'), ('breakfast', '조식'), ('bath', '대욕장·온천'), ('family', '아이 동반')]

def build_compare_data(hotels_meta, H, faq_data, monthly=None):
    """비교 페이지 전용 데이터(window.CF_CMP = {pid: {...}}). 채점 호텔만. 숫자는 전부 실측."""
    out = {}
    for pid, meta in hotels_meta.items():
        h = H.get(pid)
        if not h or not h['scored']: continue
        st = nearest_station(meta.get('latitude'), meta.get('longitude'))
        subs = []
        for c in CATS:
            for sname in SUBS[c]:
                if sname in RARE_SUBS: continue
                n1 = h['cats'][c]['subs'][sname].get('count_1y', 0)
                if n1 > 0 and h['analyzed']:
                    subs.append((n1, sname))
        top = [[SUB_PHRASE[sn], round(n1 / h['analyzed'] * 100, 1), n1] for n1, sn in sorted(subs, reverse=True)[:3]]
        fq = {it.get('t'): ' · '.join((it.get('c') or [])[:2]) for it in (faq_data.get(pid) or []) if it.get('c')}
        out[pid] = {
            'n': meta['title'], 'img': abs_img(pid, meta),
            'p': pct(h['p_crit']), 'b': h['badge'][0], 'l': h['badge'][1],
            'pt': meta.get('price_txt') or '', 'krw': meta.get('krw'),
            'g': float(meta.get('total_score') or 0), 'rc': meta.get('reviews_count') or 0, 'an': h['analyzed'],
            'lr': not h['ranked'],                          # 리뷰 적음(최근 1년 RANK_MIN 미만) — 순위 아닌 참고용
            'rs': round(REC.get(pid, 0.0), 3),              # 추천순 정렬값(추가 팝업 정렬용, 비노출)
            'la': float(meta['latitude']) if meta.get('latitude') else None,    # 추가 팝업 '비슷한 위치' 필터
            'lo': float(meta['longitude']) if meta.get('longitude') else None,
            'pd': period_label(h, (monthly or {}).get(pid)),   # 수치 기간 ('최근 1년' 또는 수집이 짧으면 '최근 N개월')
            'st': f'{st[0]} 도보 {st[1]}분' if st else '', 'sm': st[1] if st else None,
            'cs': {c: round(h['cats'][c]['score']) for c in CATS},
            'top': top,
            'fq': {k: fq.get(k, '') for k, _ in CMP_FAQ},
        }
    return out

def build_compare():
    """P5 비교 페이지 — ?ids=a,b,c(공유 URL) 또는 localStorage 비교함. 개인화·동적이라 noindex·sitemap 제외."""
    return head('호텔 비교 | 캐치플로', depth=0, extra_head='<meta name="robots" content="noindex">').replace(
        '<body>', '<body data-page="compare">') + site_header(0, back='./search') + f'''
    <main id="container">
        <section id="cmp">
            <div id="cmp-root"><div class="cmp-empty">불러오는 중…</div></div>
        </section>
    </main>
    <script>window.CF_CMP_FAQ = {json.dumps(CMP_FAQ, ensure_ascii=False)}; window.CF_CITY_KO = {json.dumps(CITY['ko'], ensure_ascii=False)};</script>
    <script src="./data/compare.js?v={BUILD}"></script>
    <script src="./js/compare.js?v={BUILD}" data-root="./"></script>
    <script src="./js/compare-page.js?v={BUILD}"></script>''' + build_footer(0) + FOOT

# ───────────────────────── search ─────────────────────────
def build_search_index(hotels_meta, H, quotes=None):
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
            'stars': stars_label(meta), 'g': float(meta.get('total_score') or 0),
            'rc': meta.get('reviews_count') or 0,
            'img': meta.get('r2_img') or (f'img/hotels/{pid}.jpg' if meta.get('local_img') else ''),
            'scored': h['scored'],
            'lr': bool(h['scored'] and not h['ranked']),    # 리뷰 적음 → 실망 확률·안심순 정렬에서 뒤로
            'p': pct(h['p_crit']) if h['scored'] else None,
            'band': h['badge'][0] if h['scored'] else None,
            'label': h['badge'][1] if h['scored'] else '분석 준비 중',
            'lat': float(meta['latitude']) if meta.get('latitude') else None,
            'lng': float(meta['longitude']) if meta.get('longitude') else None,
            'pb': meta['band'][0] if meta.get('band') else None,
            'pbw': (price_band(meta['price_we']) or (None,))[0] if meta.get('price_we') else None,   # 주말 가격대(AI 추천 '주말 기준')
            'x': rare_counts(pid, h, quotes or {}),   # 1년 심각 건수 {bug, roach, safe} — '한 번도 없어야' 조건
            'pt': meta.get('price_txt') or '',
            'ptw': man_txt(meta.get('price_we')) if (meta.get('price_txt') or '').startswith('평일') else '',   # 주말 '약 34만원'
            'ar': area_tag(meta),                # 지역 태그(하카타역·텐진·나카스·기온)
            'st': station_short(meta),           # '텐진역 도보 3분'
            'krw': meta.get('krw'),
            'rs': round(REC.get(pid, 0.0), 3),   # 추천순 정렬값 (화면 비노출)
            'krn': KRN.get(pid, 0),              # 한국인 리뷰 수(1년) — 사유줄
            'cb': cb, 'cs': cs,
            'ai': abs_img(pid, meta),          # 비교함 썸네일(깊이 무관)
            'tg': card_tags(h),                # P6 카드 태그
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
            'tok': (r.get('tok') or [])[:60],   # 토큰 매칭(FEEDBACK-2610 §15) — pipeline/build_index.py token_keys
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
        ''' + site_header(0, back='./', search=False) + f'''
        <section id="title">
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
                </div>
                <button type="button" class="f-more" id="f-more" aria-expanded="false" aria-controls="f-panel"><span class="f-more-t">조건 더 보기</span><svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="m3 5 4 4 4-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
                <div class="f-panel" id="f-panel" hidden>
                    <div class="fp-group">
                        <div class="fp-tit">불만이 적었으면 하는 항목</div>
                        <div class="fp-sub">고른 항목이 &lsquo;위험&rsquo; 등급인 호텔은 빼드려요</div>
                        <div class="fp-chips" id="fp-cats"></div>
                    </div>
                    <div class="fp-group">
                        <div class="fp-tit">1년 안에 한 번도 없어야 해요</div>
                        <div class="fp-sub">심각 리뷰 기준 · 주의 리뷰는 세지 않아요</div>
                        <div class="fp-chips" id="fp-no"></div>
                    </div>
                    <button type="button" class="fp-reset" id="fp-reset">초기화</button>
                </div>
            </div>
            <div class="map-wrap is-collapsed" id="map-wrap"><div id="map"></div>
                <div class="map-legend">
                    <span class="lg safe">양호</span><span class="lg warning">주의</span><span class="lg danger">위험</span><span class="lg none">준비 중</span>
                </div>
            </div>
            <div class="map-hint is-collapsed" id="map-hint"></div>
            <div class="total" id="total"></div>
            <div class="notice" id="notice" style="display:none"></div>
            <div class="list-head" id="list-head" style="display:none">
                <div class="lh-count" id="lh-count"></div>
                <div class="lh-sort" id="lh-sort">
                    <button type="button" class="lh-sort-btn" id="lh-sort-btn">추천순</button>
                    <div class="lh-sort-box">
                        <button type="button" class="on" data-sort="rs" data-label="추천순">추천순<span class="ls-sub">{REC_SORT_DESC}</span></button>
                        <button type="button" data-sort="p" data-label="실망 확률 낮은 순">실망 확률 낮은 순<span class="ls-sub">최근 1년 실망한 리뷰 비율이 낮은 곳부터</span></button>
                        <button type="button" data-sort="krn" data-label="한국인이 많이 가는 순">한국인이 많이 가는 순<span class="ls-sub">최근 1년 한국인 리뷰가 많은 곳부터</span></button>
                        <button type="button" data-sort="g" data-label="구글 평점 높은 순">구글 평점 높은 순<span class="ls-sub">별점만 보고 싶을 때</span></button>
                        <button type="button" data-sort="rc" data-label="구글 리뷰 많은 순">구글 리뷰 많은 순<span class="ls-sub">크고 유명한 호텔부터</span></button>
                        <button type="button" data-sort="price" data-label="1박 가격 낮은 순">1박 가격 낮은 순<span class="ls-sub">2인 1박 평일 가격 기준</span></button>
                        <div class="lh-sort-sep">걱정되는 항목이 적은 곳부터</div>
                        <button type="button" data-sort="cat:청결" data-label="청결 불만 적은 순">청결 불만 적은 순<span class="ls-sub">머리카락·벌레·곰팡이</span></button>
                        <button type="button" data-sort="cat:냄새" data-label="냄새 불만 적은 순">냄새 불만 적은 순<span class="ls-sub">담배·하수구·곰팡내</span></button>
                        <button type="button" data-sort="cat:소음" data-label="소음 불만 적은 순">소음 불만 적은 순<span class="ls-sub">옆방·도로·기계음</span></button>
                        <button type="button" data-sort="cat:객실" data-label="객실 불만 적은 순">객실 불만 적은 순<span class="ls-sub">좁은 방·침대·온도·고장</span></button>
                        <button type="button" data-sort="cat:직원" data-label="직원 불만 적은 순">직원 불만 적은 순<span class="ls-sub">불친절·대기·대응</span></button>
                        <button type="button" data-sort="cat:위치" data-label="위치 불만 적은 순">위치 불만 적은 순<span class="ls-sub">역까지 거리·주변·밤길</span></button>
                    </div>
                </div>
            </div>
            <div class="list"><ul id="results"></ul></div>
            <button type="button" class="map-toggle" id="map-toggle" aria-pressed="false"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M1.5 3.5 5.5 2l5 1.5 4-1.5v10.5l-4 1.5-5-1.5-4 1.5V3.5ZM5.5 2v10.5M10.5 3.5V14" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg><span class="mt-t">지도로 보기</span></button>
        </section>
    </main>
    <script src="./js/compare.js?v={BUILD}" data-root="./"></script>

    <script src="./data/index.js?v={BUILD}"></script>
    <script defer src="./data/search_index.js?v={BUILD}"></script>
    <script src="./js/search-key.js?v={BUILD}"></script>
    <script src="./js/search-ac.js?v={BUILD}"></script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    (function(){{
        var CITY_KO = '{CITY['ko']}', CITY_AVG = {city_avg_pct}, KRN_MAX = {max(list(KRN.values()) or [1])};
        var OTHER = {kw};
        var CATS = {cats_js};
        var AREAS = window.CF_AREAS || [];
        var $q = $('#q'), $res = $('#results'), $total = $('#total'), $notice = $('#notice');
        var $lhead = $('#list-head'), $lcount = $('#lh-count'), $hint = $('#map-hint');
        var _sq = new URLSearchParams(location.search).get('sort');
        var fPrice = '', fBand = '', fArea = '', fCats = [], fNo = [], sortCat = '';
        var MUSTS = (window.CFRec && window.CFRec.MUSTS) || [], MUST_BY = (window.CFRec && window.CFRec.mustBy) || {{}};
        function normNo(a){{ return (window.CFRec && window.CFRec.normNo) ? window.CFRec.normNo(a) : []; }}
        function passNo(h, no){{  // '1년 안에 한 번도 없어야' — 심각 건수(h.x)가 1건이라도 있으면 제외. 데이터 없는(미채점) 호텔도 제외
            if (!no.length) return true;
            if (!h.x) return false;
            for (var i=0;i<no.length;i++){{ if ((h.x[no[i]]||0) > 0) return false; }}
            return true;
        }}
        var sortBy = (['rs','p','krn','price','rc','g'].indexOf(_sq) >= 0) ? _sq : 'rs';   // 기본 추천순, ?sort= 프리셋 허용
        var CAT_ICON = {{'청결':'','냄새':'','소음':'','객실':'','직원':'','위치':'','안전':''}};
        var baseList = [];       // 검색+지역+가격+카테고리 필터 결과 (지도 뷰포트 제외)
        var syncMap = true;      // 지도 이동 시 리스트 연동 on/off
        var mapOpen = false;     // P6: 지도 기본 접힘 — 열렸을 때만 '지도 영역 내' 연동
        var lastQ = '';          // 검색어 측정 중복 방지

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
            if (!mapOpen) return;             // P6: 접힌 상태면 지도 그리기는 열 때(openMap)
            map.invalidateSize();
            if (recMode) return;              // rec 모드는 drawRecMap이 별도 처리
            if (!baseList.length) return;
            var a = fArea ? AREAS.filter(function(x){{ return x.code === fArea; }})[0] : null;
            if (a) {{ map.setView([a.lat, a.lng], 15, {{animate:false}}); drawMap(baseList, false); renderVisible(); }}
            else {{ drawMap(baseList, true); }}
        }}, 80);
        $(window).on('load', function(){{ map.invalidateSize(); }});

        function popupHtml(h){{
            var col = (h.band && BAND_COLOR[h.band]) || '#8B95A1';
            var chip = h.p != null ? '<span class="pop-p" style="background:'+col+'">실망 확률 '+h.p+'%</span>'
                                   : '<span class="pop-p" style="background:var(--ink-3)">분석 준비 중</span>';
            return '<div class="map-pop"><b>'+h.name+'</b>'
                + '<div class="pop-meta">★ '+(h.g?h.g.toFixed(1):'-')+' ('+h.rc.toLocaleString()+')'
                + (h.pt?' · 1박 '+h.pt:'')+'</div>'+chip
                + '<a class="pop-link" href="./hotels/'+h.id+'">상세 보기 →</a></div>';
        }}
        // 화면 맞춤용 좌표: 중앙값에서 5km 밖 외곽 호텔(시카노시마 등)은 맞춤에서만 제외 — 도심이 작게 보이는 문제 방지
        function fitPts(list){{
            var pts = list.filter(function(h){{ return h.lat != null; }}).map(function(h){{ return [h.lat, h.lng]; }});
            if (pts.length < 5) return pts;
            var med = function(a){{ a = a.slice().sort(function(x,y){{ return x-y; }}); return a[Math.floor(a.length/2)]; }};
            var mLat = med(pts.map(function(p){{ return p[0]; }})), mLng = med(pts.map(function(p){{ return p[1]; }}));
            var core = pts.filter(function(p){{ return km(mLat, mLng, p[0], p[1]) <= 5; }});
            return core.length >= pts.length * 0.8 ? core : pts;
        }}
        var markerById = {{}};
        function drawMap(list, fit){{
            markers.clearLayers(); markerById = {{}};
            var pts = [];
            list.forEach(function(h){{
                if (h.lat == null) return;
                var col = (h.band && BAND_COLOR[h.band]) || '#8B95A1';
                var mk = L.circleMarker([h.lat,h.lng], {{radius:8, color:'#fff', weight:2, fillColor:col, fillOpacity:0.95}});
                mk.bindPopup(popupHtml(h));
                markers.addLayer(mk); markerById[h.id] = mk;
                pts.push([h.lat,h.lng]);
            }});
            var fp = fitPts(list);
            if (fit && fp.length) {{ syncMap = false; map.once('moveend', function(){{ syncMap = true; renderVisible(); }}); map.fitBounds(fp, {{padding:[28,28], maxZoom:15}}); }}
        }}

        // ───── 정렬 ─────
        var BAND_KO = {{safe:'양호', warning:'주의', danger:'위험'}};
        function sortList(arr){{
            var a = arr.slice();
            if (sortCat){{  // 카테고리 안심순 (해당 카테고리 위험도 낮은 순)
                a.sort(function(x,y){{
                    var sx = (x.cs && x.cs[sortCat] != null) ? x.cs[sortCat] : 999;
                    var sy = (y.cs && y.cs[sortCat] != null) ? y.cs[sortCat] : 999;
                    return (x.lr?1:0)-(y.lr?1:0) || sx - sy;   // 리뷰 적은 호텔은 순위 정렬에서 뒤로
                }});
            }} else if (sortBy === 'price') a.sort(function(x,y){{ return (x.krw==null)-(y.krw==null) || (x.krw||0)-(y.krw||0); }});
            else if (sortBy === 'rc') a.sort(function(x,y){{ return (y.rc||0)-(x.rc||0); }});
            else if (sortBy === 'g') a.sort(function(x,y){{ return (y.g||0)-(x.g||0); }});
            else if (sortBy === 'krn') a.sort(function(x,y){{ return (y.krn||0)-(x.krn||0) || (x.p==null)-(y.p==null) || (x.p||0)-(y.p||0); }});   // 한국인이 많이 가는 순(최근 1년 한국인 리뷰 수)
            else if (sortBy === 'rs') a.sort(function(x,y){{ return (x.p==null)-(y.p==null) || (x.lr?1:0)-(y.lr?1:0) || (y.rs||0)-(x.rs||0) || (x.p||0)-(y.p||0); }});   // 추천순(기본): 실망 확률·한국인 리뷰·평점 복합, 리뷰 적은 호텔은 뒤로
            else a.sort(function(x,y){{ return (x.p==null)-(y.p==null) || (x.lr?1:0)-(y.lr?1:0) || (x.p||0)-(y.p||0); }});  // 실망확률 낮은순(기본) · 리뷰 적은 호텔은 뒤로
            return a;
        }}

        // ───── 리스트 렌더 ─────
        function bandChip(h){{
            if(!h.scored) return '<span class="badge-item badge-collect">분석 준비 중</span>';
            return '<span class="badge-item badge-'+h.band+'">'+h.label+'</span>'
                 + '<span class="badge-item badge-down">실망 확률 '+h.p+'%</span>';
        }}
        function catChip(h){{  // 카테고리 정렬 시 해당 카테고리 등급을 카드에 표시
            if (!sortCat || !h.scored || !h.cb || h.cb[sortCat]==null) return '';
            var band = h.cb[sortCat], v = h.cs[sortCat];
            var lab = v < 25 ? '거의 없음' : v < 45 ? '적은 편' : v < 55 ? '평균 수준' : v < 70 ? '많은 편' : '많음';   // cat_verdict와 같은 구간
            return '<div class="cat-row is-'+band+'"><span class="ci">'+(CAT_ICON[sortCat]||'')+'</span>'
                + '<span class="cn">'+sortCat+' 불만</span>'
                + '<span class="cbadge">'+lab+'</span></div>';
        }}
        var WHY_SEP = '<span class="dsep"> · </span>';
        function whyHtml(h){{  // 카드 사유줄 (HOME-CONCEPT §2.2) — generate.why_line과 같은 규칙
            if (!h.scored) return '';
            var parts = [];
            if ((h.krn||0) >= 10) parts.push('<span class="seg">한국인 리뷰 '+h.krn+'건</span>');
            var r = CITY_AVG ? h.p / CITY_AVG : 0, wc = null;
            if (r >= 1.2 && h.cs){{
                var best = null; ['청결','냄새','소음','객실','직원','위치'].forEach(function(c){{ if (h.cs[c]!=null && (best==null || h.cs[c] > h.cs[best])) best = c; }});
                if (best && h.cb && (h.cb[best]==='warning' || h.cb[best]==='danger')) wc = best;
            }}
            if (wc) parts.push('<span class="seg">주로 '+wc+' 불만</span>');
            return parts.length ? '<div class="why">'+parts.slice(0,2).join(WHY_SEP)+'</div>' : '';
        }}
        function tagsHtml(h){{  // P6 리뷰 기반 태그(빌드 시 실측 산출). 좋은 쪽/나쁜 쪽이 색으로만 갈리지 않게 나쁜 쪽엔 '주의 ·'
            var tg = (h.tg || []).slice();
            var no = recMode ? recNo : fNo;   // '한 번도 없어야' 조건이 켜져 있으면 그 결과를 태그 1개로 맨 앞에(태그 2개 상한 안에서)
            if (no.length && h.x) tg.unshift(['safe', String((MUST_BY[no[0]]||{{}}).chip||'').replace(' 0건', '') + ' 심각 0건']);
            tg = tg.slice(0, 2);
            if (!tg.length) return '';
            return '<div class="r-tags">'+tg.map(function(t){{ return '<span class="r-tag is-'+t[0]+'">'+(t[0]==='safe' ? '' : '주의 · ')+t[1]+'</span>'; }}).join('')+'</div>';
        }}
        function statLine(h){{  // 평점 · 성급 · 1박 가격 한 줄 (도시명 'JP'는 후쿠오카 전용 사이트라 생략)
            var a = ['<span class="grade"><span class="ico"><img src="./img/star.svg" alt=""></span><span class="num">'+(h.g?h.g.toFixed(1):'-')+'</span><span class="txt">('+h.rc.toLocaleString()+')</span></span>'];
            if (h.stars) a.push('<span class="si"><span class="dot"></span><span>'+h.stars+'</span></span>');   // 구분점은 뒤 항목에 붙여 줄 끝에 남지 않게
            if (h.pt) a.push('<span class="si"><span class="dot"></span><span class="price">'+priceHtml(h)+'</span></span>');
            return '<div class="stat">'+a.join('')+'</div>';
        }}
        function priceHtml(h){{  // generate.price_line_html과 같은 규칙: 평일 굵게 + 주말(굵게 안 함, 넘치면 통째로 다음 줄)
            if (!h.pt) return '';
            if (recMode && recBw && h.ptw)   // AI 추천 '주말 기준': 주말 값을 굵게 앞에
                return '1박 <b>주말 '+h.ptw+'</b> <span class="seg pl-we">· '+h.pt+'</span>';
            return '1박 <b>'+h.pt+'</b>' + (h.ptw ? ' <span class="seg pl-we">· 주말 '+h.ptw+'</span>' : '');
        }}
        function areaHtml(h){{  // 지역 태그 + 역 도보 (generate.area_line_html과 같은 줄)
            if (!h.ar && !h.st) return '';
            return '<div class="area-line">'+(h.ar ? '<span class="area-tag">'+h.ar+'</span>' : '')+(h.st ? '<span class="seg">'+h.st+'</span>' : '')+'</div>';
        }}
        function footHtml(h){{  // 태그 + 비교 담기: 오른쪽 칸이 아니라 카드 아래 전체 폭
            var t = tagsHtml(h), c = cmpBtn(h);
            return (t || c) ? '<div class="r-foot">'+t+c+'</div>' : '';
        }}
        function cmpBtn(h){{   // P5 비교 담기 (채점 호텔만)
            if (!h.scored) return '';
            return '<button type="button" class="r-cmp" data-cmp-id="'+h.id+'" data-cmp-name="'+String(h.name).replace(/"/g,'&quot;')+'" data-cmp-img="'+(h.ai||'')+'" data-off="비교" data-on="비교"><i></i><span class="cmp-t">비교</span></button>';
        }}
        function row(h){{
            var img = h.img ? (h.img.indexOf('http')===0 ? h.img : './'+h.img) : './img/placeholder.svg';
            var price = h.pt ? '<span class="price">1박 <b>'+h.pt+'</b></span>' : '';
            return '<li data-id="'+h.id+'"><div class="item'+(h.scored?' with-cmp':'')+'">'
                + '<div class="thumb"><a href="./hotels/'+h.id+'"><img src="'+img+'" width="200" height="200" loading="lazy"></a></div>'
                + '<div class="cont">'
                + '<div class="info">'
                + '<div class="name"><a href="./hotels/'+h.id+'">'+h.name+'</a></div>'
                + '<div class="badge">'+bandChip(h)+'</div>'
                + statLine(h)
                + areaHtml(h)
                + '</div>'
                + whyHtml(h)
                + catChip(h)
                + '</div>'
                + footHtml(h)
                + '</div></li>';
        }}
        function renderRows(list){{
            if (!list.length) {{ $res.html('<li class="sub-head">이 조건에 맞는 호텔이 없어요. 필터를 조정해 보세요.</li>'); return; }}
            $res.html(sortList(list).map(row).join(''));
            if (window.CFCompare) window.CFCompare.render();   // 새로 그린 카드의 담김 상태 반영
        }}

        // 지도 뷰포트 안의 호텔만 리스트에 (C-3)
        function renderVisible(){{
            if (!mapOpen) {{
                $lcount.text('전체 ' + baseList.length + '곳');
                $lhead.toggle(baseList.length > 0);
                renderRows(baseList);
                $hint.html('');
                return;
            }}
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
            if (!passNo(h, fNo)) return false;
            return true;
        }}
        function filterLabel(){{
            var t = [];
            if (fArea){{ var a=AREAS.filter(function(x){{return x.code===fArea;}})[0]; if(a) t.push(a.ko); }}
            if (fPrice) t.push($('#f-price .f-chip[data-v="'+fPrice+'"]').text());
            if (fBand) t.push($('#f-band .f-chip[data-v="'+fBand+'"]').text());
            if (fCats.length) t.push(fCats.length + '개 항목 안심');
            if (fNo.length) t.push(fNo.map(function(k){{ return (MUST_BY[k]||{{}}).chip; }}).join(' · '));
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
                var suggested = false;   // 그래도 0건이면 비슷한 이름 제안(자모 바이그램 유사도, FEEDBACK-2610 §15-4)
                if (!matched.length && window.CFAutocomplete && window.CFAutocomplete.suggest) {{
                    var sIds = {{}}; window.CFAutocomplete.suggest(q, 3).forEach(function(it){{ sIds[it.id] = 1; }});
                    matched = pool.filter(function(h){{ return sIds[h.id]; }});
                    suggested = matched.length > 0;
                }}
                // 2) 매칭 0건일 때만 타도시 안내 발동 (§7-d)
                if (q !== lastQ && typeof gtag === 'function') {{
                    gtag('event', 'search', {{search_term: q, results: suggested ? 0 : matched.length}});
                    if (!matched.length || suggested) gtag('event', 'search_no_result', {{search_term: q}});
                }}
                lastQ = q;
                if (!matched.length) {{ unsupported(q); if (mapOpen) drawMap(HOTELS.filter(passFilters), true); return; }}
                pool = matched;
                $total.html(suggested ? '&ldquo;<span>'+q+'</span>&rdquo; 와 같은 이름은 없어요 · 혹시 이 호텔인가요?'
                                      : '&ldquo;<span>'+q+'</span>&rdquo; 검색 결과 <span class="highlight">'+pool.length+'건</span>'+filterLabel());
            }} else {{
                $total.html(CITY_KO+' 호텔 <span class="highlight">'+pool.length+'곳</span>'+filterLabel()+' · 도시 평균 실망&nbsp;확률 '+CITY_AVG+'%');
            }}
            baseList = pool;
            // 지역이 선택돼 있으면 지역 중심으로 고정 줌 (fitBounds는 가장자리 호텔로 뷰가 넓어짐)
            var area = fArea ? AREAS.filter(function(x){{ return x.code === fArea; }})[0] : null;
            if (!mapOpen) {{
                // P6: 지도 접힘 — 지도는 열 때(setMap) 그린다
            }} else if (area) {{
                map.setView([area.lat, area.lng], 15, {{animate:false}});  // 애니메이션 setView는 프로그래밍 호출 시 무시됨
                drawMap(pool, false);
            }} else {{
                drawMap(pool, true);   // 전체일 때만 fitBounds
            }}
            renderVisible();
        }}

        // ───── 이벤트 ─────
        map.on('moveend', function(){{ if (mapOpen && syncMap && !recMode) renderVisible(); }});

        // PC: 목록 카드에 마우스를 올리면 지도 마커를 키워 위치를 보여줌(Tripadvisor·Airbnb 패턴)
        $res.on('mouseenter', 'li[data-id]', function(){{
            var mk = mapOpen && markerById[$(this).data('id')]; if (!mk) return;
            mk.setStyle({{radius:13, weight:3}}); mk.bringToFront();
        }}).on('mouseleave', 'li[data-id]', function(){{
            var mk = markerById[$(this).data('id')]; if (mk) mk.setStyle({{radius:8, weight:2}});
        }});

        // P6 지도 토글: 열면 지도 위로 스크롤 + 크기 재계산 + 목록을 보이는 영역으로 연동, 닫으면 전체 목록
        function setMap(open, noScroll){{
            mapOpen = open;
            $('#map-wrap, #map-hint').toggleClass('is-collapsed', !open);
            $('#map-toggle').attr('aria-pressed', open ? 'true' : 'false').find('.mt-t').text(open ? '목록만 보기' : '지도로 보기');
            $('html').toggleClass('map-open', open);
            if (open) {{
                map.invalidateSize();   // 숨김 상태(0px)에서 초기화된 지도 크기 재계산
                var a = fArea ? AREAS.filter(function(x){{ return x.code === fArea; }})[0] : null;
                if (a) map.setView([a.lat, a.lng], 15, {{animate:false}});
                else {{
                    var pts = fitPts(baseList);
                    if (pts.length) map.fitBounds(pts, {{padding:[28,28], maxZoom:15, animate:false}});  // 즉시 맞춤 → 아래 renderVisible이 바로 정확
                }}
                drawMap(baseList, false);
                if (!noScroll) {{
                    var top = $('#map-wrap').offset().top - 64;
                    window.scrollTo({{top: Math.max(0, top), behavior: 'smooth'}});
                }}
            }}
            renderVisible();
        }}
        $('#map-toggle').on('click', function(){{
            setMap(!mapOpen);
            if (typeof gtag === 'function') gtag('event', 'map_toggle', {{open: mapOpen}});
        }});

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
        if (sortBy !== 'rs'){{   // ?sort= 프리셋이면 버튼 상태 동기화
            $('#lh-sort .lh-sort-box button').removeClass('on');
            var $sb = $('#lh-sort .lh-sort-box button[data-sort="'+sortBy+'"]').addClass('on');
            if ($sb.length) $('#lh-sort-btn').text($sb.data('label') || $sb.text());
        }}
        $('#lh-sort-btn').on('click', function(e){{ e.stopPropagation(); $('#lh-sort').toggleClass('open'); }});
        $('#lh-sort .lh-sort-box button').on('click', function(){{
            var v = String($(this).data('sort'));
            if (v.indexOf('cat:') === 0) {{ sortCat = v.slice(4); sortBy = 'p'; }}
            else {{ sortCat = ''; sortBy = v; }}
            $('#lh-sort .lh-sort-box button').removeClass('on'); $(this).addClass('on');
            $('#lh-sort-btn').text($(this).data('label') || $(this).text());
            $('#lh-sort').removeClass('open');
            renderVisible();
        }});
        $(document).on('click', function(){{ $('#lh-sort').removeClass('open'); }});

        // ───── 조건 더 보기 패널 (FEEDBACK-2610 §14): 모달 대신 아래로 펼침, 칩을 누르면 바로 적용, URL ?cat=&no= 동기화 ─────
        var $fp = $('#f-panel'), $fm = $('#f-more');
        function renderPanel(){{
            $('#fp-cats').html(CATS.map(function(c){{
                var on = fCats.indexOf(c.ko) >= 0, koDisp = (window.CAT_KO && window.CAT_KO[c.ko]) || c.ko;   // data-cat은 내부키(c.ko)
                return '<button type="button" class="fp-chip'+(on?' on':'')+'" data-cat="'+c.ko+'" aria-pressed="'+on+'">'+koDisp+'</button>';
            }}).join(''));
            var allBug = fNo.indexOf('bug') >= 0;
            $('#fp-no').html(MUSTS.map(function(m){{
                var locked = m.code === 'roach' && allBug, on = locked || fNo.indexOf(m.code) >= 0;   // '벌레 전부'면 바퀴벌레 잠금 포함
                return '<button type="button" class="fp-chip'+(on?' on':'')+(locked?' is-locked':'')+'" data-no="'+m.code+'" aria-pressed="'+on+'"'+(locked?' disabled':'')+'>'+m.label+'</button>';
            }}).join(''));
            var n = fCats.length + fNo.length;
            $fm.toggleClass('active', n > 0).find('.f-more-t').text(n ? '조건 '+n+'개 적용 중' : '조건 더 보기');
        }}
        function syncUrl(){{
            var u = new URLSearchParams(location.search);
            if (fCats.length) u.set('cat', fCats.join(',')); else u.delete('cat');
            if (fNo.length) u.set('no', fNo.join(',')); else u.delete('no');
            var qs = u.toString();
            history.replaceState(history.state, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
        }}
        function applyPanel(){{ renderPanel(); syncUrl(); run(); }}
        $fm.on('click', function(){{
            var open = $fp.prop('hidden');
            $fp.prop('hidden', !open); $fm.attr('aria-expanded', open ? 'true' : 'false').toggleClass('is-open', open);
        }});
        $fp.on('click', '.fp-chip[data-cat]', function(){{
            var c = String($(this).data('cat')), i = fCats.indexOf(c);
            if (i >= 0) fCats.splice(i, 1); else fCats.push(c);
            applyPanel();
        }});
        $fp.on('click', '.fp-chip[data-no]', function(){{
            var c = String($(this).data('no')), i = fNo.indexOf(c);
            if (i >= 0) fNo.splice(i, 1); else fNo.push(c);
            fNo = normNo(fNo); applyPanel();
        }});
        $('#fp-reset').on('click', function(){{ fCats = []; fNo = []; applyPanel(); }});

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
            var demand = Math.min(100, Math.log1p(h.krn||0) / Math.log1p(KRN_MAX) * 100);   // 한국인 리뷰 수(수요 신호, RECOMMEND-PRICE-DESIGN §4.3)
            return prio*0.50 + safe*0.20 + trust*0.15 + demand*0.15;
        }}
        function recWord(c){{ var s=(RC[c]||{{}}).chip||''; var a=s.split(' '); return a.length>1 ? a.slice(1).join(' ') : s; }}
        function recReason(h, pr){{   // 선택 조건에 대한 답 + 한국인 리뷰 수. 실망 확률·가격은 배지·상태줄에 이미 있어 반복하지 않는다
            var parts = [];
            var first = RC[pr[0]], w = recWord(pr[0]);
            if (first && h.cb && h.cb[first.ko] === 'safe'){{
                parts.push('<span class="seg">선택하신 <b>'+w+'</b> 걱정이 적은 곳이에요</span>');
            }} else if (first){{
                parts.push('<span class="seg"><b>'+w+'</b> 조건을 고려해 골랐어요</span>');
            }}
            if ((h.krn||0) >= 10) parts.push('<span class="seg">한국인 리뷰 '+h.krn+'건</span>');
            return parts.join(WHY_SEP);
        }}
        function recRow(h, rank, pr){{
            var img = h.img ? (h.img.indexOf('http')===0 ? h.img : './'+h.img) : './img/placeholder.svg';
            return '<li data-id="'+h.id+'"><div class="item'+(h.scored?' with-cmp':'')+'">'
                + '<div class="thumb"><span class="rec-rank'+(rank<=3?' is-top':'')+'">'+rank+'</span><a href="./hotels/'+h.id+'"><img src="'+img+'" width="200" height="200" loading="lazy"></a></div>'
                + '<div class="cont">'
                + '<div class="info">'
                + '<div class="name"><a href="./hotels/'+h.id+'">'+h.name+'</a></div>'
                + '<div class="badge">'+bandChip(h)+'</div>'
                + statLine(h)
                + areaHtml(h)
                + '</div>'
                + '<div class="rec-reason">'+recReason(h, pr)+'</div>'
                + '</div>'
                + footHtml(h)
                + '</div></li>';
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
                    + '<a class="pop-link" href="./hotels/'+h.id+'">상세 보기 →</a></div>');
                markers.addLayer(mk); pts.push([h.lat,h.lng]);
            }});
            var a = recArea ? AREAS.filter(function(x){{return x.code===recArea;}})[0] : null;
            if (a) map.setView([a.lat,a.lng], 15, {{animate:false}});
            else if (pts.length) map.fitBounds(pts, {{padding:[30,30], maxZoom:15}});
        }}
        var recPr = [], recBud = '', recArea = '', recNo = [], recBw = false;
        function recCandidates(){{
            return HOTELS.filter(function(h){{
                if (!h.scored || h.lr) return false;   // 리뷰 적음(최근 1년 100건 미만)은 추천 모수에서 제외 (UI-STANDARDS §5)
                if (recBud && (recBw ? h.pbw : h.pb) !== recBud) return false;   // 주말 기준이면 주말 가격대(없으면 제외)
                if (!passNo(h, recNo)) return false;
                if (recArea){{ var a=AREAS.filter(function(x){{return x.code===recArea;}})[0];
                    if (a){{ if (h.lat==null) return false; if (km(a.lat,a.lng,h.lat,h.lng) > a.r) return false; }} }}
                return true;
            }});
        }}
        function renderRecHeader(){{
            var chips = recPr.map(function(c, i){{ return '<span class="rh-chip"><span class="rh-rank">'+(i+1)+'</span>'+((RC[c]||{{}}).chip||'')+'</span>'; }});
            if (recBud){{ var b=(window.CFRec.BUDGETS||[]).filter(function(x){{return x.code===recBud;}})[0]; if(b) chips.push('<span class="rh-chip">'+b.label+(recBw ? '(주말)' : '')+'</span>'); }}
            if (recArea){{ var a=AREAS.filter(function(x){{return x.code===recArea;}})[0]; if(a) chips.push('<span class="rh-chip">'+a.ko+'</span>'); }}
            recNo.forEach(function(k){{ var m=(window.CFRec.mustBy||{{}})[k]; if (m) chips.push('<span class="rh-chip">'+m.chip+'</span>'); }});
            return '<div class="rh-tit">내 조건 맞춤 추천</div>'
                + '<div class="rh-sub" id="rh-sub"></div>'
                + '<div class="rh-chips">'+chips.join('')+'</div>'
                + '<a href="javascript:;" class="rh-reset rec-reset">조건 다시 설정 ↻</a>';
        }}
        function initRec(){{
            recMode = true;
            mapOpen = true; $('#map-wrap, #map-hint').removeClass('is-collapsed'); $('#map-toggle').hide();
            recPr = (sp.get('pr')||'').split(',').filter(function(c){{ return RC[c]; }});
            recBud = sp.get('bud')||''; recArea = sp.get('area')||''; recBw = !!(recBud && sp.get('bw') === '1');
            recNo = normNo((sp.get('no')||'').split(','));
            window.CF_REC_PRESET = {{pr:recPr, bud:recBud, area:recArea, no:recNo, bw:recBw}};
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
                if (recArea) relax += '<a class="notice-btn" href="'+recUrl({{area:''}})+'">지역 넓혀 다시 보기</a> ';
                if (recNo.length) relax += '<a class="notice-btn" href="'+recUrl({{no:''}})+'">&lsquo;한 번도 없어야&rsquo; 조건 풀기</a>';
                $('#results').html('<div class="notice-card" style="margin:16px 0">'
                    + '<div class="notice-tit">'+(cands.length ? '조건에 맞는 곳이 '+cands.length+'곳뿐이에요' : '조건에 맞는 곳이 없어요')+'</div>'
                    + '<div class="notice-txt">'+(recNo.length ? '조건을 하나씩 풀면 더 보여드릴 수 있어요' : '예산이나 지역을 넓히면 더 보여드릴 수 있어요')+'</div>'
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
            var no = over.no!==undefined ? over.no : recNo.join(',');
            var qs = 'rec=1&pr='+pr; if(bud) qs+='&bud='+bud; if(bud && recBw) qs+='&bw=1'; if(area) qs+='&area='+area; if(no) qs+='&no='+no;
            return './search?'+qs;
        }}

        // URL 파라미터: ?rec= / ?area= / ?q=
        var sp = new URLSearchParams(location.search);
        if (sp.get('rec')){{ initRec(); }}
        else {{
            var initArea = sp.get('area'), initQ = sp.get('q');
            if (initArea){{ fArea = initArea; $('#f-area .f-chip').removeClass('on'); $('#f-area .f-chip[data-area="'+initArea+'"]').addClass('on'); }}
            var CAT_KEYS = CATS.map(function(c){{ return c.ko; }});
            fCats = (sp.get('cat')||'').split(',').filter(function(c){{ return CAT_KEYS.indexOf(c) >= 0; }});
            fNo = normNo((sp.get('no')||'').split(','));
            renderPanel();
            if (fCats.length || fNo.length) {{ $fp.prop('hidden', false); $fm.attr('aria-expanded', 'true').addClass('is-open'); }}   // 공유 URL로 들어오면 펼쳐서 보여줌
            if (initQ){{ $q.val(initQ); }}
            run();
            // PC: 지도 상시 표시(토글 숨김은 pc.css). 창 크기가 경계를 넘으면 따라 전환
            var mqPc = window.matchMedia('(min-width:1100px)');
            if (mqPc.matches) setMap(true, true);
            var onMq = function(e){{ setMap(e.matches, true); }};
            if (mqPc.addEventListener) mqPc.addEventListener('change', onMq); else mqPc.addListener(onMq);
        }}
    }})();
    </script>''' + build_footer(0) + FOOT

# ───────────────────────── detail ─────────────────────────
def gauge_html(p, city_crit, tone='safe', tier=None):
    """실망 확률 게이지 — 값 축(2026-10 표본 공정성). 마커 = 도시평균 대비 위치: 평균 50%, 3배 100%(항목 점수와 같은 눈금).
    예전 백분위 축은 정밀 순위처럼 보였지만 순위 오차가 ±20~30%p라 값 축으로 바꿨다.
    말풍선 = 순위 구간('상위 25% 이내', 확실할 때만) 또는 평균 대비 문장."""
    r = (p / city_crit) if city_crit else 1.0
    pos = min(max(50.0 * r if r <= 1 else 50.0 + 25.0 * (r - 1), 0.0), 100.0)
    # 말풍선(순위·평균 대비)은 헤더의 기준 줄(v-sub)로 옮겨 게이지는 점 하나 + 평균 선만 (2026-10 카피 개편)
    return f'''<div class="gauge">
        <div class="bar">
            <div class="pointer is-{tone}" style="left:calc({pos:.1f}% - 5px)"><div class="arrow"></div><span class="dot"></span></div>
        </div>
        <div class="label">
            <span>실망 적음</span>
            <span class="analysis" style="left:50%">평균</span>
            <span>실망 많음</span>
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
        tags = ''.join(f'<div class="tags-item">#{E(s)}</div>' for s, d in subs[:4] if d['count_1y'] >= 3)
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
        rep = (f'<div class="q-foot"><button type="button" class="rep-btn" data-fid="{E(q["fid"])}" data-cat="{E(q.get("mcat"))}" '
               f'data-sub="{E(q.get("scat"))}" data-grade="{E(q["grade"])}">분류가 이상해요</button></div>') if q.get('fid') else ''   # 오분류 신고(FEEDBACK-2610 §13)
        out.append(f'''<li class="swiper-slide"><div class="item">
            <div class="item-top">
                <div class="name">{E(mask_name(q.get('reviewer_name')))}</div>
                <div class="status"><div class="status-item {gband}">{E(q['grade'])}</div></div>
            </div>
            <div class="item-info">{star}<div class="web">{origin}</div>{lang_chip}</div>
            <div class="item-bottom">
                <div class="text">{emph(q.get('quote') or q.get('summary'))}</div>
                <div class="date">{E((q.get('pub') or '')[:10].replace('-', '. '))} · {E(SUB_PHRASE.get(q.get('scat') or '', q.get('scat') or ''))}</div>
            </div>
            {rep}
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
    """추천: 같은 가격대 우선 + 가까울수록 + 추천순(rec_score: 실망 확률·한국인 리뷰·구글 평점) 높을수록"""
    me = hotels_meta.get(pid, {})
    my_band = me.get('band')
    cands = []
    for p, m in hotels_meta.items():
        if p == pid or p not in H or not H[p]['scored'] or not H[p]['ranked']: continue   # 추천 모수 = 리뷰 RANK_MIN 이상
        rank = (1.0 - REC.get(p, 0.0)) * 30.0               # 추천순 역수(0~30, 실망 확률 %p와 같은 자리수) — 모수 밖(REC 없음)은 최하
        if my_band and m.get('band') and m['band'][0] != my_band[0]:
            rank += 8.0                                     # 다른 가격대 페널티
        if me.get('latitude') and m.get('latitude'):
            d = haversine_km(float(me['latitude']), float(me['longitude']),
                             float(m['latitude']), float(m['longitude']))
            rank += min(d, 5.0) * 1.5                       # 5km까지 거리 페널티
        cands.append((rank, p))
    return [p for _, p in sorted(cands)[:k]]

def kr_share_map(kr_stats, H):
    """호텔별 한국인 리뷰 비중(최근 1년) = 한국어 리뷰 ÷ 글이 있는 리뷰(text_1y). kr_n≥10만.
       별점만 남긴 리뷰는 언어(국적)를 알 수 없어 분모에서 뺀다 — 넣으면 한국인 비중이 낮게 나옴 (2026-10 검토)."""
    out = {}
    for (pid, period), r in kr_stats.items():
        if period != '1y' or pid not in H or not H[pid].get('ranked'): continue   # 순위 모수 = 리뷰 RANK_MIN 이상
        try: kr_n = int(float(r.get('kr_n') or 0))
        except (TypeError, ValueError): continue
        tn = H[pid].get('text_1y') or 0
        if kr_n >= 10 and tn > 0:
            out[pid] = min(kr_n / tn, 1.0)
    return out


def kr_rank_map(share):
    """한국인 비중 백분위 순위 (§2-a). {pid: pct_top} — 작을수록 상위.
       pct_top = round(100 * (해당보다 비중 큰 호텔 수 + 1) / 대상수)."""
    n = len(share)
    rank = {}
    for pid, ratio in share.items():
        bigger = sum(1 for o in share.values() if o > ratio)
        rank[pid] = max(1, round(100 * (bigger + 1) / n)) if n else None
    return rank


def kr_ratio_dist(share):
    """한국인 비중 오름차순 리스트 — 분포 막대 차트(§2-a)용."""
    return sorted(share.values())


def _has_station(chip):
    """실전정보 칩에 역 이름이 있는가 — '하카타역 10분'·'지하철역 6분' O, '역에서 조금 멂'·'도보 10분' X (2026-10)."""
    c = str(chip or '')
    return bool(re.search(r'[가-힣A-Za-z]{2,}역', c)) and not re.match(r'^\s*역', c)


def _station_text(answer):
    """실전정보 답변("후기가 갈려요. 하카타역에서 도보 5분 또는 10분…")에서 '하카타역 5분'처럼 역 이름+시간만 뽑아 최대 2개.
    못 뽑으면 '후기가 갈려요.'를 뺀 첫 문장(46자). 후기가 갈리면 뒤에 ' · 후기 갈림'."""
    a = re.sub(r'\*\*', '', answer or '').strip()
    split = a.startswith('후기가 갈려요')
    body = re.sub(r'^후기가 갈려요[.!]?\s*', '', a)
    found, seen = [], set()
    _STOP = ('다른', '가장', '가까운', '및', '인근', '근처', '주변')
    for m in re.finditer(r'((?:[가-힣A-Za-z]{2,}\s)?지하철역|[가-힣A-Za-z]{2,}역)(?:에서|까지|과|도|은|는)?[^.,\d]{0,14}?(\d[\d~\-]*\s*분)', body):
        st = m.group(1)
        if ' ' in st and st.split(' ')[0] in _STOP: st = st.split(' ', 1)[1]   # '다른 지하철역' → '지하철역', '와타나베도리 지하철역'은 유지
        if st in seen: continue
        seen.add(st); found.append(f'{st} {m.group(2).replace(" ", "")}')
        if len(found) == 2: break
    if found:
        txt = ', '.join(found)
    else:
        first = re.split(r'(?<=[.요다])\s', body)[0]
        txt = (first[:46] + '…') if len(first) > 47 else first
    return txt + (' · 후기 갈림' if split else '')


def period_label(h, mdata):
    """이 호텔 수치의 실제 기간 표기. 기본 '최근 1년'. 단 1년 넘은 리뷰가 하나도 없고(수집이 1년을 못 거슬러 감 —
    리뷰 많은 호텔의 수집 상한·신규 편입 등) 첫 리뷰가 1년 컷보다 늦으면 실제 개월 수('최근 6개월')로 표기.
    mdata = monthly[pid] {ym: (n, n_crit, n_warn)} — 13개월 창이라 첫 달은 월 단위 근사."""
    if not CITY['asof'] or h.get('analyzed_all', 0) > h.get('analyzed', 0):
        return '최근 1년'
    months = sorted(ym for ym, v in (mdata or {}).items() if v and v[0] > 0)
    if not months:
        return '최근 1년'
    from datetime import date as _date
    fy, fm = (int(x) for x in months[0].split('-'))
    ay, am, ad = (int(x) for x in CITY['asof'].split('-'))
    n = round((_date(ay, am, ad) - _date(fy, fm, 1)).days / 30.44)
    return '최근 1년' if n >= 12 else f'최근 {max(n, 1)}개월'


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
    """전체 통합 월별 불만 리뷰 비율 (누적 스택 트렌드). 카테고리 차트와 동일 형태·데이터 가공.
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
    now_txt = f'{labels[-1]} {tot}% · {CITY["ko"]} 평균 {pa[-1]}%'
    dt = round((pw[-1] + pc[-1]) - (pw[-2] + pc[-2]), 1)
    if abs(dt) < 0.05:
        delta_txt = '지난달과 비슷해요'
    else:
        delta_txt = f'지난달보다 {abs(dt):.1f}%p {"올랐어요" if dt > 0 else "내렸어요"}'
    # 기본 접힘(F7): 토글 버튼만 노출, 탭 시 차트 펼침(Chart.js는 펼칠 때 지연 초기화 — 0폭 canvas 함정 회피)
    html = (f'<div class="trend-fold">'
        f'<button type="button" class="trend-fold-btn"><span class="tf-tit">월별 불만 리뷰 비율 보기</span><span class="tf-arrow"></span></button>'
        f'<div class="trend-fold-body">'
        f'<div class="cat-trend cat-trend-all">'
        f'<div class="ct-head"><span class="ct-tit">월별 불만 리뷰 비율</span>'
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
        'style="fill:none;stroke:var(--line-strong);stroke-width:2.5;stroke-linejoin:round"/>'
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


def korean_card(kr, h, kr_rank_pct=None, kr_dist=None, per='최근 1년'):
    """한국인 리뷰 현황 카드 (LLM-ANALYSIS §7.3 + DETAIL-UI-REVAMP §2). kr = kr_stats 1y 행, 표본 10건 미만이면 미노출.
    2026-10 검토 반영: ① 기간을 페이지 다른 숫자와 같은 최근 1년(전체기간 X) ② 한국인·전체 비교의 분모를 둘 다
    '글을 남긴 리뷰'로 — 별점만 리뷰는 언어를 몰라 한국인 쪽엔 못 들어가는데 전체 쪽에만 들어가면
    전체 비율이 희석돼 한국인이 평균 +7%p 더 부정적으로 보이는 착시(142곳 중 88곳 결론 뒤집힘)가 있었다."""
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    if not kr or int(num(kr.get('kr_n')) or 0) < 10 or not h.get('text_1y'):
        return ''
    kr_n, text_n = int(num(kr['kr_n'])), int(h['text_1y'])
    ratio = round(min(kr_n / text_n, 1.0) * 100)
    kr_st, all_st = num(kr.get('kr_stars')), num(kr.get('all_stars'))
    # 심각·주의 리뷰 비율: 한국인(kr_risk, 한국어 글 리뷰 기준) vs 전체 글 리뷰(any_1y ÷ text_1y)
    kr_rk_raw = num(kr.get('kr_risk'))
    has_risk = kr_rk_raw is not None
    kr_rk_pct = kr_rk_raw * 100 if has_risk else None
    all_rk_pct = h.get('any_1y', 0) / text_n * 100
    small = kr_n < 30

    # 임계 (§2-c): 별점차 ±0.15, 위험비율차 ±1.5%p
    d_st = (kr_st - all_st) if (kr_st and all_st) else None
    # 인사이트 d_dp = 심각·주의 비율차(%p). risk 부재 시 실망확률(심각-only, 글 리뷰 기준)로 폴백.
    if has_risk:
        d_dp = kr_rk_pct - all_rk_pct
    else:
        d_dp = ((num(kr.get('kr_disappoint')) or 0) - h.get('crit_1y', 0) / text_n) * 100
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
    n_serious = round((num1(kr.get('kr_disappoint')) or 0) * 100)
    if n_serious == 0:
        serious_txt = f'{per} 한국인 리뷰 중 실망 리뷰는 없었어요'
    else:
        serious_txt = f'{per} 한국인 리뷰 중 <b>{n_serious}%</b>가 실망 리뷰였어요'   # 실망 리뷰 정의는 실망 확률 ?·산출 방법과 동일
    serious_block = f'<div class="kr-serious">{serious_txt}</div>'

    # §2-b 비교 — 지표당 세로 막대 2개(한국인 primary vs 전체 회색), 값은 막대 위(목업①② 스타일).
    def vcol(role, frac, val_txt, is_ko):
        vcls = ' kv-val-ko' if is_ko else ''
        fcls = ' kv-fill-ko' if is_ko else ''
        ht = max(min(frac, 1.0), 0.04) * 100       # 막대 높이(%), 0값도 최소 4% 보이게
        return (f'<div class="kv-col"><div class="kv-val{vcls}">{val_txt}</div>'
                f'<div class="kv-track"><span class="kv-fill{fcls}" style="height:{ht:.0f}%"></span></div>'
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
        vbars += vgroup('불만 리뷰 비율', kr_rk_pct / norm, all_rk_pct / norm,
                        f'{round(kr_rk_pct)}%', f'{round(all_rk_pct)}%')
        footnote = (f'<div class="kr-foot">{per} 글 리뷰 기준{DSEP}<span class="seg">불만 리뷰 = 심각·주의 불만이 적힌 리뷰</span>'
                    '<br>별점만 남긴 리뷰는 국적을 알 수 없어 양쪽 다 뺐어요</div>')

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
        this_ratio = min(kr_n / text_n, 1.0)
        chart = kr_dist_bars(this_ratio, kr_dist) if kr_dist else kr_pyramid(kr_rank_pct)
        dist_block = (f'<div class="kr-dist">{chart}'
                      f'<div class="kp-cap">한국인 비중 <b>{CITY["ko"]} {rank_txt}</b></div>'
                      f'<div class="kp-sub">{sub}</div></div>')

    count_txt = f'{per} 글 리뷰 중 한국어 <b>{kr_n:,}</b>건 ({ratio}%){" · 참고용" if small else ""}'
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


def pc_gallery_html(meta, name, fallback):
    """PC 사진 그리드(pc.css에서만 표시): 장수에 맞춰 1 / 2 / 3 / 4 / 5장 배치(KAYAK·Klook 1+4 패턴).
       호텔 사진이 대부분 1~2장(가로 960px)이라 장수별 레이아웃을 따로 둔다. 첫 장은 모바일 히어로와 같은 URL(캐시 공유)."""
    imgs = (meta.get('r2_imgs') or [fallback])[:5]
    n = len(imgs)
    cells = ''
    for i, u in enumerate(imgs):
        lazy = '' if i == 0 else ' loading="lazy"'
        cells += f'<div class="pg-cell pg-{i}" data-i="{i}" role="button" tabindex="0" aria-label="사진 {i + 1} 크게 보기"><img src="{E(u)}" alt="{E(name)} 사진 {i + 1}" width="960" height="640"{lazy}></div>'
    more = f'<span class="pg-count">사진 {len(meta.get("r2_imgs") or [])}장</span>' if len(meta.get('r2_imgs') or []) > 1 else ''
    return f'<div class="pc-gallery g{n}">{cells}{more}</div>'

def gallery_html(meta, name, fallback):
    """상세 히어로: 사진 2장+면 Swiper 갤러리(점 표시·스와이프), 아니면 단일 이미지."""
    imgs = meta.get('r2_imgs') or []
    if len(imgs) < 2:
        return f'<div class="visual"><img src="{E(imgs[0] if imgs else fallback)}" alt="{E(name)}" width="800" height="600"></div>'
    # 히어로 갤러리: 첫 장 즉시(LCP), 나머지는 lazy 대신 그냥 로드(Swiper 오프스크린+native lazy 충돌 회피)
    slides = ''.join(
        f'<div class="swiper-slide" data-i="{i}"><img src="{E(u)}" alt="{E(name)}" width="800" height="600"'
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
    # aggregateRating 의도적 미포함: 평점 출처가 구글 지도라 리뷰 스니펫 정책(타 사이트 평점 집계 마크업 금지) 위반.
    # 자체 사용자 평점이 생기기 전까지 넣지 말 것.
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
        for i, b in enumerate(blogs):
            # referrerpolicy=no-referrer 필수 — pstatic 썸네일이 외부 referer를 핫링크 차단(403 실측)
            img = (f'<img src="{E(b["img"])}" alt="" loading="lazy" referrerpolicy="no-referrer" '
                   f'onerror="this.parentNode.classList.add(\'no-img\')">'
                   if b.get('img') else '')
            d = str(b.get('d') or '')
            dd = f'{d[:4]}. {d[4:6]}. {d[6:8]}' if len(d) == 8 else d
            meta = ' · '.join(x for x in [b.get('by') or '', dd] if x)
            hide = ' nb-hidden' if i >= 3 else ''       # 기본 3개 + 더보기 펼침
            cards.append(f'''<button type="button" class="nb-card{hide}" data-url="{E(b['u'])}" data-title="{E(b['t'])}">
                <span class="nb-main"><span class="nb-tit">{E(b['t'])}</span>
                <span class="nb-meta">{E(meta)}</span></span>
                <span class="nb-thumb{'' if img else ' no-img'}">{img}</span>
            </button>''')
        more = (f'<button type="button" class="nb-more">블로그 후기 더보기 (+{len(blogs) - 3})</button>'
                if len(blogs) > 3 else '')
        out.append(f'''<div class="sect social-blog">
            <div class="head"><div class="title">네이버 블로그 후기</div>
            <div class="desc">네이버 "{E(name)} 후기" 상위 글이에요 · 탭하면 여기서 바로 읽을 수 있어요</div></div>
            <div class="nb-list">{''.join(cards)}</div>
            {more}
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

    # 이 호텔 수치의 실제 기간 — 수집이 1년을 못 채운 호텔은 '최근 N개월' (2026-10 검토 case 1)
    per = period_label(h, (monthly or {}).get(pid))
    # 표본 공정성(2026-10): 최근 1년 리뷰 RANK_MIN 미만이면 상단에 주의 문구 — 순위·추천에서 빠진 이유와 함께
    lowrev_html = ''
    if h['scored'] and not h['ranked']:
        lowrev_html = (f'<div class="lowrev-note"><b>{per} 리뷰가 {h["analyzed"]:,}개뿐이에요</b>'
                       f'<span>리뷰 몇 건에 숫자가 크게 달라질 수 있어 순위·추천에서는 뺐어요{DSEP}참고용으로 봐 주세요</span></div>')
    # ── 딜브레이커 발동 계산 (경고 스트립·점프칩·verdict 공용): 희소·고위험 최근 1년 심각 ≥3건 — 캘리브레이션 고정 ──
    # 건수는 집계(findings_sub)의 정확한 값 — 예전엔 인용문 목록(카테고리당 40건 상한·이름+날짜 중복제거)에서 세서 일부 과소집계
    db_data = []          # [(cat, strip_label, chip_label, n), ...] — 발동(≥3)분만 (점프칩 fj-risk·verdict 공용, F35로 스트립은 삭제)
    rare_crit = {}        # {scat: 최근1년 심각 건수} — 발동 여부 무관 원시 카운트 (F8 verdict A① 판정용)
    rare_cascade = {}     # F33: {scat: (label, tone)} — 희소 칩 최신성 캐스케이드(최근 3달 → 최근 1년 → 심각 리뷰 없음)
    cut_1y = None         # 분석 기간 시작일(asof-365) — 근거 리뷰 목록도 이 날짜 이후만
    if CITY['asof']:
        from datetime import date as _date, timedelta as _td
        _y, _m, _d = map(int, CITY['asof'].split('-'))
        cut_1y = str(_date(_y, _m, _d) - _td(days=365))
    if h['scored']:
        for _cat, _scat, _slabel, _clabel in (('청결', '벌레', '벌레', '벌레 리뷰'),   # F43: 신고→리뷰 · 분류 v5 칩 4종
                                              ('청결', '곰팡이', '곰팡이', '곰팡이 리뷰'),
                                              ('위치', '동네 분위기', '밤길·동네 분위기', '밤길·동네 분위기 리뷰'),
                                              ('안전', '객실 보안', '객실 보안', '객실 보안 리뷰')):
            _sb = h['cats'][_cat]['subs'][_scat]
            _n, _n3 = _sb.get('crit_1y', 0), _sb.get('crit_3m', 0)   # 최근 1년 / 최근 3달(90일) 심각
            rare_crit[_scat] = _n
            if _n >= 3:
                db_data.append((_cat, _slabel, _clabel, _n))
            # F33 캐스케이드: 최근 3달 심각 ≥1 → 최근 1년 심각 ≥1 → 둘 다 0(심각 리뷰 없음 — F43 워딩)
            if _n3 >= 1:
                rare_cascade[_scat] = (f'최근 3달 심각 {_n3}건', 'alert')
            elif _n >= 1:
                rare_cascade[_scat] = (f'{per} 심각 {_n}건', 'alert')
            else:
                rare_cascade[_scat] = (f'{per} 심각 리뷰 없음', 'clear')

    # ── 진입점 점프 칩 (info-cont 마지막 줄): 위험 칩(딜브레이커) + FAQ 질문형 칩(primary) + 전체 (최대 4칩) ──
    FAQ_CHIP_Q = [('bath', '대욕장 있나요?'), ('luggage', '짐 맡아주나요?'), ('breakfast', '조식 어때요?'),
                  ('family', '아이동반 되나요?'), ('parking', '주차 되나요?')]
    faq_jump_html = ''
    if h['scored'] and (faq or db_data):
        _chips = []
        for _cat, _sl, _cl, _n in db_data:
            _chips.append(f'<button type="button" class="fj-btn fj-risk" data-target="risk-{CAT_INDEX[_cat]}">{_cl} {_n}건</button>')
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

    # P4 약점 맞춤 대안: 최고 위험 카테고리가 주의·위험이면 같은 가격대·근거리 후보 중 그 카테고리 위험도가
    # 10 이상 낮은 곳만(3곳 미만이면 기존 일반 추천 폴백). 채점 호텔은 리스크 상세 바로 뒤에 배치(스크롤 50% 대응).
    sim = similar_hotels(pid, hotels_meta, H)
    sim_title, sim_desc, sim_extra = '이런 호텔은 어떠세요?', f'비슷한 가격대·가까운 위치에서 추천순이에요 · {REC_SORT_DESC}', {}
    if h['scored']:
        _wc = max(CATS, key=lambda c: h['cats'][c]['score'])
        _ws = round(h['cats'][_wc]['score'])
        if h['cats'][_wc]['band'] in ('warning', 'danger'):
            _alt = [p for p in similar_hotels(pid, hotels_meta, H, k=24)
                    if round(H[p]['cats'][_wc]['score']) <= _ws - 10][:8]
            if len(_alt) >= 3:
                sim = _alt
                sim_title = f'{cat_ko(_wc)} 불만이 걱정된다면'
                sim_desc = f'비슷한 가격대·가까운 위치에서 {cat_ko(_wc)} 불만이 확실히 적은 곳이에요'
                _mine = cat_verdict(h['cats'][_wc]['score'])[0]
                sim_extra = {p: (f'<div class="vs-line">{E(cat_ko(_wc))} 불만 <b>{E(cat_verdict(H[p]["cats"][_wc]["score"])[0])}</b>'
                                 f'<span> · 이 호텔은 {E(_mine)}</span></div>') for p in _alt}
    similar_block = ''
    if sim:
        sim_cards = '\n'.join(hotel_card(p, hotels_meta[p], H[p], depth=1, extra=sim_extra.get(p, '')) for p in sim)
        similar_block = f'''<div class="sect hotel" id="sec-alt">
            <div class="head"><div class="title">{E(sim_title)}</div>
            <div class="desc">{E(sim_desc)}</div></div>
            <div class="list hotel-slider"><ul class="swiper-wrapper">{sim_cards}</ul></div>
        </div>'''

    # 함께 고민하는 호텔 (HOME-CONCEPT §2 / RECOMMEND §4.4): 카페에서 자주 같이 비교되는 쌍 → 나란히 비교 링크
    pairs_block = ''
    partners = [(pb if pa == pid else pa) for pa, pb in PAIRS if pid in (pa, pb)]
    if partners and h['scored']:
        _pc = '\n'.join(hotel_card(q, hotels_meta[q], H[q], depth=1,
                         extra=f'<div class="vs-line">실망 확률 <b>{pct(H[q]["p_crit"])}%</b><span> · 이 호텔은 {pct(h["p_crit"])}%</span></div>') for q in partners)
        pairs_block = f'''<div class="sect hotel" id="sec-vs">
            <div class="head"><div class="title">이 호텔과 함께 고민하는 호텔</div>
            <div class="desc">네이버 카페에서 자주 같이 비교되는 호텔이에요 · 실망 확률·불만 항목을 나란히 놓고 보세요</div></div>
            <div class="list hotel-slider"><ul class="swiper-wrapper">{_pc}</ul></div>
            <a class="vs-more-link" href="../compare?ids={pid},{partners[0]}">나란히 비교하기 →</a>
        </div>'''

    glance_html = ''
    who_html = ''
    tabs_html = ''
    v_head, v_tone = '', 'safe'
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
        # F25: 최근 1년 심각 실측 카운트 — sev_by_cat(카테고리별 심각 리뷰 수) · crit_reviews_1y(심각 리뷰 수, 고유)
        # 집계값 그대로(정확) — 예전 인용문 기반 근사(이름+날짜 중복제거)는 28곳에서 1~6건 과소집계였음
        sev_by_cat = {c: h['cats'][c]['crit_1y'] for c in CATS if h['cats'][c].get('crit_1y')}
        crit_reviews_1y = h.get('crit_1y', 0)
        _worst = max(CATS, key=lambda c: h['cats'][c]['score'])
        _worst_sc = h['cats'][_worst]['score']
        _all_safe = all(h['cats'][c]['band'] == 'safe' for c in CATS)
        # ── 판정(1줄, 배지와 같은 색) → 기준(평균 + 확실할 때만 순위 구간) → 근거 2줄. 비유·시험 말투 없이 한 말투 (2026-10 카피 개편) ──
        _band = h['badge'][0]
        if _band == 'low':
            v_head, v_tone = '리뷰가 적어 참고용이에요', 'low'
        elif _band == 'safe':
            v_head, v_tone = '실망한 투숙객이 적어요', 'safe'
        elif _band == 'danger':
            v_head, v_tone = '실망한 투숙객이 많아요', 'danger'
        elif ratio < 1.15:
            v_head, v_tone = f'{CITY["ko"]} 평균 수준이에요', 'warning'
        else:
            v_head, v_tone = '평균보다 실망이 잦아요', 'warning'
        # 순위 구간: '상위 25% 이내' → '실망 적은 호텔 상위 25% 이내' (낮을수록 좋다는 방향을 말에 넣는다, FEEDBACK-2610 §10)
        _tier = h.get('rank_tier')
        tier_txt = ''
        if _tier:
            tier_txt = '실망 적은 호텔 ' + _tier[1]
        tier_html = f'<span class="tier-badge is-{v_tone}">{E(tier_txt)}</span>' if tier_txt else ''
        v_sub_html = f'<div class="v-sub">{CITY["ko"]} 평균 {avg}%{tier_html}</div>'
        # 근거 1: 글 리뷰 N건 중 실망 리뷰 M건 (분모 = 글 리뷰: 실망 리뷰는 글에서만 셀 수 있음) → 리스크 상세로
        _rows = []
        if h['text_1y']:
            _rows.append(('ink', f'{per} 글 리뷰 <b>{h["text_1y"]:,}건</b> 중 <b>실망 리뷰 {crit_reviews_1y}건</b>',
                          '__dis__' if crit_reviews_1y else None))   # 누르면 그 M건만 팝업으로 (openDis)
        # 근거 2: 예약을 접을 만한 문제(희소·고위험 4종) 심각 리뷰 → 있으면 건수, 없으면 '없음'. 평균 이상 호텔은 대신 가장 잦은 불만
        _RARE_KO = {'벌레': '벌레', '곰팡이': '곰팡이', '동네 분위기': '밤길·동네 분위기', '객실 보안': '객실 보안'}
        _rare_hit = [(_RARE_KO.get(_sc, _sc), _n) for _sc, _n in rare_crit.items() if _n]
        _worst6 = max(SCORED_CATS, key=lambda c: h['cats'][c]['score'])
        if _rare_hit:
            _txt = ' · '.join(f'<b>{E(k)} {n}건</b>' for k, n in _rare_hit)
            _call = '예약 전 꼭 확인하세요' if sum(n for _, n in _rare_hit) >= 3 else '리뷰를 확인해 보세요'   # 3건 미만은 경고 톤을 낮춤
            _first_sc = next(_sc for _sc, _n in rare_crit.items() if _n)     # 첫 희소 소분류(벌레 등) → 그 카테고리 아코디언을 열고 그 행으로
            _rows.append(('danger', f'{per} 심각 리뷰 {_txt}{DSEP}{_call}', f'#risk-{CAT_INDEX[SUB_CAT[_first_sc]]}', _first_sc))   # 안전(객실 보안·동네 분위기)은 CATS 밖이라 CAT_INDEX
        elif v_tone in ('warning', 'danger') and h['cats'][_worst6]['count_1y']:
            _rows.append(('warning', f'불만이 가장 많은 항목은 <b>{E(cat_ko(_worst6))}</b>{NB}({h["cats"][_worst6]["count_1y"]}건)',
                          f'#risk-{CATS.index(_worst6)}'))
        else:
            _rows.append(('safe', f'벌레, 곰팡이, 밤길·동네 분위기, 객실 보안처럼<br>예약을 접을 만한 심각 리뷰 <b>없음</b>', None))
        def _ev(tone, txt, href, sub=None):
            inner = f'<span class="ev-dot is-{tone}"></span><span class="ev-txt">{txt}</span>'
            if href == '__dis__':
                return f'<button type="button" class="ev-row" data-dis="1">{inner}<span class="ev-arrow"></span></button>'
            if href and href.startswith('#risk-'):   # 아코디언을 열고 스크롤(JS .ev-row[data-target]) — 단순 앵커는 안 열리고 헤더에 가려짐
                return f'<a class="ev-row" href="{href}" data-target="{href[1:]}"{(" data-sub=" + chr(34) + E(sub) + chr(34)) if sub else ""}>{inner}<span class="ev-arrow"></span></a>'
            if href:
                return f'<a class="ev-row" href="{href}">{inner}<span class="ev-arrow"></span></a>'
            return f'<div class="ev-row">{inner}</div>'
        v_why = ''.join(_ev(*row) for row in _rows)
        # ── P3 누구와 가세요(1단계): 구성별 관련 소분류(최근 1년 비율·희소는 심각 건수) + FAQ + 대표 인용 1건 ──
        _faq_by = {it.get('t'): it for it in (faq or [])}
        _panels, _chips = [], []
        for _gi, (_gk, _gl, _gsubs, _gfaq) in enumerate(WHO_GROUPS):
            _rows, _risk = [], []
            for _s in _gsubs:
                _sb = h['cats'][SUB_CAT[_s]]['subs'][_s]
                _n1 = _sb.get('count_1y', 0)
                if _s in RARE_SUBS:
                    _lbl, _tone = rare_cascade.get(_s, (f'{per} 심각 리뷰 없음', 'clear'))
                    _t = 'danger' if _tone == 'alert' else 'safe'
                    _rows.append((_t, E(SUB_PHRASE[_s]), E(_lbl)))
                    if _tone == 'alert': _risk.append((100, _s, 'danger'))
                elif _n1 > 0:
                    _t = _sb['band'] if _sb['band'] in ('warning', 'danger') else 'safe'
                    _rows.append((_t, E(SUB_PHRASE[_s]), f'{per} 리뷰의 <b>{round(_n1 / h["analyzed"] * 100, 1)}%</b>{NB}({_n1}건)'))
                    if _t != 'safe' and _n1 >= 3 and _n1 / h['analyzed'] >= 0.02: _risk.append((_sb['score'], _s, _t))   # P1과 같은 기준
                else:
                    _rows.append(('safe', E(SUB_PHRASE[_s]), f'{per} 불만 없음'))
            for _k in _gfaq:
                _it = _faq_by.get(_k)
                if _it and _it.get('c'):
                    _fc = [str(x) for x in (_it.get('c') or [])[:3]]   # FAQ 칩 — 바깥 _chips(일행 버튼 목록)와 이름 분리
                    if _k == 'access' and not any(_has_station(x) for x in _fc):   # '도보 6분, 도보 10분'처럼 어느 역인지 없는 칩 → 답변에서 '역 이름 N분'을 뽑음
                        _txt = _station_text(_it.get('a') or '')
                    else:
                        _txt = ', '.join(_fc)
                    _rows.append(('faq', E(WHO_FAQ_LABEL[_k]), E(_txt)))
            if _risk:
                _sc, _top, _tb = max(_risk)
                _head = (f'<em>{E(SUB_PHRASE[_top])}</em> 심각 리뷰가 있어요' if _top in RARE_SUBS         # 희소·고위험
                         else f'<em>{E(SUB_PHRASE[_top])}</em> 불만이 잦아요' if _tb == 'danger'       # 위험(평균 2배+)
                         else f'<em>{E(SUB_PHRASE[_top])}</em> 불만이 평균보다 많은 편이에요')
                _qs = sorted((q for q in quotes.get((pid, SUB_CAT[_top]), [])
                              if (q.get('scat') or '') == _top and q.get('grade') in ('심각', '주의')),
                             key=lambda q: (q.get('grade') == '심각', str(q.get('pub') or '')), reverse=True)   # 심각 우선 → 최신
            else:
                _top, _qs = None, []
                _head = '관련 불만이 적은 편이에요'
            _qhtml = ''
            if _qs:
                _q = _qs[0]
                _qt = (_q.get('quote') or _q.get('summary') or '').replace('**', '')
                _qhtml = (f'<div class="who-quote">"{E(_qt)}"<small>{E(_q.get("review_origin") or "Google")} · '
                          f'{E(str(_q.get("pub") or "")[:10].replace("-", ". "))}</small></div>')
            _li = ''.join(f'<li><span class="who-tag is-{t}">{lb}</span><span>{tx}</span></li>' for t, lb, tx in _rows)
            _on = _gk == 'two'
            _chips.append(f'<button type="button" class="who-chip{" is-on" if _on else ""}" data-who="{_gk}" aria-pressed="{"true" if _on else "false"}">{E(_gl)}</button>')
            _panels.append(f'<div class="who-panel" data-who="{_gk}"{"" if _on else " hidden"}><div class="who-h">{_head}</div><ul>{_li}</ul>{_qhtml}</div>')
        who_html = f'''<div class="sect who" id="sec-who">
            <div class="head"><div class="title">누구와 가세요?</div>
            <div class="desc">일행 구성과 관련 깊은 리뷰·실전 정보만 모아 보여드려요</div></div>
            <div class="who-chips">{''.join(_chips)}</div>
            {''.join(_panels)}
        </div>''' + WHO_JS

        # F41: 히어로 줄 = %+판정 같은 줄·같은 케이스색(verdict 별도 줄 흡수). 근거(why)는 게이지 아래 유지
        verdict_why_html = f'<div class="ev">{v_why}</div>'

        # ── P1 한눈에 보기: 걸리는 점 = 딜브레이커 발동분(희소 심각 최근 1년 ≥3, db_data와 동일 캘리브레이션) 우선
        #    + 주의·위험 소분류 중 최근 1년 3건+ & 비율 2%+ (위험도순). 없는데 판정이 C·D면 최고 위험 카테고리로 폴백.
        #    괜찮은 점 = 양호 카테고리(위험도 낮은 순 2) + 역 도보 5분 이내(위치 양호일 때만). 전부 실측 조립.
        _neg = []    # (dot, lead용 구문, 상세 html, 카테고리)
        for _rc, _rl, _rcl, _rn in db_data:
            _scat = _rl                  # 칩 라벨 = 소분류명 (벌레·곰팡이·동네 분위기·객실 보안)
            _neg.append(('danger', f'<em>{E(SUB_PHRASE[_scat])} 심각 리뷰</em>가 반복돼요',
                         f'<b>{E(SUB_PHRASE[_scat])} 심각 리뷰</b> · {per} {_rn}건', _rc, None))
        _cand = []
        for _c in CATS:
            for _s in SUBS[_c]:
                _sb = h['cats'][_c]['subs'][_s]
                _n1 = _sb.get('count_1y', 0)
                if (_s not in RARE_SUBS and _sb['band'] in ('warning', 'danger') and _n1 >= 3
                        and _n1 / h['analyzed'] >= 0.02):
                    _cand.append((-_sb['score'], _s, _sb['band'], _n1, _c))
        for _x, _s, _bd, _n1, _c in sorted(_cand):
            _neg.append((_bd, f'<em>{E(SUB_PHRASE[_s])}</em> 불만이 반복돼요',
                         f'<b>{E(SUB_PHRASE[_s])} 불만</b>{DSEP}<span class="seg">{per} 리뷰의 {round(_n1 / h["analyzed"] * 100, 1)}%{NB}({_n1}건)</span>', _c,
                         SUB_PHRASE[_s]))
        if not _neg and ratio >= 1.15 and h['cats'][_worst]['band'] in ('warning', 'danger'):
            _neg.append((h['cats'][_worst]['band'], f'<em>{E(cat_ko(_worst))}</em> 불만이 평균보다 많아요',
                         f'<b>{E(cat_ko(_worst))} 불만</b>{DSEP}<span class="seg">{E(ratio_text(_worst_sc))}</span>', _worst, None))
        _neg = _neg[:3]
        _negc = {n[3] for n in _neg}    # 걸리는 점과 같은 카테고리는 괜찮은 점에서 제외(모순 문장 방지)
        _safe = sorted((c for c in CATS if h['cats'][c]['band'] == 'safe' and c not in _negc),
                       key=lambda c: h['cats'][c]['score'])
        _pos = [f'<b>{E(cat_ko(c))} 불만 적음</b>{DSEP}<span class="seg">{E(ratio_text(h["cats"][c]["score"]))}</span>' for c in _safe[:2]]
        _st = nearest_station(meta.get('latitude'), meta.get('longitude'))
        if _st and _st[1] <= 5 and h['cats']['위치']['band'] == 'safe' and '위치' not in _negc:
            _pos.append(f'<b>역 가까움</b>{DSEP}<span class="seg">{E(_st[0])} 도보 {_st[1]}분</span>')
        if _neg or _pos:
            _ok = ratio < 1.15          # verdict A·B(통과) — 어조를 "무난 + 굳이 꼽자면"으로
            if _ok and _neg and _neg[0][4]:
                _lead = f'전반적으로 무난해요. 굳이 꼽자면 <em>{E(_neg[0][4])}</em> 불만이 있어요.'
            elif _ok and _neg:
                _lead = f'전반적으로 무난하지만, {_neg[0][1]}.'
            elif _neg and _safe:
                _lead = f'{E(cat_ko(_safe[0]))}{josa_eun(cat_ko(_safe[0]))} 괜찮지만, {_neg[0][1]}.'
            elif _neg:
                _lead = f'{_neg[0][1]}.'
            else:
                _lead = '<em>두드러진 불만이 없는</em> 호텔이에요.'
            _col = lambda tit, items: (f'<div class="gl-col"><div class="gl-h">{tit}</div><ul>'
                                       + ''.join(f'<li><span class="gl-dot is-{d}"></span><span>{t}</span></li>' for d, t in items)
                                       + '</ul></div>')
            glance_html = f'''<div class="sect glance" id="sec-sum">
                <div class="gl-box">
                    <div class="gl-eyebrow">{per} 리뷰 {h['analyzed']:,}건으로 본 한 줄 결론</div>
                    <p class="gl-lead">{_lead}</p>
                    <div class="gl-cols">
                        {_col('아쉬운 점' if _ok else '걸리는 점', [(n[0], n[2]) for n in _neg]) if _neg else ''}
                        {_col('괜찮은 점', [('safe', t) for t in _pos]) if _pos else ''}
                    </div>
                    <div class="gl-foot"><span><span class="seg">{per} 리뷰 {h['analyzed']:,}건 · 기준 {CITY['data_asof']}</span>{DSEP}<span class="seg">리뷰 숫자로 자동 작성</span></span><a class="gl-more" href="#risk-detail">근거 보기</a></div>
                </div>
            </div>'''

        # F35: 딜브레이커 경고 스트립 삭제(db_data 계산은 점프칩 fj-risk·verdict용으로 유지)
        radar_labels = json.dumps([cat_ko(c) for c in CATS], ensure_ascii=False)  # 표시 라벨만 순화(순서=CATS 고정)

        # 카테고리 × 소분류 — 아코디언(§4) + 리뷰 시트 데이터. 위험도 내림차순 정렬(§4-d).
        groups = []
        sheet_data = {}
        sheet_total = {}     # {cat: {'t': 전체 카드수, 's': {scat: 건수}}} — 팝업 실제 총건수(임베드 40 아님). REVIEW-LAZYLOAD §C
        trendc = {}          # {ci: {'m':[..'N월'], 'w':[..pw], 'c':[..pc]}} — 차트 있는 카테고리만 (CAT-TREND)
        axis = '''<div class="stat-axis"><span class="ax safe">불만 적음</span><span class="ax avg">평균</span><span class="ax danger">불만 많음</span></div>'''
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
            # 근거 리뷰도 점수와 같은 기간(최근 1년)만 — 1년 넘은 리뷰는 점수에 ×0이라 근거로 보여주면 숫자와 안 맞음
            qlist = [q for q in quotes.get((pid, c), []) if not cut_1y or str(q.get('pub') or '')[:10] >= cut_1y]
            sheet_data[c] = [{'s': q.get('scat') or '', 'g': q['grade'], 'q': q.get('quote') or q.get('summary') or '',
                              'd': (q.get('pub') or '')[:10], 'n': mask_name(q.get('reviewer_name')),
                              'st': q.get('stars'), 'o': q.get('review_origin') or 'Google',
                              'u': q.get('review_url') or '', 'tf': q.get('tfull') or '', 'of': q.get('ofull') or '',
                              'l': (q.get('lang') or '').lower(), 'r': q.get('rid'), 'f': q.get('fid'),   # f = 판정 ID(오분류 신고, R2 전체 JSON과 같은 키)
                              **({'rf': 1} if q.get('rf') else {})} for q in qlist]
            # 실제 총건수(소분류 건수 = 아코디언 표기와 동일 출처, 최근 1년). R2 전체 파일을 같은 기간으로 거른 카드 수와 일치.
            sub_cnt = {s: cat['subs'][s]['count_1y'] for s in SUBS[c] if cat['subs'][s]['count_1y'] > 0}
            sheet_total[c] = {'t': sum(sub_cnt.values()), 's': sub_cnt}
            rows = []
            # 소분류 정렬: 점수 내림차순, 단 RARE_SUBS(칩 렌더·점수 아님)는 항상 마지막 고정
            sub_order = (sorted((s for s in SUBS[c] if s not in RARE_SUBS),
                                key=lambda s: -cat['subs'][s]['score'])
                         + [s for s in SUBS[c] if s in RARE_SUBS])
            for s in sub_order:
                sub = cat['subs'][s]
                sc = round(sub['score'])
                cnt = sub['count_1y']   # 옆 비율 캡션과 같은 기간
                cnt_html = (f'<button type="button" class="stat-count has-reviews" data-cat="{E(c)}" data-sub="{E(s)}">{cnt}건</button>'
                            if cnt > 0 else '<span class="stat-count zero">0건</span>')
                if s in RARE_SUBS:
                    # §3-c 희소·고위험: 점수 막대 대신 칩 (점수는 내부 계산 유지, 화면만 미노출) — F33 최신성 캐스케이드
                    _clabel, _ctone = rare_cascade.get(s, (f'{per} 심각 리뷰 없음', 'clear'))
                    rdot = 'danger' if _ctone == 'alert' else 'safe'
                    chip = f'<div class="rare-chip is-{_ctone}">{E(_clabel)}</div>'
                    rare_btn = cnt_html if cnt > 0 else ''      # 우측 "N건" 전체보기 링크 현행 유지
                    rows.append(f'''<li class="stat-row is-rare" data-sub="{E(s)}">
                    <div class="stat-info"><div class="factor"><span class="sub-dot is-{rdot}"></span>{E(SUB_PHRASE.get(s, s))}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, '').replace(' · ', ', '))}</div></div>
                    {chip}
                    {rare_btn}
                </li>''')
                    continue
                # F34+F38: 소분류 행 최근 1년 비율 캡션 — "최근 1년 리뷰의 P%"(P=1y finding/analyzed·소수1자리), 우측 건수 링크 아래 우측정렬. 희소 칩 행은 F33이 대체.
                n1y = sub.get('count_1y', 0)
                cap_1y = (f'{per} 리뷰의 {round(n1y / h["analyzed"] * 100, 1)}%'
                          if n1y > 0 and h['analyzed'] else f'{per} 없음')
                rows.append(f'''<li class="stat-row is-{sub['band']}" data-sub="{E(s)}">
                    <div class="stat-info"><div class="factor"><span class="sub-dot is-{sub['band']}"></span>{E(s)}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, '').replace(' · ', ', '))}</div></div>
                    <div class="stat-track" title="{E(cat_verdict(sub['score'])[1])}"><div class="stat-fill" style="width:{sc}%"><i class="bubble" aria-hidden="true"></i></div></div>
                    {cnt_html}
                    <div class="sub-1y">{E(cap_1y)}</div>
                </li>''')
            qc = quote_cards(qlist)
            total_q = len(qlist)
            more_btn = (f'''<div class="more"><button type="button" class="more-btn" data-cat="{E(c)}"><strong>{E(cat_ko(c))}</strong> 리뷰 전체보기 ({sheet_total[c]['t']}건)</button></div>'''
                        if total_q > 0 else '')
            quotes_block = (f'''<div class="review"><div class="list review-slider"><ul class="swiper-wrapper">{qc}</ul></div></div>{more_btn}'''
                            if qc else '<div class="no-quote">이 카테고리는 문제 언급 리뷰가 거의 없어요</div>')
            is_open = ' is-open' if order == 0 else ''      # 1위만 초기 펼침(§4-c)

            # ── 카테고리별 월별 불만 리뷰 비율 (CAT-TREND). 최상단(axis 앞) 삽입 ──
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
                    tot = round(pw[-1] + pc[-1], 1)          # 합계 = 주의+심각 (배타)
                    now_txt = f'{labels[-1]} {tot}% · {CITY["ko"]} 평균 {pa[-1]}%'
                    dt = round((pw[-1] + pc[-1]) - (pw[-2] + pc[-2]), 1)
                    # 델타 문구(C-8): ±0.05p 미만은 "비슷", 그 외 합계 기준 증감
                    if abs(dt) < 0.05:
                        delta_txt = '지난달과 비슷해요'
                    else:
                        delta_txt = f'지난달보다 {abs(dt):.1f}%p {"올랐어요" if dt > 0 else "내렸어요"}'
                    # F24: 기본 접힘 — 토글 줄에 현재값 요약 유지(정보 손실 방지), 차트는 펼칠 때 지연 렌더
                    cat_trend = (f'<div class="trend-fold ct-fold" data-ci="{ci}">'
                        f'<button type="button" class="trend-fold-btn"><span class="tf-tit">월별 불만 리뷰 비율 보기</span>'
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
                    <span class="cat-verdict is-{band}">불만 {E(cat_verdict(cat['score'])[0])}</span>
                    <span class="risk-arrow"></span>
                </button>
                <div class="risk-acc-body">
                    {axis}
                    <ul class="stat-list">{''.join(rows)}</ul>
                    {quotes_block}
                </div>
            </div>''')
            # §3-b 레이더 카테고리 칩 (동일 순서)
            _vl, _vs, _vb = cat_verdict(cat['score'])
            radar_chips.append(
                f'<button type="button" class="radar-cat is-{band}" data-target="risk-{ci}" aria-label="{E(cat_ko(c))} 불만 {_vl}, 자세히 보기">'
                f'<span class="rc-main"><span class="rc-name">{E(cat_ko(c))}</span><span class="rc-sub">{ratio_html(cat["score"])}</span></span>'
                f'<span class="rc-verdict">{E(_vl)}</span><span class="rc-arrow" aria-hidden="true"></span></button>')
        # ── 분류 v5: 칩 전용 대분류(안전) — 점수·순위 없이 최근 1년 심각 칩 + 근거 리뷰만. 점수 대분류 뒤에 고정 ──
        for c in ALL_CATS:
            if c not in CHIP_ONLY_CATS: continue
            ci = CAT_INDEX[c]; cat = h['cats'][c]
            qlist = [q for q in quotes.get((pid, c), []) if not cut_1y or str(q.get('pub') or '')[:10] >= cut_1y]
            sheet_data[c] = [{'s': q.get('scat') or '', 'g': q['grade'], 'q': q.get('quote') or q.get('summary') or '',
                              'd': (q.get('pub') or '')[:10], 'n': mask_name(q.get('reviewer_name')),
                              'st': q.get('stars'), 'o': q.get('review_origin') or 'Google',
                              'u': q.get('review_url') or '', 'tf': q.get('tfull') or '', 'of': q.get('ofull') or '',
                              'l': (q.get('lang') or '').lower(), 'r': q.get('rid'), 'f': q.get('fid'),   # f = 판정 ID(오분류 신고, R2 전체 JSON과 같은 키)
                              **({'rf': 1} if q.get('rf') else {})} for q in qlist]
            sub_cnt = {s: cat['subs'][s]['count_1y'] for s in SUBS[c] if cat['subs'][s]['count_1y'] > 0}
            sheet_total[c] = {'t': sum(sub_cnt.values()), 's': sub_cnt}
            rows, tones = [], []
            for s in SUBS[c]:
                cnt = cat['subs'][s]['count_1y']
                _clabel, _ctone = rare_cascade.get(s, (f'{per} 심각 리뷰 없음', 'clear'))
                tones.append(_ctone)
                cnt_html = (f'<button type="button" class="stat-count has-reviews" data-cat="{E(c)}" data-sub="{E(s)}">{cnt}건</button>'
                            if cnt > 0 else '')
                rows.append(f'''<li class="stat-row is-rare" data-sub="{E(s)}">
                    <div class="stat-info"><div class="factor"><span class="sub-dot is-{'danger' if _ctone == 'alert' else 'safe'}"></span>{E(s)}</div><div class="keywords">{E(SUB_KEYWORDS.get(s, '').replace(' · ', ', '))}</div></div>
                    <div class="rare-chip is-{_ctone}">{E(_clabel)}</div>
                    {cnt_html}
                </li>''')
            alert = 'alert' in tones
            band = 'danger' if alert else 'safe'
            head_txt = rare_cascade.get(SUBS[c][0], (f'{per} 심각 리뷰 없음', 'clear'))[0]
            qc = quote_cards(qlist)
            more_btn = (f'''<div class="more"><button type="button" class="more-btn" data-cat="{E(c)}"><strong>{E(cat_ko(c))}</strong> 리뷰 전체보기 ({sheet_total[c]['t']}건)</button></div>'''
                        if qlist else '')
            quotes_block = (f'''<div class="review"><div class="list review-slider"><ul class="swiper-wrapper">{qc}</ul></div></div>{more_btn}'''
                            if qc else '<div class="no-quote">무단 입실·잠금 문제를 말한 리뷰가 거의 없어요</div>')
            groups.append(f'''<div class="risk-acc-item" id="risk-{ci}" data-order="{len(CATS)}">
                <button type="button" class="risk-acc-head">
                    <span class="risk-dot is-{band}"></span>
                    <span class="cat-name">{E(cat_ko(c))}</span>
                    <span class="cat-verdict is-{band}">{E(head_txt)}</span>
                    <span class="cat-rank">점수 대신 실제 리뷰 건수로 보여드려요</span>
                    <span class="risk-arrow"></span>
                </button>
                <div class="risk-acc-body">
                    <ul class="stat-list">{''.join(rows)}</ul>
                    {quotes_block}
                </div>
            </div>''')
        radar_cats_html = f'<div class="radar-cats">{"".join(radar_chips)}</div>'

        # ── 전체 통합 월별 흐름 라인차트 (게이지 아래·인사이트 앞) ──
        overall_trend, trendc_all = overall_trend_html(pid, monthly, monthly_cat, CITY['asof'], city_avg)
        if trendc_all is not None:
            trendc['all'] = trendc_all

        st = stars.get(pid)
        stars_block = ''
        if st and st['total_1y'] > 0:      # 최근 1년 분포 (예전엔 분포는 전체기간·비율 문장만 1년이라 기간이 섞여 있었음)
            bars = []
            for i in range(1, 6):
                w = round(st['dist_1y'][i] / st['total_1y'] * 100)
                bars.append(f'''<li><div class="num">{i}점</div><div class="bar"><i style="width:{w}%"></i></div><div class="per">{w}%</div></li>''')
            low_share = round(st['low_1y'] / st['total_1y'] * 100)
            stars_block = f'''<div class="sect recent">
                <div class="head"><div class="title">구글 별점 분포</div>
                <div class="desc">{per} 구글 리뷰 중 <b>2점 이하가 {low_share}%</b>예요.<br>별점은 구글 리뷰만 있어요 (트립닷컴 등은 별점 미제공)</div>
                <div class="count">{per} {st['total_1y']:,}건</div></div>
                <div class="list"><ul>{''.join(bars)}</ul></div>
            </div>'''

        # 산출 기준(?): ① 단순 비율과 다른 이유(암산한 고객용) ② 실망 리뷰 정의 ③ 리뷰 구성 ④ 출처·기준일 (2026-10 카피 개편)
        _so = h['star_only_1y']
        _raw = (crit_reviews_1y / h['text_1y'] * 100) if h['text_1y'] else None
        if _raw is not None and abs(_raw - h['p_crit'] * 100) >= 0.5:
            _why1 = (f"<b>{v}%는 글 리뷰 {h['text_1y']:,}건 중 {crit_reviews_1y}건을 그대로 나눈 값({_raw:.1f}%)이 아니에요.</b> "
                     f"최근 리뷰일수록 크게 보고(6개월 지나면 절반), 리뷰가 적은 호텔은 {CITY['ko']} 평균 쪽으로 보정해서 조금 달라요")
        else:
            _why1 = (f"최근 리뷰일수록 크게 보고(6개월 지나면 절반), 리뷰가 적은 호텔은 {CITY['ko']} 평균 쪽으로 보정해요. "
                     f"이 호텔은 글 리뷰 {h['text_1y']:,}건 중 {crit_reviews_1y}건을 나눈 값과 거의 같아요")
        if _so and city.get('star_p'):
            _so_txt = (f"{per} 리뷰 {h['analyzed']:,}건 = 글 리뷰 {h['text_1y']:,}건 + 별점만 남긴 {_so:,}건. "
                       f"별점만 남긴 리뷰는 같은 별점 리뷰의 실망 비율로 추정해 약 {h.get('imp_1y', 0):.1f}건으로 반영했어요")
        elif _so:
            _so_txt = f"{per} 리뷰 {h['analyzed']:,}건 = 글 리뷰 {h['text_1y']:,}건 + 별점만 남긴 {_so:,}건('문제 언급 없음'으로 셈)"
        else:
            _so_txt = f"{per} 리뷰 {h['text_1y']:,}건 모두 글 리뷰라 AI가 전부 읽었어요"
        body_scored = f'''
        <div class="sect disappear" id="sec-prob">
            <div class="head">
                <div class="eyebrow">이 호텔에서 실망할 확률<button type="button" class="basis-toggle" aria-label="산출 기준"><i class="bt-q">?</i></button></div>
                <div class="pct is-{v_tone}">{v}%</div>
                <div class="vh is-{v_tone}">{E(v_head)}</div>
                {v_sub_html}
            </div>
            {gauge_html(h['p_crit'], city['crit'], v_tone, h.get('rank_tier'))}
            {verdict_why_html}
            {overall_trend}
            <div class="basis-fold">
                <div class="basis">
                    <p>{_why1}</p>
                    <p>실망 리뷰 = 심각한 문제(벌레·파손·안전 위협 등)를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰</p>
                    <p>{_so_txt}</p>
                    <p class="basis-note">구글·트립닷컴 등 공개 리뷰 기준 · {CITY['data_asof']} · 참고용 의견이라 실제 경험과 다를 수 있어요 · <a href="../about">계산 방법 자세히</a></p>
                </div>
            </div>
        </div>
        <div class="sect risk">
            <div class="head"><div class="title">항목별로 보면</div>
            <div class="desc">{CITY['ko']} 호텔 평균과 비교한 불만 정도예요 · 누르면 근거 리뷰로 이동해요</div></div>
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
                              borderColor: '#B0B8C1', borderDash: [4,4], pointRadius: 0, borderWidth: 1.5}}
                        ]
                    }},
                    options: {{
                        responsive: true, maintainAspectRatio: false,
                        layout: {{padding: 2}},
                        plugins: {{legend: {{display: false}}, tooltip: {{enabled: false}}}},
                        scales: {{r: {{
                            min: 0, max: {radar_max},
                            angleLines: {{color: '#F2F4F6'}},
                            grid: {{color: '#E5E8EB', circular: false}},
                            ticks: {{stepSize: 25, backdropColor: 'transparent', showLabelBackdrop: false, color: '#B0B8C1', font: {{size: 12}}}},
                            pointLabels: {{font: {{size: 13, weight: '600'}}, color: '#4E5968', padding: 12}}
                        }}}}
                    }}
                }});
            }});
            </script>
            {radar_cats_html}
        </div>
        <div class="sect analysis" id="risk-detail">
            <div class="head"><div class="title">리스크 상세 분석</div>
            <div class="desc">항목별로 {CITY['ko']} 호텔 평균보다 불만이 많은지 적은지 보여드려요<br>펼치면 불만 건수와 실제 리뷰를 볼 수 있어요</div></div>
            <div class="risk-acc">{''.join(groups)}</div>
            {('<script>window.TRENDC=' + json.dumps(trendc, ensure_ascii=False) + ';</script>') if trendc else ''}
            <div class="stat-legend">
                <span class="lg is-danger">불만 많음</span><span class="lg is-warning">평균 수준·많은 편</span><span class="lg is-safe">적은 편</span>
                <span class="note">불만 리뷰 5건 미만 소분류는 위험 등급을 붙이지 않아요</span>
                <span class="note">인용문은 리뷰 원문 발췌입니다</span>
                <span class="note">벌레, 곰팡이, 밤길·동네 분위기, 객실 보안처럼 드물지만 치명적인 항목은 점수 대신 리뷰 건수로 보여드려요</span>
            </div>
        </div>
        {similar_block}
        {pairs_block}
        {faq_section(faq)}
        {'<div id="sec-rev" class="sec-anchor"></div>' if (social or stars_block) else ''}
        {social_section(social, name)}
        {stars_block}
        {korean_card(kr_1y, h, kr_rank_pct, kr_dist, per)}
        <div class="review-sheet" id="review-sheet" hidden role="dialog" aria-modal="true" aria-label="리뷰 근거">
            <div class="sheet-dim"></div>
            <div class="sheet-panel">
                <aside class="sheet-side" id="sheet-side" aria-label="카테고리"></aside>
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
        window.QSUBS = {json.dumps({c: SUBS[c] for c in ALL_CATS}, ensure_ascii=False)};
        window.QSUBKO = {json.dumps(SUB_PHRASE, ensure_ascii=False)};   // 소분류 화면 표기(아코디언·근거 줄과 같은 말) — 내부키는 QSUBS 그대로
        window.QCAT = {json.dumps({c: [round(h['cats'][c]['score']), h['cats'][c]['band']] for c in CATS}, ensure_ascii=False)};
        window.QCHIP = {json.dumps({c: rare_cascade.get(SUBS[c][0], (f'{per} 심각 리뷰 없음', 'clear')) for c in CHIP_ONLY_CATS}, ensure_ascii=False)};
        window.QFULL = {json.dumps(f'{R2_PUB}/quotes/{pid}.json')};
        window.QCUT = {json.dumps(cut_1y or '')};   // 근거 리뷰 기간 시작일 — R2 전체 파일도 이 날짜 이후만 표시
        window.QPER = {json.dumps(per)};
        window.QDIS = {json.dumps({'n': crit_reviews_1y})};   // 근거 줄의 실망 리뷰 M건 — 팝업 건수와 대조
        window.CF_FAQR = {json.dumps(f'{R2_PUB}/faq_reviews/{pid}.json')};
        window.CF_PID = {json.dumps(pid)};
        window.QSUBCAT = {json.dumps(SUB_CAT, ensure_ascii=False)};   // 소분류 → 대분류 (실망 리뷰 모아보기에서 신고 버튼의 현재 분류)
        window.CF_GREVIEWS = 'https://search.google.com/local/reviews?placeid={pid}';
        </script>'''

    # P2 고정 섹션 탭 (채점 호텔만) — DOM 순서 = 탭 순서. 없는 섹션은 탭도 생략.
    if h['scored']:
        _tabs = ([('sec-sum', '요약')] if glance_html else []) + [('sec-prob', '위험도')]
        if similar_block: _tabs.append(('sec-alt', '대안'))
        if faq: _tabs.append(('hotel-faq', '실전정보'))
        if social or stars_block: _tabs.append(('sec-rev', '후기'))
        tabs_html = ('<nav class="det-tabs" id="det-tabs" aria-label="섹션 바로가기">'
                     + ''.join(f'<a href="#{t}" class="{"is-on" if i == 0 else ""}">{lbl}</a>' for i, (t, lbl) in enumerate(_tabs))
                     + '</nav>' + DETAIL_TABS_JS)

    # P5 비교 담기 (채점 호텔만 — 비교표가 위험도 기반)
    cmp_btn = (f'<button type="button" class="cmp-btn" data-cmp-id="{pid}" data-cmp-name="{E(name)}" '
               f'data-cmp-img="{E(abs_img(pid, meta))}"><span class="cmp-ico"></span><span class="cmp-t">비교 담기</span></button>'
               if h['scored'] else '')
    # ── PC 전용: 브레드크럼(JSON-LD BreadcrumbList와 동일 경로) + 오른쪽 결정 카드(실망 확률·핵심 수치·CTA) ──
    _area = next((a for a in AREAS if _in_area(meta, a)), None)
    pc_crumb = (f'<nav class="pc-crumb" aria-label="경로"><a href="../">캐치플로</a><span>›</span><a href="../search">{CITY["ko"]} 호텔</a>'
                + (f'<span>›</span><a href="../search?area={_area["code"]}">{E(_area["ko"])}</a>' if _area else '')
                + f'<span>›</span><b>{E(name)}</b></nav>')
    _st2 = nearest_station(meta.get('latitude'), meta.get('longitude'))
    _rows = [('구글 평점', f'<b>{fmt_score(meta.get("total_score"))}</b> ({meta.get("reviews_count") or 0:,}개)'),
             ('분석 리뷰', f'<b>{h["analyzed"]:,}건</b> · {per}')]
    if meta.get('price_txt'): _rows.append(('1박 가격', f'<b>{E(meta["price_txt"])}</b>' + (f' · 주말 약 {round(meta["price_we"] / 10_000)}만원' if meta.get('price_we') else '')))
    if _st2: _rows.append(('가까운 역', f'{E(_st2[0])} 도보 <b>{_st2[1]}분</b>'))
    _rows_html = ''.join(f'<li><span>{k}</span><span>{v}</span></li>' for k, v in _rows)
    if h['scored']:
        _pv = pct(h['p_crit'])
        _top_html = (f'<div class="ps-eyebrow">이 호텔에서 실망할 확률</div>'
                     f'<div class="ps-pct">{_pv}%</div><div class="ps-verdict is-{v_tone}">{E(v_head)}</div>'
                     f'<div class="ps-avg">{CITY["ko"]} 평균 {pct(city["crit"])}%{tier_html}</div>')
    else:
        _top_html = (f'<div class="ps-eyebrow">실망 확률</div><div class="ps-collect">분석 준비 중</div>'
                     f'<div class="ps-avg">분석 리뷰가 {MIN_REVIEWS}건 이상 쌓이면 공개해요</div>')
    pc_side = f'''<aside class="pc-side" aria-label="요약">
                    {_top_html}
                    <ul class="ps-rows">{_rows_html}</ul>
                    <a class="btn-reservate ps-cta" href="{E(gmap)}" target="_blank" rel="noopener">실시간 최저가 확인</a>
                    <div class="ps-actions">{cmp_btn.replace('class="cmp-btn"', 'class="cmp-btn ps-cmp"') if cmp_btn else ''}<a href="javascript:;" class="btn-share ps-share">공유</a></div>
                    <p class="ps-note">공개 리뷰 기반 참고용 통계예요 · <a href="../about">산출 방법</a></p>
                </aside>'''
    canonical = f'{BASE}/hotels/{pid}'
    og_img = meta.get('r2_img') or (f'{BASE}/img/hotels/{pid}.jpg' if meta.get('local_img') else None)
    if h['scored']:
        _v = pct(h['p_crit']); _avg = pct(city['crit'])
        _t = h.get('rank_tier')
        rank_txt = f' 실망 확률이 낮은 순으로 {CITY["ko"]} {_t[1]}.' if (_t and _t[0] == 'top') else ''
        seo_title = f'{name} 리뷰 위험도 · 실망확률 {_v}% | 캐치플로'
        seo_desc = (f'{name} 실망 확률 {_v}% ({CITY["ko"]} 평균 {_avg}%).{rank_txt} '
                    '청결·냄새·소음·객실·직원·위치 6개 항목의 리뷰 위험도와 안전 신호를 예약 전에 확인하세요.')
    else:
        seo_title = f'{name} 리뷰 위험도 분석 | 캐치플로'
        seo_desc = (f'{name}의 리뷰를 수집·분석하고 있습니다. 위치·가격·구글 평점과 '
                    '주변의 실망 확률 낮은 추천 호텔을 캐치플로에서 확인하세요.')
    _faqld = faq_jsonld(faq) if h['scored'] else None
    _extra_head = jsonld_detail(pid, meta) + (('\n' + _jsonld(_faqld)) if _faqld else '')
    return head(seo_title, depth=1, description=seo_desc, canonical=canonical,
                og_image=og_img, extra_head=_extra_head) + f'''
    <script>window.CF_HOTEL={{pid:{json.dumps(pid)},name:{json.dumps(name)},gmap:{json.dumps(gmap)}}};</script>
    <script src="../js/report.js?v={BUILD}" defer></script>
    <script>window.CF_IMGS={json.dumps(meta.get('r2_imgs') or [], ensure_ascii=False)};</script>
    <script src="../js/lightbox.js?v={BUILD}" defer></script>
    <main id="container">
        <section id="detail">
            {site_header(1, back='../search')}
            <div class="content">
                {gallery_html(meta, name, img)}
                {pc_gallery_html(meta, name, img)}
                <div class="sect information">
                    {pc_crumb}
                    <div class="info-top"><div class="badge">{badge_html(h)}</div></div>
                    <div class="info-cont">
                        <div class="name">
                            <h1 class="name-ko">{E(name)}</h1>
                            <p class="name-en">{E(meta.get('sub_title') or '')}</p>
                        </div>
                        <div class="meta"><span>{CITY['ko']}, JP</span>{f'<span>{hstars}</span>' if hstars else ''}{f"<span class='price'>1박 <b>{meta['price_txt']}</b></span>" if meta.get('price_txt') else ''}</div>
                        {(f'<p class="price-note">' + (f'주말은 약 {round(meta["price_we"] / 10_000)}만원 · ' if meta.get('price_we') else '') + '2인 1박' + (f' · {md_ko(meta["price_seen"])} 확인' if meta.get('price_seen') else '') + '</p>') if meta.get('price_txt') else ''}
                        <button type="button" class="btn-share info-share"><img src="../img/b_share.svg" alt="">공유하기</button>
                    </div>
                    {lowrev_html}
                    <div class="info-bottom">
                        <a class="btn-link btn-google" href="{E(gmap)}" target="_blank" rel="noopener">
                            <span class="ico"><img src="../img/google.svg" alt=""></span>
                            <span class="txt"><span class="label">구글 평점 {fmt_score(meta.get('total_score'))}</span><span class="count">({meta.get('reviews_count') or 0:,}개)</span></span>
                        </a>
                        <a class="btn-link btn-audit" href="#risk-detail">
                            <span class="ico"><img src="../img/audit.svg" alt=""></span>
                            <span class="txt"><span class="label">분석 리뷰 {h['analyzed']:,}건</span><span class="count"><span class="seg">{per}</span>{DSEP}<span class="seg">구글·트립닷컴 등</span></span></span>
                        </a>
                    </div>
                    {faq_jump_html}
                </div>
                {pc_side}
                {tabs_html}
                {glance_html}
                {who_html}
                {map_block}
                {body_scored}
                {col_chip_block}
                {'' if h['scored'] else similar_block}
            </div>
            <div class="button"><a class="btn-reservate" href="{E(gmap)}" target="_blank" rel="noopener">실시간 최저가 확인</a></div>
        </section>
        <section id="float">
            <div class="float">
                {cmp_btn.replace('class="cmp-btn"', 'class="cmp-btn cmp-fab"').replace('<span class="cmp-t">비교 담기</span>', '<span class="cmp-t">비교</span>').replace('data-cmp-img', 'data-off="비교" data-on="담김" data-cmp-img') if cmp_btn else ''}
                <a href="javascript:;" class="btn-top" aria-label="맨 위로"><img src="../img/b_top.svg" alt="맨 위로"></a>
            </div>
        </section>
    </main>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="../js/compare.js?v={BUILD}" data-root="../"></script>
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
                    .then(function(j){{
                        if (window.QCUT) Object.keys(j).forEach(function(c){{ j[c] = (j[c] || []).filter(function(q){{ return (q.d || '') >= window.QCUT; }}); }});
                        window.QDATA = j; qfull = true; qloading = false; cb && cb(); }})
                    .catch(function(){{ qloading = false; render(); toast('전체 리뷰를 불러오지 못했어요'); }});
            }}

            function esc(s){{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
            function subKo(s){{ return (window.QSUBKO && window.QSUBKO[s]) || s; }}   // '동네 분위기' → '밤길·동네 분위기' 등 화면 표기
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
                    + (q.f ? repBtn(q) : '')
                    + (hasFull ? '<button type="button" class="expand-btn">전체 리뷰 <i>▾</i></button>' : '')
                    + '</div>';
                return '<li><div class="item">'
                    + '<div class="item-top"><div class="name">' + esc(q.n) + '</div>'
                    + '<div class="status"><div class="status-item ' + band + '">' + q.g + '</div></div></div>'
                    + '<div class="item-info">' + star + '<div class="web">' + esc(q.o) + '</div>' + (langLabel(q.l) ? '<span class="q-lang">' + langLabel(q.l) + '</span>' : '') + '</div>'
                    + '<div class="item-bottom"><div class="text clamp">' + emph(q.q) + '</div>'
                    + '<div class="date">' + esc((q.d||'').replace(/-/g,'. ')) + (q.s ? ' · ' + esc(subKo(q.s)) : '') + relSpan(q.d) + '</div></div>'
                    + foot + full
                    + '</div></li>';
            }}
            // 오분류 신고 버튼 (FEEDBACK-2610 §13, js/report.js) — 대분류는 소분류에서(실망 모아보기는 여러 항목이 섞임)
            function repBtn(q){{
                var c = (window.QSUBCAT && window.QSUBCAT[q.s]) || (curCat !== '__dis__' ? curCat : '');
                return '<button type="button" class="rep-btn" data-fid="' + esc(q.f) + '" data-cat="' + esc(c) + '" data-sub="' + esc(q.s) + '" data-grade="' + esc(q.g) + '">분류가 이상해요</button>';
            }}
            // F32+F39: 원문 링크 — 라벨 통일 "리뷰 원문 보기", 목적지는 저장 URL 그대로. URL 빈값이면 미출력
            function origLink(o, u){{
                if (!u) return '<span></span>';
                return '<a class="orig-link" href="' + esc(u) + '" target="_blank" rel="noopener">리뷰 원문 보기 ↗</a>';
            }}
            // F27: 시트 카드 날짜 옆 상대 뱃지 (동적 렌더 — 로드시점 계산)
            function relSpan(d){{ var s = window.CF_rel ? window.CF_rel(String(d||'').slice(0,10)) : ''; return s ? '<span class="rel-badge">' + s + '</span>' : ''; }}

            // 실망 리뷰만(근거 줄): 전 카테고리 카드 중 심각 또는 재방문·추천 거부(rf) 리뷰를 리뷰 단위(r)로 묶는다 — 근거 줄 M건과 같은 집합
            function disList(){{
                var seen = {{}}, out = [];
                Object.keys(window.QDATA).forEach(function(c){{
                    (window.QDATA[c] || []).forEach(function(q){{
                        if (!(q.g === '심각' || q.rf)) return;
                        var k = q.r || (q.n + '|' + q.d + '|' + q.o);
                        if (seen[k]) {{ if (q.g === '심각' && seen[k].g !== '심각') {{ out[out.indexOf(seen[k])] = q; seen[k] = q; }} return; }}
                        seen[k] = q; out.push(q);
                    }});
                }});
                out.sort(function(a, b){{ return ((b.g === '심각') - (a.g === '심각')) || (b.d > a.d ? 1 : b.d < a.d ? -1 : 0); }});
                return out;
            }}
            function renderDis(){{
                var list = disList();
                if (krOnly) list = list.filter(function(q){{ return q.l === 'ko'; }});
                var M = (window.QDIS && window.QDIS.n) || 0;
                $('#sheet-cat').text('실망');
                $('#sheet-cnt').text(qloading ? '불러오는 중…' : (!krOnly && qfull && M && M !== list.length) ? M + '건 중 ' + list.length + '건' : list.length + '건');
                $('#sheet-list').html(list.map(card).join('') || '<li class="sheet-empty">' + (qloading ? '리뷰를 불러오는 중…' : '실망 리뷰가 없어요') + '</li>');
                $('#sheet-chips').html('<div class="sheet-note">심각한 문제를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰예요</div>');
                $('#sheet-list').scrollTop(0);
                $('#sheet-kr').toggleClass('is-on', krOnly);
                renderSide();
            }}
            function render(){{
                if (curCat === '__dis__') return renderDis();
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
                    chips.push('<button type="button" class="sheet-chip' + (curSub === s ? ' on' : '') + '" data-sub="' + esc(s) + '">' + esc(subKo(s)) + ' ' + n + '</button>');
                }});
                $('#sheet-chips').html(chips.join(''));
                $('#sheet-list').scrollTop(0);
                $('#sheet-kr').toggleClass('is-on', krOnly);
                renderSide();
            }}
            // PC 팝업 왼쪽: 6개 카테고리(위험도·리뷰 수) — 누르면 그 카테고리 근거 리뷰로 전환 (Airbnb 리뷰 팝업 패턴)
            function renderSide(){{
                var Q = window.QCAT || {{}};
                function vlab(v){{ return v < 25 ? '거의 없음' : v < 45 ? '적은 편' : v < 55 ? '평균 수준' : v < 70 ? '많은 편' : '많음'; }}   // cat_verdict와 같은 구간
                var rows = Object.keys(window.QSUBS).map(function(c){{
                    var T = window.QTOTAL && window.QTOTAL[c], n = T ? T.t : (window.QDATA[c] || []).length;
                    var sc = Q[c] || [0, 'safe'];
                    var chip = window.QCHIP && window.QCHIP[c];          // 칩 전용 대분류(안전): 점수 대신 심각 건수 문구
                    if (chip) sc = [0, chip[1] === 'alert' ? 'danger' : 'safe'];
                    return '<button type="button" class="ss-cat' + (c === curCat ? ' is-on' : '') + '" data-cat="' + esc(c) + '"' + (n ? '' : ' disabled') + '>'
                        + '<span class="ss-dot is-' + sc[1] + '"></span>'
                        + '<span class="ss-name">' + esc((window.CAT_KO && window.CAT_KO[c]) || c) + '</span>'
                        + '<span class="ss-score is-' + sc[1] + '">' + (chip ? esc(chip[0]) : '불만 ' + vlab(sc[0])) + '</span>'
                        + '<span class="ss-cnt">' + n + '건</span></button>';
                }}).join('');
                var hn = (window.CF_HOTEL && window.CF_HOTEL.name) || '';
                $('#sheet-side').html('<div class="ss-tit">리뷰 근거</div>' + (hn ? '<div class="ss-hotel">' + esc(hn) + '</div>' : '')
                    + '<div class="ss-sub">항목을 고르면 ' + esc(window.QPER || '최근 1년') + ' 리뷰 중 그 불만이 언급된 리뷰만 보여드려요</div>'
                    + '<div class="ss-list">' + rows + '</div>'
                    + '<div class="ss-note">불만 정도는 후쿠오카 호텔 평균과 비교한 결과예요 · 인용문은 리뷰 원문 발췌이며 작성자 이름은 가렸어요</div>');
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
                void $sheet[0].offsetHeight;          // hidden 해제를 전환에 반영(백그라운드 탭에선 rAF가 안 불림)
                $sheet.addClass('is-open');
                $sheet.find('.sheet-close').trigger('focus');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);  // 뒤로가기로 시트만 닫힘
            }}
            function openDis(){{
                curCat = '__dis__'; curSub = null; krOnly = false;
                if (!qfull) loadFull(render); else render();   // 임베드는 카테고리당 40건 상한 → 전체 파일 먼저
                $sheet.prop('hidden', false);
                void $sheet[0].offsetHeight;
                $sheet.addClass('is-open');
                $sheet.find('.sheet-close').trigger('focus');
                $('body').css('overflow', 'hidden');
                if (window.CFNav) CFNav.push(closeVisual);
            }}
            $(document).on('click', '.ev-row[data-dis]', function(){{ openDis(); }});
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
            $sheet.on('click', '.ss-cat', function(){{ curCat = $(this).data('cat'); curSub = null; render(); }});
            $(document).on('keydown', function(e){{   // 팝업이 열려 있을 때 ←/→ 로 카테고리 이동(FAQ 모드 제외)
                if (!$sheet.hasClass('is-open') || $sheet.hasClass('faq-mode')) return;
                if (e.key === 'ArrowLeft') shift(-1); else if (e.key === 'ArrowRight') shift(1);
            }});
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
            // 블로그 더보기: 숨긴 카드 전체 펼침 (기본 3 → 최대 9)
            $(document).on('click', '.nb-more', function(){{
                $('.nb-card.nb-hidden').removeClass('nb-hidden');
                $(this).remove();
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

            // ── 월별 불만 리뷰 비율 라인차트 공통 생성 헬퍼 (카테고리·전체 공용) ──
            function makeTrendChart(canvasId, d){{
                var el = document.getElementById(canvasId); if (!el || !window.Chart || !d) return;
                var ctx = el.getContext('2d');
                var gW = ctx.createLinearGradient(0,0,0,130); gW.addColorStop(0,'rgba(240,160,40,.22)'); gW.addColorStop(1,'rgba(240,160,40,.02)');
                var gC = ctx.createLinearGradient(0,0,0,130); gC.addColorStop(0,'rgba(250,82,82,.22)'); gC.addColorStop(1,'rgba(250,82,82,.02)');
                var n = d.m.length, pr = Array(n).fill(0); pr[n-1] = 3;
                new Chart(ctx, {{type:'line', data:{{labels:d.m, datasets:[
                    {{label:'심각', data:d.c, borderColor:'#FA5252', backgroundColor:gC, fill:'origin', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#FA5252', stack:'risk'}},
                    {{label:'주의', data:d.w, borderColor:'#F0A028', backgroundColor:gW, fill:'-1', tension:.35, borderWidth:2, pointRadius:pr, pointBackgroundColor:'#F0A028', stack:'risk'}},
                    {{label:'후쿠오카 평균', data:d.a, borderColor:'#B0B8C1', borderDash:[4,4], borderWidth:1.5, pointRadius:0, fill:false, tension:.35, stack:'avg'}}]}},
                  options:{{responsive:true, maintainAspectRatio:false, interaction:{{mode:'index', intersect:false}},
                    plugins:{{legend:{{display:false}}, tooltip:{{displayColors:false, backgroundColor:'#fff', titleColor:'#191F28', bodyColor:'#4E5968',
                        borderColor:'#E5E8EB', borderWidth:1, cornerRadius:10, padding:10, footerColor:'#191F28', footerFont:{{weight:'bold'}},
                        callbacks:{{label:function(t){{return t.dataset.label+' '+t.parsed.y.toFixed(1)+'%';}},
                            footer:function(items){{var s=0; items.forEach(function(it){{if(it.dataset.stack==='risk') s+=it.parsed.y;}}); return '합계 '+s.toFixed(1)+'%';}}}}}}}},
                    scales:{{x:{{grid:{{display:false}}, ticks:{{font:{{size:12}}, color:'#8B95A1', maxRotation:0, autoSkip:true, maxTicksLimit:7}}}},
                            y:{{beginAtZero:true, stacked:true, grid:{{color:'#F2F4F6'}}, border:{{display:false}},
                               ticks:{{font:{{size:12}}, color:'#8B95A1', maxTicksLimit:4, callback:function(v){{return v+'%';}}}}}}}}}}}});
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
            // 실망 확률 근거 줄('심각 리뷰 벌레 3건' 등) → 해당 카테고리 아코디언을 열고 그 소분류 행으로 스크롤·잠시 강조
            $('#detail').on('click', '.ev-row[data-target]', function(e){{
                e.preventDefault();
                var t = String($(this).data('target') || ''), sub = String($(this).data('sub') || '');
                var $item = $('#' + t); if (!$item.length) return;
                $item.addClass('is-open'); initCatTrend($item);
                var $row = sub ? $item.find('.stat-row').filter(function(){{ return $(this).attr('data-sub') === sub; }}).first() : $();
                var $to = $row.length ? $row : $item;
                setTimeout(function(){{   // 본문(display:none → block)이 그려진 뒤에 위치를 재야 행 좌표가 맞는다
                    // html{{scroll-behavior:smooth}}와 jQuery animate(scrollTop)가 충돌해 제자리에 머무는 일이 있어 브라우저 기본 스크롤 사용
                    window.scrollTo({{top: Math.max(0, $to.offset().top - ($row.length ? 72 : 8)), behavior: 'smooth'}});
                    if ($row.length) {{ $row.addClass('is-flash'); setTimeout(function(){{ $row.removeClass('is-flash'); }}, 2200); }}
                }}, 60);
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
    # ── 동네별 (홈 블록 1줄째) — FEEDBACK-2610 §3. 순서 = 홈 칩·상호 링크·sitemap 순서(동네 4 → 동행 4 → 테마 4) ──
    {'slug': 'area/hakata', 'kind': 'area', 'area': 'hakata', 'min': 10, 'row': 'area',
     'name': '하카타역', 'h1': '하카타역 숙소 — 리뷰 위험도로 고른 안심 호텔',
     'title': '하카타역 호텔 TOP | 캐치플로'},
    {'slug': 'area/tenjin', 'kind': 'area', 'area': 'tenjin', 'min': 10, 'row': 'area',
     'name': '텐진', 'h1': '후쿠오카 텐진 호텔 — 리뷰 위험도로 고른 안심 숙소',
     'title': '후쿠오카 텐진 호텔 TOP | 캐치플로'},
    {'slug': 'area/nakasu', 'kind': 'area', 'area': 'nakasu', 'min': 10, 'row': 'area',
     'name': '나카스·캐널시티', 'h1': '나카스·캐널시티 호텔 — 리뷰 위험도 비교',
     'title': '나카스·캐널시티 호텔 TOP | 캐치플로'},
    {'slug': 'area/gion', 'kind': 'area', 'area': 'gion', 'min': 10, 'row': 'area',
     'name': '기온·오호리', 'h1': '기온·오호리 호텔 — 리뷰 위험도 비교',
     'title': '기온·오호리 호텔 TOP | 캐치플로'},
    # ── 동행별 — 소분류는 WHO_GROUPS(상세 '누구와 가세요')와 같은 정의를 쓴다(상수 한 곳) ──
    {'slug': 'best/solo', 'kind': 'who', 'who': 'solo', 'min': 8, 'row': 'who', 'chip': '혼자',
     'name': '혼자 여행', 'h1': '후쿠오카 혼자 여행 호텔 — 밤길·객실 보안·역 거리 기준',
     'title': '후쿠오카 혼자 여행 호텔 TOP | 캐치플로'},
    {'slug': 'best/couple', 'kind': 'who', 'who': 'two', 'min': 8, 'row': 'who', 'chip': '커플·2인',
     'name': '커플·2인', 'h1': '후쿠오카 커플·2인 호텔 — 좁은 방·침대·옆방 소음 기준',
     'title': '후쿠오카 커플 호텔 TOP | 캐치플로'},
    {'slug': 'best/group', 'kind': 'who', 'who': 'group', 'min': 8, 'row': 'who', 'chip': '친구·단체',
     'name': '친구·단체', 'h1': '후쿠오카 친구·단체 호텔 — 좁은 방·침대·온수 기준',
     'title': '후쿠오카 친구 여행 호텔 TOP | 캐치플로'},
    {'slug': 'best/family', 'kind': 'family', 'min': 8, 'row': 'who', 'chip': '아이 동반',
     'name': '가족여행', 'h1': '후쿠오카 가족여행 안심 호텔 — 방음·청결·위치 기준',
     'title': '후쿠오카 가족 호텔 TOP | 캐치플로'},
    # ── 테마별 ──
    {'slug': 'best/value', 'kind': 'value', 'min': 8, 'row': 'theme',
     'name': '가성비', 'h1': '후쿠오카 가성비 숙소 TOP — 가격대별 실망 확률 최저',
     'title': '후쿠오카 가성비 호텔 TOP | 캐치플로'},
    {'slug': 'best/luxury', 'kind': 'luxury', 'min': 8, 'row': 'theme',
     'name': '4·5성급', 'h1': '후쿠오카 4·5성급 호텔 — 고급 호텔 위험도 비교',
     'title': '후쿠오카 고급 호텔 TOP | 캐치플로'},
    {'slug': 'best/capsule', 'kind': 'capsule', 'min': 3, 'row': 'theme',
     'name': '캡슐호텔', 'h1': '후쿠오카 캡슐호텔 전부 비교 — 리뷰 위험도 순',
     'title': '후쿠오카 캡슐호텔 비교 | 캐치플로'},
    {'slug': 'best/bath', 'kind': 'bath', 'min': 5, 'row': 'theme',
     'name': '대욕장·온천', 'h1': '후쿠오카 대욕장·온천 호텔 — 리뷰 위험도로 고른 추천',
     'title': '후쿠오카 대욕장·온천 호텔 TOP | 캐치플로'},
]
COL_BY_SLUG = {c['slug']: c for c in COLLECTIONS}
COL_ROWS = [('area', '동네별'), ('who', '동행별'), ('theme', '테마별')]   # 홈 '동네·동행별로 보기' 3줄
FAQ = {}       # pid → 실전정보(faq.json) 항목들 — main()에서 채움(대욕장 허브 판정·카드 칩)
# 가족 안심 기준 카테고리 (청결, 방음=소음, 위치) — 분류 v5. 안전(칩 전용)은 점수가 없어 평균에서 제외
FAMILY_CATS = ['청결', '소음', '위치']

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

def _bath_chips(pid):
    """실전정보 '대욕장·온천' 칩(근거 있는 것만). '…없음' 칩이 하나라도 있으면 None(없다고 언급된 호텔)."""
    for it in FAQ.get(pid) or []:
        if it.get('t') == 'bath':
            c = [str(x) for x in (it.get('c') or [])]
            return None if any('없음' in x for x in c) else c
    return []

def _has_bath(pid, meta):
    """대욕장·온천 허브 대상 (FEEDBACK-2610 §3-4): amenities.spa_bath 참 또는 실전정보 bath 칩에 '없음'이 없는 호텔."""
    am = meta.get('amenities') or {}
    if isinstance(am, dict) and am.get('spa_bath'):
        return True
    return bool(_bath_chips(pid))

def _who_group(code):
    return next((g for g in WHO_GROUPS if g[0] == code), None)

def _stars_num(meta):
    m = re.match(r'(\d)성급', meta.get('hotel_stars') or '')
    return int(m.group(1)) if m else None

def collection_members(col, hotels_meta, H):
    """컬렉션 소속 scored 호텔 pid 리스트를 랭킹 순으로 반환. 데이터 부족 시 None(스킵).
       분석 준비 중(unscored)·rec_excluded(hotels_meta에서 이미 제외)는 랭킹에서 뺀다."""
    scored = [p for p in hotels_meta if p in H and H[p]['scored']]
    kind = col['kind']

    if kind == 'area':
        area = _area_by_code(col['area'])
        if not area:
            return None
        cand = [p for p in scored if _in_area(hotels_meta[p], area)]
        cand.sort(key=lambda p: (not H[p]['ranked'], -REC.get(p, 0.0), H[p]['p_crit']))   # 추천순(rec_score), 리뷰 적은 호텔은 뒤로(순위 모수 밖)
        return cand

    if kind == 'value':
        # 하위 2밴드(b1·b2) × p_crit 낮은순
        cand = [p for p in scored if hotels_meta[p].get('band') and hotels_meta[p]['band'][0] in ('b1', 'b2')]
        cand.sort(key=lambda p: (not H[p]['ranked'], -REC.get(p, 0.0), H[p]['p_crit']))   # 추천순(rec_score), 리뷰 적은 호텔은 뒤로(순위 모수 밖)
        return cand

    if kind == 'capsule':
        cand = [p for p in scored if _is_capsule(p, hotels_meta[p])]
        cand.sort(key=lambda p: (not H[p]['ranked'], -REC.get(p, 0.0), H[p]['p_crit']))   # 추천순(rec_score), 리뷰 적은 호텔은 뒤로(순위 모수 밖)
        return cand

    if kind == 'bath':
        cand = [p for p in scored if _has_bath(p, hotels_meta[p])]
        cand.sort(key=lambda p: (not H[p]['ranked'], -REC.get(p, 0.0), H[p]['p_crit']))   # 추천순(rec_score), 리뷰 적은 호텔은 뒤로(순위 모수 밖)
        return cand

    if kind == 'who':
        # 동행 허브 (FEEDBACK-2610 §3-3): 그룹 소분류 3개가 모두 위험 아님 + 그룹의 희소 소분류는 최근 1년 심각 0건.
        # 정렬 = 소분류 3개 위험도 평균 오름차순 → 동률 추천순. 리뷰 적은 호텔은 뒤로(순위 모수 밖).
        g = _who_group(col['who'])
        if not g:
            return None
        subs = [(SUB_CAT[s], s) for s in g[2]]
        def ok(p):
            for c, s in subs:
                sb = H[p]['cats'][c]['subs'][s]
                if sb['band'] == 'danger': return False
                if s in RARE_SUBS and sb.get('crit_1y', 0) > 0: return False
            return True
        cand = [p for p in scored if ok(p)]
        cand.sort(key=lambda p: (not H[p]['ranked'],
                                 round(sum(H[p]['cats'][c]['subs'][s]['score'] for c, s in subs) / len(subs), 1),
                                 -REC.get(p, 0.0)))
        return cand

    if kind == 'family':
        # 방음·청결·위치 3개 카테고리 band != danger & scored, 그 3개 평균점수 낮은순
        cand = [p for p in scored
                if all(H[p]['cats'][c]['band'] != 'danger' for c in FAMILY_CATS)]
        cand.sort(key=lambda p: (not H[p]['ranked'], sum(H[p]['cats'][c]['score'] for c in FAMILY_CATS) / len(FAMILY_CATS)))
        return cand

    if kind == 'luxury':
        cand = [p for p in scored if (_stars_num(hotels_meta[p]) or 0) >= 4]
        cand.sort(key=lambda p: (not H[p]['ranked'], -REC.get(p, 0.0), H[p]['p_crit']))   # 추천순(rec_score), 리뷰 적은 호텔은 뒤로(순위 모수 밖)
        return cand

    return None

def collection_stats(pids, hotels_meta, H, city):
    """컬렉션 집계 수치: N곳·리뷰 M건·평균 실망확률%·최다 불만 카테고리·카테고리 편차 상위.
       반환 dict. reviews M = Σ analyzed."""
    n = len(pids)
    reviews = sum(H[p]['analyzed'] for p in pids)
    # 평균·항목 편차는 리뷰 RANK_MIN 이상 호텔로 (리뷰 적은 호텔의 흔들리는 숫자가 평균을 끌지 않게). 없으면 전체
    base = [p for p in pids if H[p]['ranked']] or pids
    nb = len(base)
    avg_p = pct(sum(H[p]['p_crit'] for p in base) / nb) if nb else 0
    city_p = pct(city['crit'])
    # 항목별로 보면: 컬렉션 평균 카테고리 점수 vs 도시평균(=50). 편차 상위 2~3개.
    cat_avg = {c: sum(H[p]['cats'][c]['score'] for p in base) / nb for c in CATS} if nb else {c: 50 for c in CATS}
    devs = sorted(((c, cat_avg[c] - 50.0) for c in CATS), key=lambda kv: -abs(kv[1]))
    top_dev = [(c, d) for c, d in devs if abs(d) >= 3.0][:3]   # 의미 있는 편차만
    worst_cat = max(CATS, key=lambda c: cat_avg[c]) if n else CATS[0]
    return {'n': n, 'reviews': reviews, 'avg_p': avg_p, 'city_p': city_p,
            'cat_avg': cat_avg, 'top_dev': top_dev, 'worst_cat': worst_cat}

def _col_href(slug, depth=0):
    """컬렉션 상대경로 링크 — 사이트 전역 무확장 규칙(canonical·sitemap과 동일 표기)."""
    return f'{"../" * depth}{slug}'

def hub_card(pid, meta, h, rank, depth=1, chips=None):
    """허브 랭킹 카드 — 검색 리스트 카드와 픽셀 동일한 구조/클래스 재사용(#hub .hub-list 셀렉터 병기).
       고유 요소: 순위 배지(썸네일 좌상단)·지역 태그+역거리 1줄·시설 칩만 추가. chips를 주면 시설 칩 대신(대욕장 허브의 실전정보 칩)."""
    p_root = '../' * depth
    href = f'{p_root}hotels/{pid}'
    img = img_path(pid, meta, depth)
    name = E(meta['title'])
    al = area_line_html(meta, station=station_line(meta))     # 지역 태그 + 역 도보(허브는 직선거리까지)
    st_html = f'<div class="hub-station area-line">{al}</div>' if al else ''
    pl = price_line_html(meta)
    meta_html = f'<span>{E(meta.get("hotel_stars"))}</span>' if meta.get('hotel_stars') else ''
    chips = amenity_chips(meta, 3) if chips is None else chips[:3]
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
                    <div class="badge">
                        <div class="badge-item badge-{band}">{label}</div>
                        <div class="badge-item badge-down">실망 확률 {pct(h['p_crit'])}%</div>
                    </div>
                    <div class="stat"><span class="grade"><span class="ico"><img src="{p_root}img/star.svg" alt=""></span><span class="num">{fmt_score(meta.get('total_score'))}</span><span class="txt">({meta.get('reviews_count') or 0:,})</span></span>{('<span class="si"><span class="dot"></span><span>' + E(stars_label(meta)) + '</span></span>') if stars_label(meta) else ''}{('<span class="si"><span class="dot"></span><span class="price">' + pl + '</span></span>') if pl else ''}</div>
                    {st_html}
                </div>
                {why_line(pid, h)}
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
    summary = (f'{CITY["ko"]} {col["name"]} 지역 호텔 {n}곳의 최근 1년 리뷰 {reviews:,}건을 분석했어요. '
               if col['kind'] == 'area' else
               f'{col["h1"].split(" — ")[0]}, 총 {n}곳의 최근 1년 리뷰 {reviews:,}건을 분석했어요. ')
    summary2 = (f'평균 실망 확률은 {avg_p}%로 {CITY["ko"]} 평균({city_p}%)보다 {cmp_word}. '
                f'가장 많이 지적된 항목은 {worst_first}이에요.')
    summary_full = summary + summary2

    # ── 2. 리스크 리포트 카드 ──
    dev_rows = []
    for c, d in stats['top_dev']:
        word = c.split(' ')[0]
        # §13 결론 먼저: 점수 차(…점 낮아요) 대신 평균 대비 문장 (d = 컬렉션 평균 위험도 - 50)
        dev_rows.append(f'<li class="hub-dev is-{"up" if d>0 else "down"}"><span class="hd-cat">{E(word)} 불만</span>'
                        f'<span class="hd-val">{E(ratio_text(50 + d))}</span></li>')
    dev_html = f'<ul class="hub-devs">{"".join(dev_rows)}</ul>' if dev_rows else \
               '<div class="hub-dev-none">카테고리별로 도시 평균과 큰 차이가 없어요</div>'
    p_cmp_cls = 'is-good' if avg_p <= city_p else 'is-bad'
    risk_card = f'''<div class="hub-risk">
        <div class="hub-risk-top">
            <div class="hr-block"><span class="hr-label">이 컬렉션 평균 실망 확률</span><span class="hr-num {p_cmp_cls}">{avg_p}%</span></div>
            <div class="hr-block"><span class="hr-label">{CITY['ko']} 평균</span><span class="hr-num">{city_p}%</span></div>
        </div>
        <div class="hub-risk-prof">
            <div class="hr-prof-tit">항목별로 보면</div>
            {dev_html}
        </div>
    </div>'''

    # ── 3. 랭킹 리스트 TOP 10~15 ──
    is_all = col['kind'] in ('capsule',)     # 전부 비교 컬렉션
    ranked_p = [p for p in pids if H[p]['ranked']]          # 순위 모수 = 최근 1년 리뷰 RANK_MIN 이상
    low_p = [p for p in pids if not H[p]['ranked']]
    top = ranked_p if is_all else ranked_p[:15]
    def chips_of(p):   # 대욕장 허브: 시설 칩 대신 실전정보 칩('대욕장 있음'·'사우나'), 근거 없으면 시설 칩 '온천·사우나'
        if col['kind'] != 'bath': return None
        return _bath_chips(p) or [AMENITY_LABEL['spa_bath']]
    rank_cards = '\n'.join(hub_card(p, hotels_meta[p], H[p], i + 1, depth, chips_of(p)) for i, p in enumerate(top))
    if col['kind'] == 'who':
        _g = _who_group(col['who'])
        rank_note = (f'{"·".join(SUB_PHRASE[s] for s in _g[2])} 불만이 모두 위험 등급이 아닌 곳을, 세 항목 불만이 적은 순으로 보여드려요 '
                     f'(최근 1년 리뷰 {RANK_MIN}개 미만·분석 준비 중 호텔 제외)')
    else:
        rank_note = (f'조건에 맞는 곳을 추천순으로 보여드려요 · {REC_SORT_DESC} (최근 1년 리뷰 {RANK_MIN}개 미만은 아래 따로)' if is_all else
                     f'추천순이에요 · {REC_SORT_DESC} (최근 1년 리뷰 {RANK_MIN}개 미만·분석 준비 중 호텔 제외)')
    search_link = f'<a class="hub-more" href="{"../" * depth}search{("?area=" + col["area"]) if col["kind"]=="area" else ""}">{CITY["ko"]} 호텔 전체 검색 →</a>'
    rank_block = (f'''<div class="hub-sect">
        <div class="hub-h2">추천 TOP {len(top)}</div>
        <div class="hub-sub">{rank_note}</div>
        <ul class="hub-list">{rank_cards}</ul>
        {search_link}
    </div>''' if top else '')
    # 리뷰 적은 호텔: 순위 없이 참고용 목록 (전부 비교 컬렉션이거나 순위 대상이 적을 때만 — 지역 TOP15엔 섞지 않음)
    if low_p and (is_all or len(ranked_p) < 5):
        low_cards = '\n'.join(hub_card(p, hotels_meta[p], H[p], '–', depth, chips_of(p)) for p in low_p)
        rank_block += f'''<div class="hub-sect">
        <div class="hub-h2">리뷰가 적은 호텔 {len(low_p)}곳</div>
        <div class="hub-sub">최근 1년 리뷰가 {RANK_MIN}개 미만이라 순위 없이 참고용으로 보여드려요</div>
        <ul class="hub-list">{low_cards}</ul>
        {'' if top else search_link}
    </div>'''

    # ── 4. 가격대별 베스트 (지역 컬렉션만) ──
    price_block = ''
    if col['kind'] == 'area':
        parts = []
        for code, label, lo, hi in PRICE_BANDS:
            band_pids = [p for p in pids if H[p]['ranked'] and hotels_meta[p].get('band') and hotels_meta[p]['band'][0] == code][:2]
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
                <div class="hub-sub">가격대마다 실망 확률이 가장 낮은 곳이에요{DSEP}<span class="seg">2인 1박 평일 가격 기준({CITY["price_seen"]} 확인)</span></div>
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
        <div class="hub-method"><span class="seg">실망 확률 = 실망 리뷰(심각한 문제·재방문 거부)의 최신성 가중 비율</span>{DSEP}<span class="seg">글 리뷰 {round(ai_reviews_total() / 10000)}만 건 AI 분석 · 기준 {CITY['data_asof']}</span></div>
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
                og_image=og_img, extra_head=ld) + site_header(depth, back=('../' * depth or './')) + f'''
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
    a1p = f'{CITY["ko"]} {name} 관련 호텔 {n}곳, 최근 1년 리뷰 {reviews:,}건을 분석했어요. 평균 실망 확률은 {avg_p}%예요.'
    faqs.append((q1, E(a1p), a1p))

    # (2) 컬렉션 고유 질문
    if kind == 'area':
        # 지역: ○○ vs 하카타 비교 (하카타 평균과 대조)
        other = 'hakata' if col['area'] != 'hakata' else 'tenjin'
        other_area = _area_by_code(other)
        other_ko = other_area['ko'] if other_area else '하카타'
        other_pids = [p for p in hotels_meta if p in H and H[p]['scored'] and H[p]['ranked'] and _in_area(hotels_meta[p], other_area)] if other_area else []
        other_p = pct(sum(H[p]['p_crit'] for p in other_pids) / len(other_pids)) if other_pids else None
        q2 = f'{name} vs {other_ko}, 어디에 잡을까요?'
        if other_p is not None:
            cmp_w = '더 낮아' if avg_p < other_p else ('더 높아' if avg_p > other_p else '비슷해')
            a2p = (f'{name} 평균 실망 확률은 {avg_p}%, {other_ko}{josa_eun(other_ko)} {other_p}%예요. '
                   + ('두 지역이 비슷한 수준이에요.' if avg_p == other_p else
                      f'{name}{josa_iga(name)} {cmp_w} {"안심할 만해요" if avg_p < other_p else "조금 더 주의가 필요해요"}.')
                   + ' 역·번화가 접근성도 함께 보고 고르세요.')
        else:
            a2p = f'{name} 평균 실망 확률은 {avg_p}%예요. 지역별 편차가 있으니 개별 호텔 리포트를 함께 확인하세요.'
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'who':
        g = _who_group(col['who'])
        names = [SUB_PHRASE[s] for s in g[2]]
        rare = [SUB_PHRASE[s] for s in g[2] if s in RARE_SUBS]
        q2 = f'{name} 여행이면 호텔에서 뭘 봐야 하나요?'
        a2p = (f'{", ".join(names)} 불만이 적은지가 특히 중요해요. 이 페이지는 세 항목이 모두 위험 등급이 아닌 곳만 골라 세 항목 불만이 적은 순으로 보여드려요.'
               + (f' {", ".join(rare)}{josa_eun(rare[-1])} 드물지만 치명적이라 최근 1년 심각 리뷰가 한 건이라도 있으면 뺐어요.' if rare else ''))
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'bath':
        q2 = f'{CITY["ko"]}에 대욕장·온천 있는 호텔은 몇 곳인가요?'
        a2p = (f'시설 정보나 투숙객 리뷰에서 대욕장·온천·사우나가 확인된 곳은 {n}곳이에요. '
               '리뷰에 \'대욕장 없음\'으로 언급된 호텔은 뺐어요. 이용 시간·요금은 상세 페이지 실전정보에서 확인하세요.')
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'capsule':
        typ = '캡슐호텔'
        q2 = f'{CITY["ko"]}에 {typ}은 총 몇 곳인가요?'
        _nlow = sum(1 for p in pids if not H[p]['ranked'])
        a2p = (f'캐치플로가 분석한 {CITY["ko"]} {typ}은 총 {n}곳이에요. 이 페이지에서 실망 확률 순으로 비교할 수 있어요'
               + (f' (최근 1년 리뷰 {RANK_MIN}개 미만 {_nlow}곳은 순위 없이 참고용).' if _nlow else '.'))
        faqs.append((q2, E(a2p), a2p))
    elif kind == 'value':
        # 질문이 '10만원 미만 + 실망 확률 최저'이므로 그 조건 그대로: 순위 모수(ranked) 안, 가격대 b1(평일 10만원 미만), p_crit 최소.
        # (예전: 추천순 1위를 b1·b2(20만원 미만) 통틀어 골라 '평일 약 15만원' 호텔이 답으로 나갔다)
        _b1 = [p for p in pids if H[p]['ranked'] and (hotels_meta[p].get('band') or ('',))[0] == 'b1']
        best_pid = min(_b1, key=lambda p: H[p]['p_crit']) if _b1 else None
        q2 = '10만원 미만에서 실망 확률이 가장 낮은 곳은?'
        if best_pid:
            a2p = f'현재 기준 {E(hotels_meta[best_pid]["title"])}가 실망 확률 {pct(H[best_pid]["p_crit"])}%로 가장 낮아요. 가격은 2인 1박 평일 기준이라 주말·성수기엔 더 비싸요.'
            faqs.append((q2, f'현재 기준 <b>{E(hotels_meta[best_pid]["title"])}</b>가 실망 확률 {pct(H[best_pid]["p_crit"])}%로 가장 낮아요. 가격은 2인 1박 평일 기준이라 주말·성수기엔 더 비싸요.', a2p))
        else:
            a2p = '가격대별 실망 확률이 가장 낮은 곳을 위 랭킹에서 확인하세요.'
            faqs.append((q2, E(a2p), a2p))
    elif kind == 'family':
        q2 = '가족여행 호텔은 뭘 봐야 하나요?'
        a2p = '아이와 함께라면 방음(옆방·복도 소음), 청결(머리카락·벌레·곰팡이), 위치(밤길·동네 분위기) 3가지가 특히 중요해요. 이 페이지는 세 항목이 모두 위험 등급이 아닌 곳만 골라 평균 점수가 낮은 순으로 보여드려요.'
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
        f'캐치플로는 {CITY["ko"]} 호텔 {n_live}곳의 공개 리뷰 {reviews_txt}을 모으고 그중 글 리뷰 {ai_reviews_total():,}건을 AI로 분석해, '
        '심각한 문제를 겪었거나 다시 안 가겠다고 한 리뷰의 비율을 <b>실망 확률</b>로 보여드립니다. '
        '별점에 묻힌 치명적인 단점을 예약 전에 미리 확인하실 수 있어요.')
    s2 = sect('실망 확률은 이렇게 계산해요',
        '<ul class="about-list">'
        '<li>심각한 문제(벌레·파손·안전 위협 등)를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰를 <b>실망 리뷰</b>로 세요</li>'
        '<li>최근 12개월 리뷰를 쓰고, 최근일수록 크게 반영해요 (6개월 지난 리뷰는 절반 비중)</li>'
        '<li>별점만 남긴 리뷰는 같은 별점 리뷰에서 실망이 나온 비율로 추정해 반영해요</li>'
        f'<li>리뷰가 적은 호텔은 몇 건에 크게 흔들리지 않도록 {CITY["ko"]} 평균 쪽으로 보정해요</li>'
        f'<li>최근 1년 리뷰(별점만 리뷰 포함)가 {MIN_REVIEWS}건 미만이면 신뢰도가 낮아 확률을 공개하지 않아요</li>'
        f'<li>최근 1년 리뷰가 {RANK_MIN}개 미만이면 \'리뷰 적음\'으로 표시하고 순위·추천에서 빼요. 리뷰가 적어도 위험 신호가 뚜렷하면 위험으로 알려 드려요</li>'
        '<li>순위는 정밀한 백분위 대신 \'상위 25% 이내\'처럼 넉넉한 구간으로, 80% 이상 확실할 때만 보여 드려요</li>'
        '<li>배지(양호·주의·위험)는 경계 근처에서 매주 바뀌지 않도록, 경계를 충분히 넘었을 때만 바꿔요</li>'
        '</ul>')
    s2b = sect('항목별 점수는 이렇게 매겨요',
        '<ul class="about-list">'
        '<li>청결·냄새·소음·객실·직원·위치 6개 항목을 불만의 양과 심각도로 점수화해요</li>'
        f'<li>{CITY["ko"]} 평균을 50으로 두고, 평균의 3배 이상이면 100이에요</li>'
        '<li>불만 리뷰가 5건 미만인 항목·소분류에는 위험 등급을 붙이지 않아요</li>'
        '<li>벌레, 곰팡이, 밤길·동네 분위기, 객실 보안처럼 드물지만 치명적인 문제는 점수 대신 리뷰 건수로 보여드려요</li>'
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
                description=desc, canonical=f'{BASE}/about') + site_header(0, back='./') + f'''
    <main id="container">
        <section id="about">
            <h1 class="about-h1">캐치플로 소개</h1>
            <p class="about-lead">공개된 투숙객 리뷰를 AI로 분석해, 예약 전에 알아야 할 위험을 알려드려요.</p>
            {s1}{s2}{s2b}{s3}{s4}{s5}
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


REDIRECTS = [('/best/pool', '/best/luxury'), ('/best/pool.html', '/best/luxury')]

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


def prev_badges():
    """지난 빌드의 배지(docs/data/compare.js의 b) — 배지 흔들림 방지용(scoring.assess). docs를 지우기 전에 읽는다. 없으면 {}."""
    f = os.path.join(OUT, 'data', 'compare.js')
    try:
        t = open(f, encoding='utf-8').read()
        return {pid: d.get('b') for pid, d in json.loads(t[t.index('=') + 1:].strip().rstrip(';')).items()}
    except Exception:
        return {}


def main():
    # UI 규칙 v2 게이트 (UI-STANDARDS §14): 토큰 밖 글자 크기·색, 배지 외 12px, PC 규칙 위치 등 위반 시 빌드 중단
    import lint_ui
    lint_ui.run(strict=True)
    city, H = compute(SRC, prev_badges=prev_badges())
    hotels_meta, quotes, stars, kr_stats, monthly, monthly_cat, faq_data, social_data = load()
    city_n, city_avg, city_cat_avg = city_averages(monthly, monthly_cat)
    # 추천순·수요 신호·비교 쌍 (RECOMMEND-PRICE-DESIGN §4 / HOME-CONCEPT-DESIGN) — 홈·검색·허브·상세 대안이 공용
    CITY['crit'] = city['crit']
    KRN.clear(); KRN.update(kr_n_map(kr_stats))
    REC.clear(); REC.update(rec_scores(H, hotels_meta, KRN))
    PAIRS[:] = resolve_pairs(hotels_meta, H)
    FAQ.clear(); FAQ.update(faq_data or {})

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
        open(full, 'w', encoding='utf-8').write(polish_breaks(s) if path.endswith('.html') else s)

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
    col_index = [(c['slug'], c['name']) for c, _ in built_cols]   # 상호링크·홈칩·상세칩 공용 (COLLECTIONS 순서 = 동네 → 동행 → 테마)

    W('index.html', build_index(hotels_meta, H, quotes, col_index))
    W('search.html', build_search(pct(city['crit'])))
    W('404.html', build_404())
    W('recent.html', build_recent(hotels_meta, H))   # F40: 개인화 페이지 — sitemap 제외
    W('about.html', build_about(hotels_meta, H, city))
    idx = build_search_index(hotels_meta, H, quotes)
    W('data/index.js', 'window.HOTELS=' + json.dumps(idx, ensure_ascii=False) + ';')
    W('data/search_index.js', 'window.CF_IDX=' + build_search_ac_index(hotels_meta, H) + ';')
    W('data/compare.js', 'window.CF_CMP=' + json.dumps(build_compare_data(hotels_meta, H, faq_data, monthly),
                                                       ensure_ascii=False, separators=(',', ':')) + ';')
    W('compare.html', build_compare())   # P5: 개인화 페이지 — sitemap 제외·noindex
    open(os.path.join(OUT, '.nojekyll'), 'w').close()

    # 상세 컬렉션 칩용: pid → [(slug, name), ...] (가장 가까운 지역 1 + 동행·테마 매칭, 최대 3)
    detail_col_map = defaultdict(list)
    for col, pids in built_cols:
        for p in pids:
            if col['kind'] == 'area':
                tag = area_tag(hotels_meta[p])
                if any(COL_BY_SLUG[s]['kind'] == 'area' for s, _ in detail_col_map[p]): continue   # 지역은 1개만
                if tag and _area_by_code(col['area'])['ko'].split('·')[0] != tag: continue        # 반경이 겹치면 가장 가까운 지역
            detail_col_map[p].append((col['slug'], col['name']))

    kr_share = kr_share_map(kr_stats, H)
    krrank = kr_rank_map(kr_share)
    kr_dist = kr_ratio_dist(kr_share)
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
    # 없어진 허브 → 가장 가까운 허브로 301 (Cloudflare 정적 자산 _redirects: 파일 조회보다 먼저 적용 —
    #  배포가 삭제된 파일을 남겨 둬도 옛 페이지가 뜨지 않게). best/pool(수영장)은 2026-10 허브 재구성(ecaf414)에서 제거 → 고급 숙소
    W('_redirects', ''.join(f'{a} {b} 301\n' for a, b in REDIRECTS))
    col_slugs = [c['slug'] for c, _ in built_cols]
    W('sitemap.xml', build_sitemap(written, col_slugs))
    scored = sum(1 for p in H if H[p]['scored'])
    sitemap_n = n + 3 + len(col_slugs)   # 홈·검색·about + 허브 + 상세
    print(f'OK: 상세 {n}p (점수 노출 {scored}, 분석 준비 중 {n - scored}) · sitemap {sitemap_n} URL · 도시평균 실망확률 {pct(city["crit"])}%')
    print(f'컬렉션 생성 {len(built_cols)}개: ' + ', '.join(f'{c["slug"]}({len(p)})' for c, p in built_cols))
    print(f'추천순 모수 {len(REC)}곳 · 비교 쌍 {len(PAIRS)}개 · 한국인 리뷰 최대 {max(list(KRN.values()) or [0])}건')
    if skipped_cols:
        print('컬렉션 스킵 ' + str(len(skipped_cols)) + '개: ' + ', '.join(f'{s}({r})' for s, r in skipped_cols))

if __name__ == '__main__':
    main()
