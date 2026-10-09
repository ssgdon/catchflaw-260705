# -*- coding: utf-8 -*-
"""추천순 수용 기준 점검 (RECOMMEND-PRICE-DESIGN §4.7). 빌드와 무관한 읽기 전용 스크립트.
   python scripts/check_rec.py  → 카페 24곳 중앙 순위 ≤60 · 상위 30 안 ≥7 · 위험 배지 ≤10% · 홈 TOP8에 한국인 리뷰 30건 미만 0곳"""
import json, os, re, sys, statistics
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import scoring
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data-src')
CAFE24 = [r'니시테츠 그랜드', r'크룸 하카타$', r'솔라리아', r'니시테츠 인 후쿠오카', r'오리엔탈 호텔 후쿠오카 하카타',
          r'익스프레스 후쿠오카 텐진', r'익스프레스 후쿠오카 나카스', r'라 스루', r'^호텔 몬토레 후쿠오카',
          r'리치몬드호텔 후쿠오카 텐진', r'니시도리', r'리치몬드호텔 하카타', r'종크 호텔 하카타', r'데아이바시',
          r'미쓰이 가든 호텔 후쿠오카 기온', r'미쓰이 가든 호텔 후쿠오카 나카스', r'컴포트 호텔 하카타', r'컴포트인',
          r'코믹앤북스', r'코코 호텔 하카타', r'코코 호텔 후쿠오카 텐진', r'칸데오', r'더 로얄 파크 호텔', r'캔버스']

def main():
    city, H = scoring.compute(SRC)
    meta = {h['place_id']: h for h in json.load(open(os.path.join(SRC, 'hotels.json'), encoding='utf-8')) if not h.get('rec_excluded')}
    krn = {}
    for r in json.load(open(os.path.join(SRC, 'kr_stats.json'), encoding='utf-8')):
        if r['period'] == '1y':
            try: krn[r['place_id']] = int(float(r.get('kr_n') or 0))
            except (TypeError, ValueError): pass
    rec = scoring.rec_scores(H, meta, krn)
    order = sorted(rec, key=lambda p: -rec[p])
    rank = {p: i + 1 for i, p in enumerate(order)}
    fav = []
    for rx in CAFE24:
        m = [p for p in rec if re.search(rx, meta[p]['title'])]
        if m: fav.append(m[0])
        else: print('  (매칭 없음)', rx)
    fr = sorted(rank[p] for p in fav)
    scored = [p for p in H if H[p]['scored'] and p in meta]
    danger = [p for p in scored if H[p]['badge'][0] == 'danger']
    home = [p for p in order if H[p]['badge'][0] != 'danger'][:8]
    low_home = [meta[p]['title'] for p in home if krn.get(p, 0) < 30]
    ok1, ok2 = statistics.median(fr) <= 60, sum(1 for x in fr if x <= 30) >= 7
    ok3, ok4 = len(danger) / len(scored) <= 0.10, not low_home
    print(f'모수 {len(rec)}곳 · 도시 평균 실망 확률 {city["crit"]*100:.2f}% · 위험 문턱 {scoring.DANGER_MULT}배')
    print(f'[{"OK" if ok1 else "FAIL"}] 카페 24곳 추천순 중앙 순위 {statistics.median(fr)} (기준 ≤60)')
    print(f'[{"OK" if ok2 else "FAIL"}] 카페 24곳 중 상위 30 안 {sum(1 for x in fr if x <= 30)}곳 (기준 ≥7)')
    print(f'[{"OK" if ok3 else "FAIL"}] 위험 배지 {len(danger)}/{len(scored)}곳 = {100*len(danger)/len(scored):.0f}% (기준 ≤10%)')
    print(f'[{"OK" if ok4 else "FAIL"}] 홈 TOP8에 한국인 리뷰 30건 미만: {low_home or "없음"}')
    print('홈 TOP8:', ' · '.join(f"{meta[p]['title']}(p{H[p]['p_crit']*100:.1f}·kr{krn.get(p,0)})" for p in home))
    return 0 if all((ok1, ok2, ok3, ok4)) else 1

if __name__ == '__main__':
    sys.exit(main())
