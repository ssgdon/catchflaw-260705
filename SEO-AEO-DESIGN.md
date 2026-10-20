# 검색·AI 노출 최적화 (SEO · AEO) — 현황 진단과 실행안

> 작성 2026-10-19. 라이브(catchflaw.com, main 92dbdd5 이후) 실측과 `scripts/generate.py` 코드 대조로 썼다.
> 구현 세션은 §9 체크리스트를 순서대로 진행한다. **§10 사용자 결정**(특히 AI 봇 허용)은 구현 전에 받는다.
> 화면을 건드리는 항목은 `UI-STANDARDS.md` v3 규칙(토큰·h1 1개·lint 게이트)을 그대로 따른다.

---

## 0. 결론 요약

| 순위 | 할 일 | 왜 | 비용 |
|---|---|---|---|
| 1 | **AI 봇 차단 정책을 고친다**(Cloudflare 설정 + 우리 robots) | GPTBot·ClaudeBot은 지금 **403**, Google-Extended·Applebot-Extended·meta-externalagent·Amazonbot은 robots로 차단. 모델이 '캐치플로'를 배울 길과 Gemini 앱 근거 수집이 막혀 있다 | 설정 10분(사용자) |
| 2 | **Bing 웹마스터 도구 등록** | ChatGPT 검색·Copilot·DuckDuckGo가 Bing 색인을 쓴다. IndexNow는 이미 보내지만 소유 확인·사이트맵·색인 현황을 볼 곳이 없다 | 10분(사용자) |
| 3 | **URL 슬러그 전환**(`/hotels/ChIJ…` → `/hotels/oriental-express-fukuoka-tenjin`) | 구글 색인이 3곳뿐인 **지금이 바꿀 때**. 색인이 쌓인 뒤엔 비용이 커진다 | 반나절 |
| 4 | **답이 먼저 나오는 문장 + 제목 태그** | AI는 문단 하나를 떼어 인용한다. 지금 결론 문장엔 호텔 이름·기준이 없고, 섹션 제목은 `<div class="title">`이라 문서 구조가 안 보인다 | 반나절 |
| 5 | **리뷰 원문 일부를 HTML에** | 가장 고유한 내용(근거 리뷰)이 지금은 JS로 불러오는 JSON에만 있다. 크롤러·AI는 요약만 본다 | 반나절 |
| 6 | **`llms.txt`·전체 호텔 표·호텔별 마크다운** | AI 에이전트가 사이트 전체를 한 번에 읽을 입구. 검색 페이지는 서버 렌더 글이 491자·호텔 링크 0개다 | 하루 |
| 7 | **구조화 데이터 보강**(Organization·WebPage·Dataset·Hotel 필드) | 브랜드 개체 인식, '실망 확률'이 정의된 지표라는 신호, 갱신일 | 반나절 |
| 8 | **정적 비교 페이지 `/vs/a-vs-b`·질문형 허브** | 카페 질문의 15%가 'A vs B'. 지금 비교 페이지는 noindex라 이 수요를 못 받는다 | 1~2일 |
| 9 | **네이버 전용**: RSS 제출, 블로그·카페 노출, AI 브리핑 대응 | 유입의 98%가 네이버. 네이버 AI 브리핑은 블로그·카페·웹문서를 함께 인용한다 | 운영 |
| 10 | **측정**: AI 유입 채널, 봇 방문, 월 1회 질문 테스트 | 효과를 숫자로 봐야 다음 우선순위를 정한다 | 1시간 |

핵심 판단: 기술 차단은 거의 없다(서버 렌더 HTML, canonical, 사이트맵 205개, IndexNow, www·.html 301/308, 진짜 404). 막힌 것은 **① AI 봇 정책 ② 외부 신호(링크·언급) ③ AI가 그대로 인용할 수 있는 문장과 구조** 세 가지다.

---

## 1. 현황 진단 (2026-10-19 실측)

### 1-1. 크롤러별 접근 (상세 페이지에 User-Agent를 바꿔 요청)

