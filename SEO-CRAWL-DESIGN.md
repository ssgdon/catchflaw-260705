# SEO-CRAWL-DESIGN — 구글이 상세 페이지를 가져가게 만드는 코드 3종 (2026-10-20, 설계 = Fable · 구현 = Opus)

> 이 문서만 보고 구현한다. 기준 코드 = `origin/main` **8c15bb2**(속도 최적화 반영본). 앵커(줄 번호)는 그 커밋 기준이며 함수 이름으로 다시 찾는다.
> 상위 설계 = `SEO-AEO-DESIGN.md` §4(슬러그)·§5-1(답 문단)·§7-4(전체 표). 이 문서가 그 세 항목의 **실행 사양**이고, 충돌하면 이 문서가 우선.
> 화면 규칙 = `UI-STANDARDS.md` §0·§3·§4·§14·§18, 문구 = 메모리 `copy-style-rules`(비유 금지·한 말투·숫자가 서로 설명·정밀 순위 금지). 빌드 게이트 `scripts/lint_ui.py`를 통과해야 한다.

## 0. 왜 · 무엇을 · 성공 기준

**진단(2026-10-20 GSC 내보내기)**: '발견됨 – 현재 색인이 생성되지 않음' 176 URL, **마지막 크롤링 전부 없음**(7/25부터 10/12까지 변화 0). 기술 차단은 없다(Googlebot 200·robots Allow·canonical·사이트맵 정상). 구글이 가져갈 가치를 낮게 보는 이유 = 외부 링크 0 · 7월 크롤 2쪽 미색인 판정 · `/hotels/ChIJ…` 기계 생성형 주소 · 얇은 내부 링크(호텔 189곳 중 홈·허브에서 바로 이어지는 곳 70, 107곳은 다른 호텔의 '대안' 슬라이더에서만 1번; 허브는 회원 84곳 중 15~17곳만 HTML에).

**이번 작업 3종**
- **A. 주소 슬러그 전환** `/hotels/ChIJ…` → `/hotels/hotel-monterey-fukuoka` + 옛 주소 301. 지금 아무 상세도 크롤되지 않아 비용이 0에 가깝다.
- **B. 내부 링크 두껍게** — 허브에 회원 전체를 HTML로(TOP 15 카드 + 나머지는 한 줄 행) + 전체 호텔 목록 페이지 `/hotels`(홈·푸터·검색·404에서 링크).
- **C. 상세 '답 문단'** — 호텔명·기간·리뷰 수·실망 확률·평균·판정·걸리는 점·괜찮은 점·기준일이 한 문단에 다 있는 인용용 첫 문단 + 같은 문장을 meta description으로.

**성공 기준**(배포 2~4주 뒤 GSC): '발견됨-미색인' 176 → 감소, '색인됨' 3 → 증가(허브·목록·검색량 상위 호텔부터). 코드 쪽 완료 기준은 §9 체크리스트.

**범위 밖**(이번에 안 함): 제목 태그 h2 정리(SEO-AEO §5-2), llms.txt·CSV(§8), 정적 비교 페이지·질문형 허브(§7-2·7-3), 리뷰 발췌 추가 서버 렌더(§5-3 — 확인 결과 위험도 아코디언에 인용 카드가 항목당 최대 6건, 호텔당 ~29건 **이미 HTML에 있음**. `quote_cards()`. 추가하지 않는다).

---

## 1. 현재 코드 사실 (8c15bb2 기준 앵커)

