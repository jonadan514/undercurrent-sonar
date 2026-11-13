"""기업 기초조사 카드(/company)용 회사 프로필 파일(frontend/src/data/companyProfiles.json)을 만든다 (2026-11-05).

출처는 이미 있는 파일만 쓴다 - 새로 조회하지 않는다:
  - 사업 요약·섹터·산업: data/us_profiles.json, data/kr_profiles.json (yfinance 원문, 영문). 한국 산업 분류는
    data/kr_profile_overrides.json의 보정값을 덮어쓴다(src/collectors/kr_profiles.py와 같은 규칙, 요약은 건드리지 않음).
  - 이름: 미국 data/sp500_list.csv·sp400_list.csv, 한국 data/kr_universe.json
화면에 다 실을 필요는 없어 요약은 SUMMARY_MAX자까지만 담는다(파일 크기). 프로필은 토요일 Refresh Universe Data가
data/*.json을 갱신하므로, 크게 바뀌면 이 스크립트를 다시 돌려 커밋한다(gen_kr_stock_names.py와 같은 수동 갱신).

    python scripts/gen_company_profiles.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from analyzers.ksic import ksic_levels  # noqa: E402
DATA = ROOT / "data"
OUT = ROOT / "frontend" / "src" / "data" / "companyProfiles.json"
SUMMARY_MAX = 900


def _cut(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= SUMMARY_MAX:
        return text
    cut = text[:SUMMARY_MAX]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > SUMMARY_MAX // 2 else cut.rstrip()) + " …"


def build() -> dict:
    us_names: dict[str, str] = {}
    for f in ("sp500_list.csv", "sp400_list.csv"):
        with (DATA / f).open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("Symbol"):
                    us_names.setdefault(row["Symbol"].strip(), (row.get("Security") or "").strip())
    kr_names = {it["symbol"]: it.get("name") for it in json.loads((DATA / "kr_universe.json").read_text(encoding="utf-8")).get("items", [])}
    overrides = json.loads((DATA / "kr_profile_overrides.json").read_text(encoding="utf-8")).get("industry", {})
    # 한국 KSIC 업종 묶음(2026-11-13, scripts/fetch_kr_ksic.py) - "g": [[키, 이름], ...] 소분류·중분류 순. 업종 기준 밸류 등급·동료 비교용
    try:
        ksic = json.loads((DATA / "kr_ksic.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        ksic = {}

    out: dict[str, dict] = {"US": {}, "KR": {}}
    for market, path, names in (("US", "us_profiles.json", us_names), ("KR", "kr_profiles.json", kr_names)):
        profiles = json.loads((DATA / path).read_text(encoding="utf-8"))
        for sym, p in sorted(profiles.items()):
            if not isinstance(p, dict):
                continue
            industry = p.get("industry")
            if market == "KR" and sym in overrides:
                industry = overrides[sym].get("industry") or industry
            out[market][sym] = {k: v for k, v in {
                "n": names.get(sym), "s": p.get("sector"), "i": industry,
                "d": _cut(p.get("summary_long") or p.get("summary") or ""),
                "g": [list(x) for x in ksic_levels(ksic.get(sym) or p.get("industry_code"))] if market == "KR" else None,
            }.items() if v}
    return out


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: 미국 {len(data['US'])} · 한국 {len(data['KR'])}종목, {OUT.stat().st_size // 1024}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
