# -*- coding: utf-8 -*-
"""캐치플로 점수 산식 v2 (UI-STANDARDS.md §5)
도시평균=50, 3배=100 구간선형 · k=20 보정 · 소분류 가드(불만 5건 미만 상한 65) · 분석 30건 미만 미노출
"""
import json, os
from collections import defaultdict

W = {'w10': 1.0, 'w07': 0.7, 'w04': 0.4, 'w015': 0.0}   # 결정 #5(2026-07-06): 12개월 초과 리뷰 점수 제외(×0)
K = 20                # 소표본 보정 의사표본 (도시평균 리뷰 20건)
GUARD_MIN = 5         # 소분류 불만 리뷰 최소 건수 (미만이면 상한 65)
GUARD_CAP = 65
MIN_REVIEWS = 30      # 점수 노출 최소 분석 리뷰 수

# CATS/SUBS/SUB_KEYWORDS = TAXONOMY-V4-AB-DESIGN §1 정본 (pipeline/prompt.py·pipeline/score.py 와 동기화 완료)
CATS = ['위생', '냄새', '소음', '시설', '불친절', '위치·안전']
SUBS = {
    '위생': ['침구/바닥 청결', '청소 상태', '해충/곰팡이'],
    '냄새': ['담배 냄새', '화장실·곰팡 악취'],
    '소음': ['내부 소음', '외부 소음'],
    '시설': ['공간 협소', '노후/고장', '냉난방/수압', '네트워크/TV'],
    '불친절': ['응대 태도', '체크인/처리 지연', '사후 대처'],
    '위치·안전': ['접근성', '주변 편의', '치안·안심'],
}
SUB_KEYWORDS = {
    '침구/바닥 청결': '얼룩 · 머리카락 · 먼지', '청소 상태': '청소 불량 · 쓰레기 방치', '해충/곰팡이': '벌레 · 빈대 · 곰팡이 발견',
    '담배 냄새': '금연실 담배 냄새 · 배인 냄새', '화장실·곰팡 악취': '하수구 · 꿉꿉함 · 곰팡내',
    '내부 소음': '옆방 소리 · 복도 · 기기음', '외부 소음': '도로 · 전철 · 유흥가 소음',
    '공간 협소': '비좁음 · 사진보다 작음', '노후/고장': '낡은 시설 · 설비 고장', '냉난방/수압': '냉난방 불량 · 수압 약함', '네트워크/TV': '와이파이 · TV 불량',
    '응대 태도': '불친절 · 무시 · 언어소통', '체크인/처리 지연': '체크인 지연 · 긴 대기', '사후 대처': '보상 거부 · 무대응',
    '접근성': '역에서 멀다 · 언덕 · 계단', '주변 편의': '편의점 · 식당 없음', '치안·안심': '밤길 · 보안 미비 · 프라이버시',
}
# 희소·고위험 소분류(점수 막대 대신 "신고 N건" 칩으로 렌더 — TAXONOMY-V4 §1·§3-c)
RARE_SUBS = {'해충/곰팡이', '치안·안심'}

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
        den[d['place_id']] += d['n'] * W[d['bucket']]
        den_n[d['place_id']] += d['n']
        if d['bucket'] != 'w015':          # 최근 1년(365일 이내) 카운트 = 표시·게이트 모수 (w015=365일 초과)
            den_1y[d['place_id']] += d['n']

    m_num = defaultdict(float); m_cnt = defaultdict(int)
    for f in findings_main:
        k = (f['place_id'], f['cat'])
        m_num[k] += f['n'] * W[f['bucket']] * f['s']
        m_cnt[k] += f['n']

    s_num = defaultdict(float); s_cnt = defaultdict(int); s_cnt_1y = defaultdict(int)
    for f in findings_sub:
        k = (f['place_id'], f['mcat'], f['scat'])
        s_num[k] += f['n'] * W[f['bucket']] * f['s']
        s_cnt[k] += f['n']
        if f['bucket'] != 'w015':          # F34: 최근 1년(365일 이내) finding 수 — 표시 전용(산식 불변)
            s_cnt_1y[k] += f['n']

    crit_w = defaultdict(float)
    for r in reviewlevel:
        crit_w[r['place_id']] += r['has_crit'] * W[r['bucket']]

    scored = [p for p in den if den_1y[p] >= MIN_REVIEWS]   # 노출 게이트 = 최근 1년 리뷰 ≥30 (전체기간 아님)
    tot_den = sum(den[p] for p in scored)

    city = {
        'crit': sum(crit_w[p] for p in scored) / tot_den,
        'cat': {c: sum(m_num[(p, c)] for p in scored) / tot_den for c in CATS},
        'sub': {(c, s): max(sum(s_num[(p, c, s)] for p in scored) / tot_den, 1e-6)
                for c in CATS for s in SUBS[c]},
    }

    hotels = {}
    for p in den:
        h = {'analyzed': den_1y[p], 'analyzed_all': den_n[p], 'scored': den_1y[p] >= MIN_REVIEWS}
        if h['scored']:
            pc = (crit_w[p] + K * city['crit']) / (den[p] + K)
            h['p_crit'] = pc
            h['badge'] = hotel_badge(pc, city['crit'])
            h['cats'] = {}
            for c in CATS:
                radj = (m_num[(p, c)] + K * city['cat'][c]) / (den[p] + K)
                sc = _score_from_ratio(radj / (city['cat'][c] or 1e-9))   # 0분모 방어(score.py와 동기화). 산식 불변(정상데이터 시 영향 없음)
                if m_cnt[(p, c)] < GUARD_MIN: sc = min(sc, GUARD_CAP)
                h['cats'][c] = {'score': sc, 'band': grade_band(sc), 'count': m_cnt[(p, c)], 'subs': {}}
                for s in SUBS[c]:
                    radj_s = (s_num[(p, c, s)] + K * city['sub'][(c, s)]) / (den[p] + K)
                    ss = _score_from_ratio(radj_s / city['sub'][(c, s)])
                    if s_cnt[(p, c, s)] < GUARD_MIN: ss = min(ss, GUARD_CAP)
                    h['cats'][c]['subs'][s] = {'score': ss, 'band': grade_band(ss),
                                               'count': s_cnt[(p, c, s)], 'count_1y': s_cnt_1y[(p, c, s)]}
        hotels[p] = h

    # 백분위 (같은 도시 내, 카테고리 점수 기준)
    for c in CATS:
        vals = sorted(hotels[p]['cats'][c]['score'] for p in scored)
        n = len(vals)
        for p in scored:
            v = hotels[p]['cats'][c]['score']
            below = sum(1 for x in vals if x < v)
            hotels[p]['cats'][c]['pctl_worse'] = round(100 * (n - below) / n)  # "하위 N%"

    return city, hotels
