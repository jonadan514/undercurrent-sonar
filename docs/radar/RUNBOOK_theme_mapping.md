# 테마 매핑 운영 절차 (RUNBOOK)

2026-09-15 확정. 분기마다 `Quarterly Theme Mapping` 워크플로가 매핑과 감사를 자동으로
돌리고 텔레그램으로 검토를 요청한다. **승인은 사람이 한다** - 이 문서는 그 이후 절차다.

## 왜 자동 승인하지 않는가

LLM 매핑에는 도구로 다 걸러지지 않는 오류가 남는다(2026-09-15 실측).
- **티커 착오**: 게임 테마에 코스맥스(화장품), AI반도체에 오뚜기 - 테마 정의로 못 막는다
- **사명 기반 추측**: 레인보우로보틱스를 "수술 로봇"으로 - 사업정보 부착으로 크게 줄었으나 코스닥 일부는 정보가 없다
- **실행마다 흔들리는 누락**: 한 번의 실행이 LS ELECTRIC(전력망)·한전KPS(원전)를 놓친다
- **감사 도구의 한계**: 정답지 기준 정밀도·재현율 약 94%, 함께 판정되는 종목 묶음이 바뀌면 판정이 달라진다

## 주기

분기 1회(1·4·7·10월 1일 01:00 UTC). 테마 정의(`value_chain`)나 경계를 바꿨을 때는
그 테마만 수시로 재매핑한다(`Theme Company Mapping`, theme_ids 지정).

## 절차

1. **감사 결과·검토 초안 받기** - 워크플로 아티팩트 `quarterly-mapping-audit`
   (`evidence_audit_<run>_KR.txt/.json`, `_US`, `review_draft_<run>_KR.txt/.json`, `_US`)
   - 초안은 판정 원장(`data/eval/mapping_decisions.json`)을 적용한 결과다. 이미 판정한
     (테마, 종목)은 `exclude`·`restore`에 자동으로 들어가 있고, **사람이 볼 것은 `needs_review`뿐**이다
   - `info_hold_in_run`은 판단보류로 유지했던 행이 이번 run에도 있는 경우
   - **규칙 점검** `mapping_rules_KR.tsv`·`_US.tsv`(2026-10-23 추가, LLM 없음): 원장 판정이 없는 행 중
     업종 불일치·규제 전력회사·지주사(같은 테마에 상장 자회사)·사업정보 근거 없음에 걸린 것.
     감사가 놓친 것을 보충한다 - `needs_review`에 없더라도 여기 걸린 행은 함께 본다(자동 제외 아님).
     근거 단어는 `config/theme_evidence_keywords.yaml`. 지금 소속을 바로 점검하려면 로컬에서
     `python scripts/check_mapping_rules.py --market KR`(운영 사이트에서 읽음), 규칙을 고친 뒤에는 `--evaluate`로 원장 채점
2. **검토 파일 작성** - 초안 json을 `data/eval/<버전>_manual_review_<날짜>.json`으로 저장한다.
   사람이 할 일은 두 가지다.
   - **`needs_review`를 판단해 `exclude`/`keep`으로 옮긴다** (처음 보는 경우만 여기 온다)
     - `exclude`: 감사가 틀렸다고 한 행 중 **확신 있는 오류만**
     - `keep`: 감사 오탐(대개 한글 인용·엉뚱한 원문 인용으로 인용 검증 실패) 또는 판단보류
   - **`restore`에서 빼야 할 것만 지운다** (2026-09-16 변경 - 넣는 방식에서 빼는 방식으로).
     한 번 사람이 확인한 소속은 기본으로 되살아난다. LLM 매핑은 실행마다 흔들려서(같은
     프롬프트 두 run 일치율 83%) 멀쩡한 소속이 매 분기 무작위로 빠지기 때문이다.
     **사업이 바뀌어 더는 맞지 않는 것만 지운다** - `[판정 N일 지남]` 표시가 붙은 행을 먼저 본다
     (OXY의 OxyChem 매각, Viatris 바이오시밀러 매각, GM Cruise 중단 같은 사례)
   - `unapprove`: 병합 run에 행이 없는 테마에서 오류로 확정한 예전 행
   - 판정마다 이유를 남긴다. 코드는 반드시 이름맵과 대조(기억으로 적은 코드는 틀린다)
   - **시장 인식(perceived) 후보**: `Theme ETF Perception Candidates` 워크플로 결과에서 넣을 것만 `add`에,
     근거가 사라진 것(`stale`)은 `exclude`에 - SPEC_theme_company_mapping.md 11장
