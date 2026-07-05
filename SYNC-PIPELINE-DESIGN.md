# 캐치플로 주간 동기화 & 인프라 설계서

v1 · 2026-07-05 작성 · 실행 담당: 내일 다른 PC의 Opus 세션 (이 문서가 유일한 지시서라고 가정하고 씀)

> 이 문서는 **설계서**다. 구현 순서는 §10 체크리스트를 따르고, 구현 전에 §11 결정 대기 항목의 답을 사용자에게 받는다.

---

## 0. 현재 상태 (2026-07-05 기준)

| 항목 | 상태 |
|---|---|
| 데이터 | Supabase "Nitpicker" (ref `iixztaazwpjvxnpgegod`). 후쿠오카 150개 호텔, 리뷰 48,935건(마지막 수집 2026-03-30), 분석 38,828건(gemini-2.5-flash) |
| 프론트 | 정적 사이트. 리포 `ssgdon/catchflaw-260705`, `scripts/export.py → fetch_images.py → generate.py` 로 `docs/` 생성, GitHub Pages 배포 |
| 점수 | v2 산식 (scripts/scoring.py): 도시평균=50·3배=100 구간선형, k=20, 소분류 가드, 30건 미만 미노출. 실망확률 = 심각 태그 리뷰의 최신성 가중 비율(실측) |
| 이미지 | 호텔 대표 1장만 자체호스팅(127/150). **리뷰 이미지 URL 40,976장 DB에 있으나 전부 만료형(gps-cs-s) → 사용 불가** |
| 피드백 | Supabase `mvp_feedbacks` (anon INSERT 전용 RLS) — 프론트에서 직접 저장, 작동 확인됨 |
| 공백 | **2026-03-30 이후 리뷰 없음** → 첫 캐치업 런 필요 (§4.4) |
| Apify 액터 | `nwua9Gu5YrADL7ZDj` = **compass/crawler-google-places** (장소 정보+이미지+리뷰 통합). 기존 hotels_new.raw_json 구조가 이 액터 출력과 일치 |

핵심 수치 (설계 판단 근거):
- 최근 90일 리뷰 5,844건 → **주간 신규 약 450건** (호텔당 ~3건/주)
- **분석 대상 모수 = 텍스트 분석 리뷰 + 별점-only 리뷰** (§7.0). 이 기준으로 200건 이상 호텔 = **104/150**(전체기간)·**71/150**(최근1년), 100건 이상 = 126/150. (텍스트만 세면 91/58/117 — 별점-only 제외 시 과소집계)
- 리뷰 중 이미지 보유 8,018건 / 이미지 총 40,976장 (전부 URL 만료 → §5.5 백필 판단 필요)

---

## 1. 목표 아키텍처 (권고안)

```
[Google Places API(공식)]──월1회 호텔 마스터 diff──┐
                                                  ▼
[Apify crawler-google-places]──주1회 리뷰/이미지──▶ [Oracle VM (무료티어)]
                                                    ├─ PostgreSQL  (원본+분석+점수)
                                                    ├─ 주간 배치 cron (weekly_sync)
                                                    ├─ 이미지 처리 (다운로드→WebP 리사이즈)
                                                    └─ (선택) FastAPI: 피드백/단축링크 해석
                                                  │
                        이미지 업로드               │ 사이트 생성(generate.py)
                                                  ▼
[Cloudflare R2 (이미지 CDN)] ◀──────┐   [Cloudflare Pages (정적 사이트)]
        img.catchflaw.xxx           └──── 고객 브라우저 ────▶
```

### 1.1 결정: 프론트는 **Cloudflare Pages 정적 유지** (오라클 VM 서빙보다 권고)

| | Cloudflare Pages (권고) | Oracle VM에서 직접 서빙 |
|---|---|---|
| 속도 | 글로벌 CDN, 한국 사용자에 빠름 | VM 리전(춘천/도쿄 등) 단일, CDN 없음 |
| 안정성 | VM이 죽어도 사이트는 살아있음 | VM = 단일 장애점 (무료티어 회수 리스크도 있음) |
| 운영 | git push 또는 wrangler 한 줄 배포 | nginx/도메인/인증서 직접 관리 |
| 비용 | 무료 (500빌드/월) | 무료지만 대역폭 10TB 한도 공유 |

→ **VM은 데이터 평면(DB·배치·이미지 처리) 전용, 서빙은 Cloudflare에 위임**한다. 사이트가 정적이라 가능한 구조이고, 주 1회 갱신 모델과 정확히 맞는다. GitHub Pages는 배포 실패가 잦았으므로(이번에 2회 겪음) **Cloudflare Pages로 이전**한다 (리포 연결, output dir = `docs`).

