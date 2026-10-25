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


def test_value_scale_and_debt():
    from src.collectors.sec_13f import is_debt, normalize_rows, value_scale
    thousands = {("632307104", ""): {"shares": 3186306, "value": 864923}, ("874039100", ""): {"shares": 589680, "value": 281613}}
    dollars = {("037833100", ""): {"shares": 227917808, "value": 65950296923}}
    assert value_scale(thousands) == 1000 and value_scale(dollars) == 1
    assert is_debt("007973AE0") and not is_debt("037833100")
    rows = normalize_rows({("632307104", ""): {"cusip": "632307104", "put_call": "", "issuer": "Natera", "title": "COM", "shares": 3186306, "value": 864923},
                           ("874039100", ""): {"cusip": "874039100", "put_call": "", "issuer": "TSM", "title": "ADR", "shares": 589680, "value": 281613},
                           ("007973AE0", ""): {"cusip": "007973AE0", "put_call": "", "issuer": "ADV ENERGY", "title": "NOTE", "shares": 1000, "value": 1}})
    assert rows[("632307104", "")]["value"] == 864923000 and ("007973AE0", "DEBT") in rows


def test_merge_renamed_cusip_change():
    from src.collectors.sec_13f import merge_renamed
    rows = [
        {"cusip": "NEW1", "put_call": "", "issuer": "EXXON MOBIL CORP", "shares": 100, "value": 1000, "status": "new", "prev_shares": None, "prev_value": None, "share_chg": None},
        {"cusip": "OLD1", "put_call": "", "issuer": "Exxon Mobil Corp", "shares": 0, "value": 0, "status": "sold", "prev_shares": 120, "prev_value": 1100, "share_chg": -1.0},
        {"cusip": "X", "put_call": "", "issuer": "Other Inc", "shares": 5, "value": 5, "status": "new", "prev_shares": None, "prev_value": None, "share_chg": None},
    ]
    out = merge_renamed(rows)
    assert len(out) == 2
    xom = next(r for r in out if r["cusip"] == "NEW1")
    assert xom["status"] == "reduced" and xom["prev_shares"] == 120


def test_name_match():
    from src.collectors.sec_13f import name_match, norm_issuer
    titles = {norm_issuer("Arcosa, Inc."): "ACA"}
    assert name_match({"039653100": "ARCOSA INC", "Z": "Nothing Corp"}, titles) == {"039653100": "ACA"}


def test_figi_pick_only_us_equity():
    from src.collectors.sec_13f import _pick_figi, norm_ticker, valid_ticker
    assert _pick_figi([{"ticker": "SMCI 7 06.01.29", "marketSector": "Corp", "exchCode": "US"}]) is None
    assert _pick_figi([{"ticker": "CPRXEUR", "marketSector": "Equity", "exchCode": "GR"}]) is None
    d = _pick_figi([{"ticker": "AM6", "marketSector": "Equity", "exchCode": "GF"},
                    {"ticker": "ACA", "marketSector": "Equity", "exchCode": "UN", "securityType": "Common Stock"}])
    assert d["ticker"] == "ACA"
    assert norm_ticker("WBD*") == "WBD" and valid_ticker("BRK.B") and not valid_ticker("HO1")
