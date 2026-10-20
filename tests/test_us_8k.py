from src.collectors.us_8k import describe, excerpt, html_text, item_section, officer_change, recent_8k, tracked_items

DOC = """<html><body><p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>
<p><b>Item&nbsp;5.02. Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers;
Compensatory Arrangements of Certain Officers.</b></p>
<p>On October 15, 2026, Jane Roe notified the Board of Directors of her decision to resign as Chief Financial Officer,
effective November 1, 2026. Ms. Roe's resignation is not the result of any disagreement with the Company.</p>
<p><b>Item 9.01 Financial Statements and Exhibits.</b></p><p>99.1 Press release</p>
<p>SIGNATURES</p></body></html>"""


def test_tracked_items_and_recent():
    assert tracked_items("2.02,7.01,9.01") == ["2.02"] and tracked_items("7.01,9.01") == []
    sub = {"filings": {"recent": {"form": ["8-K", "8-K/A", "8-K", "4"], "accessionNumber": ["a", "b", "c", "d"],
                                  "filingDate": ["2026-10-15", "2026-10-15", "2026-08-01", "2026-10-15"],
                                  "primaryDocument": ["x.htm", "y.htm", "z.htm", "f.xml"],
                                  "items": ["5.02,9.01", "5.02", "1.01", ""]}}}
    got = recent_8k(sub, "2026-10-01")
    assert [g["accession"] for g in got] == ["a"] and got[0]["items"] == ["5.02"]


def test_item_section_strips_title():
    seg = item_section(html_text(DOC), "5.02")
    assert seg.startswith("On October 15, 2026, Jane Roe") and "Item 9.01" not in seg and "99.1" not in seg
    assert officer_change(seg) == "사임·퇴임"


def test_describe_and_officer_kinds():
    d = describe(["5.02"], html_text(DOC))
    assert not d["warn"] and d["items"][0]["label"] == "임원·이사 변동(사임·퇴임)" and d["items"][0]["excerpt"]
    assert officer_change("The Board appointed John Doe as Chief Operating Officer.") == "선임"
    assert officer_change("The Committee approved the annual bonus plan.") == "보상·기타"
    e = describe(["2.02"], None)
    assert e["earnings_only"] and not e["warn"] and e["items"][0]["excerpt"] is None
    assert describe(["1.02", "2.06"], None)["warn"] and not describe(["1.01"], None)["warn"]


def test_excerpt_cuts_at_sentence():
    s = "First sentence is here. " * 30
    out = excerpt(s, 100)
    assert out.endswith(". …") and len(out) <= 104