| 항목 | 위치 | 지금 |
|---|---|---|
| 상세 파일 쓰기 | `main()` `W(f'hotels/{pid}.html', build_detail(...))` · `written.append(pid)` (~L4460) | 파일명·URL = pid |
| 상세 canonical·OG·description | `build_detail` `canonical = f'{BASE}/hotels/{pid}'` (~L3716), `seo_desc` (~L3723) | description = "이름 실망 확률 N% (평균 M%). 청결·냄새·… 확인하세요." (항목 나열) |
| JSON-LD | `jsonld_detail(pid, meta)` (~L2731) `url = f'{BASE}/hotels/{pid}'` + BreadcrumbList item 3 | pid |
| 카드 링크 | `hotel_card()` (~L990) `<a href="{p}hotels/{pid}" class="hcard …">` — 홈·허브·상세 대안·최근 본 공용 | pid |
| 사이트맵 | `build_sitemap(detail_pids, collection_slugs)` (~L4343) `f'{BASE}/hotels/{pid}'`, lastmod `hotel_lastmod()`(pid 키) | pid |
| 리다이렉트 | `REDIRECTS = [('/best/pool','/best/luxury'), …]` (~L4278) → `W('_redirects', …)` | 2줄 |
| 검색 데이터 | `build_search_index()` (~L1490) → `data/index.js` `window.HOTELS=[{id,name,…}]` · `build_search_ac_index()` (~L1529) → `data/search_index.js` `window.CF_IDX` · `build_compare_data()` (~L1393) → `data/compare.js` `window.CF_CMP={pid:{…}}` | URL 없음, JS가 `'./hotels/' + h.id` |
| 검색 인라인 링크 | `build_search`/`build_index` 인라인 JS `'./hotels/' + h.id` — L1240(지도 팝업), L1275·L1844(구글맵 링크 해석 `r.hit.id`), L1624(지도 카드), L1733(목록 카드), L1830(자동완성 항목) | pid |
| js 파일 링크 | `js/compare-page.js` L108·L165·L170 `'./hotels/' + h.id` · `js/search-ac.js` L213 `hrefPrefix + h.id` | pid |
| 최근 본 호텔 | `js/engage.js` `cf_recent` = pid 배열(`H.pid` = `window.CF_PID`) · `build_recent()` (~L1299) 숨김 풀 카드의 href에서 `/hotels\/([\w-]+)/`로 pid를 뽑아 키로 씀 | href = pid라서 동작 |
| 허브 | `build_collection()` (~L3964): `ranked_p[:15]`만 `hub_card()`(와이드 카드), `low_p`(1년 100건 미만)는 `is_all`(캡슐)·순위 5곳 미만일 때만 | 회원 85~154곳 중 15곳만 HTML |
| 상세 첫 화면 | `.sect.information`: `name` → `{info_meta}` → `{price_info}` → `{info_sum}`(실망 확률·구글 평점·분석 리뷰 3칸, ~L3640) → `{lowrev_html}`(1년 100건 미만 주의, ~L3001) | 답 문단 없음 |
| 판정 문구 | `build_detail` `v_head`(~L3107): '리뷰가 적어 참고용이에요' / '실망한 투숙객이 적어요' / '실망한 투숙객이 많아요' / '후쿠오카 평균 수준이에요'(ratio<1.15) / '평균보다 실망이 잦아요' · 순위 구간 `h['rank_tier']` → `tier_txt` '실망 적은 호텔 상위 25% 안' | 위험도 섹션에서만 사용 |
| 한눈에 보기 재료 | `_neg` 튜플 (dot, lead html, 상세 html, 대분류, 소분류 평문 또는 None) ~L3214, `_pos`(괜찮은 점 html) ~L3238, `per = period_label(...)`(‘최근 1년’ 또는 ‘최근 N개월’), `h['analyzed']`, `CITY['asof']`·`md_ko()` | HTML 조각(em·b 포함) |
| 영문 이름 | `data-src/hotels_index.json` 항목 `en`(202곳 중 201 있음; `s`는 **sub_title**이니 슬러그 키로 쓰지 말 것) | — |
| 푸터 | `build_footer()` `.foot-links` '캐치플로 소개·산출 방법 · 정정·이의제기' | 목록 링크 없음 |
| 검색 페이지 | `build_search` `<div class="list"><ul id="results"></ul></div>`(~L2267) — JS가 그림, 서버 렌더 호텔 링크 1개 | — |

데이터·키가 **그대로인 것**(바꾸지 않는다): `data/q/{pid}.json`·`data/fe/{pid}.json`·R2 `quotes/{pid}.json`·`window.CF_PID`·`data-cmp-id`(비교함 localStorage `cf_cmp`)·`cf_recent`·`compare?ids=pid,pid`·GA4 이벤트의 hotel_id·`scripts/compare_pairs.json`·`check_rec.py`. 외부에 보이는 **페이지 주소만** 바뀐다.

---

## 2. A. 슬러그 URL 전환

