"""yfinance에 사업정보가 없는 한국 종목을 DART로 채운다 (분기 재설계 4-1 기업개황).

2026-09-17 기준 KR 유니버스 664종목 중 84종목(81개가 코스닥)은 yfinance에 산업분류·사업
설명이 아예 없다. 티씨케이·에코프로·주성엔지니어링 같은 테마 핵심 종목이 포함돼 있어,
매핑이 이 종목들을 이름만 보고 판단하게 된다(사명 기반 추측 오류의 원천).

채우는 값 (data/kr_profiles.json)
  industry      KSIC 중분류 이름 (DART 기업개황의 업종코드 앞 두 자리)
  summary       사업의 개요 앞 140자 (매핑 프롬프트용)
  summary_long  사업의 개요 2500자 (근거 감사용)
  source        "dart" - yfinance 원본과 구별

사업의 개요는 가장 최근 사업보고서 원문(II. 사업의 내용 > 1. 사업의 개요)에서 뽑는다.
한국어 원문이다 - 다른 종목의 요약은 yfinance 영문이지만, 한국 기업을 한국어 원문으로
설명하는 편이 매핑·감사 모두 더 정확하다.

Usage:
  python scripts/fill_kr_profiles_from_dart.py              # 사업정보 없는 종목 전부
  python scripts/fill_kr_profiles_from_dart.py --tickers 064760 086520
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors import dart_client as dart
from collectors.kr_profiles import backfill_field_sources

PROFILES = ROOT / "data" / "kr_profiles.json"
UNIVERSE = ROOT / "data" / "kr_universe.json"
CORP_CACHE = ROOT / "data" / "dart_corp_codes.json"

# 한국표준산업분류(KSIC) 10차 중분류. DART 업종코드 앞 두 자리로 찾는다.
from analyzers.ksic import KSIC_DIVISION  # noqa: E402 - 중분류 이름표는 업종 비교와 같이 쓴다(2026-11-13 옮김)


# 중분류로는 오해를 부르는 코드. 지주회사는 KSIC상 금융업(64)으로 분류되는데, 그대로
# "금융업"이라고 적으면 매핑 프롬프트가 에코프로·LG 같은 사업지주회사를 금융사로 읽는다.
KSIC_SPECIFIC = {
    "642": "지주회사", "64992": "지주회사", "6499": "기타 금융업",
    "261": "반도체 제조업", "262": "전자부품 제조업", "263": "컴퓨터 및 주변장치 제조업",
    "264": "통신 및 방송장비 제조업", "265": "영상·음향기기 제조업",
    "271": "의료용 기기 제조업", "272": "측정·시험·항해·제어 장비 제조업",
    "212": "의약품 제조업", "213": "의료용품 제조업",
}


def industry_label(code: str) -> str:
    """DART 업종코드(KSIC) -> 사람이 읽을 업종명."""
    code = str(code or "").strip()
    if not code:
        return ""
    for length in (5, 4, 3):
        hit = KSIC_SPECIFIC.get(code[:length])
        if hit:
            return hit
    return KSIC_DIVISION.get(code[:2], f"KSIC {code}")


def apply_dart_fields(existing: dict, *, industry: str | None, industry_code: str | None,
                      overview: str | None, refresh: bool = False) -> dict:
    """DART가 가져온 값을 프로필에 반영한다. 원본을 바꾸지 않고 새 dict를 돌려준다.

    실제로 바꾼 필드만 <필드>_source="dart"로 기록한다 - 예전에는 레코드 전체에
    source="dart" 하나만 붙여서, 산업분류는 DART지만 요약은 yfinance인 경우를 구별할 수 없었다.
    기존 source 필드는 하위 호환을 위해 그대로 남긴다(무언가 바꿨을 때만).

    기존 값이 있으면 덮어쓰지 않는다. 예외는 refresh=True일 때 **DART가 채운** 요약뿐이다 -
    yfinance 요약은 refresh여도 건드리지 않는다.
    """
    rec = backfill_field_sources(existing)
    changed = False

    if industry and not rec.get("industry"):
        rec["industry"] = industry
        rec["industry_source"] = "dart"
        if industry_code:
            rec["industry_code"] = industry_code
        changed = True

    if overview:
        dart_owned = rec.get("summary_source") == "dart"
        if not rec.get("summary") or (refresh and dart_owned):
            rec["summary"] = overview[:140]
            rec["summary_source"] = "dart"
            changed = True
        if not rec.get("summary_long") or (refresh and rec.get("summary_long_source") == "dart"):
            rec["summary_long"] = overview[:2500]
            rec["summary_long_source"] = "dart"
            changed = True

    if changed:
        rec["source"] = "dart"
    return rec


def _log(msg: str) -> None:
    print(f"[dart-profile] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--refresh-dart", action="store_true",
                     help="이미 DART로 채운 종목(source=dart)의 사업의 개요를 다시 받아 덮어쓴다")
    args = ap.parse_args()

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    universe = {i["symbol"]: i for i in json.loads(UNIVERSE.read_text(encoding="utf-8"))["items"]}
    if args.tickers:
        todo = args.tickers
    elif args.refresh_dart:
        todo = [s for s in universe if (profiles.get(s) or {}).get("source") == "dart"]
    else:
        todo = [s for s in universe if not (profiles.get(s) or {}).get("industry")
                or not (profiles.get(s) or {}).get("summary")]
    corp = dart.load_corp_codes(CORP_CACHE)
    _log(f"사업정보 보강 대상 {len(todo)}종목")

    end = date.today()
    bgn = end - timedelta(days=550)  # 최근 사업보고서가 들어오도록 1년 반
    filled = no_corp = no_overview = 0
    for t in todo:
        name = universe.get(t, {}).get("name", "")
        cc = corp.get(t)
        if not cc:
            no_corp += 1
            _log(f"  {t} {name}: DART 기업코드 없음")
            continue
        existing = profiles.get(t) or {}
        info = dart.fetch_company(cc)
        code = str(info.get("induty_code") or "")
        time.sleep(0.15)

        overview = None
        try:
            rcept = dart.latest_annual_report_no(cc, bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            time.sleep(0.15)
            if rcept:
                overview = dart.business_overview(rcept)
                time.sleep(0.15)
        except dart.DartKeyError:
            raise
        except Exception as e:  # noqa: BLE001 - 한 종목 실패로 전체를 멈추지 않는다
            _log(f"  {t} {name}: 사업의 개요 조회 실패 {type(e).__name__}: {str(e)[:100]}")
        if not overview:
            no_overview += 1

        rec = apply_dart_fields(existing, industry=industry_label(code) if code else None,
                                industry_code=code or None, overview=overview,
                                refresh=args.refresh_dart)
        if rec != existing:
            profiles[t] = rec
            filled += 1
        snippet = " ".join((overview or "")[:70].split())
        _log(f"  {t} {name}: 업종 {rec.get('industry', '-')} / 개요 {len(overview) if overview else 0}자"
             + (f" | {snippet}" if snippet else ""))

    PROFILES.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
    _log(f"완료: 보강 {filled} / 기업코드 없음 {no_corp} / 사업의 개요 못 찾음 {no_overview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
