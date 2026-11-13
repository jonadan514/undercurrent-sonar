"""한국 유니버스 종목의 DART 업종코드(KSIC)를 모은다 (2026-11-13).

왜: 워치리스트 밸류 등급·동료 비교는 같은 업종끼리 견준다. 한국 회사 정보의 업종은 yfinance 영문 업종과 DART 중분류
한글 이름이 섞여 123개로 쪼개지고, 그중 86개는 5곳 미만이라 넓은 섹터(자동차·유통이 카지노와 한 묶음)로 넘어갔다.
DART 기업개황의 업종코드를 전 종목에 붙여 두면 'yfinance 업종(5곳 이상) → KSIC 소분류(3자리) → KSIC 중분류(2자리)'로
같은 기준의 공식 분류를 쓸 수 있다.

결과: data/kr_ksic.json {종목코드: 업종코드(KSIC, 보통 5자리)} - 저장소에 커밋(Collect DART mode=ksic).
이미 있는 종목은 건너뛴다(--refresh면 다시). 기업코드가 없거나 응답이 비면 그 종목만 빠진다(데이터부족).

    python scripts/fetch_kr_ksic.py            # 없는 종목만
    python scripts/fetch_kr_ksic.py --refresh  # 전부 다시
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart  # noqa: E402

OUT = ROOT / "data" / "kr_ksic.json"
UNIVERSE = ROOT / "data" / "kr_universe.json"
PROFILES = ROOT / "data" / "kr_profiles.json"
CORP_CACHE = ROOT / "data" / "dart_corp_codes.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    have: dict[str, str] = {} if args.refresh or not OUT.exists() else json.loads(OUT.read_text(encoding="utf-8"))
    syms = {i["symbol"] for i in json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]}
    try:   # 회사 정보 파일에 있는 종목(유니버스 밖 테마 소속 포함)도
        syms |= set(json.loads(PROFILES.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        pass
    todo = sorted(s for s in syms if s not in have)
    corp = dart.load_corp_codes(CORP_CACHE)
    print(f"[ksic] 대상 {len(todo)}종목 (이미 있음 {len(have)})", flush=True)
    miss = 0
    for i, s in enumerate(todo):
        cc = corp.get(s)
        if not cc:
            miss += 1
            continue
        try:
            code = str(dart.fetch_company(cc).get("induty_code") or "").strip()
        except dart.DartKeyError:
            print("[ksic] DART 키 오류 - 여기까지 저장", flush=True)
            break
        except Exception as e:  # noqa: BLE001 - 한 종목 실패는 건너뛴다
            print(f"[ksic] {s} 실패 {type(e).__name__}", flush=True)
            code = ""
        if code:
            have[s] = code
        else:
            miss += 1
        time.sleep(0.12)
        if (i + 1) % 100 == 0:
            OUT.write_text(json.dumps(have, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
            print(f"[ksic] {i + 1}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(have, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"[ksic] 저장 {len(have)}종목, 못 구함 {miss}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