### 2-1. 슬러그 정본 `scripts/slugs.json`
- 형식 `{"ChIJ…": "hotel-monterey-fukuoka", …}`. **git 추적**. 한 번 정하면 바꾸지 않는다(호텔명이 바뀌어도 유지 — 색인·외부 링크 보존).
- 생성 규칙(`generate.py`에 `slugify(s)`·`ensure_slugs(hotels_meta)` 추가, 빌드 시작 때 호출):
  1. 원문 = `hotels_index.json`의 `en`. 없으면 `None`.
  2. NFKD 정규화 → ASCII 외 제거(전각 '９'→'9', 'Ⅲ'→'III', 일본어·괄호 제거) → 소문자 → `[^a-z0-9]+` → `-` → 앞뒤 `-` 제거.
  3. 결과가 비었거나 **8자 미만**이면 자동으로 정하지 않고 **빌드를 중단**하며 pid·이름을 출력한다 → 사람이 `slugs.json`에 직접 적는다(§8 결정 2).
  4. 충돌(같은 슬러그)은 먼저 정해진 쪽이 유지, 나중 것에 `-2`, `-3`.
  5. 파일에 이미 있는 pid는 건드리지 않는다. 새 pid(주간 배치 편입)는 위 규칙으로 추가하고 파일을 다시 써서 **빌드 산출물과 함께 커밋**한다.
- 2026-10-20 데이터로 돌린 결과: 202곳 중 199 자동, 충돌 0. 수동 필요 4곳(§8 결정 2에 값 제시).
- 최장 51자(`del-style-fukuoka-nishinakasu-by-daiwa-roynet-hotel`) — 그대로 둔다.

### 2-2. 생성기(`scripts/generate.py`) 변경
- 전역 `SLUG = {}`(pid → slug), `def hotel_url(pid, depth=0)` → `f'{"../" * depth}hotels/{SLUG[pid]}'`, `def hotel_abs(pid)` → `f'{BASE}/hotels/{SLUG[pid]}'`. **pid로 href를 만드는 모든 곳**을 이 두 함수로 바꾼다. 검증: 빌드 뒤 `docs/`에서 `hotels/ChIJ` 문자열이 남는 곳은 `_redirects`·`data-pid`·`data-cmp-id`·`compare?ids=`·`data/q`·`data/fe`·R2 URL·`CF_PID`뿐이어야 한다(§9의 검사 스크립트).
- 바꿀 곳: `hotel_card` href · `jsonld_detail` url·crumbs · `build_detail` canonical·`og:url`(head()가 canonical로 만든다) · `build_sitemap` loc · `main()`의 `W(f'hotels/{SLUG[pid]}.html', …)` · 상세 `<link rel="alternate">` 없음 · 허브 `hub_card`는 `hotel_card` 경유라 자동.
- `hotel_card`의 `<li …>`에 `data-pid="{pid}"` 추가(최근 본 호텔이 href 대신 이걸로 키를 잡는다 §2-4).
- 데이터에 슬러그 키 **`u`** 추가(`s`는 자동완성 원본에서 sub_title이라 피한다): `build_search_index` 항목 `'u': SLUG[pid]` · `build_search_ac_index` 출력 항목 `'u'` · `build_compare_data` 항목 `'u'`.
- 인라인 JS: `build_index`·`build_search` 안에 공용 헬퍼 `function hurl(h){ return './hotels/' + (h.u || h.id); }`를 넣고 L1240·L1275·L1624·L1733·L1830·L1844의 `'./hotels/' + h.id`·`'./hotels/' + r.hit.id`를 `hurl(h)`·`hurl(r.hit)`로. `byId()`(search-ac.js)가 돌려주는 `{id,t}`에 `u`를 넣는다(`window.HOTELS` 항목의 `u`).
- `REDIRECTS`에 빌드 때 전 호텔 `('/hotels/'+pid, '/hotels/'+slug)`를 **append**(정적 규칙 189+2줄, Cloudflare 정적 한도 2,000 안). `.html` 옛 주소는 플랫폼이 먼저 308로 확장자를 떼고 우리 301로 이어지니(2홉) 따로 넣지 않는다. 사이트맵에서 빠진 옛 pid 주소(hidden 호텔 13·`best/pool`)는 404/기존 301 그대로.
- `docs/_headers`의 `/hotels/*` Link 규칙은 슬러그에도 그대로 맞는다(건드리지 않음).
- `data/q`·`data/fe` 파일명·`QDATA_URL`·`FAQEVID_URL`은 pid 유지.

