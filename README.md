# CatchFlaw (캐치플로)

**https://catchflaw.com** — 후쿠오카 호텔 203곳의 공개 리뷰 6.6만 건을 LLM으로 읽고, 호텔마다 '실망 확률'을 숫자 하나로 보여 주는 사이트. 로그인 없음, 무료, 매주 갱신.

CatchFlaw reads 66k public reviews for 203 hotels in Fukuoka, Japan, and gives each hotel one number: the probability a guest leaves disappointed. Every number links to the source review and date.

- 전체 목록 203곳: https://catchflaw.com/hotels
- 계산 방법: https://catchflaw.com/about
- 상세 예시: https://catchflaw.com/hotels/the-blossom-hakata-premier

## 실망 확률

최근 1년 리뷰 중 **심각한 문제를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰의 비율**. 최신성 가중(반감기 180일, 1년 초과 0), k=20 베이지안 보정, 별점만 리뷰는 같은 별점 글 리뷰의 실망 비율로 기대값 반영, 글이 있는 1~2점 리뷰는 그 비율만큼 바닥값. 최근 1년 평가 리뷰 30건 미만 미노출, 100건 미만 순위 제외. 후쿠오카 평균 6%, 호텔별 2~23%.

산식 정본: [`scripts/scoring.py`](scripts/scoring.py)

## 이 리포

프론트(정적 사이트)만 있다. 리뷰 수집·LLM 분류 파이프라인과 DB는 별도(비공개).

- `scripts/generate.py` — 빌드 정본. `data-src/`(빌드 입력 JSON, 비공개)에서 HTML 203장·데이터 JSON·사이트맵을 `docs/`에 생성
- `docs/` — Cloudflare가 서빙하는 산출물 (`wrangler.toml`)
- `css/ js/ img/` — 원본 자산(빌드가 `docs/css/site.css` 한 파일로 합침)
- `scripts/lint_ui.py` — 디자인 시스템 규칙 검사(빌드 게이트)
- `scripts/slugs.json` — 호텔 주소 슬러그 정본

규칙 문서: `UI-STANDARDS.md`(디자인 시스템 v3), `CLAUDE.md`(구조·규칙 요약).

## 스택

Python 정적 생성 → Cloudflare 정적 서빙. 프론트는 빌드 없이 jQuery + Swiper, 모바일 360px 기준. 분류 LLM: Gemini. DB: PostgreSQL.
