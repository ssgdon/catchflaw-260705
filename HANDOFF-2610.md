# HANDOFF 2026-10-09 — 클라우드 인수 세션 (라이브 QA · 가격 브랜치 리뷰)

- 기준: origin/main `6ae7a7e` (라이브 catchflaw.com = 이 커밋의 docs)
- 이 세션의 결과는 **브랜치로만** 올렸다. main push 없음, force push 없음.
  - `cloud/qa-2610` — 라이브 QA에서 찾은 소스 수정 10커밋 + 이 문서
  - `wip/price-overhaul` — 가격 개편 리뷰 수정 2커밋 추가(f445a1a → b2cb957, fast-forward)
- data-src·VM 접근 없음 → `generate.py` 빌드·docs 갱신은 하지 않았다. **docs 재빌드·배포는 로컬이 한다.**
- 검사: `python -m py_compile scripts/generate.py`, `node --check js/*.js`, `python scripts/lint_ui.py` 모두 통과.
- 근거 자료(스크린샷 139장, 점검 스크립트, 원시 결과 jsonl): `C:\Users\do931\dev\catchflaw_2607\archive\qa-2610\` (gitignore 폴더)
  - 스크린샷 `archive\qa-2610\shots\*.png` / 전 호텔 팝업 대조 `archive\qa-2610\popup_all.jsonl`
  - 재실행: `python archive/qa-2610/popup_all.py ids.txt out.jsonl`, `python archive/qa-2610/page_qa.py <tag> <url> 360,375,1280`

---

## 1. 작업 A — 라이브 점검 결과 (Playwright headless Chromium, 360·375·1280)

판정: OK = 기대대로 / **문제** = 아래 2절에서 소스 수정 / 보고 = 데이터·결정 사항이라 수정 안 함

| 페이지 | 360 | 375 | 1280 | 점검 내용·결과 | 스크린샷 (archive/qa-2610/shots/) |
|---|---|---|---|---|---|
| 상세 · 실망 확률 영역 (6곳: 안전 ChIJ-xGc… / 위험 ChIJOd14…·ChIJcVWb… / 리뷰 적음 ChIJsfwE… / 평균 수준 ChIJCc2Y… / 평균보다 잦음 ChIJP-fg…) | OK | OK | OK | 숫자 → 판정 → 기준(평균·순위 배지) → 근거 2줄 순서 정상. 판정 문구 분포(170곳): 적어요 46 · 평균 수준 37 · 평균보다 잦아요 29 · 많아요 14 · **리뷰가 적어 참고용이에요 44**(5번째 문구, 리뷰 적음 배지용). 가로 스크롤 0 | `detail_*_{w}_prob.png`, `detail_*_1280_top.png` |
| 상세 · ? 산출 기준 토글 | OK | OK | OK | `.basis-toggle` 클릭 시 펼침(0 → 242~287px), 다시 클릭 시 닫힘. 실망 리뷰 정의 문구 = "심각한 문제(벌레·파손·안전 위협 등)를 겪었거나, 불만과 함께 다시 안 가겠다고 한 리뷰" 일치 | 같은 파일 |
| 상세 · 근거 줄 '실망 리뷰 M건' 팝업 | OK | OK | OK | **채점 170곳 전수**: M>0인 164곳 모두 팝업 카드 수 = M(불일치 0), M=0인 6곳은 버튼 없음. 6곳×3너비도 동일 | `detail_*_{w}_popup.png`, `popup_all.jsonl` |
| 상세 · 근거 줄 줄바꿈 | **문제** | **문제** | OK | '실망 리뷰 / 27건' — 숫자만 다음 줄 | `detail_ChIJOd141YWR_360_prob.png` |
| 상세 · 떠 있는 버튼 스크롤 숨김 | **문제** | **문제** | **문제** | 아래로 스크롤해도 안 숨음. 원인 ① 생성 페이지가 `js/common.js`를 로드하지 않음 ② 상세는 CSS 우선순위로 opacity가 안 빠져 버튼 윗부분이 화면 아래에 걸림 | `detail_*_scrolldown.png`(라이브), `fixed_detail_{360,1280}_scrolldown.png`(수정 주입) |
| 상세 · 누구와 가세요 | **문제(심각)** | **문제** | **문제** | 일행 칩(혼자·둘이·일행·아이 동반)이 사라지고 FAQ 칩 글자('더블룸트윈룸엑스트라베드 유료')+'아이 동반' 하나만 남음. **채점 170곳 전부** | `live_who_360_broken.png` |
| 상세 · PC 오른쪽 결정 카드 | — | — | OK | 실망 확률·판정·구글 평점·분석 리뷰·1박·가까운 역·최저가 CTA·비교 담기·공유, 스크롤 따라 고정 | `detail_*_1280_scrollup.png` |
| 상세 · 리뷰 카드·팝업 소분류 표기 | **문제** | **문제** | **문제** | 카드 날짜줄·팝업 소분류 칩이 내부 키('동네 분위기', '청소 안 됨', '악취', '좁은 방')를 그대로 표시 | `detailA_360.png` |
| 상세 · 상단 리뷰 배지 | — | — | **문제(경미)** | '분석 리뷰 187개' vs 결정 카드 '187건' 단위 불일치 | `detail_ChIJOd141YWR_1280_top.png` |
| 상세 · 리뷰 적음·미채점 호텔 | OK | OK | OK | ChIJsfwE…(리뷰 적음), ChIJebeP…(미채점) 오류·가로 스크롤 없음 | `detailLow_*.png`, `detailUnscored_*.png` |
| 용어 '밤길·동네 분위기' | **문제** | **문제** | **문제** | 근거 줄·아코디언·범례·about·허브 FAQ는 통일됨. 리뷰 카드/팝업만 '동네 분위기'(위 행) → 수정. '밤길 치안'은 사이트 전역 0건 | — |
| 'AI가 N건 분석' = 글 리뷰 | OK | OK | OK | 홈 "리뷰 3만 개를 분석", 허브 "글 리뷰 3만 건 AI 분석" 모두 `ai_reviews_total()`(글 리뷰) 사용. (단위 '개' vs '건'은 보고 4) | `home_*.png` |
| 검색 · 카드 호텔명 | OK | OK | OK | 단어 중간 끊김 0건(전 텍스트 노드 자동 검사). 2줄 이름은 띄어쓰기 자리에서만 | `search_{w}_top.png` |
| 검색 · '비교' 토글 위치 | OK | OK | OK | `.r-foot` 안, 카드 오른쪽 아래(오른쪽·아래 여백 0) | 같은 파일 |
| 검색 · 정렬 메뉴 | OK | OK | OK | 열림·화면 안(가로 넘침 없음). 단 추천순 설명이 REC_SORT_DESC와 다름 → 수정. 요약줄 '실망확률' 붙여쓰기 → 수정 | `search_{w}_sortmenu.png` |
| 비교 A (미야코·미즈카·리브맥스) | **문제** | **문제** | OK | 한눈에 비교 박스 OK, '평균의 / N배' 2줄·막대 높이 일치 OK. '10% 리뷰 / 적음' 갈림, 자주 나온 불만 '1%' vs '12.5%' 소수점 불일치 | `cmpA_*.png`, `fixed_cmpA_360_lowreview.png` |
| 비교 B (도큐스테이·마리노아·언플랜) | **문제** | **문제** | OK | '리뷰에서 자주 나온 불만' 1위 행: '낡은 시설· / 고장'이 2줄이 되며 그 칸 비율만 한 줄 아래 → 수정 후 세 칸 top 동일 | `cmpB_*.png`, `fixed_cmpB_{360,1280}_top3.png` |
| 홈 · 비교 카드 .vs-card | OK | OK | **문제(경미)** | 3열 표·이긴 열 색 면 OK. PC 4장 높이 291/312/333px로 들쭉날쭉·결론 줄 높이 제각각 → 수정 후 354px 통일 | `home_*.png`, `fixed_home_1280_vs.png` |
| 홈 · 추천 슬라이더·문구 줄바꿈 | OK | OK | OK | 단어 중간 끊김 0, 가로 스크롤 0 | `home_*.png` |
| 허브(나카스)·about | OK | — | OK | 끊김 0, 가로 스크롤 0 | `hubNakasu_*.png`, `about_*.png` |
| ds.css `p{word-break:keep-all}` | OK | OK | OK | 소스 css/ds.css 16행·라이브 /css/ds.css 모두 존재 | — |
| 단어 중간 끊김 전반 | OK | OK | OK | 전 텍스트 노드 검사: 비교표 2곳만(아래 보고 1·2, 데이터·긴 고유명사) | `pages.jsonl` |

한계: 수정 검증은 라이브 페이지에 로컬 js/css를 주입(Playwright route·add_script_tag)해서 했다. generate.py 쪽 수정(일행 칩·소분류 표기·줄바꿈 묶음·문구)은 data-src가 없어 py_compile + 정규식 단위 확인까지만 했으므로 **로컬 빌드 후 360·1280에서 한 번 더 확인**할 것.

---

## 2. 고친 것 — 브랜치 `cloud/qa-2610` (origin/main 6ae7a7e 위, 심각도순)

| 커밋 | 내용 | 원인 |
|---|---|---|
| `fbf180a` | 상세 '누구와 가세요' 일행 칩 복구 | 6ae7a7e가 루프 안에서 FAQ 칩 목록을 바깥 변수 `_chips`(일행 버튼 목록)에 대입 → 변수명 `_fc`로 분리 |
| `e1c7683` | 떠 있는 버튼 스크롤 숨김 실제 동작 | `head()`가 `js/common.js`를 로드하지 않음 → defer로 추가. 상세 `#detail ~ #float{opacity:1}`(id 2개)가 숨김 규칙을 이김 → `html.is-scroll-down #detail ~ #float` 추가 |
| `432ba28` | 리뷰 카드·근거 팝업 소분류 표기 = SUB_PHRASE | 서버 카드 `q.scat`, JS 카드 `q.s`·칩 라벨이 내부 키 그대로 → `window.QSUBKO` + `subKo()` (필터 키는 그대로) |
| `d902b85` | `_GLUE`에 '한글 단어 + N건' 묶음 | '실망 리뷰 / 27건' 갈림 (UI-STANDARDS §15) |
| `dff811b` | 비교: '리뷰&nbsp;적음', 자주 나온 불만 `toFixed(1)` | 좁은 3열 갈림, '1%' vs '12.5%' |
| `4fb37cc` | 비교: 순위 행 비율 숫자 높이 맞춤 + `glue()` 가운뎃점 결합자 | 항목명 2줄 칸만 숫자가 내려감, JS 문구는 polish_breaks 밖 |
| `16daa7b` | 홈 PC 비교 카드 4장 높이·결론 줄 통일(pc.css) | 모바일 flex의 `align-items:flex-start`를 PC 그리드가 물려받음 |
| `3c9f377` | 검색 요약 '실망확률' → '실망 확률' | UI-STANDARDS §1 용어 |
| `bc8f659` | 상세 상단 '분석 리뷰 N개' → 'N건' | 같은 화면 결정 카드·근거 줄과 단위 불일치 |
| `f350639` | 검색 정렬 '추천순' 설명 = `REC_SORT_DESC` | §16 정본과 다른 문구(구글 평점 축 누락) |

