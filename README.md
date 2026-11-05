# Undercurrent Sonar (U-Sonar)

> 2026-10-04 AlphaDesk에서 이름을 바꿨다. "알파(초과수익)"가 매수 신호처럼 읽혀, 테마의 물밑 흐름을 따로 보는
> 리서치 도구라는 성격에 맞게 바꿈. 마크는 U-Sonar, 긴 제목은 Undercurrent Sonar.

개인용 미국(S&P 500·400)·한국(KOSPI) **테마 기반 주간 리서치 레이더**. 테마마다 뉴스·실적·주가 세 축을 따로 보여주고,
재무 필터를 통과한 종목을 순위 없이 리스트업하며, 공시·내부자 매수·13F를 모아 주간 브리핑으로 정리한다.
매수 신호·종합 점수는 만들지 않는다.

> 2026-11-05 README를 지금 상태로 다시 씀. 예전 종목 스크리너 시절(시장 체제 게이트·매수 체크·포트폴리오·지수 예측)은
> 2026-08에 제거됐다 - `docs/radar/REMOVAL_PLAN.md`. 작업 전에는 `CLAUDE.md`와 `docs/radar/MASTER_PLAN_research_radar.md`를 먼저 읽을 것.
> 변경 이력은 `docs/radar/PROGRESS.md`.

## 원칙 (CLAUDE.md 요약)

1. 단일 종합 점수·등급을 만들지 않는다. 세 축을 각각 표시한다.
2. LLM은 재무 수치를 생성하지 않는다. 숫자는 저장된 데이터에서만 나온다.
3. 트랩 필터 기준값(F-Score 6, ROE 미국 12%/한국 8%, 이자보상 3배, 부채비율 150%)을 임의로 바꾸지 않는다.
4. 판정은 통과/탈락/데이터부족 3분류. 계산 불가를 탈락으로 처리하지 않는다.
5. 이력 테이블은 덮어쓰지 않는다.

## 아키텍처

```
GitHub Actions (cron, 매일·매주·분기)
  ├─ 수집: 한국 공시·내부자·미국 8-K·13F·매크로(매일), 테마 뉴스·분기 재무·실적 발표일(매주)
  ├─ 계산: 테마 세 축(뉴스·실적·주가)·라벨, 워치리스트 스크리닝·밸류·성장, 섹터 분석, 성적표·신호 사후 확인
  └─ 발송: 월요일 아침 텔레그램(테마 레이더 요약 + 주간 브리핑 요약), 실패 알림
        │
        ▼
Turso (libSQL) ── Python은 HTTP(Hrana), Next.js는 @libsql/client
        │
        ▼
Next.js 15 (App Router) ── frontend/app/**/page.tsx, frontend/app/api/**/route.ts
        │
        ▼
https://u-sonar.vercel.app (Vercel, main push 시 자동 배포)
```

- 주간 브리핑 총평은 GPT(gpt-4o)가 쓰지만, 무엇을 쓸지는 코드가 고른다(`src/analyzers/briefing_points.py` - 칸 사이 겹침·엇갈림,
  관찰 노트 회고, 매크로↔테마). 숫자는 넘기지 않고, 원인 짐작·수치 문장은 뒷손질로 뺀다.
- LLM 모델은 역할별로 `config/models.yaml`.

## 화면 (사이드바 순서)

| 메뉴 | 경로 | 한 줄 설명 |
|---|---|---|
| 개요 | `/` | 이번 주 물밑 흐름, 매크로 지표 |
| 테마 레이더 | `/radar`, `/radar/theme` | 테마별 뉴스·실적·주가 세 축과 조합 라벨(숨은 강세·뉴스 선행 등), 테마 상세 타임라인 |
| 섹터 분석 | `/sector` | 섹터 상대강도(주가 축의 기반) |
| 주간 브리핑 | `/briefing` | 관심 종목에 생긴 일, 총평(짚을 점 + 관련 기사), 시장, 종목 변화, 테마, 일정, 공시·내부자 |
| 분기 리서치 | `/quarterly` | 분기 재무 신호 × 뉴스 비율로 테마 4칸 분류 |
| 워치리스트 | `/watchlist` | 재무 필터 통과 후보(순위 없음, 밸류·성장 등급) + 내 워치리스트 |
| 유명 투자자 13F | `/investors` | 투자 성향별 운용사 13F 변동 |
| 관찰 노트 | `/notes` | 테마·종목에 남긴 기대와 4주·12주 회고(판정은 사람이) |
| 성적표 | `/scorecard` | 과거 후보의 이후 수익률, 신호 사후 확인 - 필터 검증용 |
| 가이드 | `/guide`, `/guide/playbook`, `/guide/detail` | 사용 설명서, 리서치 실행 가이드, 세부 설명서 |
| 데이터 상태 | `/status` | 표마다 마지막 갱신 시각(사이드바 아래) |

`docs/PAGES.md`는 2026-08 이전 화면 기준이라 지금과 다르다.

## 디렉터리

```
frontend/            Next.js 앱 (app/ 화면·API, src/components, src/lib)
src/analyzers/       테마 세 축·라벨, 트랩 필터, 밸류·성장, 브리핑 짚을 점·관련 기사 등
src/collectors/      DART·SEC·yfinance·뉴스(Google News RSS·네이버·Finnhub)·13F 수집
src/db/              Turso 접근, 표 정의
src/llm/             OpenAI 호출(재시도·모델 계열 차이)
scripts/             실행 진입점(수집·계산·발송·리포트), scripts/tools/ 점검 도구
config/              themes.yaml(테마·키워드), models.yaml, institutions.yaml 등
docs/radar/          계획·스펙·진행 기록·런북
.github/workflows/   정기 실행 + 수동 실행(보고서·매핑 승인·백필 등)
```

## 로컬 실행

```bash
cd frontend && npm install && npm run dev     # http://localhost:3000 (frontend/.env.local에 Turso 접속 정보)
npx next build                                # 커밋 전 빌드 확인
python -m pytest tests                        # Python 테스트 (requirements.txt, requirements-dev.txt)
```

## 점검 (읽기 전용 워크플로)

- `Report Data Health` - 사이트 데이터 상태 API를 표로(늦거나 빠진 데이터)
- `Site Tour` - 사이트 페이지를 돌며 섹션·빈 칸·콘솔 오류·실패 API를 로그로
- `Preview Briefing Comment` - 저장된 최근 브리핑으로 총평만 다시 만들어 보기(저장·발송 없음)
- `Report Briefing` / `Report 13F` / `Report Data Coverage` / `Report DB Size` 등