### 1.2 결정: 이미지 저장소는 **Cloudflare R2** (VM 디스크(나스 개념)보다 권고)

| | Cloudflare R2 (권고) | Oracle VM 블록볼륨 + nginx |
|---|---|---|
| 무료 한도 | 10GB 저장, **egress 무료** | 200GB (VM 부트볼륨 포함) |
| 예상 사용량 | 초기 ~3GB, 연 +2GB 수준 → 수년간 무료 | 여유 충분 |
| 서빙 | 자체 CDN + 커스텀 도메인, 유실 없음 | nginx 설정 + Cloudflare 프록시 캐시 필요 |
| 유실 리스크 | 사실상 없음 | VM 회수/디스크 장애 시 유실 (백업 필요) |

→ R2 버킷 1개 (`catchflaw-img`), 공개 커스텀 도메인 연결. **VM 디스크에는 원본 백업만 보관**(rsync)해서 이중화. 만약 R2 계정 만들기 싫으면 VM+nginx+Cloudflare 프록시(캐시 TTL 30일)로 대체 가능 — §11 결정#2.

### 1.3 Oracle VM 구성 (무료티어)

- **Ampere A1** (ARM, 최대 4 OCPU/24GB RAM/200GB) 권장 — 하나로 충분. 이미 만들어 둔 VM 사용.
- 설치: PostgreSQL 16, Python 3.11+(venv), nginx(선택), cron. 방화벽: 5432는 외부 차단(로컬만), SSH만 오픈.
- DB 백업: 매일 `pg_dump` → R2 업로드 (7일 보관).

### 1.4 피드백 저장은 당분간 Supabase 유지

`mvp_feedbacks`는 이미 작동 중이고 프론트가 정적이라, DB 이관 후에도 **피드백만 Supabase 무료 프로젝트에 남겨두는 게 가장 단순**하다. VM에 FastAPI를 올리는 시점(카카오 로그인, 단축링크 해석 등 동적 기능 필요 시)에 함께 이관한다.

---

## 2. DB 스키마 (Oracle PostgreSQL) — DDL 초안

원칙: place_id를 전역 키로, "정상은 저장하지 않는다", 모든 분석 행에 run_id, 이미지·잡로그 테이블 신설.