| 봇 | 용도 | 결과 |
|---|---|---|
| Googlebot(PC·모바일) | 구글 검색 + **AI Overviews·AI 모드** | 200 |
| Yeti | 네이버 검색 | 200 |
| bingbot | Bing → ChatGPT 검색·Copilot | 200 |
| OAI-SearchBot · ChatGPT-User | ChatGPT 검색 색인·사용자 요청 열람 | 200 |
| PerplexityBot | Perplexity | 200 |
| Claude-SearchBot | Claude 검색 | 200 |
| **GPTBot** | OpenAI 학습 | **403** (Cloudflare AI 봇 차단) |
| **ClaudeBot** | Anthropic 학습 | **403** |
| Google-Extended | Gemini 앱·Vertex 근거·학습 | robots에서 Disallow |
| Applebot-Extended · meta-externalagent · Amazonbot · CCBot · GoogleOther 등 | 학습·기타 | robots에서 Disallow |

- robots 앞부분은 **Cloudflare Managed robots.txt**가 붙인다(`Content-Signal: search=yes,ai-train=no,use=reference` + 학습 봇 30여 종 차단). 우리 `ROBOTS_TXT`는 그 뒤에 `Allow: /` + `Sitemap`.
- 즉 **AI 검색(실시간 인용)은 열려 있고, AI 학습은 막혀 있다.** 학습이 막히면 모델이 '캐치플로'라는 이름과 '실망 확률'이라는 지표를 스스로 알지 못한다. 작은 신생 브랜드에게는 손해가 더 크다(§2).

### 1-2. 페이지별

| 페이지 | 서버 렌더 글 | 제목 구조 | 구조화 데이터 | 문제 |
|---|---|---|---|---|
| 홈 | 4,363자 | h1 '이 호텔,실망할 확률은몇 %일까요?'(줄바꿈 태그 사이 공백 없음) · h2 '메뉴'뿐 · 섹션 제목은 h3/div | WebSite(+SearchAction) | Organization 없음 |
| 상세 | 13,275자 | h1 호텔명 · h2 '리뷰 리뷰 근거'(중복)·빈 h2·빈 h3 · **섹션 제목 11개가 `<div class="title">`** | Hotel(이름·주소·사진·좌표·가격대·성급) · Breadcrumb · FAQPage | 결론 문장에 주어 없음, 리뷰 원문은 `data/q/*.json`(JS)에만, 갱신일 없음 |
| 허브(텐진) | 2,881자 | h1 · 목록 h3 | ItemList · FAQPage · Breadcrumb | 결론 문단 짧음 |
| 소개 | 충분 | h1 + 섹션 div | **없음** | 방법론을 기계가 읽을 형태가 없음 |
| 검색 | **491자 · 호텔 링크 0** | h1(blind) | 없음 | 목록이 전부 JS |
| 맞춤 추천 | 354자 | h1 | 없음 | 앱 화면이라 괜찮음 |
| 비교 | — | — | — | noindex(개인화 URL이라 맞음). 다만 'A vs B' 수요를 받을 정적 페이지가 없음 |

- 메타: 페이지별 title·description·canonical·OG·twitter `summary_large_image` 있음. **`og:locale` 없음**, 기본 OG 이미지가 옛 `img/search_bg.jpg`(`DEFAULT_OG`).
- `aggregateRating`은 의도적으로 뺐다(구글 평점 출처라 리뷰 스니펫 정책 위반) — **맞는 판단, 유지.**
- 구글 Search Console: 182 중 색인 3, '발견됨-색인 안 됨' 176(10/9 기준). 기술 차단이 아니라 새 도메인·외부 링크 0·비슷한 프로그래매틱 페이지가 원인.
- 외부 검색에서 'catchflaw.com 후쿠오카 호텔 실망 확률'로 사이트가 나오지 않는다(웹 검색 확인). 브랜드 언급이 사실상 없다.

### 1-3. 2026년 기준 사실 (설계 전제)

- 구글 AI Overviews·AI 모드는 **Googlebot 색인**을 쓴다. Google-Extended를 막아도 AI Overviews 노출에는 영향이 없다. 대신 Gemini 앱 답변의 근거 수집·학습에는 쓰이지 않는다.
- 구글 FAQ 리치 결과는 2026년 5월 종료. **FAQPage 마크업은 남겨도 해가 없고** Bing·ChatGPT·Perplexity 등은 계속 읽는다. 단 화면에 보이는 글과 같아야 한다.
- AI 기능용 '특별한 마크업'은 없다. 결정적인 것은 **보이는 글이 질문에 바로 답하는지**와 **외부에서 언급되는지**다.
- 네이버는 2023년 7월부터 **IndexNow를 지원**한다. 우리 `scripts/indexnow.py`(api.indexnow.org)는 Bing·네이버·Yandex 등에 함께 전달된다.