`cloud/qa-2610`과 `wip/price-overhaul`은 `git merge-tree`로 충돌 없음 확인.

---

## 3. 로컬에서만 할 수 있는 남은 일

### 인계받은 목록 (그대로)
- 가격: VM에서 `price_sample.py --budget 6` 실행 중(2026-10-09 18시대 누적 $3.66, 숙박일 10/21·10/24·11/4·11/7·11/18 완료). 끝나면 VM에서 `export_pg.py --out /home/opc/catchflaw/data-src`(기본 출력 경로는 배포가 안 읽는 /home/opc/data-src이니 반드시 --out) → 로컬에서 data-src scp → `wip/price-overhaul`을 origin/main에 rebase·병합 → generate.py 빌드 → push. 원래 세션이 말한 '확인 조건 두 가지'는 기록에 내용이 없음 → 로컬 세션이 RECOMMEND-PRICE-DESIGN.md §7·§9에서 확인.
- 메인 폴더(catchflaw_2607)는 아직 HEAD 24e5915에 가격 개편 미커밋 변경이 남아 있다(이제 wip/price-overhaul에 보존됨). 병합 후 메인 폴더 정리는 사용자 결정.
- 분류 신고 기능('캐치플로 커뮤니티 피벗 검토' 세션): 사용자가 Supabase SQL(`pipeline/sql/classification_reports.sql`, 로컬 전용)과 VM `./venv/bin/python setup_report_overrides.py`(review_findings 뷰를 finding_overrides 조인으로 교체, --rollback 있음)를 실행해야 함 → 그 뒤 피벗 세션이 cron(*/15 report_review.py, 정본 pipeline/crontab.new) 등록. 프론트 신고 버튼(js/report.js)은 사용자 진행 승인 대기.
- 정리할 로컬 worktree: catchflaw_rec(rec-home2), scratchpad wt4(evidence-popup), .claude/worktrees/friendly-curie-288145, cf_price(wip/price-overhaul).