```sql
create table cities (
  code        varchar primary key,          -- 'fukuoka'
  name_ko     varchar not null,             -- '후쿠오카'
  name_en     varchar,
  center_lat  numeric, center_lng numeric,
  is_active   boolean default true
);

create table hotels (
  place_id    varchar primary key,          -- 구글 place_id (전역 키)
  city_code   varchar references cities(code),
  title       text not null,
  sub_title   text,                         -- 현지어 표기
  hotel_stars varchar,
  total_score numeric,                      -- 구글 평점 (마스터 갱신 시 업데이트)
  reviews_count int,                        -- 구글 리뷰 총수
  address     text,
  latitude    numeric, longitude numeric,
  price_raw   varchar,                      -- 'US$98' 원문
  price_krw   int,                          -- 환산 (배치에서 계산)
  website     text, phone varchar,
  status      varchar default 'active',     -- active | new | closed | delisted
  first_seen_at timestamptz default now(),
  last_scraped_at timestamptz,              -- 마지막 리뷰 스크랩 완료 시각
  raw_json    jsonb
);
create index on hotels (city_code, status);

create table hotel_images (
  place_id    varchar references hotels(place_id),
  seq         smallint,                     -- 0 = 대표
  storage_key text not null,                -- 'hotels/{place_id}/{seq}.webp'
  width int, height int, bytes int,
  source_url  text,                         -- 다운로드 원본 (만료돼도 기록용)
  fetched_at  timestamptz default now(),
  primary key (place_id, seq)
);

create table reviews (
  review_id   varchar primary key,
  place_id    varchar references hotels(place_id),
  reviewer_name varchar, reviewer_id varchar,
  stars       int,                          -- 구글 외 출처는 null
  text_original text, text_translated text,
  original_language varchar,
  published_at timestamptz,
  review_url  text,
  review_origin varchar,                    -- Google | Trip.com | ...
  likes_count int,
  image_urls  jsonb,                        -- 스크랩 시점 원본 URL (만료성 — 즉시 다운로드용)
  is_analyzed boolean default false,        -- 텍스트가 있어 LLM을 태운 리뷰만 true
  is_evaluation boolean generated always as (is_analyzed or stars is not null) stored,
                                            -- 분석 대상 모수 플래그: 텍스트분석 OR 별점만 있어도 '평가' (§7.0)
  analysis_run_id bigint,
  scraped_at  timestamptz default now()
);
create index on reviews (place_id, published_at desc);
create index on reviews (is_analyzed) where not is_analyzed;
create index on reviews (place_id) where is_evaluation;   -- 모수 카운트/점수 계산용

create table review_images (
  review_id   varchar references reviews(review_id),
  seq         smallint,
  storage_key text not null,                -- 'reviews/{review_id}/{seq}.webp'
  width int, height int, bytes int,
  fetched_at  timestamptz default now(),
  primary key (review_id, seq)
);

create table analysis_runs (
  run_id      bigint generated always as identity primary key,
  model       varchar not null,             -- 'gemini-2.5-flash'
  prompt_version varchar not null,          -- 'v3-2026-07' (프롬프트 바뀌면 반드시 올림)
  started_at timestamptz, completed_at timestamptz,
  total_reviews int, ok_reviews int,
  prompt_tokens bigint, output_tokens bigint, cost_usd numeric
);

create table review_findings (               -- 주의/심각만 저장. "행 없음 = 전항목 정상"
  id          bigint generated always as identity primary key,
  review_id   varchar references reviews(review_id),
  category    varchar not null,             -- 대분류 6 고정 (check 제약 권장)
  sub_category varchar not null,            -- 소분류 20 고정
  grade       varchar not null check (grade in ('주의','심각')),
  summary     text, quote text,             -- quote 안 **강조** 마크업 유지
  run_id      bigint references analysis_runs(run_id)
);
create index on review_findings (review_id);

create table sync_jobs (                     -- 주간 배치 감사 로그
  job_id      bigint generated always as identity primary key,
  job_type    varchar,                      -- weekly | catchup | backfill_images | master_refresh
  started_at timestamptz, completed_at timestamptz,
  status      varchar,                      -- running | ok | failed
  stats       jsonb,                        -- {new_reviews: 450, new_hotels: 1, images: 320, ...}
  error       text
);

-- 파생 (배치에서 재계산, 프론트 생성기 입력)
create table hotel_scores (
  place_id varchar, category varchar, score numeric, band varchar,
  complaint_n int, computed_at timestamptz, primary key (place_id, category)
);
create table city_baselines (
  city_code varchar, category varchar, r_avg numeric, frozen_at timestamptz,
  primary key (city_code, category)          -- 월 1회 동결 갱신
);
```

### 2.1 Supabase → 신 스키마 매핑

| Supabase | → | Oracle | 비고 |
|---|---|---|---|
| hotels_new | → | hotels | 컬럼 정리, price_krw는 배치 계산, status='active' |
| reviews_new | → | reviews | published_at_date→published_at, review_image_urls→image_urls |
| reviews_analysis_new (주의/심각, quote 있음) | → | review_findings | **정상 68,242행 버림**. category 빈 값 6,583행은 소분류→대분류 매핑으로 복원(scripts/export.py의 NORM_MCAT CASE 그대로 사용), 오타 '공간/노hu화'→'공간/노후화', '외부 소음'/'벽간 소음'→'벽간/외부 소음' 등 표준화 |
| analysis_cost_log | → | analysis_runs | model, 비용 이관, prompt_version='legacy' |
| mvp_feedbacks | — | (Supabase에 유지) | §1.4 |
| 도쿄 구테이블 4종 | — | 이관 안 함 | 필요 시 나중에 재분석 (약 $21) |

마이그레이션 방법: Supabase 대시보드 연결 문자열(psql)로 `\copy` CSV 추출 → VM에서 `\copy` 적재. 검증 쿼리: 행 수 일치 + `select count(*) from review_findings where grade='심각'` = 6,945 - (정상행 제외분 검산).

---

## 3. 호텔 마스터 갱신 (월 1회) — Google Places API 공식

목적: **폐업 감지 + 신규 호텔 편입**. 리뷰 내용은 여기서 안 가져온다(공식 API는 리뷰 5개 제한이라 스크래핑 대체 불가 — 리뷰는 계속 Apify).

### 3.1 방법: Places API (New) — Nearby Search 그리드

