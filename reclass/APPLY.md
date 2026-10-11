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