### 이 세션이 추가하는 것
1. **`cloud/qa-2610` 배포** — 최신 origin/main 위로 rebase(또는 병합) → `python scripts/generate.py` → 상세 1곳에서 일행 칩 4개·스크롤 숨김·팝업 칩 '밤길·동네 분위기' 확인(360·1280) → push. 일행 칩 회귀는 채점 170곳 전부라 가격 개편보다 먼저 배포 권장.
2. **cf_price 워크트리의 로컬 `wip/price-overhaul`이 origin보다 2커밋 뒤** (origin b2cb957). 작업 전 `git pull --ff-only`.
3. **'확인 조건 두 가지' 후보**: wip 브랜치의 RECOMMEND-PRICE-DESIGN.md §5.5 "남은 일" ① 날짜 8개 수집 완료 후 채점 호텔 80% 이상이 숙박일 ≥3 ② 시트5 18곳 재대조로 배율 1.0±0.15. (§7 P1 마지막 항목과 같은 내용) — 원래 세션 의도인지 로컬이 최종 확인.
4. 데이터 문제 (수정 안 함, 보고만):
   - FAQ 칩 띄어쓰기 소실: 미야코 호텔 하카타 `fq.family` "곁들여자는무료 · 유아용온수풀", `fq.luggage` "체크인전 O · 체크아웃후O" → 비교표에서 단어 중간 강제 줄바꿈. `faq_extract.py` 칩 정규화 확인.
   - 호텔 마리노아 리조트 후쿠오카(ChIJn1TykzuTQTURdHnTUOXWZI0) 가까운 역 "텐진역 도보 105분" — 가장 가까운 역 산출이 시내 역 목록에 한정된 듯. 도보 30분 초과면 '역에서 멂' 등으로 바꾸거나 역 목록 확장 검토.
   - 호텔 수 표기 3가지: 홈 히어로 "후쿠오카 호텔 170곳 분석 완료"(채점), 검색 "후쿠오카 호텔 184곳"(수집중 포함), CLAUDE.md "173곳". 의도된 구분이면 검색 쪽에 '(분석 170곳)' 병기 검토.
   - 허브 요약 "최근 1년 리뷰 19,546건을 분석했어요"는 `H[p]['analyzed']`(별점만 리뷰 포함) 합. 같은 페이지 하단 "글 리뷰 3만 건 AI 분석"과 대상이 다름 — '분석' 대신 '최근 1년 리뷰 N건 기준' 등 문구 결정 필요.
   - 홈 히어로 "리뷰 3만 개를 분석해" — 사이트 다른 곳은 '건'. '글 리뷰 3만 건' 통일 여부 결정.
