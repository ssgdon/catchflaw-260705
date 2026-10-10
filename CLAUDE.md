# CATCHFLAW (캐치플로)

호텔 리뷰를 LLM으로 분석해 "실망 확률"을 보여주는 서비스. 후쿠오카 전용 MVP, **운영(라이브) 단계**.

> **⭐ 운영 절차(배포·주간배치·cron·백업·롤백)의 정본은 [RUNBOOK.md](RUNBOOK.md)** (로컬 전용).
> 완료된 설계 히스토리(SYNC·LLM·DISCOVERY·AI-RECOMMEND·DETAIL·RISK 등)는 `archive/design-docs/`에 보존.

## 리포 구조 (3분할)

- **프론트(배포, git 추적)**: `docs/`(Cloudflare가 서빙하는 산출물) · `css/ js/ img/ assets/hotels/`(원본) · `scripts/generate.py`(빌드 정본, `scripts/scoring.py`를 import) · 루트 `*.html`(퍼블리싱 목업 원본) · `wrangler.toml`.
- **백엔드(파이프라인, gitignored·VM 미러)**: `pipeline/`(scrape→ingest→images→analyze→score→stats→export_pg→build_index + weekly_sync·monthly_master·backup·master_refresh) · `data-src/`(빌드 입력 JSON) · `.env` · `infra/`.
- **히스토리(gitignored)**: `archive/`(설계문서·구 스크립트·1회성).
- 배포: GitHub `ssgdon/catchflaw-260705` → **Cloudflare**가 `docs/`를 정적 서빙(`wrangler.toml [assets] directory=./docs`, `html_handling=none`). push → 자동 배포. 도메인 catchflaw.com.

## 프론트 규칙

- 정적 HTML + jQuery + Swiper, 빌드 없음, 모바일 360px 기준. 페이지: index / search / recommend(맞춤형 추천) / compare / hotels/{id}(상세, generate.py 생성) / 목업 detail·detail-2·detail-3 / review / recent / wishlist.
- CSS 로드 순서: `tokens.css → common.css(리셋) → layout.css(원본) → swiper.css → uplift.css → mvp.css(오버라이드) → ds.css(디자인 시스템 v2 정규화) → pc.css(PC 전용, 미디어쿼리 안에서만)`. 모바일 규칙은 ds.css까지, PC(≥1100px) 레이아웃은 pc.css에만 쓴다.
- **모든 화면 수정은 `UI-STANDARDS.md`를 따른다.** 색/폰트/간격은 `css/tokens.css` 변수만 사용. 이모지 미사용(제품 폴리시).
- **⛔ UI를 추가·수정하기 전에 `UI-STANDARDS.md` §0(디자인 시스템 v2)·§3(글자 단계)·§14(강제 장치·체크리스트)를 먼저 읽는다 — 예외 없음.**
  - 글자는 `--fs-*` 토큰만(px 금지), 읽는 글자 최소 14px(`--fs-meta`), 13px(`--fs-micro`)는 배지·범례 전용. 색은 토큰만(hex 금지). 페이지 여백 24·섹션 48·제목→내용 20, 버튼·칩 높이는 `--h-*` 토큰, 섹션 사이는 1px 선, 상자 안에 상자 금지.
  - 강제: `scripts/lint_ui.py`를 `generate.py`가 빌드 시작 때 실행 → 위반 시 **빌드 중단**. css·js·generate.py 편집 직후엔 Claude Code 훅이 같은 검사를 돌려 위반을 되돌려 준다. 위반은 고쳐서 통과시킬 것(기준선·allow 주석으로 우회 금지, 긴급 배포만 `CF_UI_LINT=warn`).
  - 새 CSS 파일 금지(로드 순서 등록부터). 화면 확인은 360·375 모바일 + 1280 PC.
  - 문구 줄바꿈은 UI-STANDARDS §15(빌드 시 `polish_breaks` 자동 + `.dsep`/`.seg`/`.nw`). 360px에서 뜻이 갈리는 줄바꿈이 생기면 묶음 규칙을 추가한다.

## 데이터

