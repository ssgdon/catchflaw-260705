# -*- coding: utf-8 -*-
"""캐치플로 점수 산식 v2 (UI-STANDARDS.md §5)
도시평균=50, 3배=100 구간선형 · k=20 보정 · 가드(최근 1년 불만 5건 미만 상한 65) · 분석 30건 미만 미노출
최신성 가중 = 반감기 180일 감쇠(1년 초과 ×0) · 별점만 리뷰는 같은 별점 분석 리뷰의 실망 비율로 대체 (2026-10 산식 개선)
"""
import json, os
from collections import defaultdict

W = {'w10': 1.0, 'w07': 0.7, 'w04': 0.4, 'w015': 0.0}   # 구 내보내기(계단 라벨) 호환용 — 12개월 초과 ×0(결정 #5)
HALF_LIFE = 180       # 최신성 가중: 180일마다 절반. 계단(1.0/0.7/0.4)은 리뷰가 90·180일 경계를 넘을 때
                      # 새 리뷰 없이도 숫자가 튀어(주간 표시값 변동 39곳→21곳) 감쇠로 교체 (2026-10 산식 개선)

def wt(bucket):
    """기간 라벨 → 가중치. 신 형식은 나이(일) 문자열 '0'~'365' → 0.5^(나이/180), 'w015'(1년 초과) → 0.
    구 형식(w10/w07/w04)은 예전 계단 가중치 그대로."""
    b = str(bucket)
    if b in W: return W[b]
    return 0.5 ** (int(b) / HALF_LIFE)

def in_3m(bucket):
    """최근 3달(90일) 이내인가 — 희소 칩 '최근 3달 심각' 판정용."""
    b = str(bucket)
    return b == 'w10' or (b.isdigit() and int(b) <= 90)
K = 20                # 소표본 보정 의사표본 (도시평균 리뷰 20건)
GUARD_MIN = 5         # 소분류 불만 리뷰 최소 건수 (미만이면 상한 65)
GUARD_CAP = 65
MIN_REVIEWS = 30      # 점수 노출 최소 분석 리뷰 수

# 분류 v5.7 (2026-10-09 확정) — 정본: pipeline/prompt_v5.py SUBS · 판정 기준서 pipeline/eval_v5/SPEC.md
CATS = ['청결', '냄새', '소음', '객실', '직원', '위치', '안전']
SUBS = {
    '청결': ['벌레', '곰팡이', '머리카락·얼룩', '청소 안 됨'],
    '냄새': ['담배 냄새', '악취'],
    '소음': ['실내 소음', '바깥 소음'],
    '객실': ['좁은 방', '침대·베개', '낡음·고장', '실내 온도', '온수·수압', '와이파이·TV'],
    '직원': ['불친절', '대기·지연', '대응 미흡'],
    '위치': ['역 거리', '주변 편의', '동네 분위기'],
    '안전': ['객실 보안'],
}
SUB_KEYWORDS = {
    '벌레': '바퀴 · 빈대 · 물림', '곰팡이': '욕실 · 벽 · 에어컨', '머리카락·얼룩': '머리카락 · 먼지 · 얼룩', '청소 안 됨': '쓰레기 · 수건 미교체 · 물때',
    '담배 냄새': '객실 · 복도 · 로비', '악취': '하수구 · 곰팡내 · 꿉꿉함',
    '실내 소음': '옆방 · 복도 · 기계음', '바깥 소음': '도로 · 전철 · 유흥가',
    '좁은 방': '비좁음 · 창문 없음', '침대·베개': '딱딱함 · 꺼짐 · 짧은 침대', '낡음·고장': '노후 · 파손 · 가전 고장',
    '실내 온도': '더움 · 추움 · 외풍', '온수·수압': '온수 · 수압 · 배수', '와이파이·TV': '와이파이 · TV · 콘센트',
    '불친절': '무례 · 무시 · 말 안 통함', '대기·지연': '체크인 줄 · 요청 지연', '대응 미흡': '해결 안 됨 · 보상 거부',
    '역 거리': '먼 거리 · 언덕 · 찾기 어려움', '주변 편의': '편의점 · 식당', '동네 분위기': '유흥가 · 호객 · 어두운 밤길',
    '객실 보안': '무단 입실 · 잠금 · 사생활 노출',
}
# 희소·고위험 소분류: 점수 막대 대신 "최근 1년 심각 N건" 칩으로 렌더
RARE_SUBS = {'벌레', '곰팡이', '동네 분위기', '객실 보안'}
# 점수(0~100)로 보여주는 대분류. 안전은 소분류가 칩 하나뿐이고 표본이 희소해 점수 없이 칩만 보여준다
SCORED_CATS = [c for c in CATS if c != '안전']
CHIP_ONLY_CATS = {'안전'}
# 실망 확률의 분자: True면 '심각 있음 OR (재방문·추천 거부 AND 불만 있음)' 리뷰, False면 '심각 있음'만 (v4 정의)
DISAPPOINT_INCLUDES_REFUSAL = True

