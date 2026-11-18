"""코스피200 편입 종목을 위키백과에서 받아 KR 유니버스 확장분을 생성한다.

왜 런타임 조회가 아니라 생성 스크립트인가:
공공데이터포털·pykrx는 GitHub Actions IP에서 차단되고(2026-08-27 확인), 위키백과는
열리지만 매 실행마다 긁으면 편입/편출 시점에 유니버스 크기가 조용히 바뀐다. 테마
매핑·스크리닝 결과의 재현성이 깨지므로, 결과를 kr_kospi_list.py에 정적으로 커밋하고
지수 정기변경 때 이 스크립트를 의도적으로 다시 돌리는 방식을 택했다.

사용법:
    python scripts/gen_kospi200_universe.py          # 확장분 미리보기
    python scripts/gen_kospi200_universe.py --write  # kr_kospi_list.py에 반영할 코드 출력

출력은 항상 파일(out/kospi200_additions.py)로 쓴다 - Windows 콘솔에서 한글 print는
깨져 보일 수 있어 화면 출력만으로 검증하지 않는다.
"""
import argparse
import html
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

WIKI_URL = "https://ko.wikipedia.org/wiki/%EC%BD%94%EC%8A%A4%ED%94%BC_200"

# 위키백과 표의 한글 섹터 -> yfinance 섹터 문자열.
# yfinance 조회가 실패한 종목의 폴백으로만 쓴다(kr_sector_analyzer가 이 영문
# 문자열로 경기사이클 섹터를 매칭하므로 표기를 맞춰야 한다).
SECTOR_KO_TO_EN = {
    "건설": "Industrials",
    "경기소비재": "Consumer Cyclical",
    "금융": "Financial Services",
    "산업재": "Industrials",
    "생활소비재": "Consumer Defensive",
    "소재": "Basic Materials",
    "에너지": "Energy",
    # 위키 표의 복합 분류. 실제 구성은 정유(Energy)보다 화학(Basic Materials)이
    # 다수라 폴백 기본값을 화학 쪽에 둔다 - yfinance 조회가 되면 그쪽이 우선한다.
    "에너지/화학": "Basic Materials",
    "철강/소재": "Basic Materials",
    "유틸리티": "Utilities",
    "정보기술": "Technology",
    "커뮤니케이션서비스": "Communication Services",
    "헬스케어": "Healthcare",
    "중공업": "Industrials",
    "철강": "Basic Materials",
    "운송": "Industrials",
    "IT": "Technology",
}

ROW_RE = re.compile(
    r"<td[^>]*>\s*<a[^>]*title=\"([^\"]+)\"[^>]*>([^<]+)</a>\s*</td>"
    r"\s*<td[^>]*>(\d{6})</td>"
    r"\s*<td[^>]*>([^<]*)</td>",
    re.S,
)


def fetch_kospi200() -> list[tuple[str, str, str]]:
    """(code, name, sector_ko) 목록."""
    r = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for _title, name, code, sector_ko in ROW_RE.findall(r.text):
        if code in seen:
            continue
        seen.add(code)
        out.append((code, html.unescape(name).strip(), sector_ko.strip()))   # 'F&amp;F'로 저장됐었다(2026-11-18)
    return out


def yf_sector(code: str) -> str | None:
    try:
        import yfinance as yf

        info = yf.Ticker(f"{code}.KS").info
        sec = info.get("sector")
        return sec or None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-yfinance", action="store_true",
                    help="yfinance 섹터 조회를 건너뛰고 한글 섹터 매핑만 쓴다")
    args = ap.parse_args()

    from src.collectors.kr_kospi_list import KOSPI_STOCKS

    existing = {code for code, _n, _s in KOSPI_STOCKS}
    rows = fetch_kospi200()
    new_rows = [r for r in rows if r[0] not in existing]

    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    report = out_dir / "kospi200_report.txt"
    snippet = out_dir / "kospi200_additions.py"

    lines: list[str] = []
    lines.append(f"위키 코스피200 파싱: {len(rows)}종목")
    lines.append(f"기존 정적 리스트: {len(existing)}종목")
    lines.append(f"신규(합집합 추가분): {len(new_rows)}종목")
    lines.append(f"합집합 총계: {len(existing) + len(new_rows)}종목")
    only_static = existing - {r[0] for r in rows}
    lines.append(f"코스피200에 없는 기존 종목(합집합이라 유지): {len(only_static)}종목")
    lines.append("  " + ", ".join(sorted(only_static)))
    lines.append("")

    sec_ko_counts: dict[str, int] = {}
    for _c, _n, s in new_rows:
        sec_ko_counts[s] = sec_ko_counts.get(s, 0) + 1
    lines.append("신규 종목 한글 섹터 분포:")
    for s, n in sorted(sec_ko_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {s}: {n}  -> {SECTOR_KO_TO_EN.get(s, '(미매핑)')}")
    lines.append("")

    resolved: list[tuple[str, str, str, str]] = []  # code, name, sector_en, source
    for i, (code, name, sector_ko) in enumerate(new_rows, 1):
        sector_en = None
        if not args.no_yfinance:
            sector_en = yf_sector(code)
            time.sleep(0.2)
        source = "yfinance"
        if not sector_en:
            sector_en = SECTOR_KO_TO_EN.get(sector_ko)
            source = "위키매핑"
        if not sector_en:
            sector_en = "Industrials"
            source = "기본값"
        resolved.append((code, name, sector_en, source))
        if i % 20 == 0:
            lines.append(f"  ... 섹터 해석 {i}/{len(new_rows)}")

    src_counts: dict[str, int] = {}
    for _c, _n, _s, src in resolved:
        src_counts[src] = src_counts.get(src, 0) + 1
    lines.append("")
    lines.append(f"섹터 출처: {src_counts}")

    unmapped = [r for r in resolved if r[3] == "기본값"]
    if unmapped:
        lines.append(f"경고 - 섹터를 못 구해 기본값 처리: {len(unmapped)}종목")
        for c, n, _s, _src in unmapped:
            lines.append(f"  {c} {n}")

    report.write_text("\n".join(lines), encoding="utf-8")

    body = ["# 위키백과 코스피200 편입 종목 중 기존 정적 리스트에 없던 종목.",
            "# scripts/gen_kospi200_universe.py 로 생성 - 지수 정기변경 때 재생성한다.",
            "KOSPI200_ADDITIONS = ["]
    for code, name, sector_en, _src in sorted(resolved):
        body.append(f'    ("{code}", "{name}", "{sector_en}"),')
    body.append("]")
    snippet.write_text("\n".join(body) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
