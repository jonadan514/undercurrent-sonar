# 페이지 구성 안내

사이드바 탭별 내용과 데이터 소스 정리. (2026-10 기준 — 상세 사용법은 앱 내 가이드 탭 참고)

모든 시장 구분 페이지는 상단 탭으로 🇺🇸 미국 / 🇰🇷 한국을 전환한다 (`MarketContext`, localStorage 유지).

---

## 시장 분석

### 개요 `/`
이번 주 워치리스트 후보 수(순위 없음) + 테마 레이더 라벨 요약 중심의 최소 화면. 주간 브리핑·섹터 분석으로 이동하는 링크.
- 소스: `/api/watchlist/candidates`, `/api/radar`

### 섹터 분석 `/sector`
경기 사이클 판단(회복/성장/과열/침체), 선행·후행 섹터(1개월 RS 상위/하위 3), 주간 RS 추이(4주), 섹터별 수익률·상대강도 히트맵(섹터 클릭 시 구성 종목 + Piotroski F-Score).
- 소스: `/api/data/sector`, `/api/data/kr/sector`

### 테마 레이더 `/radar` (미국·한국)
미국·한국 산업 테마를 뉴스·실적·주가 세 축으로 매주 관찰. 종합 점수 없이 화살표만 표시하고, 정해진 6개 조합에만 라벨("Quiet Strength" 등)을 붙인다. 테마 카드를 펼치면 소속 기업(가치사슬 단계·근거·주력/일부/간접·재무 통과 여부)과 이번 주 수집 기사 목록.
- 소스: `/api/radar`, `/api/radar/{members,news,ticker-themes}`
- 배경: `docs/radar/MASTER_PLAN_research_radar.md`, `docs/radar/SPEC_phase_a_signals.md`

### 테마 흐름 이력 `/radar/theme?theme_id=…` (2026-10-05)
테마 하나의 최근 12주 세 축 화살표·라벨 타임라인과 축별 추이, 최근 주 기여 기업 표(4주 수익률·매출 YoY·실적 판정·분기 영업이익률·EPS 서프라이즈·52주 위치·애널리스트 수·워치리스트 여부), 이 테마의 관찰 노트. 레이더·분기 리서치의 "흐름 이력 보기 →"로 들어온다.
- 소스: `/api/radar/theme-history`, `/api/notes`

## 내 투자

### 워치리스트 `/watchlist`
주간 스크리닝: 함정 필터(Piotroski·ROE·부채·현금흐름) 통과 종목을 순위 없이 리스트업(모멘텀 랭킹 없음 — 1~3년 펀더멘털 투자용). 좁혀 보기: 테마 흐름과 겹치는 종목(라벨 전에는 "실적 먼저 움직인 테마")·관심도 오른 종목(`▲관심` 배지, 최근 주간 갱신 기준)·조합 프리셋("실적 반전" = 3년 정체·역성장인데 최근 1년 성장 포함). 종목 클릭 → 재무 지표(분기 영업이익률 전년동기 비교·최근 실적 서프라이즈·52주 위치·애널리스트 수 포함) + 소속 테마 레이더 배지(있는 경우) + 네러티브 브리프(장기 스토리·촉매·리스크·시장 단기 관심도 HOT/WARM/COLD·전일 대비 전환) + 종목별 정성 체크리스트(구 투자 워크북, stock_checklist에 독립 저장) + 매수 이유 메모.
- 소스: `/api/watchlist/{candidates,my,narrative,narrative-shifts,checklist}`

## 돌아보기

### 관찰 노트 `/notes` (2026-10-05)
테마·종목에 대한 가설과 축별 기대(↑/↓)를 남기면 작성 시점 값이 고정 저장되고, 4주·12주 뒤 그때 값과 지금 값을 나란히 붙인다. 맞았는지는 사람이 판정하고 배운 점을 적는다. 가설·스냅샷은 수정 불가.
- 소스: `/api/notes`, 회고 생성 `scripts/review_observations.py`

## 도구

### 성적표 `/scorecard`
과거 워치리스트 후보에 실제 주가를 대조한 사후 검증. 지수 단순 보유 vs 필터 통과 종목 균등매수 2-way 비교(30일~2년).
- 소스: `/api/data/scorecard`

### 가이드 `/guide` · 세부 설명서 `/guide/detail`
사용 설명서(3분 시작 가이드·매일 루틴·점수 구조) / 기능별 원리·해석법 아코디언.

---

## 백엔드 파이프라인 (GitHub Actions)

| 워크플로우 | 주기 | 하는 일 |
|---|---|---|
| Weekly Watchlist Screen | 일요일 22:00 UTC | 함정 필터 → 순위 없는 후보 리스트 갱신 → 네러티브 브리프 생성 → 주간 브리핑(테마 레이더 라벨 변동 포함) |
| Collect Earnings Calendar | 일요일 20:00 UTC | 워치리스트·내 관심·노트 종목 다음 실적 발표일(yfinance) → 브리핑 "이번 주 실적 발표" (2026-10-17) |
| Collect KR Disclosures | 매일 11:30 UTC | DART 공급계약·잠정실적·결산실적 공시예고 → 관심 종목은 바로 텔레그램, 브리핑 "한국 공시" (2026-10-17) |
| Collect Insider Trades | 매일 13:00 UTC | 관심 종목(워치리스트·내 관심·노트·테마) 내부자 장내 매수 - 미국 SEC Form 4(거래코드 P), 한국 DART 임원ㆍ주요주주 소유보고(장내매수만) → 브리핑 "내부자 장내 매수", 워치리스트 상세 카드 (2026-10-21) |
| Collect US 8-K | 매일 13:20 UTC | 관심 종목 미국 8-K - 항목 번호로 종류(중요 계약·해지·인수·차입·구조조정·손상·임원 변동 등) + 원문 첫머리 → 브리핑 "미국 주요 공시", 워치리스트 상세 카드 (2026-10-21) |
| Compute Theme Events | 매일 14:00 UTC | 한국 공시·미국 8-K·내부자 매수를 테마 소속(direct+partial)으로 묶어 7일·30일 건수와 목록 → 테마 레이더 📄 표시·"축은 조용, 소속 기업 공시는 있음" (2026-10-21) |
| Weekly Market Analysis | 월요일 22:00 UTC | US/KR 섹터 분석 갱신 → 텔레그램 요약 발송 |
| Performance Tracking | 일요일 23:00 UTC | 과거 후보들의 30~730일 후 실제 수익률 계산 (성적표) |
| Collect Theme News → Compute Theme Earnings → Compute Theme Price → Compute Theme Labels → Send Radar Digest | 일요일 22:00~23:00 UTC (15분 간격 순차) | 테마 레이더 뉴스·실적·주가 세 축 계산 → 라벨 부여 → 텔레그램 발송. Weekly Watchlist Screen과 별개 워크플로우라 브리핑 생성 시점엔 아직 이번 주 라벨이 안 끝나 있을 수 있음(주간 브리핑은 그래서 실제 계산 완료 주를 그대로 표시). |

데이터 저장소: Turso (libsql). 프론트는 읽기 전용 API로 접근.

**2026-08 제거**: 마켓 게이트·체제 판정·지수 예측(`/regime`), 리스크 분석(`/risk`), 페이퍼 포트폴리오·실거래 기록(`/portfolio`), 매수 체크(`/workflow`) — 순위 없는 리스트업 도구로 전환하며 정리. 배경은 `docs/radar/REMOVAL_PLAN.md` 참고.
**2026-09 추가**: 테마 레이더(`/radar`, 미국·한국) — 배경은 `docs/radar/MASTER_PLAN_research_radar.md` 참고.