def _score_from_ratio(ratio):
    if ratio <= 1:
        return max(0.0, 50.0 * ratio)
    return min(100.0, 50.0 + 25.0 * (ratio - 1))

def grade_band(score):
    if score >= 70: return 'danger'
    if score >= 45: return 'warning'
    return 'safe'

def hotel_badge(p_crit, city_crit):
    """호텔 등급 배지: 도시평균 1.5배↑=위험, 0.8배↓=양호"""
    if p_crit >= 1.5 * city_crit: return ('danger', '위험')
    if p_crit <= 0.8 * city_crit: return ('safe', '양호')
    return ('warning', '주의')

def compute(data_dir):
    J = lambda f: json.load(open(os.path.join(data_dir, f), encoding='utf-8'))
    denoms, findings_main, findings_sub, reviewlevel = (
        J('agg_denom.json'), J('agg_findings.json'), J('findings_sub.json'), J('agg_reviewlevel.json'))

    den = defaultdict(float); den_n = defaultdict(int); den_1y = defaultdict(int)
    for d in denoms:
        den[d['place_id']] += d['n'] * wt(d['bucket'])
        den_n[d['place_id']] += d['n']
        if d['bucket'] != 'w015':          # 최근 1년(365일 이내) 카운트 = 표시·게이트 모수 (w015=365일 초과)
            den_1y[d['place_id']] += d['n']

    # 건수는 전부 '최근 1년'(w015 제외) 기준 — 점수가 1년 넘은 리뷰를 ×0으로 버리므로(결정 #5),
    # 화면 건수·5건 가드도 같은 기간이어야 숫자끼리 맞는다 (2026-10 검토: 전체기간 건수 표기·가드 불일치 수정)
    m_num = defaultdict(float); m_cnt = defaultdict(int); m_cnt_1y = defaultdict(int); m_crit_1y = defaultdict(int)
    for f in findings_main:
        k = (f['place_id'], f['cat'])
        m_num[k] += f['n'] * wt(f['bucket']) * f['s']
        m_cnt[k] += f['n']
        if f['bucket'] != 'w015':
            m_cnt_1y[k] += f['n']
            if f['s'] == 2: m_crit_1y[k] += f['n']        # 이 카테고리에서 심각 판정된 리뷰 수

    s_num = defaultdict(float); s_cnt = defaultdict(int); s_cnt_1y = defaultdict(int)
    s_crit_1y = defaultdict(int); s_crit_3m = defaultdict(int)
    for f in findings_sub:
        k = (f['place_id'], f['mcat'], f['scat'])
        s_num[k] += f['n'] * wt(f['bucket']) * f['s']
        s_cnt[k] += f['n']
        if f['bucket'] != 'w015':          # F34: 최근 1년(365일 이내) finding 수
            s_cnt_1y[k] += f['n']
            if f['s'] == 2:
                s_crit_1y[k] += f['n']
                if in_3m(f['bucket']): s_crit_3m[k] += f['n']

    crit_w = defaultdict(float)
    text_1y = defaultdict(int); crit_1y = defaultdict(int); any_1y = defaultdict(int)
    for r in reviewlevel:
        # 실망 리뷰 수: v5 내보내기의 has_disappoint(심각 OR 거부+불만), 없으면(구 데이터) has_crit
        dis = r.get('has_disappoint', r['has_crit']) if DISAPPOINT_INCLUDES_REFUSAL else r['has_crit']
        crit_w[r['place_id']] += dis * wt(r['bucket'])
        if r['bucket'] != 'w015':          # 글이 있어 LLM이 읽은 리뷰(별점만 리뷰 제외)와 그중 실망·불만 리뷰 수
            text_1y[r['place_id']] += r['analyzed']
            crit_1y[r['place_id']] += dis
            any_1y[r['place_id']] += r.get('has_any', 0)

    # 별점만 리뷰 보정 (2026-10 산식 개선): 미분석 & 별점 있는 리뷰(대부분 글 없는 구글 리뷰)는 분모에만 들어가고
    # 분자는 0이었다 — 1점짜리도 '실망 아님'. 별점만 리뷰가 많은 호텔일수록 낮게 나와 출처 구성에 따라 불공정.
    # → 같은 별점 분석 리뷰의 실망 비율(도시 단위, star_crit.json)을 기대값으로 더한다. 파일이 없으면(구 데이터) 보정 없음.
    star_p = {}
    if os.path.exists(os.path.join(data_dir, 'star_crit.json')):
        for r in J('star_crit.json'):
            num = r.get('n_disappoint', r['n_crit']) if DISAPPOINT_INCLUDES_REFUSAL else r['n_crit']
            if r['n']: star_p[int(r['stars'])] = num / r['n']
    imp_1y = defaultdict(float)
    if star_p and os.path.exists(os.path.join(data_dir, 'agg_staronly.json')):
        for r in J('agg_staronly.json'):
            e = r['n'] * star_p.get(int(r['stars']), 0.0)
            crit_w[r['place_id']] += e * wt(r['bucket'])
            if r['bucket'] != 'w015': imp_1y[r['place_id']] += e   # 표시용: 최근 1년 별점만 리뷰의 추정 실망 건수

    scored = [p for p in den if den_1y[p] >= MIN_REVIEWS]   # 노출 게이트 = 최근 1년 리뷰 ≥30 (전체기간 아님)
    tot_den = sum(den[p] for p in scored)

    city = {
        'crit': sum(crit_w[p] for p in scored) / tot_den,
        'star_p': star_p,                  # 별점 → 실망 비율 (보정 근거, 없으면 빈 dict)
        'cat': {c: sum(m_num[(p, c)] for p in scored) / tot_den for c in CATS},
        'sub': {(c, s): max(sum(s_num[(p, c, s)] for p in scored) / tot_den, 1e-6)
                for c in CATS for s in SUBS[c]},
    }

    hotels = {}
    for p in den:
        # analyzed = 최근 1년 평가 리뷰(글 리뷰 + 별점만 리뷰) = 실망확률·비율의 분모. text_1y = 그중 글 리뷰(LLM 분석분)
        h = {'analyzed': den_1y[p], 'analyzed_all': den_n[p], 'scored': den_1y[p] >= MIN_REVIEWS,
             'text_1y': text_1y[p], 'star_only_1y': max(den_1y[p] - text_1y[p], 0),
             'crit_1y': crit_1y[p], 'any_1y': any_1y[p], 'imp_1y': imp_1y[p]}
        if h['scored']:
            pc = (crit_w[p] + K * city['crit']) / (den[p] + K)
            h['p_crit'] = pc
            h['badge'] = hotel_badge(pc, city['crit'])
            h['cats'] = {}
            for c in CATS:
                radj = (m_num[(p, c)] + K * city['cat'][c]) / (den[p] + K)
                sc = _score_from_ratio(radj / (city['cat'][c] or 1e-9))   # 0분모 방어(score.py와 동기화). 산식 불변(정상데이터 시 영향 없음)
                if m_cnt_1y[(p, c)] < GUARD_MIN: sc = min(sc, GUARD_CAP)   # 가드 = 최근 1년 불만 건수(점수에 반영되는 리뷰만)
                h['cats'][c] = {'score': sc, 'band': grade_band(sc), 'count': m_cnt[(p, c)],
                                'count_1y': m_cnt_1y[(p, c)], 'crit_1y': m_crit_1y[(p, c)], 'subs': {}}
                for s in SUBS[c]:
                    radj_s = (s_num[(p, c, s)] + K * city['sub'][(c, s)]) / (den[p] + K)
                    ss = _score_from_ratio(radj_s / city['sub'][(c, s)])
                    if s_cnt_1y[(p, c, s)] < GUARD_MIN: ss = min(ss, GUARD_CAP)
                    h['cats'][c]['subs'][s] = {'score': ss, 'band': grade_band(ss),
                                               'count': s_cnt[(p, c, s)], 'count_1y': s_cnt_1y[(p, c, s)],
                                               'crit_1y': s_crit_1y[(p, c, s)], 'crit_3m': s_crit_3m[(p, c, s)]}
        hotels[p] = h

    # 백분위 (같은 도시 내, 카테고리 점수 기준) — 칩 전용 대분류(안전)는 순위를 매기지 않는다
    for c in SCORED_CATS:
        vals = sorted(hotels[p]['cats'][c]['score'] for p in scored)
        n = len(vals)
        for p in scored:
            v = hotels[p]['cats'][c]['score']
            below = sum(1 for x in vals if x < v)
            hotels[p]['cats'][c]['pctl_worse'] = round(100 * (n - below) / n)  # "하위 N%"

    return city, hotels