- 후쿠오카 도심을 **반경 2km 원 × 약 12셀 그리드**로 커버 (하카타·텐진·나카스 중심 + 외곽 4셀). Nearby Search는 호출당 최대 20결과 × 3페이지 = 60개 → 셀당 60개 상한 때문에 그리드 필수.
- 요청: `includedTypes=["lodging"]`, `locationRestriction={circle}`, **FieldMask는 최소로**: `places.id,places.displayName,places.businessStatus,places.location,places.userRatingCount,places.rating` (Essentials/Pro SKU 하위 유지 → 비용 최소).
- 월 1회 × ~36콜(12셀×3페이지) → Google 무료 크레딧 한도 내 (사실상 $0).

### 3.2 diff 로직

```
API 결과 place_id 집합 = G, DB hotels(city='fukuoka') 집합 = D
1) G - D (신규): userRatingCount >= 100 이면 hotels에 status='new' 삽입 → §4.3 신규 스크랩 대상
2) D ∩ G: businessStatus 갱신. CLOSED_PERMANENTLY → status='closed' (사이트에서 제외, 데이터는 보존)
3) D - G (API에서 안 잡힘): 즉시 삭제하지 말 것. 2회 연속 미출현 시 status='delisted' 후 수동 확인
```

- 편입 기준(초기값): `lodging` + 후쿠오카 시 경계 내 + **구글 리뷰 100개 이상** (너무 낮추면 게스트하우스 수백 개가 들어옴 — 리스트 품질 관리).
- 준비물: Google Cloud 프로젝트 + Places API(New) 활성화 + API 키 (결제수단 등록 필요하지만 무료 한도로 충분).

---

## 4. 주간 리뷰 증분 스크래핑 (Apify)

액터: **compass/crawler-google-places** (`nwua9Gu5YrADL7ZDj`) — 확인 완료. 호텔 정보+이미지+리뷰를 한 액터로 처리한다.
(참고: 리뷰만 필요하면 compass/Google-Maps-Reviews-Scraper 라는 리뷰 전용 액터도 있음 — 요금 비교 후 선택 가능. 아래 설계는 통합 액터 기준.)

> ⚠️ 구현 전 콘솔에서 input 스키마 최신값 확인할 것. 아래 필드명은 2026-07 기준이며 액터가 자주 업데이트된다.

### 4.1 실행 그룹 A — 기존 호텔 주간 증분

```jsonc
{
  "startUrls": [ {"url": "https://www.google.com/maps/place/?q=place_id:ChIJ..."}, ... ],  // active 호텔 전체
  "maxReviews": 100,                    // 주간 신규는 호텔당 ~3건, 100이면 4주 밀려도 커버
  "reviewsSort": "newest",
  "reviewsStartDate": "{지난 배치 성공일 - 3일}",   // 겹침 버퍼 3일 → 중복은 review_id upsert로 해소
  "maxImages": 0,                       // 이미지는 그룹 C에서만 (비용 절약)
  "language": "ko",
  "scrapeReviewsPersonalData": true     // reviewer_name 등 (현행과 동일)
}
```

- **reviewsStartDate는 run 단위 설정만 가능**하므로 호텔별 커서 대신 "지난 배치일 − 3일"을 전체에 적용한다. 남는 중복은 `review_id` PK upsert(`ON CONFLICT DO UPDATE`)로 무해화. `hotels.last_scraped_at` 갱신.
- 부수 효과: 이 액터는 장소 메타(평점·리뷰수·가격)도 함께 반환 → hotels의 total_score/reviews_count/price_raw를 매주 자동 갱신.

### 4.2 인제스트 (VM 파이썬)

1. Apify Run API로 실행 → run 폴링 → dataset items JSON 다운로드
2. reviews upsert (review_id PK). `image_urls` 필드 저장
3. **인제스트 직후 이미지 다운로드 큐에 즉시 투입** (§5 — URL이 만료형이라 지연 금지)
4. sync_jobs에 신규/갱신 건수 기록

### 4.3 실행 그룹 B — 신규 호텔 초도 스크랩 (사용자 정책 반영)

- 대상: `status='new'` 호텔
- **기간 최대 1년** (`reviewsStartDate = now − 365d`), **newest 정렬**, **maxReviews = 300**
- `maxImages = 10` (호텔 이미지 §5.2와 함께)
- 완료 후 `status='active'`

### 4.4 첫 캐치업 런 (3월 공백 해소 — 이관 직후 1회)

- 그룹 A 변형: `reviewsStartDate = "2026-03-27"` (마지막 수집 3/30 − 3일), `maxReviews = 300` (3개월치 밀림 → 호텔당 ~40건 예상, 인기 호텔 여유)
- 예상 신규 ~6,000건 → LLM 분석 1회분 ~$4

