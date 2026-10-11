# 재분류 적용 절차 (로컬 세션 / VM)

클라우드 세션에서 Opus 2회 검증(1차 검증 → 2차 반박 확인)으로 만든 수정 목록을 DB에 반영하고, 프롬프트를 v5.8로 올리는 절차. 설계·결과는 `RECLASSIFY-AUDIT-2610.md`.

## 0. 파일

| 파일 | 건수 | 내용 | 적용 |
|---|---|---|---|
| `corrections_classification.jsonl` | 323 | 분류 변경(소분류·대분류) 또는 판정 해제(`new_grade: "정상"`, 131건). `source`: audit-2610 277 · policy-2610 46 | **적용** |
| `corrections_grade.jsonl` | 140 | 등급만 변경(심각→주의 91, 주의→심각 49) — 벌레·곰팡이·동네 분위기·객실 보안 제외 | SPEC.md 대조 후 적용 |
| `hold_owner_review.jsonl` | 33 | 희귀 소분류 등급 변경 제안 — 운영자가 이미 전수 점검한 영역 | 운영자가 한 건씩 보고 결정 |
| `fewshot_v58.md` | — | 오류 패턴 · 규칙 추가안 · 예시 · 회귀 체크리스트 | prompt_v5.py v5.8 |
| `RUBRIC.md` | — | 검증 기준(체계 표 + 경계 규칙) | 참고 |

행 키: `place_id` + `fid`(사이트·신고 기능과 같은 판정 ID) + `rid`(리뷰 ID). `cur_*`는 검증 당시 값, `new_*`는 바꿀 값. 2026-10-10 빌드(data-src 10-10) 기준으로 대조했고, 그 사이 바뀐 판정은 이미 뺐다.

## 1. 적용 (분류)

1. **기존 신고 반영 코드 재사용**: `classification_reports` → `report_review.py`가 판정을 바꾸는 함수(fid로 판정 행을 찾아 cat/sub/grade 갱신 또는 판정 해제)를 그대로 쓴다. 디스코드 승인 단계는 건너뛰는 배치 모드로 호출하거나, 같은 UPDATE를 하는 작은 스크립트 `pipeline/apply_reclass.py`를 만든다.
2. **안전장치**
   - 반영 전 해당 판정 행 백업(`reclass_backup_2610` 테이블 또는 JSON 덤프).
   - 행마다 `cur_*`가 지금 DB 값과 같은지 확인 — 다르면 건너뛰고 기록(그 사이 다른 반영이 있었다는 뜻).
   - 드라이런으로 건수·변경 요약 출력 → 확인 → 반영.
   - 출처 기록: 가능하면 판정 행에 `reclass_src='audit-2610'` 같은 표시(없으면 백업 테이블로 추적).
3. `new_grade: "정상"`은 신고 승인 시 '불만 아님' 처리와 같은 방식(판정 삭제 또는 정상 등급)으로.
4. 같은 리뷰(`rid`)에 판정이 여러 개면 각 `fid`만 바꾼다(다른 판정은 그대로).

## 2. 적용 (등급) — 별도

- `corrections_grade.jsonl`은 `pipeline/eval_v5/SPEC.md`의 심각/주의 정의와 대조한다. 검증 기준은 "심각 = 방 변경·환불·조기 퇴실·건강 피해·안전 / 4–5성 리뷰의 '유일한 단점'·재방문 의사는 심각 아님"이었다. SPEC과 어긋나면 SPEC을 따른다.
- 심각→주의가 91건이라 **실망 확률이 내려가는 호텔이 생긴다.** 반영 전 `score.py`로 전후 실망 확률·배지·순위 변화를 뽑아 확인한다(위험 배지 변동 호텔 목록). `scripts/check_rec.py`도 다시 돌린다.

## 3. 프롬프트 v5.8

