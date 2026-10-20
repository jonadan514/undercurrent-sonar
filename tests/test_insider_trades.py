"""내부자 장내 매수 파싱 (src/collectors/insider_trades.py)."""
from src.collectors.insider_trades import cluster_buyers, parse_form4, raw_xml_name

FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000723125</issuerCik><issuerName>MICRON TECHNOLOGY INC</issuerName><issuerTradingSymbol>MU</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>125.5</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>21000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-15</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>20</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-16</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>300</value></transactionShares>
        <transactionPricePerShare><value>130</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_only_open_market_purchases():
    t = parse_form4(FORM4)
    assert len(t) == 1                          # 옵션 행사(M)·매도(S)는 뺀다
    x = t[0]
    assert x["symbol"] == "MU" and x["owner"] == "Doe Jane" and x["role"] == "CFO · 이사"
    assert x["trade_date"] == "2026-10-15" and x["shares"] == 1000 and x["value"] == 125_500
    assert x["owned_after"] == 21000 and x["direct"] and not x["plan"]


def test_plan_flag_and_helpers():
    assert parse_form4(FORM4.replace("<aff10b5One>0</aff10b5One>", "<aff10b5One>1</aff10b5One>"))[0]["plan"]
    assert raw_xml_name("xslF345X05/wk-form4_1729.xml") == "wk-form4_1729.xml"
    assert cluster_buyers([{"owner": "A"}, {"owner": "B"}, {"owner": "A"}]) == 2


def test_recent_form4_filter():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "collect_insider_trades", Path(__file__).resolve().parent.parent / "scripts" / "collect_insider_trades.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sub = {"filings": {"recent": {"form": ["4", "4/A", "8-K", "4"], "accessionNumber": ["a1", "a2", "a3", "a4"],
                                  "filingDate": ["2026-10-15", "2026-10-16", "2026-10-16", "2026-09-01"],
                                  "primaryDocument": ["xslF345X05/f.xml", "x.xml", "k.htm", "old.xml"]}}}
    assert m.recent_form4(sub, "2026-10-01") == [("a1", "2026-10-15", "f.xml")]
