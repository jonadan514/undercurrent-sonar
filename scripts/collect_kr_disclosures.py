"""한국 공시 알림 - 단일판매·공급계약, 영업(잠정)실적 (2026-10-17). 확인용 --probe 단계."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", nargs=2, metavar=("BGN", "END"), required=True)
    ap.add_argument("--show", type=int, default=2)
    args = ap.parse_args()
    items = dart.list_disclosures(*args.probe)
    print(f"공시 {len(items)}건")
    names = Counter(i["report_nm"].strip() for i in items)
    for n, c in names.most_common(40):
        print(f"  {c:4d} {n}")
    for kw in ("공급계약", "잠정)실적", "기업설명회"):
        hits = [i for i in items if kw in i["report_nm"] and i.get("stock_code")][:args.show]
        for h in hits:
            print(f"\n===== {h['corp_name']} {h['stock_code']} {h['corp_cls']} {h['report_nm']} {h['rcept_no']}")
            for r in dart.document_rows(h["rcept_no"])[:70]:
                print("  " + r[:220])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
