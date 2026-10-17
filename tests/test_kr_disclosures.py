"""한국 공시 원문 표 파싱 (src/collectors/kr_disclosures.py) - 2026-10-16 실제 공시 행."""
from src.collectors.kr_disclosures import classify, num, parse_contract, parse_notice, parse_prelim

CONTRACT = [
    "씨이랩/단일판매ㆍ공급계약체결/(2026.10.16)단일판매ㆍ공급계약체결 단일판매ㆍ공급계약체결 1. 판매ㆍ공급계약 내용 | AI 인프라 구축",
    "2. 계약내역 | 조건부 계약여부 | 미해당", "확정 계약금액 | 1,908,000,000", "조건부 계약금액 | -",
    "계약금액 총액(원) | 1,908,000,000", "최근 매출액(원) | 10,272,320,511", "매출액 대비(%) | 18.57",
    "3. 계약상대방 | (주)슈퍼솔루션", "- 최근 매출액(원) | 71,862,152,783", "- 주요사업 | 시스템통합 개발, 유지보수 및 유통업",
    "4. 판매ㆍ공급지역 | 대한민국", "5. 계약기간 | 시작일 | 2026-10-16", "종료일 | 2027-07-31",
]
CONTRACT_OLD_FORM = ["1. 판매ㆍ공급계약 구분 | 기타 판매ㆍ공급계약", "- 체결계약명 | 부동산 임대차 계약 체결",
                     "2. 계약내역 | 계약금액(원) | 46,800,000", "최근매출액(원) | 461,606,000", "매출액대비(%) | 10.14",
                     "3. 계약상대 | 개인"]
PRELIM = [
    "당기실적 | 2026-07-01 | ~ | 2026-09-30", "전기실적 | 2026-04-01 | ~ | 2026-06-30",
    "1. 연결실적내용 | 단위 : 백만원, %",
    "구분 | 당기실적 | 전기실적 | 전기대비 | 전년동기실적 | 전년동기대비",
    "매출액 | 당해실적 | 439,857 | 534,254 | -17.7 | - | 354,481 | 24.1 | -",
    "누계실적 | 1,388,040 | - | - | - | 1,022,299 | 35.8 | -",
    "영업이익 | 당해실적 | 4,815 | 47,954 | -90.0 | - | 10,765 | -55.3 | -",
    "당기순이익 | 당해실적 | -7,092 | 43,893 | - | 적자전환 | 5,949 | - | 적자전환",
]
NOTICE = ["1. 회사명 | 한미약품 주식회사", "2. 결산대상기간 | 시작일 | 2026-07-01", "종료일 | 2026-09-30",
          "3. 결산실적 공시예정일 | 2026-10-27"]


def test_classify():
    assert classify("단일판매ㆍ공급계약체결") == "contract"
    assert classify("단일판매ㆍ공급계약체결(자율공시)") == "contract"
    assert classify("[기재정정]단일판매ㆍ공급계약체결") is None
    assert classify("단일판매ㆍ공급계약체결(자회사의 주요경영사항)") is None
    assert classify("연결재무제표기준영업(잠정)실적(공정공시)") == "prelim"
    assert classify("영업(잠정)실적(공정공시)") == "prelim"
    assert classify("결산실적공시예고(안내공시)") == "notice"
    assert classify("기업설명회(IR)개최(안내공시)") is None


def test_num():
    assert num("1,908,000,000") == 1908000000 and num("-7,092") == -7092 and num("(7,650)") == -7650
    assert num("-") is None and num("") is None and num("미해당") is None and num("18.57") == 18.57


def test_contract_both_forms():
    c = parse_contract(CONTRACT)
    assert c["amount"] == 1_908_000_000 and c["pct_of_revenue"] == 18.57
    assert c["recent_revenue"] == 10_272_320_511            # 계약상대방 매출이 아니라 회사 매출
    assert c["title"] == "AI 인프라 구축" and c["counterparty"] == "(주)슈퍼솔루션"
    assert c["start"] == "2026-10-16" and c["end"] == "2027-07-31"
    o = parse_contract(CONTRACT_OLD_FORM)
    assert o["amount"] == 46_800_000 and o["pct_of_revenue"] == 10.14 and o["title"] == "부동산 임대차 계약 체결"


def test_prelim_units_yoy_and_turn():
    p = parse_prelim(PRELIM)
    assert p["period_end"] == "2026-09-30" and p["unit"] == 1e6
    assert p["revenue"] == 439_857e6 and p["revenue_yoy_pct"] == 24.1
    assert p["operating_income_yoy_pct"] == -55.3
    assert p["net_income"] == -7_092e6 and p["net_income_yoy_pct"] is None and p["net_income_yoy_turn"] == "적자전환"