### 4.5 비용 추정 (Apify)

- compass 액터는 결과량 과금(place + 리뷰 단가). 주간: 150 place + ~450 리뷰 → **월 $5~15 수준** 예상. 첫 캐치업/이미지 백필은 1회성 $10~20. (정확 단가는 콘솔 요금표 확인 — 크레딧 $5/월 무료 포함)

---

## 5. 이미지 파이프라인 (유실 방지가 목적)

### 5.0 대원칙

**구글 이미지 URL은 만료된다.** 현재 DB의 리뷰 이미지 URL 40,976장이 전부 만료형(gps-cs-s)임을 확인했다. 호텔 이미지도 `/p/` 타입만 준영구이고 나머지는 만료된다. 따라서:

> **모든 이미지는 스크랩 인제스트 직후(같은 배치 안에서) 다운로드하여 자체 스토리지에 저장한다. URL을 믿지 않는다.**

### 5.1 저장 규격 (필요한 크기만, 딱 맞게)

| 용도 | 규격 | 포맷 | 예상 크기 |
|---|---|---|---|
| 호텔 갤러리 (스와이프) | 긴 변 960px | WebP q75 | ~70KB |
| 호텔 카드 썸네일 | 폭 480px | WebP q72 | ~25KB |
| 리뷰 이미지 (스와이프 뷰) | 긴 변 720px | WebP q72 | ~50KB |
| 리뷰 썸네일 (카드 내 스트립) | 240px 정방 크롭 | WebP q70 | ~10KB |

- 원본은 보관하지 않는다 (용량 관리). 저장 키: `hotels/{place_id}/{seq}.webp`, `hotels/{place_id}/{seq}_s.webp`(썸네일), `reviews/{review_id}/{seq}.webp`, `..._s.webp`
- 처리: Python Pillow (`Image.thumbnail` + `save(format='WEBP')`), 병렬 8쓰레드, 실패 3회 재시도 후 스킵 기록
- 용량 추정: 호텔 150×10장×2규격 ≈ 300MB, 리뷰 이미지 신규분 연간 ~20,000장×2규격 ≈ 1.2GB → **R2 무료 10GB로 수년 여유**

### 5.2 호텔 이미지 7~10장 (현재 1장 → 확대)

- 그룹 B/C 스크랩에서 `maxImages: 10` 설정 → 액터 출력 imageUrls에서 상위 10장 (스크린샷/메뉴 등 노이즈는 imageCategories로 필터 가능하면 필터)
- seq=0을 대표로, 프론트 상세 visual을 **Swiper 갤러리**로 교체 (기존 swiper.js 재사용, 페이지 dot 표시)

### 5.3 리뷰 이미지

- 그룹 A 인제스트 시 `image_urls`가 있는 리뷰 → 즉시 다운로드 → review_images 기록
- 프론트: 리뷰 시트 카드에 **이미지 스트립(가로 스와이프)** 추가 — 썸네일 나열, 탭하면 720px 라이트박스. "사진 리뷰"는 신뢰도 핵심이므로 심각/주의 리뷰에서 놓치지 않고 노출

### 5.4 보완 서브로직 (백필) — 사용자 요청 반영

주간 배치 마지막 단계에서 자동 추출·실행:

```sql
-- (a) 호텔 이미지 부족 (7장 미만) → Apify 그룹 C 대상
select place_id from hotels h where status='active'
  and (select count(*) from hotel_images i where i.place_id=h.place_id) < 7;
```
그룹 C input: 해당 place_id들의 startUrls + `maxReviews: 0, maxImages: 10` → 다운로드/최적화/업로드 → hotel_images upsert. **hotel id(place_id)+구글 id 기반 재스크랩으로 빈 사진을 채우는 로직이 이것.**

