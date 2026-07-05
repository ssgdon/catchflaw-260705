# CATCHFLAW (캐치플로)

호텔 리뷰를 LLM으로 분석해 "실망 확률"을 보여주는 서비스. 현재 후쿠오카 전용 MVP 검증 단계.

> **⭐ 주간 동기화·오라클 이관 작업을 하러 왔다면 [SYNC-PIPELINE-DESIGN.md](SYNC-PIPELINE-DESIGN.md)부터 읽을 것.** 실행 순서는 그 문서 §10, 사용자 결정 대기 항목은 §11.
> **⭐ AI 맞춤 추천 기능(3스텝 마법사 + 순위 결과) 구현은 [AI-RECOMMEND-DESIGN.md](AI-RECOMMEND-DESIGN.md)를 그대로 따를 것.** 특히 §6 디자인 가드레일과 §8 카피는 수정 금지. 지역 지도 줌 버그 수정(§1)도 이 문서에 포함.

## 이 리포

디자인 퍼블리싱 원본 (정적 HTML + jQuery + Swiper, 빌드 없음, 모바일 360px 기준).

- 페이지: index(메인) / search(검색결과) / detail·detail-2·detail-3(상세 상태 변형) / review(리뷰 전체) / recent / wishlist
- CSS 로드 순서: `tokens.css → common.css(리셋) → layout.css(원본) → swiper.css → uplift.css(개선 오버라이드)`
- **모든 화면 수정은 `UI-STANDARDS.md`를 따른다.** 색/폰트/간격은 `css/tokens.css` 변수만 사용.

## 데이터

- Supabase 프로젝트 "Nitpicker". 현행 데이터 = 후쿠오카 150개 호텔 (`hotels_new`, `reviews_new`, `reviews_analysis_new`).
- 점수체계 v2 (검증 완료): 도시평균=50, 3배=100 구간선형, k=20 보정, 카테고리 불만 5건 미만 상한 65, 분석 30건 미만 미노출. 실망확률 = 심각 태그 리뷰의 최신성 가중 비율(실측).
- 카테고리: 대분류 6 (위생 경보/오감 지옥/시설 사기단/동선 파괴자/불친절 레이더/안전 그림자) × 소분류 20.

## MVP 규칙

- 후쿠오카 외 도시: 검색 단계에서 "미지원" 안내. 상세 진입 금지.
- 로그인 없음 (카카오 로그인/리뷰 블라인드 제거). 찜·최근 본 호텔은 localStorage.
- 목업의 "실망 확률 80%" 류 데모 값은 실데이터 스케일(2.7~35.2%)로 교체할 것.