### 2-3. JS 파일
- `js/compare-page.js` L108·L165·L170: `'./hotels/' + h.id` → `'./hotels/' + (h.u || h.id)` (`CF_CMP[pid].u`; `h.id`는 키에서 넣어 주던 그대로).
- `js/search-ac.js` L213: `hrefPrefix + h.id` → `hrefPrefix + (h.u || h.id)`.
- `js/engage.js`: 변경 없음(`cf_recent`는 pid).
- `js/detail-page.js`: 변경 없음(`?rv=` 처리는 주소와 무관).

### 2-4. 최근 본 호텔 페이지(`build_recent`)
- 숨김 풀에서 카드 키를 href 정규식 대신 `$(this).data('pid')`로 잡고, `rc-x data-rm`도 pid. 그 밖의 로직 동일. (href가 슬러그로 바뀌어도 localStorage의 pid 기록과 맞게.)

### 2-5. 배포 뒤(사용자·운영)
- 라이브 확인: 옛 주소 3곳 `curl -I https://catchflaw.com/hotels/{pid}` → `301` + `location: /hotels/{slug}`; 새 주소 200; canonical·`og:url`·JSON-LD url·사이트맵 `<loc>` 전부 슬러그; `hotels/ChIJ` 링크 0.
- `python scripts/indexnow.py`(사이트맵 전 URL 전송, 키 파일은 이미 라이브).
- GSC: Sitemaps에서 `sitemap.xml` 다시 제출 → URL 검사로 `/hotels`(목록)·허브 12·검색량 상위 호텔 순으로 하루 10개 '색인 생성 요청'. 네이버 서치어드바이저도 사이트맵 재제출(기존 등록 URL은 301로 따라온다).
- 블로그·인스타 등에 적어 둔 옛 주소는 301로 살아 있으니 손대지 않아도 된다(새 글부터 슬러그).

---

## 3. B. 허브 전 회원 + 전체 호텔 목록 `/hotels`

### 3-1. 공용 부품: 한 줄 호텔 행 `.hrow` (ds.css 끝 §v3 블록, UI-STANDARDS §18-5 '목록 행' 규격)
```html
<li class="hrow">
  <a class="hrow-name" href="../hotels/hotel-monterey-fukuoka">호텔 몬토레 후쿠오카</a>
  <span class="hrow-meta">텐진역 도보 3분 · 3성급 · 실망 확률 <b>2%</b> 적어요 · 평일 약 14만원</span>
</li>
```
- 생성기 함수 `hotel_row(pid, meta, h, depth)`: 이름 = `card_name(meta['title'])` 링크(`hotel_url`), 메타 = `' · '.join` of [`station_short(meta) or area_tag(meta)`, `stars_label(meta)`, 실망 확률 구(아래), `price_card_html`이 아니라 평문 '평일 약 14만원'(`meta['price_txt']`, 없으면 생략)].
- 실망 확률 구 = `실망 확률 <b>N%</b> ` + 판정어 한 단어: 배지 키(`badge_key(h)`)로 safe→'적어요', warning→(ratio<1.15 '평균 수준' / 그 외 '잦아요'), danger→'많아요', low·lowdanger→'N% · 리뷰 적음'(등급어는 `.blind` 없이 평문 — 색이 아니라 글자로 뜻을 전한다). 분석 준비 중은 '분석 준비 중'만.
- 스타일: 행 최소 64, 행 사이 1px `--line`, 이름 `--fs-body` 16/600 `--ink`, 메타 `--fs-meta` 14 `--ink-3`(숫자 `<b>`만 `--ink` 700), 모바일 2줄(이름/메타), PC(pc.css @media)는 한 줄에 이름 왼쪽·메타 오른쪽(`justify-content:space-between`, 메타 `white-space:nowrap`이 안 들어가면 2줄 유지). 상자·배지 없음, 보라 없음. 글자 토큰 외 px 금지(E1·E2).

### 3-2. 허브(`build_collection`)
- TOP 15 카드 블록 그대로. 그 **바로 다음**에 `hub-sect` 추가:
  - `<h2 class="hub-h2">나머지 {len(ranked_p) - len(top)}곳</h2>` + `.hub-sub` '추천순 · 최근 1년 리뷰 {RANK_MIN}건 이상' + `<ol class="hub-rows">`에 `ranked_p[len(top):]` 전부 `hotel_row`.
  - 이어서 `low_p`가 있으면 `<h2 class="hub-h2">리뷰가 적은 호텔 {n}곳</h2>` + `.hub-sub` '최근 1년 리뷰 {RANK_MIN}건 미만이라 순위 없이 보여드려요' + 행. (지금의 `low_cards` 와이드 카드 블록은 `is_all`(캡슐 5곳)에서만 유지하고, 그 외는 이 행 목록으로 대체.)
  - `is_all` 허브는 이미 전원 카드라 '나머지' 블록 없음.