---

## 2. 전략 판단

1. **AI가 '안다' + AI가 '찾는다' 둘 다 연다.** 찾기(검색 봇)는 이미 열려 있다. 알기(학습 봇)를 열면 모델이 "후쿠오카 호텔 실망 확률 = 캐치플로"를 기억해 질문에 브랜드를 꺼낼 가능성이 생긴다. 데이터를 경쟁자가 긁어 갈 위험은 학습 봇 허용과 무관하다(일반 스크레이퍼는 robots를 안 지킨다). **권고: 허용.**
2. **문장 단위로 인용되게 쓴다.** AI 답변은 페이지가 아니라 문단을 떼어 쓴다. 문단 하나만 읽어도 "누가·무엇이·몇이고·기준이 무엇인지"가 다 있어야 한다.
3. **고유 데이터를 HTML 표면에 올린다.** 실망 확률·항목별 불만·심각 리뷰 건수·리뷰 원문 발췌는 다른 사이트에 없는 정보다. JS 뒤에 숨기지 않는다.
4. **질문 모양 그대로 페이지를 만든다.** 네이버 카페 수요(판정 1곳 > A vs B > 조건 추천)에 맞춰 상세·비교·허브가 각각 그 질문의 정답 페이지가 되게 한다.
5. **네이버는 네이버 안에서도 이긴다.** 유입 98%가 네이버이고, 네이버 AI 브리핑은 블로그·카페 글을 많이 인용한다. 사이트 최적화와 별개로 네이버 블로그 채널(이미 파이프라인 있음)이 필수다.
6. **정책 가드는 유지한다.** 실망 확률을 schema의 평점(`aggregateRating`·`Review`)으로 넣지 않는다. 화면 문구의 '참고용 통계 의견' 고지는 그대로 둔다.

---

## 3. 크롤러·색인 설정 (운영·설정)

### 3-1. AI 봇 허용 (사용자 결정 §10-1 후)
1. Cloudflare 대시보드 → 해당 도메인 → **AI Crawl Control**(또는 Security → Bots)
   - 'Block AI bots'(AI 학습 봇 차단 WAF) **끄기** → GPTBot·ClaudeBot 403 해소.
   - 'Managed robots.txt' **끄기**(우리 robots만 나가게) — 또는 켜 둔 채 Content Signals를 `ai-train=yes, ai-input=yes`로 바꾼다.
   - 'AI Labyrinth' 같은 함정 기능은 끈 상태 확인.
2. `generate.py ROBOTS_TXT`를 명시형으로 바꾼다(Cloudflare 관리본을 끈 경우).
   ```
   # 캐치플로 — 검색·AI 검색·AI 학습 모두 허용. 데이터 출처 표기(캐치플로, catchflaw.com)를 부탁드립니다.
   User-agent: *
   Content-Signal: search=yes, ai-input=yes, ai-train=yes
   Allow: /
   Disallow: /compare
   Disallow: /recent

   User-agent: Bytespider
   Disallow: /

   Sitemap: https://catchflaw.com/sitemap.xml
   ```
   - `/compare`·`/recent`는 이미 noindex인 개인화 페이지라 크롤 낭비만 막는다. 무거운 스크레이퍼(Bytespider) 하나만 막는다.
3. 확인: 상세 URL을 GPTBot·ClaudeBot UA로 요청해 200, `/robots.txt`에 Managed 블록이 없거나 바뀐 신호인지.

### 3-2. 검색엔진 등록·제출
| 엔진 | 할 일 | 비고 |
|---|---|---|
| 구글 GSC | 사이트맵 제출 상태 확인, '페이지' 보고서에서 색인 추이 확인, 상위 20 URL 색인 요청 | 10/10 유효성 검사 진행 중 |
| **Bing 웹마스터 도구** | GSC에서 가져오기로 등록 → 사이트맵 제출 → URL 검사 | ChatGPT 검색·Copilot의 바탕 |
| 네이버 서치어드바이저 | 사이트맵·**RSS 제출**(§7-1), '수집 요청'으로 허브·상위 호텔, '웹 페이지 최적화' 점검 | 소유 확인 meta 있음 |
| IndexNow | 배포 뒤 `python scripts/indexnow.py` 유지 | 네이버·Bing 공용 |

### 3-3. HTTP 헤더 (`docs/_headers` — Cloudflare Pages)
- `/llms.txt`, `/*.md` → `Content-Type: text/markdown; charset=utf-8`
- 사이트맵·llms 계열 → `Cache-Control: public, max-age=3600`

