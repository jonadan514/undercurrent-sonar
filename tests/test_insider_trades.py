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


KR_ROWS = [
    "보고의무발생일 : | 2026년 10월 14일",
    "보고자 : | (주)지본",
    "임원(등기여부) | - | 직위명 | -",
    "주요주주 | 10%이상주주",
    "직전보고서 | 2026년 10월 14일 | 5,025,520 | 24.04 | 5,025,520 | 24.04",
    "장내매수(+) | 2026년 10월 14일 | 보통주 | 5,025,520 | 113,000 | 5,138,520 | 1,339.72 | - | 2026년 08월 25일",
    "장내매수(+) | 2026.10.15 | 보통주 | 5,138,520 | 30,000 | 5,168,520 | 1,322.15 | - | 2026.08.25",
    "주식매수선택권(+) | 2026년 10월 13일 | 보통주 | 49,000 | 21,000 | 70,000 | 3,000 | - | -",
    "합 계 | 5,025,520 | 186,000 | 5,211,520 | 1,327.84 | -",
]


def test_kr_ownership_only_open_market_buys():
    from src.collectors.insider_trades import parse_kr_ownership
    t = parse_kr_ownership(KR_ROWS)
    assert [x["trade_date"] for x in t] == ["2026-10-14", "2026-10-15"]     # 스톡옵션·합계 줄은 뺀다
    assert t[0]["owner"] == "(주)지본" and t[0]["role"] == "10% 이상 주주"
    assert t[0]["shares"] == 113_000 and t[0]["price"] == 1339.72 and t[0]["owned_after"] == 5_138_520
    rows = [r.replace("임원(등기여부) | - | 직위명 | -", "임원(등기여부) | 등기임원 | 직위명 | 대표이사").replace("주요주주 | 10%이상주주", "주요주주 | -") for r in KR_ROWS]
    assert parse_kr_ownership(rows)[0]["role"] == "대표이사"


def test_clean_role():
    from src.collectors.insider_trades import clean_role
    assert clean_role("10%?씠?긽주주") == "10% 이상 주주" and clean_role("대표?씠?궗") is None
    assert clean_role("대표이사") == "대표이사" and clean_role("-") is None


def test_open_market_buy_reason():
    from src.collectors.insider_trades import is_open_market_buy
    assert is_open_market_buy("장내매수(+)") and is_open_market_buy("?옣?궡매수(+)")
    assert not is_open_market_buy("?옣?쇅매수(+)") and not is_open_market_buy("장외매수(+)")
    assert not is_open_market_buy("주식매수선택권행사(+)") and not is_open_market_buy("?옣?궡매도(-)")
