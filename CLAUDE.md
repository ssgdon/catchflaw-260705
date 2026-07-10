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

- 정적 HTML + jQuery + Swiper, 빌드 없음, 모바일 360px 기준. 페이지: index / search / hotels/{id}(상세, generate.py 생성) / 목업 detail·detail-2·detail-3 / review / recent / wishlist.
- CSS 로드 순서: `tokens.css → common.css(리셋) → layout.css(원본) → swiper.css → uplift.css → mvp.css(최후순위 오버라이드)`.
- **모든 화면 수정은 `UI-STANDARDS.md`를 따른다.** 색/폰트/간격은 `css/tokens.css` 변수만 사용. 이모지 미사용(제품 폴리시).

## 데이터

- **현행 DB = Oracle VM PostgreSQL `catchflaw`** (158.179.173.211, localhost 전용). 후쿠오카 173곳(active 159 / watch 14 / closed 1, 사이트엔 active+watch만) · 리뷰 6만+ · 분석 3.8만+. Supabase는 `mvp_feedbacks`(피드백)·`analysis_requests`(온디맨드 요청)만 사용.
- 점수체계 v2 (검증 완료): 도시평균=50, 3배=100 구간선형, k=20 보정, 카테고리 불만 5건 미만 상한 65, 분석 30건 미만 미노출. 실망확률 = 심각 태그 리뷰의 최신성 가중 비율(실측, 도시평균 ~9%). 기준일(asof)은 최신 리뷰일로 매주 이동(`data-src/meta.json` → generate.py 동적 표기).
- 카테고리(A층): 대분류 6 (위생/냄새/소음/시설/불친절/위치·안전) × **소분류 17** (v4). **정본 = `pipeline/prompt.py` SUBS = `scripts/scoring.py` SUBS = `pipeline/score.py` CATS (동기화 완료).** v3→v4 전환은 `pipeline/migrate_v4.py`(1회성). 희소·고위험 소분류(해충/곰팡이·치안·안심)는 점수 대신 "신고 N건" 칩으로 렌더.
- FAQ(B층): 리뷰에서 사전 추출한 실전 정보 카드(짐보관·조식·주차 등). `pipeline/faq_topics.py`(토픽 정본)+`pipeline/faq_extract.py`(gemini 종합, `hotel_faq` 테이블) → `export_pg.py`가 `data-src/faq.json` 생성 → generate.py 상세 FAQ 섹션(근거 없으면 미노출).
- 추천 제외(`hotels.rec_excluded`): 러브호텔·넷카페 등은 검색·상세엔 노출되나 홈 추천·검색 기본목록·지도에선 숨김(호텔명 직접 검색 시에만 노출).

## MVP 규칙

- 후쿠오카 외 도시: 검색 단계에서 "미지원" 안내. 상세 진입 금지.
- 로그인 없음. 찜·최근 본 호텔은 localStorage.
- 미등록 호텔은 검색 미매칭 시 "분석 요청"(Supabase `analysis_requests`) → 운영자 심사 후 편입.