---

## 4. URL 슬러그 전환 (지금이 적기)

- 새 주소: `/hotels/{slug}` — 영문명(`hotels_index.json`의 `en` 또는 구글 영문 표시명)을 소문자·하이픈으로. 예 `/hotels/hotel-oriental-express-fukuoka-tenjin`. 겹치면 `-2`.
- 슬러그 정본 파일 `scripts/slugs.json`(pid → slug)을 만들고 **한 번 정하면 바꾸지 않는다**(호텔명이 바뀌어도 유지). 새 호텔은 빌드가 자동 추가.
- 옛 주소 `/hotels/ChIJ…` → 새 주소 **301**: `generate.py REDIRECTS`(이미 `docs/_redirects`를 만든다)에 전부 추가. Cloudflare Pages `_redirects` 한도(정적 2,000줄)안이다.
- 내부 링크·canonical·사이트맵·JSON-LD·OG URL·검색 인덱스·비교 데이터·`data/q`·`data/fe` 파일 이름을 모두 슬러그 기준으로. 파일명은 `docs/hotels/{slug}.html`, 사이드 파일은 pid 그대로 둬도 된다(외부에 안 보임).
- 배포 뒤: GSC·Bing·네이버에 새 사이트맵, IndexNow로 새 URL 전체 전송.
- 허브는 이미 `/area/tenjin` 형태라 그대로.

---

## 5. 페이지 내용 — 답이 먼저, 구조가 보이게

### 5-1. 상세: 첫 문단 '답 블록'
지금 '한눈에 보기' 리드는 "위치는 괜찮지만, 벌레 심각 리뷰가 반복돼요."처럼 주어와 기준이 없다. 그 바로 위(호텔명 h1 아래 요약 행 다음)에 **인용용 한 문단**을 둔다. 화면 위계를 해치지 않게 본문 16 `--ink`, 상자 없이.

```
호텔 오리엔탈 익스프레스 후쿠오카 텐진은 최근 1년 투숙객 리뷰 611건을 분석한 결과 실망 확률 8%로,
후쿠오카 평균(4%)보다 실망이 잦아요. 걸리는 점은 벌레 심각 리뷰 3건과 실내 온도 불만(리뷰의 8.5%)이고,
위치 불만은 평균보다 63% 적어요. (2026년 10월 11일 기준, 캐치플로)
```
- 조립 재료는 이미 있다: `pct(h['p_crit'])`·판정 문구(카피 원칙의 4단계)·`_neg`/`_pos`(한눈에 보기)·`CITY['data_asof']`.
- 같은 문장을 `<meta name="description">`의 앞 120자로 쓴다(지금 description은 항목 나열이라 답이 아니다).
- 문구는 `copy-style` 원칙(비유 금지·숫자 상호 설명·같은 경계)을 지킨다. 리뷰 적음·분석 준비 중은 각자 문장 틀을 따로 둔다.

### 5-2. 제목 태그 정리
- 상세 섹션 제목 `<div class="title">` 11개 → `<h2 class="title">`(클래스·스타일 그대로, 태그만). 하위 묶음은 h3.
- 질문형이 자연스러운 곳은 그대로 질문으로: '누구와 가세요?'는 유지, 실전정보 각 카드 질문('대욕장 있나요?')은 h3.
- 고칠 것: h2 '리뷰 리뷰 근거'(blind 텍스트 중복), 빈 h2·빈 h3(아이콘·숫자만 든 제목), 홈 h1 줄바꿈 사이 공백 없음(`이 호텔,실망할` → `<br>` 앞뒤 공백 또는 `aria-label` 없이 텍스트에 공백).
- 홈·허브의 '메뉴' h2는 오버레이 안 제목이라 `<p class="ov-title">`로 내려도 된다(문서 개요 첫 h2가 '메뉴'인 것을 피한다).
- `lint_ui.py`의 E14(h1 1개)는 그대로, 'h2 다음에 h4로 건너뛰지 않기'를 새 검사로 추가할지는 §10-5.