- `fewshot_v58.md`의 규칙·예시를 `pipeline/prompt_v5.py`에 넣는다(필드 이름은 실제 출력 스키마에 맞춘다).
- 회귀: `pipeline/eval_v5` SPEC 세트 전후 비교 + `corrections_classification.jsonl` 리뷰들을 다시 분석해 `new_*`와 맞는 비율 확인. 채택 기준은 `fewshot_v58.md` §5.
- 채택하면 버전 표기(v5.8)와 RUNBOOK §5-1(분석기 전환·롤백)에 기록.

## 4. 마무리

`score.py` → `export_pg.py` → `python scripts/lint_ui.py && python scripts/generate.py` → `check_rec.py` → docs 커밋·푸시(RUNBOOK). 상세 페이지의 '분류가 이상해요' 신고 중 이번 목록과 겹치는 건은 처리 완료로 닫는다.

## 5. 따로 확인할 것

- 다른 도시(삿포로) 호텔 리뷰가 후쿠오카 호텔에 붙은 사례: `ChIJ4y8nKrmRQTURPqdJtGO4kXg`(리뷰 본문에 오도리·삿포로역). 해당 리뷰의 다른 판정과 수집 매칭을 확인.
- 리뷰 텍스트를 700자로 잘라 검증해 인용이 잘린 부분에 있던 몇 건은 검증하지 못했다(목록에 없음 = 그대로 둠).
- 운영자 결정(2026-10-11, 권장안 채택): 창문 안 열림=실내 온도(창문 없음=좁은 방) · 습도·건조=실내 온도 · 일행 간 사생활(반투명 욕실 등)=좁은 방 · 투숙하지 않은 방문객 리뷰=판정 없음. `RUBRIC.md` 마지막 절, `fewshot_v58.md` 규칙 15–18에 반영했고, 이 규칙으로 다시 본 판정은 `corrections_classification.jsonl`에 `source: policy-2610`으로 들어 있다.

## 6. 적용 기록 (2026-10-11, 로컬 Opus 세션)

### 분류 323건 — 반영 완료
- 스크립트 `pipeline/apply_reclass.py`(VM `~/catchflaw/`): 신고 반영 경로(`report_review.load_finding`·`apply_override`)를 그대로 써서 `finding_overrides`에 기록(report_id null). 행마다 지금 화면 값 = `cur_*`·place_id·rid 확인, 다르면 건너뜀.
- 드라이런: 323/323 일치, 건너뜀 0 → 반영: override 323건(change 192 · remove 131), 기존 활성 기록 11건 대체. 뷰 `review_findings` 10,472 → 10,341행.
  - 73건은 같은 리뷰에 이미 있는 소분류로 옮겨짐 — 점수·내보내기가 (리뷰, 소분류)로 묶으므로 영향 없음.
- 백업·추적: 테이블 `reclass_backup_2610_fo`(반영 전 finding_overrides 전체 69행) · `logs/reclass_2610_backup.json`(새 id·대체한 id) · 테이블 `reclass_log`(override_id·fid·source·issue·tag).
- 되돌리기: VM `./venv/bin/python apply_reclass.py --rollback --tag 2610` → `score.py prod` → `stats.py` → `export_pg.py --out /home/opc/catchflaw/data-src` → `upload_quotes.py --src …` → 빌드·배포.
- 이후 실행: score.py prod → stats.py → export_pg.py → upload_quotes.py → lint_ui → generate.py(상세 179 · 점수 170) → check_rec.py 4/4 OK. 배지 변화 0, 도시 평균 실망 확률 4.77% → 4.68%.

### 등급 140건 — 미반영 (운영자 결정 대기)
- SPEC.md 대조(`GRADE_SPEC_CHECK.md`): spec_ok 60 · spec_conflict 67 · unclear 13. 심각→주의 91건 중 53건은 리뷰에 근거(잠을 못 잠·깸, 기능 전혀 안 됨, 증상, 방 이동)가 명시돼 있어 SPEC상 심각 유지가 맞다 — 검증 기준의 "별 4–5·유일한 단점이면 주의"가 SPEC에 없는 규칙이라서다.
- 시뮬레이션(DB 불변, 등급 대체 뷰로 export → scoring.compute, 지난 배지 기준 흔들림 방지 포함):
  - 140건 전부: 도시 평균 4.68% → 4.44%, 실망 확률 0.05%p 이상 변화 163곳, **위험 배지 변화 0**, 순위 구간 변화 7, 추천순 이동 91곳.
  - SPEC 일치 60건만(`corrections_grade_specok.jsonl`): 4.68% → 4.60%, 변화 66곳, **위험 배지 변화 0**, 순위 구간 변화 4.
