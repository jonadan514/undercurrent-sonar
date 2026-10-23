"""테마 소속 자동 점검 - 규칙에 걸린 소속을 사람 검토 후보로 뽑는다 (src/analyzers/mapping_rules.py).

읽기 전용 - DB에 쓰지 않는다. LLM을 쓰지 않는다.

소속 행을 가져오는 곳:
  --source site   운영 사이트 API(/api/radar/members)의 현재 승인 소속(로컬에서 키 없이 돌릴 때)
  --source db     theme_members 표의 --run-id 행(분기 자동 매핑 직후, GitHub Actions에서)

원장(data/eval/mapping_decisions.json)에 사람 판정이 있는 행은 건너뛴다(keep/hold는 사람이 확인한 것,
exclude는 apply_decision_ledger.py가 이미 처리한다). 시장 인식(perceived) 소속도 건너뛴다 - 사업 근거가
아니라 ETF 편입이 근거라 이 규칙들의 대상이 아니다.

--evaluate: 원장 판정을 정답지로 채점한다. 원장의 exclude 행을 얼마나 잡는지(잡은 비율)와, keep/hold 행과
원장에 없는 현재 소속을 얼마나 잘못 거는지(헛걸림 비율)를 규칙별로 낸다.

사용법:
  python scripts/check_mapping_rules.py --market KR
  python scripts/check_mapping_rules.py --market US --evaluate
  python scripts/check_mapping_rules.py --market KR --source db --run-id 20270101...
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from src.analyzers.mapping_rules import check_member, load_keyword_patterns  # noqa: E402

SITE = "https://u-sonar.vercel.app"
LEDGER = ROOT / "data" / "eval" / "mapping_decisions.json"


def _log(msg: str) -> None:
    print(f"[map-check] {msg}", flush=True)


def load_names(market: str) -> dict[str, str]:
    names: dict[str, str] = {}
    if market == "US":
        for f in ("sp500_list.csv", "sp400_list.csv"):
            path = ROOT / "data" / f
            if path.exists():
                for r in csv.DictReader(path.open(encoding="utf-8")):
                    names[r["Symbol"].replace(".", "-")] = r["Security"]
        return names
    ts = ROOT / "frontend" / "src" / "lib" / "krStockNames.ts"
    if ts.exists():
        for code, name in re.findall(r'"([0-9A-Z]{6})"\s*:\s*"([^"]+)"', ts.read_text(encoding="utf-8")):
            names[code] = name
    uni = ROOT / "data" / "kr_universe.json"
    if uni.exists():
        for it in json.loads(uni.read_text(encoding="utf-8")).get("items", []):
            names.setdefault(it["symbol"], it.get("name") or "")
    return names


def load_profiles(market: str) -> dict[str, dict]:
    try:
        from collectors.kr_profiles import load_profiles as _load
    except ImportError:
        from src.collectors.kr_profiles import load_profiles as _load
    return _load(market)


def load_ledger(market: str) -> dict[tuple[str, str], dict]:
    return {(d["theme_id"], d["ticker"]): d
            for d in json.loads(LEDGER.read_text(encoding="utf-8"))["decisions"] if d["market"] == market}


def active_themes(market: str) -> list[str]:
    raw = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))
    return [t["id"] for t in raw["themes"] if t.get("status") == "active" and market in t.get("markets", [])]


def members_from_site(market: str) -> list[dict]:
    rows = []
    for theme in active_themes(market):
        with urllib.request.urlopen(f"{SITE}/api/radar/members?theme_id={theme}&market={market}", timeout=60) as r:
            for m in json.load(r).get("members", []):
                rows.append({"theme_id": theme, "ticker": m["ticker"], "linkage": m.get("linkage") or ""})
    return rows


def members_from_db(market: str, run_id: str) -> list[dict]:
    from src.db.data_store import get_db
    conn = get_db()
    rows = conn.execute("SELECT theme_id, ticker, linkage FROM theme_members WHERE run_id = ? AND market = ?",
                        (run_id, market)).fetchall()
    conn.close()
    return [{"theme_id": r[0], "ticker": r[1], "linkage": r[2] or ""} for r in rows]


def check_rows(rows: list[dict], names: dict[str, str], profiles: dict[str, dict],
               patterns) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """행마다 걸린 규칙. 같은 테마 소속 이름 목록(지주사 규칙용)은 rows로 만든다."""
    peers: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        peers[r["theme_id"]].append(names.get(r["ticker"], ""))
    return {(r["theme_id"], r["ticker"]): check_member(r["theme_id"], r["ticker"], names.get(r["ticker"], ""),
                                                       profiles, peers[r["theme_id"]], patterns)
            for r in rows}


def evaluate(market: str, current: list[dict], names, profiles, patterns) -> dict:
    """원장 판정으로 채점. exclude = 잡아야 할 것, keep/hold + 원장 없는 현재 소속 = 걸면 안 되는 것."""
    ledger = load_ledger(market)
    cur = [r for r in current if r["linkage"] != "perceived"]
    # 원장에는 있는데 지금 소속이 아닌 행(빠졌거나 제외된 것)도 채점에 넣는다. 단 시장 인식 검토에서
    # 나온 판정은 사업 소속이 아니므로 뺀다 - 지금 소속에서 perceived를 뺀 것과 같은 이유.
    all_keys = {(r["theme_id"], r["ticker"]) for r in current}
    extra = [{"theme_id": t, "ticker": k, "linkage": ""} for (t, k), d in ledger.items()
             if (t, k) not in all_keys and d["decision"] in ("exclude", "keep", "hold")
             and "perception" not in (d.get("source") or "")]
    flags = check_rows(cur + extra, names, profiles, patterns)

    groups = {"exclude": [], "keep_hold": [], "unlabeled": []}
    for key, f in flags.items():
        d = ledger.get(key, {}).get("decision")
        g = "exclude" if d == "exclude" else "keep_hold" if d in ("keep", "hold") else "unlabeled"
        groups[g].append((key, f))

    def rate(items, code=None):
        hit = [k for k, f in items if any(c == code for c, _ in f)] if code else \
              [k for k, f in items if any(c != "no_profile" for c, _ in f)]
        return len(hit), len(items), hit

    out = {"market": market}
    for code in (None, "industry", "utility", "holding", "support"):
        label = code or "any"
        out[label] = {g: rate(items, code)[:2] for g, items in groups.items()}
    out["missed_exclude"] = [k for k, f in groups["exclude"] if not any(c != "no_profile" for c, _ in f)]
    out["false_keep"] = [(k, [c for c, _ in f]) for k, f in groups["keep_hold"] if any(c != "no_profile" for c, _ in f)]
    out["flagged_unlabeled"] = [(k, [c for c, _ in f]) for k, f in groups["unlabeled"]
                                if any(c != "no_profile" for c, _ in f)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["US", "KR"])
    ap.add_argument("--source", default="site", choices=["site", "db"])
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--out-dir", default="out")
    args = ap.parse_args()
    if args.source == "db" and not args.run_id:
        ap.error("--source db 에는 --run-id가 필요하다")

    names, profiles, patterns = load_names(args.market), load_profiles(args.market), load_keyword_patterns()
    rows = members_from_site(args.market) if args.source == "site" else members_from_db(args.market, args.run_id)
    _log(f"{args.market}: 소속 {len(rows)}행 ({args.source})")
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(exist_ok=True)

    if args.evaluate:
        ev = evaluate(args.market, rows, names, profiles, patterns)
        for label in ("any", "industry", "utility", "holding", "support"):
            e = ev[label]
            _log(f"  {label:9s} 원장 제외 중 잡음 {e['exclude'][0]}/{e['exclude'][1]}"
                 f" · 원장 유지 중 헛걸림 {e['keep_hold'][0]}/{e['keep_hold'][1]}"
                 f" · 원장 없는 현재 소속 중 걸림 {e['unlabeled'][0]}/{e['unlabeled'][1]}")
        path = out_dir / f"mapping_rules_eval_{args.market}.json"
        path.write_text(json.dumps(ev, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
        _log(f"채점 결과 저장: {path}")
        return 0

    ledger = load_ledger(args.market)
    todo = [r for r in rows if r["linkage"] != "perceived" and (r["theme_id"], r["ticker"]) not in ledger]
    flags = check_rows(todo, names, profiles, patterns)
    hits = [(k, f) for k, f in flags.items() if f]
    by_code = Counter(c for _, f in hits for c, _ in f)
    _log(f"원장 판정 없는 사업 소속 {len(todo)}행 중 규칙에 걸림 {len(hits)}행 {dict(by_code)}")
    lines = []
    for (theme, ticker), f in sorted(hits):
        lines.append(f"{theme}\t{ticker}\t{names.get(ticker, '')}\t" + " / ".join(f"[{c}] {d}" for c, d in f))
    path = out_dir / f"mapping_rules_{args.market}.tsv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log(f"검토 후보 저장: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