### 5-3. 리뷰 원문 발췌를 HTML에
- 위험도 섹션의 항목마다 **대표 인용 2건**(심각 우선 → 최신)을 서버 렌더한다: 발췌 1~2문장 · 출처(Google/Trip.com) · 'YYYY. MM.' · 심각도 태그. 나머지는 지금처럼 시트에서 JSON으로.
- `<blockquote>`에 `cite`는 넣지 않는다(원문 URL은 외부라 '리뷰 원문 보기' 링크로 충분). 개인 이름은 지금 규칙대로 마스킹.
- 발췌 길이 상한 120자, 호텔당 최대 12건 — HTML 크기(현재 158KB)를 +15KB 이내로.

### 5-4. 갱신일을 보이게
- 상세·허브 상단 메타 줄에 '2026. 10. 11. 기준 · 매주 갱신'(이미 일부 있음 — 첫 화면으로).
- schema `dateModified`(§6)와 사이트맵 `lastmod`(호텔별 최근 리뷰일, 이미 있음)를 같은 날짜로.

### 5-5. 이미지
- 사진 alt를 '호텔명 + 사진 순번'에서 '호텔명 외관/객실/욕실'로는 데이터가 없어 못 한다 → 현행 유지. 대신 첫 사진만 `fetchpriority="high"`(이미 있음) 확인.
- 기본 OG를 새 히어로(`img/home_bg_pc.jpg` 1200×630 크롭)로 교체하고 `og:locale` = `ko_KR` 추가.
- (2단계) 호텔별 OG 카드 자동 생성(1200×630: 사진 + 호텔명 + '실망 확률 8% · 주의'), 빌드 때 PIL로 `docs/og/{slug}.jpg`. 네이버·카카오 공유 미리보기와 AI 답변 카드 클릭률을 올린다.

---

## 6. 구조화 데이터 보강

| 페이지 | 추가 | 내용 |
|---|---|---|
| 전 페이지(공통 `head()`) | **Organization** 1벌(@id `https://catchflaw.com/#org`) | name 캐치플로 · alternateName CATCHFLAW · url · logo(`img/favicon.svg`가 아니라 512 PNG 로고 새로) · email · sameAs(인스타·네이버 블로그·유튜브 등 실제 계정만) |
| 홈 | WebSite에 `publisher: {"@id": "#org"}`, `inLanguage: "ko-KR"` | |
| 상세 | **WebPage** 래퍼 | `@type: WebPage`, `name`=title, `description`=§5-1 답 블록(보이는 글과 같게), `dateModified`=asof, `inLanguage`, `publisher` #org, `about`·`mainEntity` = Hotel(@id `…#hotel`), `breadcrumb` |
| 상세 Hotel | 필드 추가 | `alternateName`(일본어명) · `hasMap`(구글 지도 place_id URL) · `containedInPlace`(지역 허브 Place: 텐진·하카타역…) · `amenityFeature`(amenities 표준키 → LocationFeatureSpecification) · `checkinTime`/`checkoutTime`(있을 때) · `telephone`(있을 때). **평점·리뷰 마크업은 계속 금지** |
| 소개 | **AboutPage** + **Dataset** | Dataset: name '후쿠오카 호텔 실망 확률', description(산식 한 문단), `variableMeasured`(실망 확률·항목별 불만 6), `measurementTechnique`(LLM 리뷰 분류 v5.7·최신성 가중·k=20 보정), `spatialCoverage` Fukuoka, `temporalCoverage` 최근 1년, `dateModified`, `creator` #org, `license`(§10-3), `distribution`(llms-full.txt·hotels.csv — §8) |
| 소개 | **DefinedTerm** '실망 확률' | 정의 문장 1개 — AI가 지표 이름과 뜻을 함께 가져가게 |
| 허브 | ItemList 항목에 `item: {"@id": 호텔 URL#hotel}` 연결 + WebPage `dateModified` | |
| 정적 비교(§7-2) | WebPage + `about` 두 Hotel | |

- 모두 `generate.py`에서 만든다(`_jsonld()` 재사용). 화면에 없는 내용은 넣지 않는다.
- 검증: Rich Results Test·Schema Markup Validator로 상세·허브·소개 각 1장.

---

## 7. 새 페이지 — 질문 모양 그대로

### 7-1. 네이버 RSS (`/rss.xml`)
- 항목 = 이번 주 바뀐 호텔(실망 확률·배지가 바뀐 곳, 새로 분석된 곳) + 허브. `title`=호텔명 + '실망 확률 N%', `description`=§5-1 답 블록, `pubDate`=그 호텔 최근 리뷰일, `link`=슬러그 URL.
- 네이버 서치어드바이저에 RSS 제출 → 새 문서 수집이 빨라진다. `<link rel="alternate" type="application/rss+xml">`를 head에.