- 반영하려면: `apply_reclass.py reclass/corrections_grade_specok.jsonl --tag 2610g`(드라이런 → `--apply`).

### 운영자 확인 33건 — 미반영
- `HOLD_OWNER_REVIEW.md` 표. 건마다 반영/유지를 정하면 같은 스크립트로 넣는다.

### 프롬프트 v5.8 패치 — 미채택
- `analyze_v5.py`는 original을 항상, korean은 다를 때 함께 넘긴다 → 규칙 1(원문 우선)은 그대로 작동.
- 후보 2종(VM `~/catchflaw/eval_v58_2610/`): B = 규칙 1–12·15–18 + 등급 규칙을 SPEC 쪽으로 고침 + 예시 15개(v5.8.1, 회귀 보정판 v5.8.2) / A = fewshot_v58.md 등급 규칙 13–14 원문 그대로 + 예시 18개.
  - 규칙 3·7의 "원인 없는 가려움 = 판정 없음"은 운영자 결정(2026-10-10, 가려움만 = 벌레 주의)과 어긋나 그 결정을 따랐다. E7·E17·E23은 SPEC상 심각(여행망침·수면방해)이라 B에서 뺐다.
- eval_v5 정본 400건, 각 3회 평균 (gemini-3.5-flash, temperature 0.1):

| 프롬프트 | 소분류 일치 | 과잉 | F1 | 심각 리뷰 재현 | 문제 없는 리뷰 오탐 |
|---|---|---|---|---|---|
| 현행 v5.8(10/10) | 307 | 35 | 0.87 | 0.78 | 12.0/224 |
| B v5.8.1 | 284 | 37 | 0.83 | 0.79 | 10.7/224 |
| B v5.8.2 | 293 | 39 | 0.85 | 0.75 | 11.3/224 |
| A | 284 | 37 | 0.84 | 0.77 | 10.3/224 |

- 미니 회귀(1회): 분류 수정 일치 49% → 77%(B v5.8.1)·75%(v5.8.2) · 등급 일치 28% → 29~38% · 부작용(검증 통과 판정 300건 같은 소분류 유지) 87% → 81~84%.
- 채택 기준(§5: 전체 정확도 하락 없음·심각 재현율 하락 없음·오탐 감소) 미충족 → **운영 프롬프트는 10/10 v5.8 그대로**(VM과 md5 동일).
  - 정답셋이 잃은 라벨 31건 중 약 10건은 운영자 결정 규칙과 정답이 어긋난 것(창문 안 열림 = 실내 온도, 누수 = 낡음·고장, 직원 부재 = 대응 미흡)이라 정답셋을 고치면 차이가 줄어든다. 나머지는 실제 손실(바깥 소음·역 거리·껌 등).

### 삿포로 리뷰 (ChIJ4y8nKrmRQTURPqdJtGO4kXg, 코코 호텔 하카타 에키마에)
- 해당 리뷰 1건(구글, zh-Hant, 2026-03-27: "離大通站跟扎幌站都很近")은 수집 매칭 문제가 아니다 — 이 호텔의 구글 리뷰 389건이 모두 같은 장소 CID(0x7891b863b449a73e)이고, 작성자가 구글에서 다른 지점(삿포로)에 쓸 리뷰를 하카타 지점에 올린 것.
- 판정 3건 중 악취·불친절은 이번 반영으로 해제됐고 **실내 온도(fid 5660)만 남아 있다** — 운영자 OK면 remove 1건 추가 권장.
- 삿포로 지명 정규식에 걸린 다른 호텔 3건은 후쿠오카 리뷰다(오호리 공원(大濠公園)을 '오도리 공원'으로 번역한 것 등).