```sql
-- (b) 리뷰 이미지 미저장 (URL은 있는데 다운로드 안 된 것)
select review_id from reviews r where jsonb_array_length(image_urls) > 0
  and not exists (select 1 from review_images ri where ri.review_id=r.review_id);
```
→ URL이 아직 살아있으면 다운로드. **기존 8,018건은 URL이 이미 만료라 다운로드 불가** → 이 리뷰들의 이미지를 살리려면 해당 호텔 리뷰 재스크랩이 필요한데 비용 대비 가치 낮음. **권고: 기존분은 포기하고 신규분부터 완벽 저장** (§11 결정#4).

### 5.5 기존 호텔 대표이미지 23개 공백

이미지 없는 23개 호텔(영구 URL 부재 20 + 404 3)은 그룹 C 첫 실행에서 자동으로 채워진다 (백필 (a) 조건에 걸림).

---

## 6. LLM 분석 루프

### 6.1 흐름

```
큐 = select * from reviews where not is_analyzed and text_original <> '' order by published_at desc
→ 20~30건씩 배치로 프롬프트 구성 → LLM 호출 → 파싱/검증 → review_findings 저장(주의/심각만)
→ reviews.is_analyzed=true, analysis_run_id 기록 → analysis_runs에 토큰/비용 집계
```

### 6.2 프롬프트 (내일 기존 PC의 프롬프트+파이썬 소스로 재구성)

고정할 것 (기존 데이터와 호환 필수):
- 태그 스키마: **대분류 6** (위생 경보/오감 지옥/시설 사기단/동선 파괴자/불친절 레이더/안전 그림자) × **소분류 20** (scripts/scoring.py SUBS 딕셔너리가 정본) — 신규 소분류 임의 생성 금지, 반드시 목록 강제
- grade: 정상/주의/심각 3단계. **출력·저장은 주의/심각만** ("전항목 정상 = 출력 없음" 규약)
- 출력 필드: category, sub_category, grade, summary(한 줄), quote(원문 발췌, 핵심에 `**강조**`)
- 구조화 출력(JSON mode/function calling) 사용, 파싱 실패 시 1회 재시도

바꿀 것:
- `prompt_version` 명시 (예: v3-2026-07). 프롬프트를 고치면 버전을 올리고 analysis_runs에 기록 — 도시 baseline은 같은 버전끼리만 비교
- **프롬프트 캐싱**: 시스템 프롬프트(태그 정의+규칙, ~2K 토큰)를 앞에 고정하고 리뷰 텍스트만 가변 → Gemini implicit caching / Claude prompt caching 모두 적용됨. 배치 안에서 호출 간격을 붙여 캐시 히트 유지

### 6.3 모델과 비용

- 기본: **gemini-2.5-flash 유지** (실적 단가 리뷰당 ~$0.0007, 태깅 품질 검증됨). 프롬프트 버전 올리는 김에 gemini 최신 flash 또는 claude-haiku-4-5와 샘플 200건 비교 후 선택해도 됨 — 단 모델을 바꾸면 baseline 세대 분리 필요하니 **첫 이관에서는 기존 모델 유지 권장**
- 주간 ~450건 → **주 $0.3~0.5**. 캐치업 6,000건 → 1회 $4~5

---

## 7. 점수 재계산 & 노출 정책 (변경 3건)

### 7.0 분석 대상 모수 = 텍스트 분석 리뷰 + 별점-only 리뷰 (사용자 정책 · 적용 완료)

**핵심 원칙**: 별점만 있고 텍스트가 없는 리뷰도 "평가"다. 분석 대상 모수(denominator)에 포함한다.

- **이유**: 텍스트를 쓰는 사람은 불만을 남길 확률이 높다(선택편향). 별점-only 리뷰(=문제 언급 안 한 투숙객)를 분모에서 빼면 실망확률이 과대평가된다. 포함하면 "전체 투숙객 중 심각 문제를 언급한 비율"이 되어 더 정확하다.
- **모수 정의**: `is_analyzed(텍스트 분석) OR stars IS NOT NULL(별점 있음)` = `is_evaluation`. 후쿠오카 기준 별점-only 10,097건(호텔당 평균 67건)이 새로 포함됨.
- **분자는 그대로**: 심각/주의 findings는 텍스트 리뷰에서만 나온다. 별점-only는 분모에만 들어가는 "무언급" 데이터.
- **적용 효과 (실측)**: 도시평균 실망확률 12% → **9.5%**, 개별 호텔 예) 28% → 24%. 카테고리 위험도는 도시평균 대비 상대값이라 순위·분포 거의 안 변함(중앙값 42~48). **200 컷 통과 91→104개**로 정확해짐.
- **구현**: `reviews.is_evaluation` 컬럼 + 점수 denominator를 이 플래그로 카운트. (현행 MVP에는 `export.py`의 agg_denom 쿼리를 `where is_analyzed or stars is not null`로 이미 반영 완료.)
- **표시 라벨**: "분석 리뷰 N건" = 이 모수 기준(텍스트+별점). 별점-only 리뷰 자체는 리뷰 목록에 노출하지 않되(인용문 없음) 모수에는 포함.

