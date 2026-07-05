# -*- coding: utf-8 -*-
"""캐치플로 점수 산식 v2 (UI-STANDARDS.md §5)
도시평균=50, 3배=100 구간선형 · k=20 보정 · 소분류 가드(불만 5건 미만 상한 65) · 분석 30건 미만 미노출
"""
import json, os
from collections import defaultdict

W = {'w10': 1.0, 'w07': 0.7, 'w04': 0.4, 'w015': 0.15}
K = 20                # 소표본 보정 의사표본 (도시평균 리뷰 20건)
GUARD_MIN = 5         # 소분류 불만 리뷰 최소 건수 (미만이면 상한 65)
GUARD_CAP = 65
MIN_REVIEWS = 30      # 점수 노출 최소 분석 리뷰 수

CATS = ['위생 경보', '오감 지옥', '시설 사기단', '동선 파괴자', '불친절 레이더', '안전 그림자']
SUBS = {
    '위생 경보': ['침구/바닥 청결', '청소 서비스', '해충/곰팡이'],
    '오감 지옥': ['벽간/외부 소음', '악취 역류', '기기 소음'],
    '시설 사기단': ['공간/노후화', '냉난방/수압', '네트워크/TV'],
    '동선 파괴자': ['역/거점 접근성', '지형적 난관', '주변 편의성', '허위 위치 정보'],
    '불친절 레이더': ['응대 태도', '처리 지연', '사후 대처', '소통 불가'],
    '안전 그림자': ['보안 시설', '주변 치안', '사생활 보호'],
}
SUB_KEYWORDS = {
    '침구/바닥 청결': '얼룩 · 머리카락 · 먼지', '청소 서비스': '청소 불량 · 쓰레기 방치', '해충/곰팡이': '벌레 · 빈대 · 곰팡이',
    '벽간/외부 소음': '옆방 소리 · 도로 소음', '악취 역류': '하수구 · 담배 · 곰팡내', '기기 소음': '에어컨 · 냉장고 소음',
    '공간/노후화': '비좁음 · 낡은 시설', '냉난방/수압': '냉난방 불량 · 수압 약함', '네트워크/TV': '와이파이 · TV 불량',
    '역/거점 접근성': '역에서 멀다 · 찾기 어려움', '지형적 난관': '언덕 · 계단', '주변 편의성': '편의점 · 식당 없음', '허위 위치 정보': '위치 정보 불일치',
    '응대 태도': '불친절 · 무시', '처리 지연': '체크인 지연 · 대기', '사후 대처': '보상 거부 · 무대응', '소통 불가': '언어 소통 문제',
    '보안 시설': '도어락 · CCTV', '주변 치안': '밤길 · 우범지대', '사생활 보호': '방음 · 프라이버시',
}

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

    den = defaultdict(float); den_n = defaultdict(int)
    for d in denoms:
        den[d['place_id']] += d['n'] * W[d['bucket']]
        den_n[d['place_id']] += d['n']

    m_num = defaultdict(float); m_cnt = defaultdict(int)
    for f in findings_main:
        k = (f['place_id'], f['cat'])
        m_num[k] += f['n'] * W[f['bucket']] * f['s']
        m_cnt[k] += f['n']

    s_num = defaultdict(float); s_cnt = defaultdict(int)
    for f in findings_sub:
        k = (f['place_id'], f['mcat'], f['scat'])
        s_num[k] += f['n'] * W[f['bucket']] * f['s']
        s_cnt[k] += f['n']

    crit_w = defaultdict(float)
    for r in reviewlevel:
        crit_w[r['place_id']] += r['has_crit'] * W[r['bucket']]

    scored = [p for p in den if den_n[p] >= MIN_REVIEWS]
    tot_den = sum(den[p] for p in scored)

    city = {
        'crit': sum(crit_w[p] for p in scored) / tot_den,
        'cat': {c: sum(m_num[(p, c)] for p in scored) / tot_den for c in CATS},
        'sub': {(c, s): max(sum(s_num[(p, c, s)] for p in scored) / tot_den, 1e-6)
                for c in CATS for s in SUBS[c]},
    }

    hotels = {}
    for p in den:
        h = {'analyzed': den_n[p], 'scored': den_n[p] >= MIN_REVIEWS}
        if h['scored']:
            pc = (crit_w[p] + K * city['crit']) / (den[p] + K)
            h['p_crit'] = pc
            h['badge'] = hotel_badge(pc, city['crit'])
            h['cats'] = {}
            for c in CATS:
                radj = (m_num[(p, c)] + K * city['cat'][c]) / (den[p] + K)
                sc = _score_from_ratio(radj / city['cat'][c])
                if m_cnt[(p, c)] < GUARD_MIN: sc = min(sc, GUARD_CAP)
                h['cats'][c] = {'score': sc, 'band': grade_band(sc), 'count': m_cnt[(p, c)], 'subs': {}}
                for s in SUBS[c]:
                    radj_s = (s_num[(p, c, s)] + K * city['sub'][(c, s)]) / (den[p] + K)
                    ss = _score_from_ratio(radj_s / city['sub'][(c, s)])
                    if s_cnt[(p, c, s)] < GUARD_MIN: ss = min(ss, GUARD_CAP)
                    h['cats'][c]['subs'][s] = {'score': ss, 'band': grade_band(ss), 'count': s_cnt[(p, c, s)]}
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