3. **현재 승인분과 테마별 비교** - 정당한 소속을 잃는 테마가 있는지 확인 후 restore에 반영
4. **병합** - `Build Merged Mapping Run` dry_run=true 로 행 수·누락 확인 → dry_run=false
   - 되살릴 근거 문장은 승인된 최신 행에서 가져오고, 없으면 과거 아무 run에서나 찾는다.
     한 분기 빠졌다고 확정 소속이 영영 못 돌아오는 일을 막기 위함(2026-09-16)
5. **승인** - `Approve Theme Mapping`, run_id=병합 run, only_market=KR
   - US는 변경 사유가 있는 테마만(신규 테마 등) 원 run에서 only_market=US + exclude로
6. **게이트 감사** - `Audit Mapping Evidence`, run_id 비움(화면 표시분), eval_labels 지정
   - 적발 행이 **전부 검토됐으면 통과**. 새로 걸린 행은 검토 후 `Unapprove Theme Members`
   - 정답지(`data/eval/evidence_audit_labels_*.json`)의 오류가 화면에 남았는지도 확인
7. **테마 비우기** - 검토 결과 해당 기업이 없는 테마는 `Unapprove Theme Members`
   empty_themes. 최신 run에 행이 없으면 더 오래된 승인분이 드러나기 때문이다
8. **판정 원장 갱신** - 이번 검토 파일을 `data/eval/review_manifest.json` 끝에 `{path, decided_at}`
   항목으로 추가하고 `python scripts/build_decision_ledger.py` 실행, `mapping_decisions.json` 커밋.
   다음 분기부터 이번 판정이 재사용된다. manifest에서 빠진 검토 파일이 있으면 실행 때 경고가 나온다
9. **후속** - `backfill-quarterly-financials` → 실적 → 주가 → 라벨 재계산(이번 주 week_start)
10. **확인** - 레이더 API에서 소속 수·na 테마·이름 표시 확인. 이름맵 누락 시
   최신 유니버스로 `krStockNames.ts` 재생성

## 테마 정의를 바꿀 때

- `config/themes.yaml`의 `value_chain`에 편입 단계와 "편입하지 않음" 경계를 함께 적는다
- 키워드를 바꾸면 `keywords_changed_at` 기록 - 뉴스 기준선이 그 주 이전을 안 쓴다(4주간 na)
- 테마 추가·개명 후 `python scripts/gen_theme_names.py` (화면 이름)
- 신규 테마는 `Collect Theme News` weeks_back=8 로 뉴스 백필

## 코드가 자동으로 거르는 것 (사람 검토 전에)

- 유니버스 밖 티커, 시가총액 미달, 근거 15자 미만
- 근거 주어 불일치(근거 문장이 다른 회사 이야기)
- **업종-테마 불일치**(`INDUSTRY_THEME_ALLOW`, src/analyzers/mapping_rules.py - 2026-10-23 map_theme_companies.py에서 옮김): 금융·보험은 어떤 테마에도,
  식품은 K푸드에만, 화장품은 K뷰티에만, 게임사는 게임에만 등. 산업분류가 없거나 틀린 종목은
  적용 안 됨 - 산업분류 오류는 `data/kr_profile_overrides.json`으로 고친다

## 원칙

- 기존 행은 수정·삭제하지 않는다. 승인 해제는 approved만 0으로
- 확인 불가(unverifiable·unclear)는 오류로 치지 않는다
- 해당 사업을 하는 상장 자회사가 따로 있으면 지주사 대신 자회사