### 7-2. 정적 비교 페이지 `/vs/{slugA}-vs-{slugB}`
- 대상: `compare_pairs.json` 시드 + `auto_pairs`(검색량·가격·거리 비슷) 상위 30~40쌍. 같은 쌍은 이름순 하나만(반대 순서는 301).
- 내용(서버 렌더): h1 'A vs B, 어디가 나을까요?' → **답 문단**(비교 페이지 '한눈에 비교'의 헤드라인 규칙을 Python으로: "가장 큰 차이는 가격과 역 거리예요. A는 실망 확률 2%로 …, B는 평일 약 13만원으로 …") → 핵심 표(실망 확률·평일가·역 도보·구글 평점·한국인 리뷰) → 항목별 불만 6행 → 심각 리뷰 표 → '나란히 비교하기'(동적 /compare로) 버튼.
- 구조화 데이터 WebPage + 두 Hotel 참조, Breadcrumb. 사이트맵 포함, priority 0.7.
- 상세 '이 호텔과 함께 고민하는 호텔'이 이 페이지로 링크(지금은 동적 compare).

### 7-3. 질문형 허브 (네이버 검색량으로 고른다)
- 후보: '후쿠오카 바퀴벌레 없는 호텔'(홈 안심 목록을 페이지로), '후쿠오카 곰팡이 없는 호텔', '하카타역 근처 조용한 호텔', '텐진 깨끗한 호텔', '후쿠오카 가성비 호텔 10만원대', '후쿠오카 호텔 벌레'(정보형 — 벌레 심각 리뷰가 많은 곳·적은 곳 둘 다).
- 선정: `pipeline/kw_volume.py`(네이버 키워드 도구)로 후보 키워드 월 검색량을 뽑아 **월 300회 이상**만 만든다.
- 형식은 기존 허브 그대로(`COLLECTIONS`에 kind 추가) + 맨 위 답 문단 + FAQ.

### 7-4. 전체 호텔 표 (검색 페이지 보강)
- `/search` 본문에 JS가 그리기 전 **서버 렌더 표**를 넣는다: 호텔명(링크)·지역·실망 확률·등급·평일가 182행. JS가 시작되면 지금 카드 목록으로 바꿔 끼운다(같은 자리, 화면 변화 없음 — `noscript`가 아니라 실제 DOM).
- 효과: 크롤러가 모든 상세로 가는 링크를 한 페이지에서 얻고, AI가 "후쿠오카 호텔 실망 확률 순위"를 한 번에 읽는다.

---

## 8. AI 에이전트용 입구

| 파일 | 내용 | 생성 |
|---|---|---|
| `/llms.txt` | 사이트 한 단락 소개 · '실망 확률' 정의 · 데이터 기준일 · 주요 페이지 링크(소개·검색·허브 12·비교 상위) · 인용 부탁 문구 | generate.py 매 빌드 |
| `/llms-full.txt` | 위 + **호텔 182곳 한 줄씩**: '호텔명 — 지역 · 실망 확률 N%(등급) · 걸리는 점 · 평일가 · URL' | 매 빌드 |
| `/hotels/{slug}.md` | 상세 페이지의 마크다운판(답 블록·항목별 불만·심각 리뷰·실전정보·대표 인용·기준일) | 매 빌드(작다) |
| `/data/hotels.csv` | 공개 열만: 이름·지역·위도경도·실망 확률·등급·항목 결론 6·평일가·기준일·URL | 매 빌드 · Dataset `distribution` |

- `<link rel="alternate" type="text/markdown" href="….md">`를 상세 head에.
- 라이선스 문구(§10-3)를 llms 계열·CSV 머리에 둔다.
- 비용: 빌드 시간 수 초, 파일 합계 1MB 이하.

---

## 9. 구현 체크리스트 (순서대로 · 배치마다 빌드·확인·커밋)

**A. 설정(사용자) — 코드 없이**
- [ ] A1 §10-1 결정 → Cloudflare AI 봇 차단·Managed robots 정리(§3-1)
- [ ] A2 Bing 웹마스터 도구 등록·사이트맵 제출
- [ ] A3 네이버 서치어드바이저 사이트맵 상태 확인(RSS는 B 배포 후)