def test_prelim_drops_inconsistent_pct():
    rows = [r.replace("| 24.1 |", "| 99.0 |") for r in PRELIM]     # 칸 위치가 다른 양식이면 맞지 않는다
    assert parse_prelim(rows)["revenue_yoy_pct"] is None


def test_notice():
    assert parse_notice(NOTICE) == {"announce_date": "2026-10-27", "period_start": "2026-07-01", "period_end": "2026-09-30"}


def test_summary_lines():
    from src.collectors.kr_disclosures import fmt_eok, summary
    assert fmt_eok(1_908_000_000) == "19억" and fmt_eok(1.23e12) == "1.2조" and fmt_eok(46_800_000) == "0.5억"
    assert summary("contract", parse_contract(CONTRACT)) == "공급계약 19억 (매출 대비 18.6%) · AI 인프라 구축"
    assert summary("prelim", parse_prelim(PRELIM)) == "잠정실적 26.3Q 전년동기 대비 매출 +24% · 영업익 -55%"
    assert summary("notice", parse_notice(NOTICE)) == "실적 발표 예정 2026-10-27"


def test_alert_only_tagged():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "collect_kr_disclosures", Path(__file__).resolve().parent.parent / "scripts" / "collect_kr_disclosures.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    new = [{"rcept_no": "1", "rcept_dt": "2026-10-16", "stock_code": "189330", "corp_name": "씨이랩", "kind": "contract",
            "payload": parse_contract(CONTRACT)},
           {"rcept_no": "2", "rcept_dt": "2026-10-16", "stock_code": "007690", "corp_name": "국도화학&Co", "kind": "prelim",
            "payload": parse_prelim(PRELIM)}]
    assert m.alert_text(new, {}) is None
    text = m.alert_text(new, {"007690": ["my", "cand"]})
    assert "관심 종목 1건" in text and "국도화학&amp;Co" in text and "내 관심 · 워치" in text and "씨이랩" not in text


def test_contract_withheld_and_detail_title():
    rows = ["1. 판매ㆍ공급계약 구분 | 기타 판매ㆍ공급계약", "- 체결계약명 | -", "2. 계약내역 | 계약금액(원) | -",
            "최근매출액(원) | 3,664,150,568,020", "매출액대비(%) | -", "8. 공시유보 관련내용 | 유보사유 | 경영상 비밀유지"]
    c = parse_contract(rows)
    assert c["amount"] is None and c["title"] is None and c["withheld"] == "경영상 비밀유지"
    from src.collectors.kr_disclosures import summary
    assert summary("contract", c) == "공급계약 금액 비공개"
    d = parse_contract(["1. 판매ㆍ공급계약 구분 | 기타 판매ㆍ공급계약", "- 세부내용 | AI 반도체 기판 장비 수주",
                        "2. 계약내역 | 계약금액(원) | 24,480,000,000", "8. 공시유보 관련내용 | 유보사유 | -"])
    assert d["title"] == "AI 반도체 기판 장비 수주" and d["amount"] == 24_480_000_000 and d["withheld"] is None


def test_prelim_trillion_unit_and_monthly():
    rows = ["당기실적 | 2026-07-01 | ~ | 2026-09-30", "1. 연결실적내용 | 단위 : 조원, %",
            "매출액 | 당해실적 | 195.00 | 171.50 | 13.70 | - | 86.06 | 126.59 | -",
            "영업이익 | 당해실적 | 107.40 | 89.49 | 20.01 | - | 12.17 | 782.50 | -"]
    p = parse_prelim(rows)
    assert p["revenue"] == 195e12 and p["revenue_yoy_pct"] == 126.59 and p["operating_income_yoy_pct"] == 782.5
    assert p["monthly"] is False
    m = parse_prelim(["당기실적 | 2026-09-01 | ~ | 2026-09-30", "1. 실적내용 | 단위 : 억원, %",
                      "매출액 | 당해실적 | 16,476 | 15,738 | 4.7 | - | 14,812 | 11.2 | -",
                      "영업이익 | 당해실적 | - | - | - | - | - | - | -"])
    from src.collectors.kr_disclosures import prelim_has_values, summary
    assert m["monthly"] is True and summary("prelim", m) == "잠정실적 26.9월 전년동기 대비 매출 +11%"
    assert prelim_has_values(m) and not prelim_has_values(parse_prelim(["당기실적 | 2026-09-01 | ~ | 2026-09-30"]))


def test_prelim_annual_label():
    from src.collectors.kr_disclosures import quarter_label
    p = parse_prelim(["당기실적 | 2026-01-01 | ~ | 2026-12-31"])
    assert p["annual"] is True and p["monthly"] is False
    assert quarter_label(p["period_end"], p["monthly"], p["annual"]) == "26년"
    assert quarter_label("2026-12-31") == "26.4Q"