### 7.1 "최근 1년 리뷰만" (사용자 정책)

- **표시**: 리뷰 인용·건수·별점분포 전부 최근 1년(배치 기준일 − 365d)만 사용
- **점수 계산도 1년 컷 권고** (표시와 계산이 다르면 고객 신뢰 문제): 가중치 버킷 재정의 → 3개월 내 ×1.0 / 3~6개월 ×0.7 / 6~12개월 ×0.4 / **12개월 초과 ×0 (제외)**. 기존 0.15 → 0. §11 결정#3
- 기준일 = 배치 실행일 (매주 자동 갱신 — "옛 불만 자연 감쇠"가 매주 일어남)

### 7.2 노출 최소 기준 200건 (사용자 정책 — 영향 큼, 결정 필요)

§7.0 모수(텍스트+별점) 기준 분석 200건 이상 호텔 = **104/150**(전체기간), 최근1년 컷 적용 시 **71/150**. (텍스트만 세던 옛 방식은 91/58 — 별점-only 포함으로 컷이 정확해짐.)

권고안 — **3단계 노출**:

| 단계 | 조건 (모수 = 텍스트+별점) | 노출 |
|---|---|---|
| 정식 | 200건 이상 | 등급 배지 + 실망확률 + 전체 분석 (현행 UI 그대로) |
| 참고 | 30~199건 | 점수는 보여주되 "분석 {n}건 기준 · 참고용" 라벨, 큐레이션/추천에서 제외 |
| 수집중 | 30건 미만 | "리뷰 수집중" (현행) |

이렇게 하면 후쿠오카 커버리지(150개)를 유지하면서 "믿을 만한 점수"와 "참고 점수"를 구분한다. 사용자가 200 하드컷을 원하면 §11 결정#1에서 선택. 캐치업 스크랩(300건 상한)이 돌면 200+ 호텔이 더 늘어난다.

### 7.3 재계산 규칙 (기존 유지)

- v2 산식 그대로 (scripts/scoring.py 이식). city_baselines는 **월 1회 동결**(주간 점수 흔들림 방지), 계산 모수는 정식(200+) 호텔만
- 재계산은 전량 배치 (SQL/파이썬 수 초) — 증분 계산 설계 불필요

---

## 8. 주간 배치 오케스트레이션 (VM cron)

```
# crontab (KST 기준, 월요일 03:00 — 주말 리뷰까지 포함해 월요일 아침 갱신)
0 3 * * 1  /opt/catchflaw/weekly_sync.sh >> /var/log/catchflaw/sync.log 2>&1
0 4 1 * *  /opt/catchflaw/monthly_master.sh   # 월 1회: 호텔 마스터 갱신 + baseline 동결
```

`weekly_sync.sh` 단계 (각 단계 idempotent — 중간 실패 시 같은 명령 재실행으로 이어가기):

```
1. scrape    : Apify 그룹 A 실행·폴링 → reviews upsert          (§4.1~4.2)
2. new_hotels: status='new' 있으면 그룹 B 실행                    (§4.3)
3. images    : 신규 image_urls 다운로드→WebP→R2 업로드            (§5)
4. backfill  : 호텔 이미지 <7 대상 그룹 C (주 1회 최대 20곳 제한)  (§5.4)
5. analyze   : LLM 분석 루프 (미분석 소진까지)                     (§6)
6. score     : 점수 재계산 → hotel_scores 갱신                    (§7)
7. build     : generate.py → docs/ (이미지 경로는 R2 도메인)
8. deploy    : Cloudflare Pages 배포 (wrangler pages deploy docs/ 또는 git push)
9. report    : sync_jobs 마감 + 텔레그램/메일 요약 알림(선택): "신규 리뷰 431 · 신규 호텔 1 · 이미지 268 · 비용 $0.4"
```

실패 정책: 각 단계는 sync_jobs에 상태 기록. 5단계(LLM)가 부분 실패해도 is_analyzed=false로 남아 다음 주에 자동 재시도된다. 배포(8)는 6·7 성공 시에만.

---

## 9. 마이그레이션 계획 (Supabase → Oracle, 1회성)

순서 (내일 작업의 Phase 3):