- 검색 링크 버튼(`search_link`)은 지금 위치(TOP 블록 끝)에서 **행 목록 끝**으로 옮긴다(목록 다음에 '전체 검색').
- 허브 하나의 HTML 증가분 = 행 ~130B × 최대 140 ≈ 18KB. 허용.
- 허브 FAQ(`build_collection_faq`)의 'N곳' 숫자는 그대로(회원 수 기준).

### 3-3. 전체 호텔 목록 페이지 `docs/hotels.html` → `/hotels` (§8 결정 1)
- `build_hotels_list(hotels_meta, H)` 신설, `main()`에서 `W('hotels.html', …)`(상세 쓰기 뒤, 사이트맵 전).
- head: title `후쿠오카 호텔 전체 목록 {n_live}곳 | 캐치플로`, description `후쿠오카 호텔 {n_live}곳의 실망 확률·등급·평일 가격을 한 페이지에서. {asof} 기준, 매주 갱신.`, canonical `{BASE}/hotels`, `site_header(0, back='./')`.
- 본문(`<section id="hlist">`, 페이지 여백 24, 섹션 48·1px 선 리듬):
  - `<h1 class="page-title">후쿠오카 호텔 전체 목록</h1>` + 리드 한 문단: '{n_live}곳의 최근 1년 리뷰를 분석해 실망 확률을 매겼어요. {md_ko(asof)} 기준이고 매주 갱신해요. 산출 방법은 <a href="./about">소개·산출 방법</a>에 있어요.'
  - 동네별 섹션 `<h2>`: 하카타역 · 텐진 · 나카스·캐널시티 · 기온·오호리 · 그 외(`area_tag(meta)`로 묶기, `AREAS` 순서, 빈 묶음은 생략). 각 섹션 안 순서 = ranked(추천순 `REC` 내림차순) → 리뷰 적음(`scored and not ranked`, 실망 확률 오름차순) → 분석 준비 중(`not scored`, 이름순). 행 = `hotel_row`.
  - 섹션 제목에 곳 수: '하카타역 85곳'.
  - 맨 아래 `<a class="btn-gray btn-block" href="./search">조건으로 걸러 보기</a>`.
- 사이트맵에 `(f'{BASE}/hotels', 'weekly', '0.9')` 추가(`build_sitemap` rows, search 다음). lastmod는 기본(asof).
- 링크 진입점: 푸터 `.foot-links`에 '전체 호텔 목록' 추가(전 페이지) · 홈 '동네·동행별로 보기' 섹션 끝에 `.btn-gray.btn-block` '호텔 전체 목록 {n_live}곳' · 검색 페이지 `<div class="list">` **아래**(JS가 안 건드리는 자리)에 정적 `<a class="btn-gray btn-block" href="./hotels">전체 호텔 목록</a>` · 404 페이지의 '호텔 전체 보기' 버튼을 `/hotels`로.
- 분석 준비 중 호텔은 상세가 noindex라도 목록에 링크해도 된다(크롤러가 가서 noindex를 읽고 끝). 링크 텍스트 옆 메타는 '분석 준비 중'만(§8 결정 4).
- 주소 확인: `docs/hotels/` 폴더와 `docs/hotels.html`이 함께 있어도 Cloudflare 정적 자산이 `/hotels`를 `hotels.html`로 풀어 주는지 **배포 전 미리보기에서는 알 수 없다**. 배포 뒤 `curl -I https://catchflaw.com/hotels` → 200 확인. 404나 리다이렉트 루프면 즉시 §8 결정 1의 대안 주소 `/all-hotels`로 바꿔 재배포(파일명·링크·사이트맵·canonical 모두).

---

## 4. C. 상세 '답 문단' + description

### 4-1. 위치·마크업
> **2026-10-20 수정(배포 뒤 사용자 피드백 "길고 줄바꿈이 나빠 안 읽힘")**: 화면에 보이는 문단은 §4-2 전체 문장이 아니라 **판정 한 문장 + 근거 한 줄**(`.ia-meta`)로 줄였다. 호텔명은 h1, 걸리는 점·괜찮은 점은 '한눈에 보기'가 맡는다. §4-2의 전체 문장은 **meta description에만** 쓴다. 정본 = UI-STANDARDS §7 '상세 답 문단'.