5. 경미한 UI 메모 (결정 필요, 수정 안 함): 검색 카드 360에서 '· 1박 약 11만원'이 줄 첫머리에 '·'를 달고 시작(구분점을 뒤 항목에 붙이는 현행 설계의 부작용). 근거 팝업 안내문 '…다시 안 가겠다고 한 / 리뷰예요' 마지막 단어 매달림(`.sheet-note`에 `text-wrap:pretty` 후보). 360 상세 '+ 비교' 플로팅이 근거 줄 화살표를 가림(스크롤 숨김 배포 후 재확인).

---

## 4. 작업 B — `wip/price-overhaul` 리뷰 (f445a1a → b2cb957)

리뷰 대상: `git diff origin/main...origin/wip/price-overhaul` (generate.py price_stats·md_ko·CITY['price_seen']·상세 .price-note·홈/허브/FAQ 문구, compare-page.js '1박 가격', ds.css .price-note, CLAUDE.md 가격 줄).

### 추가한 커밋 (wip/price-overhaul에 fast-forward push)
- `4634a3c` 가격 기준 문구 정본 `PRICE_BASIS = '2인 1박 날짜별 보통 가격'` — 홈 슬라이더·허브·상세 각주·FAQ가 세 가지 다른 말을 쓰던 것 통일. 검색 정렬 '1박 가격 낮은 순' 설명이 옛 "구글 최저가 기준 · 날짜 따라 달라요"로 남아 있던 것 갱신. 상세 `.price-note`·허브 `.hub-sub`는 `.desc`가 아니라 polish_breaks가 ' · '를 DSEP로 안 바꿈 → `{DSEP}`+`.seg` 직접. 표본 없는 호텔(price_raw 폴백 '약 N만원')은 "날짜별 보통 가격"이 아니므로 각주를 "2인 1박 기준 · 날짜에 따라 달라요"로 분리, 표본 있는 호텔만 "{PRICE_BASIS} · M월 D일 확인".
- `b2cb957` `'보통 9~12만원'`에 NBSP — 검색 카드·비교표·홈 비교 카드는 JS/데이터 경로라 polish_breaks 밖.