1. VM에 PostgreSQL 설치, §2 DDL 적용
2. Supabase에서 CSV 추출 (psql `\copy`): hotels_new, reviews_new, reviews_analysis_new(주의/심각 & quote 정규화), analysis_cost_log
3. 신 스키마 적재 + §2.1 매핑/정제 (정상행 제거, category 복원, 표기 통일 — 기존 export.py의 CASE문 재사용)
4. 검증: 행 수 대조표 + 점수 v2 재계산 결과가 현행 사이트 수치(§7.0 모수 적용 후 도시평균 실망확률 **9.5%**, 리브맥스 **24%**, 200+ 호텔 104개 등)와 일치하는지 스팟 체크
5. 기존 자체호스팅 호텔 이미지 127장 → R2 이관 (`assets/hotels/*.jpg` → WebP 변환 후 업로드, hotel_images 등록)
6. `scripts/export.py`를 "Supabase Management API" → "로컬 Postgres 직결(psycopg)"로 교체. generate.py는 입력 JSON 규약이 같으므로 거의 무수정
7. Supabase는 읽기전용으로 두고 2주 병행 후 정리 (mvp_feedbacks만 유지)

---

## 10. 내일 작업 체크리스트 (Opus 실행 순서)

**사용자가 준비/제공할 것:**
- [ ] Apify 계정 토큰 (콘솔 → Settings → API tokens)
- [ ] Google Cloud API 키 (Places API New 활성화) — §3
- [ ] Oracle VM SSH 접속 정보
- [ ] Cloudflare 계정 (Pages 리포 연결 + R2 버킷 생성 권한)
- [ ] **기존 PC의 LLM 프롬프트 + 파이썬 소스** (이걸 §6.2 규약으로 재정리)
- [ ] §11 결정 4개의 답

**Phase 순서:**
1. §11 결정 확인 → 이 문서 업데이트
2. VM 셋업 (PostgreSQL, Python venv, 방화벽) + R2 버킷/도메인
3. §9 마이그레이션 (스키마 → 데이터 → 검증 → 이미지 이관)
4. 파이프라인 스크립트 작성: `pipeline/` 디렉터리에 scrape.py(Apify), ingest.py, images.py, analyze.py(프롬프트 이식), score.py, weekly_sync.sh — **기존 scripts/scoring.py·generate.py 재사용**
5. 첫 캐치업 런 (§4.4) 실행: 스크랩 → 이미지 → 분석 → 점수 → 배포. 여기서 3월 공백 해소 + 호텔 이미지 백필 첫 실행
6. 프론트 반영: 호텔 갤러리 스와이프, 리뷰 이미지 스트립, 1년 컷, 노출 3단계(또는 200 하드컷), 이미지 R2 경로
7. Cloudflare Pages 전환 + cron 등록 + 1주 뒤 첫 자동 실행 모니터링

**주의사항 (이번 세션에서 겪은 함정들):**
- Apify input 필드명은 콘솔에서 최신 스키마 재확인 (액터 업데이트 잦음)
- 구글 이미지 URL은 만료형 → 인제스트와 같은 배치에서 즉시 다운로드
- GitHub Pages는 "Deployment failed, try again later" 실패가 잦다 → Cloudflare Pages 전환이 낫고, 유지 시 빈 커밋 재푸시로 복구
- 리뷰의 35%는 Trip.com(별점 null) — 별점 기반 로직에 null 가드 유지
- generate.py 재생성 시 캐시버스터(BUILD)가 자동으로 붙음 — CSS 수정이 반영 안 보이면 캐시 문제

---

## 11. 결정 대기 (구현 전 사용자 확인)

| # | 질문 | 옵션 | 권고 |
|---|---|---|---|
| 1 | 노출 기준 200건 | (a) 하드컷 — 사이트 91개로 축소 / (b) 3단계 노출(정식 200+/참고 30~199/수집중) | **(b)** |
| 2 | 이미지 저장소 | (a) Cloudflare R2 / (b) Oracle VM 디스크+nginx | **(a)** R2, VM은 백업 |
| 3 | 12개월 초과 리뷰 | (a) 점수에서 완전 제외(×0) / (b) 기존대로 ×0.15 유지 | **(a)** — "최근 1년만 보여준다"와 일관 |
| 4 | 기존 리뷰 이미지 8,018건 (URL 만료) | (a) 포기, 신규부터 저장 / (b) 해당 호텔 리뷰 재스크랩 (비용 ~$15+, 이미지 회수율 불확실) | **(a)** |

---

*작성 근거 데이터: Supabase 실측 (2026-07-05), Apify API 액터 메타 확인, 이번 세션의 MVP 구축·배포 경험. 관련 문서: UI-STANDARDS.md(디자인 표준), CLAUDE.md(리포 안내), scripts/scoring.py(점수 v2 정본).*
