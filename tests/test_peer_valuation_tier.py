"""업종 기준 밸류 등급(2026-11-13) - 같은 시장·같은 업종 유니버스 PSR 분포의 가운데 절반 밖이면 싼 편/비싼 편."""
from src.analyzers.company_valuation import CHEAP, EXPENSIVE, MID, peer_valuation_tier

IND = {"Software": [6.0, 8.0, 9.0, 10.0, 12.0, 14.0], "Tiny": [1.0, 2.0]}
SEC = {"Technology": [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0]}


def test_tier_against_industry_not_market():
    # 소프트웨어 PSR 7은 시장 전체로는 비싸도 업종 안에서는 싼 편
    r = peer_valuation_tier(7.0, "Software", "Technology", IND, SEC)
    assert (r["tier"], r["basis"], r["group"], r["n"]) == (CHEAP, "업종", "Software", 6)
    assert peer_valuation_tier(9.5, "Software", "Technology", IND, SEC)["tier"] == MID
    assert peer_valuation_tier(13.5, "Software", "Technology", IND, SEC)["tier"] == EXPENSIVE


def test_falls_back_to_sector_then_none():
    r = peer_valuation_tier(3.0, "Tiny", "Technology", IND, SEC)   # 업종 2곳뿐 -> 섹터
    assert (r["basis"], r["group"], r["tier"]) == ("섹터", "Technology", MID)
    r = peer_valuation_tier(1.5, "Tiny", "Unknown", IND, SEC)
    assert r["tier"] is None and r["basis"] is None      # 데이터부족 - 탈락이 아니다


def test_no_own_psr_keeps_basis():
    r = peer_valuation_tier(None, "Software", None, IND, SEC)
    assert r["tier"] is None and r["basis"] == "업종" and r["median"] == 9.5
