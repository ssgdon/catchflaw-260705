# -*- coding: utf-8 -*-
"""Supabase → data-src/*.json 스냅샷 추출
사용:  set SUPABASE_ACCESS_TOKEN=sbp_...  (또는 환경변수 등록)
       python scripts/export.py
이후:  python scripts/generate.py  →  docs/ 재생성
"""
import json, os, sys
import urllib.request

TOKEN = os.environ.get('SUPABASE_ACCESS_TOKEN')
PROJECT_REF = 'iixztaazwpjvxnpgegod'   # Nitpicker
ASOF = "timestamp '2026-03-30'"        # 최신성 가중 기준일 = 마지막 스크랩일. 재수집 시 갱신할 것!

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data-src')

NORM_MCAT = """
    case
      when a.category in ('동선 파괴자','불친절 레이더','시설 사기단','안전 그림자','오감 지옥','위생 경보') then a.category
      when a.sub_category in ('공간/노후화','공간/노hu화','냉난방/수압','네트워크/TV') then '시설 사기단'
      when a.sub_category in ('침구/바닥 청결','청소 서비스','해충/곰팡이') then '위생 경보'
      when a.sub_category in ('역/거점 접근성','지형적 난관','주변 편의성','허위 위치 정보','편의시설 전무') then '동선 파괴자'
      when a.sub_category in ('악취 역류','벽간/외부 소음','기기 소음','외부 소음','벽간 소음','오감 지옥') then '오감 지옥'
      when a.sub_category in ('응대 태도','처리 지연','사후 대처','소통 불가') then '불친절 레이더'
      when a.sub_category in ('주변 치안','보안 시설','사생활 보호','직원의 노크 없는 출입') then '안전 그림자'
      when a.category = '냉난방/수압' then '시설 사기단'
      else null
    end"""
NORM_SCAT = """
    case
      when a.sub_category = '공간/노hu화' then '공간/노후화'
      when a.sub_category in ('외부 소음','벽간 소음') then '벽간/외부 소음'
      when a.sub_category = '오감 지옥' then '악취 역류'
      when a.sub_category = '직원의 노크 없는 출입' then '사생활 보호'
      when a.sub_category = '편의시설 전무' then '주변 편의성'
      when coalesce(a.sub_category,'') = '' then null
      else a.sub_category
    end"""
BUCKET = f"""
  case
    when r.published_at_date >= {ASOF} - interval '90 days' then 'w10'
    when r.published_at_date >= {ASOF} - interval '180 days' then 'w07'
    when r.published_at_date >= {ASOF} - interval '365 days' then 'w04'
    else 'w015'
  end"""

QUERIES = {
    'hotels.json': """
        select place_id, title, sub_title, hotel_stars, total_score, reviews_count, city, address,
          price, latitude, longitude, website
        from hotels_new""",
    'images.json': """
        select place_id, raw_json->>'imageUrl' img0,
          raw_json->'imageUrls'->>1 img1, raw_json->'imageUrls'->>2 img2
        from hotels_new""",
    # 분석 대상 모수(denominator) = 텍스트 분석 리뷰 + 별점만 있는 리뷰.
    # 별점-only도 '평가'이므로 포함 → 텍스트 작성자 선택편향 교정, 200컷 정확화.
    'agg_denom.json': f"""
        select place_id, {BUCKET} bucket, count(*) n
        from reviews_new r where is_analyzed or stars is not null group by 1,2""",
    'agg_reviewlevel.json': f"""
        select r.place_id, {BUCKET} bucket, count(*) analyzed,
          count(*) filter (where exists (select 1 from reviews_analysis_new a where a.review_id=r.review_id and a.grade='심각')) has_crit,
          count(*) filter (where exists (select 1 from reviews_analysis_new a where a.review_id=r.review_id and a.grade in ('주의','심각'))) has_any
        from reviews_new r where r.is_analyzed group by 1,2""",
    'agg_findings.json': f"""
        with norm as (
          select a.review_id, a.place_id, {NORM_MCAT} cat,
            case a.grade when '심각' then 2 when '주의' then 1 else 0 end s
          from reviews_analysis_new a where a.grade in ('주의','심각')
        ),
        per_rc as (
          select review_id, place_id, cat, max(s) s from norm where cat is not null
          group by review_id, place_id, cat
        )
        select p.place_id, p.cat, p.s, {BUCKET} bucket, count(*) n
        from per_rc p join reviews_new r on r.review_id = p.review_id
        group by 1,2,3,4""",
    'findings_sub.json': f"""
        with norm as (
          select a.review_id, a.place_id, {NORM_MCAT} mcat, {NORM_SCAT} scat,
            case a.grade when '심각' then 2 when '주의' then 1 else 0 end s
          from reviews_analysis_new a where a.grade in ('주의','심각')
        ),
        per_rsc as (
          select review_id, place_id, mcat, scat, max(s) s
          from norm where mcat is not null and scat is not null
          group by review_id, place_id, mcat, scat
        )
        select p.place_id, p.mcat, p.scat, p.s, {BUCKET} bucket, count(*) n
        from per_rsc p join reviews_new r on r.review_id = p.review_id
        group by 1,2,3,4,5""",
    'stars.json': f"""
        select place_id, stars, count(*) n,
          count(*) filter (where published_at_date >= {ASOF} - interval '365 days') n_1y
        from reviews_new r where stars is not null group by 1,2""",
    'quotes.json': f"""
        with norm as (
          select a.review_id, a.place_id, a.grade, a.summary, a.quote, {NORM_MCAT} mcat, {NORM_SCAT} scat
          from reviews_analysis_new a
          where a.grade in ('주의','심각') and coalesce(a.quote,'') <> ''
        ),
        dedup as (
          select distinct on (review_id, place_id, mcat, scat) *
          from norm where mcat is not null
          order by review_id, place_id, mcat, scat, case grade when '심각' then 0 else 1 end
        ),
        ranked as (
          select d.*, r.published_at_date::date pub, r.reviewer_name, r.stars, r.review_origin,
            r.review_url, left(r.text_translated, 800) tfull, left(r.text_original, 800) ofull,
            row_number() over (partition by d.place_id, d.mcat
              order by case d.grade when '심각' then 0 else 1 end, r.published_at_date desc) rn
          from dedup d join reviews_new r on r.review_id = d.review_id
        )
        select place_id, mcat, scat, grade, left(summary, 80) summary, left(quote, 200) quote,
          pub, left(reviewer_name, 20) reviewer_name, stars, review_origin,
          review_url, tfull, ofull
        from ranked where rn <= 40""",
}

def run_sql(sql):
    req = urllib.request.Request(
        f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query',
        data=json.dumps({'query': sql}).encode('utf-8'),
        headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json',
                 'User-Agent': 'catchflaw-export/1.0'},
        method='POST')
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode('utf-8'))

def main():
    if not TOKEN:
        sys.exit('환경변수 SUPABASE_ACCESS_TOKEN 이 필요합니다 (sbp_...)')
    os.makedirs(OUT, exist_ok=True)
    for fname, sql in QUERIES.items():
        rows = run_sql(sql)
        with open(os.path.join(OUT, fname), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, default=str)
        print(f'{fname}: {len(rows)} rows')
    print('완료. 다음: python scripts/generate.py')

if __name__ == '__main__':
    main()