- **현행 DB = Oracle VM PostgreSQL `catchflaw`** (158.179.173.211, localhost 전용). 후쿠오카 189곳(active 173 / watch 14 / closed 2, 사이트엔 active+watch만, 상세 184·점수 노출 172) · 리뷰 7.2만(사이트 평가 리뷰 5.9만) · v5 분석 2.9만(최근 1년 글 리뷰). Supabase는 `mvp_feedbacks`(피드백)·`analysis_requests`(온디맨드 요청)만 사용.
- 점수체계 v2 (검증 완료): 도시평균=50, 3배=100 구간선형, k=20 보정, 카테고리·소분류 불만 5건 미만 상한 65, 최근 1년 평가 리뷰(별점만 포함) 30건 미만 미노출. 100건 미만은 '리뷰 적음'(순위·추천 제외, 확실한 위험만 위험 배지), 순위는 확실할 때만 구간('상위 25% 안') — UI-STANDARDS §5.
- 실망 확률 = 실망 리뷰의 최신성 가중 비율(k=20 보정, 도시평균 4.9%). 실망 리뷰 = 심각 OR (재방문 거부 AND 불만). 가중 = 0.5^(나이/180일), 1년 초과 0. 별점만 리뷰는 같은 별점 글 리뷰의 실망 비율로 기대값 반영(`agg_staronly.json`·`star_crit.json`). 정본 `scripts/scoring.py` = `pipeline/score.py` prod. 기준일(asof)은 최신 리뷰일로 매주 이동(`data-src/meta.json` → generate.py 동적 표기).
- 카테고리(A층, 분류 v5.7): 대분류 7 = 점수 6(청결/냄새/소음/객실/직원/위치) + 안전(칩 전용) × **소분류 21**. **정본 = `pipeline/prompt_v5.py` SUBS = `scripts/scoring.py` SUBS = `pipeline/score.py` CATS_V5.** 분석기 `pipeline/analyze_v5.py`(v4 `analyze.py` 사용 금지, 전환·롤백은 RUNBOOK §5-1). 희소·고위험 소분류 4종(벌레·곰팡이·동네 분위기·객실 보안)은 점수 대신 리뷰 건수 칩으로 렌더.
- FAQ(B층): 리뷰에서 사전 추출한 실전 정보 카드(짐보관·조식·주차 등). `pipeline/faq_topics.py`(토픽 정본)+`pipeline/faq_extract.py`(gemini 종합, `hotel_faq` 테이블) → `export_pg.py`가 `data-src/faq.json` 생성 → generate.py 상세 FAQ 섹션(근거 없으면 미노출).
- **추천순(2026-10)**: `scripts/scoring.rec_scores` = 안전(실망 확률, 15% 포화) 0.4 + 신뢰(베이지안 구글 평점) 0.3 + 수요(최근 1년 한국인 리뷰 수 순위와 보정 비율 순위의 평균, `scoring.kr_demand`) 0.3, 모수 = ranked(1년 리뷰 100+). **정렬 전용, 숫자 비노출** — 메인 콘셉트는 실망 확률 유지. 홈·검색 기본 정렬·허브·상세 대안·비교 팝업이 공용, AI 맞춤 추천은 '고른 항목 모두 평균 이하 → 추천순' 묶음 정렬(UI-STANDARDS §16). 배지 위험 문턱 2.0배(`DANGER_MULT`). 비교 쌍 시드 `scripts/compare_pairs.json`, 수용 기준 `scripts/check_rec.py`. 근거·설계 = `RECOMMEND-PRICE-DESIGN.md`·`HOME-CONCEPT-DESIGN.md`.
- 가격: `hotel_prices` 표본(주간 구글 지도 가격 자동 누적 + `pipeline/price_sample.py` 날짜 지정 2인 1박 수집) → `export_pg` prices.json(최근 8주) → generate.py `price_stats`가 평일 밤 중앙값 "평일 약 13만원"(사용자 실측 17곳과 배율 0.99)을 대표값·가격대(표시 만원 기준)·정렬로, 주말(금·토 밤, 평일의 약 2.6배)은 상세에 따로 표기. 가격대 = 분포 기준 평일 4구간(10만원 미만/10~15/15~20/20만원 이상)·주말 4구간(30만원 미만/30~40/40~50/50만원 이상) — UI-STANDARDS §16. 평일 근거(날짜 지정 1건 또는 표본 2건) 없으면 숫자 비표시. 이상치 검증: `price_sample.py`가 정기 수집 뒤 주말/평일 3.5배 초과·같은 종류 다른 날 2배 초과 표본을 찾아 다른 날짜(3·5주 뒤 목·금·토)를 재수집하고, 여전히 튀면 `hotel_prices.excluded`로 내보내기에서 뺀다(RUNBOOK §5-2). 운영은 RUNBOOK §5-2.
- 호텔 status: active(운영) · watch(리뷰 적음, 매주 수집·사이트 노출) · new(편입 대기 → 주간 배치 그룹B 초도 수집) · closed(폐업·구글 병합) · **hidden(품질 의심 — 중복 등록·표본 극소, 2026-10-10 신설: 수집·집계·사이트 전부 제외, master_refresh도 재편입 안 함)**. export_pg·score.py 집계는 active·watch만.
- **네이버 검색량(인지도)**: `pipeline/kw_volume.py`(네이버 검색광고 키워드 도구, 키는 VM .env `NAVER_AD_*`) 매월 2일 cron → DB `hotel_search_volume` + `data-src/search_volume.json`(호텔별 별칭 합산 월간 검색량·미등록 후보). 추천 순위엔 안 쓰고 많이 찾는 호텔 칩·비교 쌍 자동 선정·사이트맵 우선순위에만(UI-STANDARDS §16). 호텔 상태 `pending`(관찰) = 편입 후보지만 한국인 검색이 적어 수집·노출을 미룬 곳(파이프라인 전 단계가 무시) — kw_volume이 매달 조회해 월 300회 이상이면 `new`로 올림(2026-10-10: 월 300회 이상 또는 리뷰 1,000건 이상 20곳 new, 나머지 18곳 pending).
- 추천 제외(`hotels.rec_excluded`): 러브호텔·넷카페 등은 검색·상세엔 노출되나 홈 추천·검색 기본목록·지도에선 숨김(호텔명 직접 검색 시에만 노출).

## MVP 규칙

- 후쿠오카 외 도시: 검색 단계에서 "미지원" 안내. 상세 진입 금지.
- 로그인 없음. 찜·최근 본 호텔은 localStorage.
- 미등록 호텔은 검색 미매칭 시 "분석 요청"(Supabase `analysis_requests`) → 운영자 심사 후 편입.