- `.sect.information` 안 `{info_sum}` **바로 다음, `{lowrev_html}` 앞**에 `<p class="info-answer">…</p>`. 상자·배경 없음. `ds.css` §v3: `#detail .information .info-answer{margin-top:var(--sp-4);font-size:var(--fs-body);line-height:var(--lh-body);color:var(--ink);word-break:keep-all;}` + 숫자 `<b>` 700. PC는 같은 글자(pc.css 추가 없음). 글자 토큰·색 토큰만(E1·E3).
- `polish_breaks`가 자동 적용되니 `{DSEP}`·`.seg`는 쓰지 않는다(문단은 줄바꿈 자유).

### 4-2. 문장 틀 (재료는 전부 §1의 기존 변수 — 새 계산 금지, 화면의 다른 숫자와 같은 출처)
공통 재료: `name`, `per`(‘최근 1년’/‘최근 N개월’), `n = h['analyzed']`, `v = pct(h['p_crit'])`, `avg = pct(city['crit'])`, `v_head`, `tier_txt`, `_neg`·`_pos`의 평문, `md_ko(CITY['asof'])`.

**(1) 채점 + 순위 모수(`h['scored'] and h['ranked']`)**
```
{name}은(는) {per} 투숙객 리뷰 {n:,}건을 분석한 결과 실망 확률 {v}%로, {후쿠오카 평균 {avg}%와 비교한 판정 구}.
{걸리는 점 구}{괜찮은 점 구} ({md_ko(asof)} 기준, 캐치플로)
```
- 판정 구 = `v_head`를 그대로 문장에 녹인다(같은 말, 같은 경계): safe → `후쿠오카 평균({avg}%)보다 낮아 실망한 투숙객이 적어요` · warning(ratio<1.15) → `후쿠오카 평균({avg}%)과 비슷한 수준이에요` · warning → `후쿠오카 평균({avg}%)보다 실망이 잦아요` · danger → `후쿠오카 평균({avg}%)보다 훨씬 높아 실망한 투숙객이 많아요`. `tier_txt`가 있으면 뒤에 ` {tier_txt}예요.`(예: '실망 적은 호텔 상위 25% 안이에요.').
- 걸리는 점 구 = `_neg[:2]`를 평문으로: 희소 심각(`_neg[i][4] is None` 이고 db 발동) → `{SUB_PHRASE} 심각 리뷰 {n}건`, 소분류 → `{SUB_PHRASE} 불만({per} 리뷰의 {p}%)`, 폴백(최고 위험 카테고리) → `{cat_ko} 불만이 평균보다 많아요`. 조립: `걸리는 점은 A와 B이고, ` (하나면 `걸리는 점은 A이고, `; 없으면 생략).
- 괜찮은 점 구 = `_pos[:1]` 평문: `{cat_ko} 불만은 평균보다 N% 적어요`(`ratio_text` 문장 그대로) 또는 역 `{역} 도보 N분으로 가까워요`. 걸리는 점이 없고 괜찮은 점만 있으면 `{cat_ko} 불만이 적고 …`로 시작. 둘 다 없으면 `항목별 불만은 평균과 비슷해요.`
- 평문 만들기: 기존 html 조각에서 태그 제거(`re.sub(r'<[^>]+>', '', x)`)하고 `{DSEP}`·`{NB}`를 공백/'·'로 치환. 조사는 `josa_eun(name)` 등 기존 조사 함수 사용(기본형 '은(는)' 표기 금지).
- 예: `호텔 오리엔탈 익스프레스 후쿠오카 텐진은 최근 1년 투숙객 리뷰 611건을 분석한 결과 실망 확률 8%로, 후쿠오카 평균(4%)보다 실망이 잦아요. 걸리는 점은 벌레 심각 리뷰 3건과 실내 온도 불만(최근 1년 리뷰의 8.5%)이고, 위치 불만은 평균보다 63% 적어요. (2026년 10월 19일 기준, 캐치플로)`

**(2) 채점 + 리뷰 적음(`scored and not ranked`)** — 숫자는 보여 주되 참고용임을 문장 안에서 먼저:
```
{name}은(는) {per} 리뷰가 {n:,}건뿐이라 참고용이에요. 그 리뷰로 본 실망 확률은 {v}%({후쿠오카 평균 {avg}%})예요. {걸리는 점 구}{괜찮은 점 구} ({asof} 기준, 캐치플로)
```
(`lowrev_html` 주의 상자는 그대로 그 아래에 남긴다. 같은 뜻을 두 번 말하지만 하나는 문단, 하나는 주의 표시라 허용 — §8 결정 3.)