**B. 빠른 코드 개선 — 1일**
- [ ] B1 `ROBOTS_TXT` 명시형(§3-1-2) · `docs/_headers`(§3-3)
- [x] B2 상세 답 블록 + description 교체(§5-1) — 2026-10-20 `e4f61f24`(실행 사양 SEO-CRAWL-DESIGN §4, 브랜치 crawl)
- [ ] B3 제목 태그 정리(§5-2) — lint E14 통과, 화면 변화 0(스크린샷 360·1280 전후 비교)
- [ ] B4 Organization·WebPage·Hotel 필드·AboutPage·Dataset·DefinedTerm(§6) + 검증 도구 통과
- [ ] B5 기본 OG 교체·`og:locale`(§5-5)
- [ ] B6 `llms.txt`·`llms-full.txt`·`hotels.csv`(§8)
- [ ] B7 RSS(§7-1) → 네이버 제출(사용자)

**C. 구조 변경 — 1~2일**
- [x] C1 슬러그 전환 + 301 + 전 링크 교체(§4) — 2026-10-20 `4b60f004`(SEO-CRAWL §2, `scripts/slugs.json`·`check_links.py`) → 배포 후 사이트맵 재제출·IndexNow 전체
- [ ] C2 리뷰 발췌 서버 렌더(§5-3)
- [x] C3 검색 페이지 서버 렌더 표(§7-4) — 2026-10-20 대체 구현: 전체 호텔 목록 `/hotels`(SEO-CRAWL §3-3, `e15ac6ef`) + 허브 회원 전체 행 목록(`873bbaf3`). 검색 페이지 목록 아래에 `/hotels` 링크
- [ ] C4 호텔별 `.md`(§8)

**D. 새 페이지 — 2일**
- [ ] D1 정적 비교 `/vs/…` 30~40쌍(§7-2)
- [ ] D2 질문형 허브 — 키워드 검색량 확인 후(§7-3)
- [ ] D3 호텔별 OG 카드(§5-5 2단계)

**E. 측정 — 1시간 + 월 1회**
- [ ] E1 GA4 채널 그룹에 'AI'(chatgpt.com·perplexity.ai·gemini.google.com·copilot.microsoft.com·claude.ai) 추가, 내부 트래픽 필터
- [ ] E2 Cloudflare AI Crawl Control에서 봇별 방문 수 주간 확인
- [ ] E3 월 1회 질문 테스트 10개를 ChatGPT·Perplexity·Gemini·Claude·네이버 AI 브리핑에 던져 캐치플로 인용 여부 기록(예: '후쿠오카 오리엔탈 익스프레스 텐진 단점', '하카타역 근처 벌레 없는 호텔', '몬토레 라 스루 vs 오리엔탈 익스프레스 텐진')
- [ ] E4 GSC·Bing·네이버 색인 수를 2주마다 기록(기준: 구글 색인 3 / 182)

---

## 10. 사용자 결정

1. **AI 학습 봇 허용 여부**(권고: 허용). 허용하면 GPTBot·ClaudeBot·Google-Extended·Applebot-Extended 등이 학습에 쓸 수 있다. 막으면 AI 검색 인용만 가능하고 모델의 브랜드 인지는 생기지 않는다.
2. **슬러그 전환 시점**(권고: 이번 배치). 미루면 색인이 쌓인 뒤 301 비용이 커진다.
3. **데이터 라이선스**: llms·CSV·Dataset에 적을 문구. 권고 '출처(캐치플로, catchflaw.com)를 밝히면 인용·요약 허용, 원본 데이터 재판매 금지'(CC BY-NC 4.0 계열).
4. **리뷰 발췌 서버 렌더 범위**: 항목당 2건·120자(권고) / 더 적게.
5. **제목 건너뛰기 검사를 lint에 추가할지**(권고: R 래칫으로 시작).
6. **정적 비교 페이지 수**: 30~40쌍(권고) / 검색량 기준으로 더.

---

## 11. 하지 않는 것 (근거 있음)

- 실망 확률을 `aggregateRating`·`Review`로 넣기 — 구글 정책 위반이고 법적 표현 가드와도 충돌.
- 숨긴 글·키워드 나열·AI용 별도 문구 — 보이는 글과 마크업이 다르면 오히려 신뢰가 깎인다.
- hreflang·일본어/영어판 — 대상이 한국 여행자다. 도시 확장 때 다시 본다.
- FAQPage 삭제 — 구글 리치 결과는 끝났지만 다른 엔진이 읽고 해가 없다.
