# 리뷰 판정 재검증 · 재분류 · 프롬프트 보강 (2026-10)

분류 v5.7로 '심각'·'주의' 판정된 리뷰를 Opus로 다시 검증하고, 틀린 판정은 고치고, 같은 실수가 반복되지 않게 분류 프롬프트에 예시(few-shot)와 경계 규칙을 넣는 구조.

## 1. 흐름

```
[클라우드]  ① 대상 추출 → ② 1차 검증(Opus, 400건 묶음) → ③ 2차 확인(Opus, 고칠 것만) → ④ 오류 패턴 분석
            → 산출물: corrections.jsonl · fewshot_v58.md · 이 문서의 결과 표
[로컬/VM]   ⑤ corrections 적용(드라이런 → 백업 → 반영) → ⑥ prompt_v5.py v5.8(예시·규칙 추가)
            → ⑦ eval_v5 회귀(SPEC.md 기준 세트, 정확도 하락 없을 때만 채택) → ⑧ score → export_pg → generate 빌드
```

- 클라우드에는 DB·`pipeline/`·`data-src/`가 없다. 그래서 ①은 배포된 상세 페이지의 `QDATA`(사이트에 보이는 심각·주의 판정 전부, 판정 ID `f` 포함)에서 뽑고, ⑤~⑧은 로컬 세션/VM에서 한다.
- 대상: 사이트 노출 판정 **9,616건**(심각 1,041 · 주의 8,575), 리뷰 6,195건(2,230건은 판정 2개 이상), 언어 ko 28% · ja 27% · en 16% · zh 27%.

## 2. 검증 기준 (요약 — 전문은 `reclass/RUBRIC.md`)

- 판정 = (대분류, 소분류, 등급, 근거 인용). 판정마다 ① 실제 불만인가 ② 분류(소분류 정의) ③ 등급이 **명백히** 틀렸나 ④ 인용이 근거인가를 본다.
- 문제 유형: `not_complaint`(칭찬·부정문·기대·다른 호텔) · `wrong_sub` · `wrong_cat` · `out_of_taxonomy`(조식·가격·주차 등 체계 밖) · `grade_too_high` · `grade_too_low` · `quote_mismatch`.
- **정밀도 우선**: 고친 값은 DB와 점수에 반영되므로, 1차·2차 두 번 모두 '틀렸다'고 본 것만 고친다. 확신이 없으면 그대로 둔다.
- 등급 변경은 SPEC.md(pipeline/eval_v5) 기준과 어긋날 수 있어 **분류 변경과 분리**해 적용 여부를 로컬에서 SPEC과 대조 후 정한다.

## 3. 산출물 형식

`reclass/corrections.jsonl` — 한 줄 = 고칠 판정 1건, `classification_reports`와 같은 키를 써서 VM의 기존 재판정 반영 코드(report_review.py)를 그대로 쓸 수 있게 한다.

```json
{"place_id": "ChIJ…", "fid": 84, "rid": "Ci9D…", "cur_cat": "직원", "cur_sub": "대응 미흡", "cur_grade": "주의",
 "issue": "wrong_sub", "new_cat": "직원", "new_sub": "불친절", "new_grade": "주의",
 "conf": "high", "why": "…", "confirmed_by": "opus-2nd", "source": "audit-2610"}
```

- `new_grade: "정상"` = 불만 아님(판정 삭제 또는 정상 처리 — 기존 신고 승인 시 처리와 동일하게).
- 적용 순서: `not_complaint`·`out_of_taxonomy`·`wrong_cat`·`wrong_sub` 먼저(분류), 등급(`grade_*`)은 별도 확인 후.

## 4. 프롬프트 보강 원칙 (`reclass/fewshot_v58.md` → `pipeline/prompt_v5.py` v5.8)

- 오류가 많이 나온 혼동 쌍마다 **대조 예시 한 쌍**(맞는 것 / 틀리기 쉬운 것)과 한 줄 경계 규칙을 넣는다. 예: 에어컨 소음 → 실내 소음(낡음·고장 아님), 곰팡이 냄새만 → 악취(곰팡이 아님), "벌레 없었음" → 불만 아님.
- 예시는 실제 리뷰에서 뽑되 호텔명·개인정보는 지운다. 언어별(ko/ja/en/zh)로 고르게.
- 예시 추가로 프롬프트가 길어지는 만큼 기존 설명 중 중복은 줄인다. 채택 조건: eval_v5 회귀에서 전체 정확도·심각 재현율이 떨어지지 않을 것.

## 5. 결과

(검증 완료 후 채움: 묶음별 검토 수, 유형별 오류 수·비율, 소분류별 오류율, 혼동 쌍 상위, 2차 확인 일치율, 반영 대상 건수)