**(3) 분석 준비 중(`not scored`)**
```
{name}은(는) 분석한 리뷰가 {n}건뿐이라 아직 실망 확률을 내지 않았어요. {MIN_REVIEWS}건 이상 쌓이면 공개해요. 위치·가격·구글 평점은 아래에서 볼 수 있어요. ({asof} 기준, 캐치플로)
```

### 4-3. description
- `seo_desc`를 답 문단의 **첫 문장 + 걸리는 점 구**로 교체(채점 호텔). `head()`가 150자에서 자르니 첫 문장이 150자 안에 호텔명·실망 확률·평균·판정을 담도록 걸리는 점은 뒤에 둔다. 리뷰 적음·분석 준비 중도 각 문단의 첫 문장.
- `seo_title`은 그대로.

### 4-4. 문구 검사(카피 원칙)
- 같은 화면의 숫자가 서로 설명되는지: 요약 3칸의 `{v}%`·`{n}건`과 문단의 숫자가 **같은 변수**에서 나온다. 위험도 섹션 `v_head`와 문단 판정 구가 같은 분기다.
- 비유·'통과'·'확인이 필요해요' 금지. 정밀 백분위 금지(`tier_txt`만).
- 360px에서 뜻이 갈리는 줄바꿈이 보이면 `polish_breaks` 묶음 규칙(UI-STANDARDS §15)에 추가.

---

## 5. 문서·규칙 갱신(같은 커밋에)
- `CLAUDE.md` 프론트 규칙: 페이지 목록에 `hotels(전체 목록)` 추가, 상세 주소 `hotels/{slug}`(정본 `scripts/slugs.json`, 옛 pid 주소 301) 한 줄.
- `UI-STANDARDS.md` §18-5 목록 행에 `.hrow` 규격 한 줄 · §7(데이터 표기)에 답 문단 틀 요약 한 줄.
- `SEO-AEO-DESIGN.md` §9 체크리스트 B2·C1·C3 완료 표시(날짜·커밋).
- 메모리(`seo-setup`·`traffic-index-2610`)는 Fable이 배포 보고 뒤 갱신.

---

## 6. 영향 점검(구현 중 확인)
- 상세 184쪽 파일명이 바뀌므로 `docs/hotels/` 옛 pid 파일은 빌드가 `rmtree`로 지운다 — 커밋 diff가 크다(삭제 184 + 추가 184). 정상.
- `_redirects` 정적 189줄 + 기존 2줄. 플랫폼 한도 2,000.
- `data-pid`를 붙인 `hotel_card`는 홈·허브·상세 대안·최근 본 전부에 들어가지만 CSS 영향 없음.
- `window.HOTELS` 항목에 `u` 추가 → `data/index.js` +4KB, `CF_IDX`·`CF_CMP`도 소폭.
- 허브 HTML +18KB/쪽, 목록 페이지 ~40KB. 상세 +0.5KB(문단).
- `lint_ui` E14(h1 1개): 목록 페이지 h1 1개·허브는 기존대로. `.hrow` 글자 토큰만.
- 검색 페이지 인라인은 파싱 시점 실행이라 `hurl` 정의를 **사용하는 코드보다 위**에 둔다(2026-10-20 defer 규칙: 홈 인라인은 `$(function)` 안).
- `check_rec.py`·`compare_pairs.json`은 pid라 무관. `scripts/indexnow.py`는 사이트맵을 읽으니 자동.

---

## 7. 검증 스크립트(구현 세션이 만들어 두고 빌드마다 돌린다 — `scripts/check_links.py`, 커밋)
1. `docs/**/*.html`의 모든 `href="…hotels/…"`가 실제 파일(`docs/hotels/{slug}.html`)로 풀리는지(깨진 링크 0).
2. `docs/`에서 `hotels/ChIJ` 문자열 위치가 허용 목록(§2-2)뿐인지.
3. 사이트맵 `<loc>` 수 = 상세(scored) + 허브 12 + 정적(홈·search·recommend·about·hotels) · 모든 loc가 파일로 존재.
4. `_redirects` 줄 수 = 호텔 수 + 2, 대상 슬러그 파일 존재.
5. 호텔 189곳 모두 **홈·허브·목록 중 어디선가** 링크됨(홈/허브/목록 서버 렌더 href 집합 ⊇ 전 호텔).
6. 상세 184쪽 모두 `.info-answer` 1개, description에 호텔명·'실망 확률' 포함(채점 호텔).

