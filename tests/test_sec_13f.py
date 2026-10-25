"""13F 파싱·정정 합치기·분기 비교(2026-10-25)."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.collectors.sec_13f import (aggregate, combine_period, diff_positions, norm_ticker, parse_infotable,  # noqa: E402
                                    parse_primary, quarter_label, with_weights)
from collect_13f import _quarter_gap, cutoff_period  # noqa: E402

INFO = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>1000000</value>
    <shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>200000</value>
    <shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass><cusip>037833100</cusip><value>50000</value>
    <shrsOrPrnAmt><sshPrnamt>300</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
</informationTable>"""
PRIMARY = """<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><formData><coverPage><isAmendment>true</isAmendment>
<amendmentInfo><amendmentType>NEW HOLDINGS</amendmentType></amendmentInfo></coverPage>
<summaryPage><tableEntryTotal>3</tableEntryTotal><tableValueTotal>1250000</tableValueTotal></summaryPage></formData></edgarSubmission>"""


def test_parse_and_aggregate():
    rows = parse_infotable(INFO)
    assert len(rows) == 3 and rows[2]["put_call"] == "CALL"
    agg = aggregate(rows)
    assert agg[("037833100", "")]["shares"] == 6000 and agg[("037833100", "")]["value"] == 1200000
    assert agg[("037833100", "CALL")]["shares"] == 300


def test_parse_primary_amendment():
    p = parse_primary(PRIMARY)
    assert p == {"amendment_type": "NEW HOLDINGS", "entries": 3, "value_total": 1250000}


def _pos(**kw):
    return {(c, ""): {"cusip": c, "put_call": "", "issuer": c, "title": "COM", "shares": s, "value": s * 10} for c, s in kw.items()}


def test_combine_new_holdings_adds_and_restatement_replaces():
    base = {"form": "13F-HR", "filed": "2026-08-14", "amendment_type": None, "rows": _pos(AAA=100)}
    newh = {"form": "13F-HR/A", "filed": "2026-11-14", "amendment_type": "NEW HOLDINGS", "rows": _pos(BBB=50)}
    got = combine_period([newh, base])
    assert set(k[0] for k in got) == {"AAA", "BBB"}
    rest = {"form": "13F-HR/A", "filed": "2026-09-01", "amendment_type": "RESTATEMENT", "rows": _pos(CCC=7)}
    got = combine_period([base, rest, newh])
    assert set(k[0] for k in got) == {"CCC", "BBB"}


def test_diff_statuses():
    prev = _pos(AAA=100, BBB=100, CCC=100)
    cur = _pos(AAA=150, BBB=40, DDD=10, CCC=100)
    st = {r["cusip"]: r["status"] for r in diff_positions(prev, cur)}
    assert st == {"AAA": "added", "BBB": "reduced", "CCC": "same", "DDD": "new"}
    sold = [r for r in diff_positions(_pos(EEE=5), _pos(AAA=1)) if r["status"] == "sold"]
    assert sold and sold[0]["cusip"] == "EEE" and sold[0]["shares"] == 0
    assert all(r["status"] is None for r in diff_positions(None, cur))   # 직전 분기 없음 = 비교 안 함


def test_weights_skip_options():
    rows = with_weights([{"value": 300, "put_call": ""}, {"value": 100, "put_call": ""}, {"value": 999, "put_call": "PUT"}])
    assert rows[0]["weight"] == 0.75 and rows[2]["weight"] is None


def test_quarters():
    assert cutoff_period(5, date(2026, 10, 25)) == "2025-06-01"
    assert cutoff_period(1, date(2026, 2, 10)) == "2025-09-01"
    assert _quarter_gap("2026-03-31", "2026-06-30") == 1 and _quarter_gap("2025-12-31", "2026-06-30") == 2
    assert quarter_label("2026-06-30") == "2026 Q2" and norm_ticker("BRK/B") == "BRK.B"