### 확인한 것 (문제 없음)
- UI-STANDARDS: 새 CSS는 ds.css 한 줄(토큰만, `--fs-meta` 14px, `--ink-3`), lint 통과. 이모지·hex·px 글자 없음.
- `price_stats` 단독 실행: 빈 표본 → None, 1일 → '약 10만원', 4일 → '보통 9~12만원'(중앙값 107,500), 같은 숙박일 gmaps(US$)·ghotels(KRW) 동시 → ghotels 우선, 지난 숙박일 제외, 좁은 범위(9.9~10.1만) → '약 10만원', 미지원 통화 → None.
- `price_band`를 표시 만원 기준으로 바꾼 것: '약 10만원'이 '10만원 미만'에 들던 어긋남 해소.
- 비교표 라벨 '1박 가격', 상세 PC 카드 '1박 가격 · 2인', 홈 비교 카드 '1박', 검색 카드 '1박' — 라벨 계열 일관.
- `CITY['price_seen']` 폴백 = `CITY['data_asof']`('2026년 10월') → "(2026년 10월 확인)"으로 자연스럽게 읽힘.
- `cloud/qa-2610`과 병합 충돌 없음.

### 남은 지적 (병합 전 로컬 판단)
1. **병합 시점**: 지금 데이터(§5.5: ghotels는 10/21 하루분)로 빌드하면 대부분 호텔이 숙박일 1~2개 → '약 N만원'인데 홈·허브 설명은 "날짜별 보통 가격"이라 말이 앞선다. 수집 완료 + 커버리지 조건(위 3-3) 충족 뒤 병합.
2. 가격대 필터·슬라이더는 중앙값 기준이라 "보통 9~12만원" 호텔이 '10만원 미만'(중앙값 9.4만 → 9만)에 들어갈 수 있다. 의도라면 그대로, 아니면 밴드 판정을 25%값(lo)으로 하는 안 검토.
3. JSON-LD `priceRange`에 '보통 9~12만원'(한글)이 들어간다. 구글 권장 형식은 '₩90,000-₩120,000' — SEO 세션에서 결정.
4. 검색 '1박 가격 낮은 순' 정렬 노출 여부는 §5.5 ④(커버리지 80% 뒤 복구)와 §9-4 결정을 따를 것. 현재는 그대로 노출.
5. `price_stats`의 `observed_on`/`stay_date`는 ISO 문자열 비교에 의존 — `export_pg.py`가 날짜를 'YYYY-MM-DD' 문자열로 내보내는지 재추출 후 한 번 확인.