---

## 8. 사용자 결정 — **2026-10-20 사용자 확정: 아래 권고안 전부 채택**(1 `/hotels` · 2 수동 슬러그 4곳 제시값 · 3 숫자 포함+참고용 명시 · 4 넣는다 · 5 ItemList 없음 · 6 한 번에 push, 커밋 C→B→A)
1. **목록 페이지 주소**: 권고 `/hotels`(`docs/hotels.html`). 배포 뒤 200이 아니면 `/all-hotels`.
2. **수동 슬러그 4곳**(자동 생성이 비거나 2자):
   - `ChIJi_euFMyRQTURImJjbEDysoE` SG레지던스 인 하카타 → `sg-residence-inn-hakata`
   - `ChIJ-xf-ueCRQTURvRoCqKKk6Zo` 후쿠오카쉐어호텔 → `fukuoka-share-hotel`
   - `ChIJWbnV_8aRQTURX1bIzMiGmGE` 하카타 에키마에 SB 호텔 → `hakata-ekimae-sb-hotel`
   - MK 호텔즈 니시나카스(en 'MKホテルズ西中洲' → 'mk') → `mk-hotels-nishinakasu`
   - 그 밖에 8자 미만이 더 나오면 빌드가 멈추고 목록을 출력한다 → 같은 방식으로 적는다.
3. **리뷰 적음 호텔의 문단**: 권고 (2)처럼 숫자 포함 + 참고용 명시(주의 상자도 유지). 숫자를 아예 빼고 싶으면 '{n}건뿐이라 확률은 참고용이에요'까지만.
4. **분석 준비 중 호텔을 목록·허브 행에 넣을지**: 권고 넣는다(링크 + '분석 준비 중').
5. **목록 페이지 JSON-LD `ItemList`**: 권고 넣지 않는다(상세 Hotel 마크업으로 충분, 평점 정책 가드 유지).
6. **배포 단위**: 권고 A·B·C를 한 번에 push(사이트맵이 두 번 바뀌지 않게). 커밋은 C → B → A 순 3개.

---

## 9. 구현 순서(Opus · 각 단계 빌드·확인·커밋)
- [ ] 0 worktree: `C:\Users\do931\dev\catchflaw_speed`(branch `speed` = main)에서 `git fetch && git reset --hard origin/main` 후 새 브랜치 `crawl`, `data-src`는 VM에서 복사(`scp opc@158.179.173.211:/home/opc/catchflaw/data-src/*.json data-src/`). 다른 세션 push 확인 후 시작.
- [x] C1 답 문단 + description(§4) — `e4f61f24` → 상세 3종(순위·리뷰 적음·준비 중) 360·375·1280 스크린샷, `lint_ui` 통과 → 커밋 `feat(detail): 답 문단`.
- [x] B1 `.hrow` 부품 + `hotel_row()` → 허브 '나머지'·'리뷰 적은' 블록(§3-2) → 허브 3종(지역·동행·캡슐) 확인 → 커밋. — `873bbaf3`
- [x] B2 목록 페이지 `/hotels`(§3-3) + 진입 링크 4곳 + 사이트맵 → 커밋. — `e15ac6ef`
- [x] A1 `slugs.json` 생성기(§2-1) → 수동 4곳 → `hotel_url`·`u` 키·인라인 `hurl`·js 3파일·최근 본 `data-pid`·REDIRECTS·사이트맵·canonical(§2-2~2-4) → 커밋. — `4b60f004`(수동 슬러그 4곳 + H 호텔 `h-hotel-fukuoka`)
- [x] V `scripts/check_links.py`(§7) 6항목 통과, 로컬 미리보기에서 홈→허브→상세→최근 본→비교→검색(자동완성·지도 팝업·구글맵 링크 해석) 링크 클릭 경로 확인, 콘솔 오류 0.
- [ ] 문서 갱신(§5) → `pull --rebase` → push(사용자 지시 "배포") → 라이브 확인(§2-5) → `python scripts/indexnow.py` → 사용자에게 GSC 사이트맵 재제출·색인 요청 순서 안내 → 보고.
