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


def test_kr_levels_use_ksic_not_sector():
    """한국(2026-11-13): yfinance 업종이 모자라면 KSIC 소분류 → 중분류, 섹터로는 넓히지 않는다."""
    from src.analyzers.company_valuation import peer_levels, tier_from_levels
    prof = {"i": "Resorts & Casinos", "s": "Consumer Cyclical",
            "g": [["ksic3:912", "유원지 및 기타 오락관련 서비스업"], ["ksic2:91", "스포츠 및 오락관련 서비스업"]]}
    levels = peer_levels("KR", prof)
    assert [b for b, _, _ in levels] == ["업종", "업종", "업종 대분류"]
    table = {"i:Resorts & Casinos": [1.0, 2.0], "ksic3:912": [0.8, 1.0, 1.2, 1.5, 2.0], "s:Consumer Cyclical": [0.1] * 20}
    r = tier_from_levels(1.1, levels, table)
    assert (r["basis"], r["group"], r["tier"]) == ("업종", "유원지 및 기타 오락관련 서비스업", MID)
    assert tier_from_levels(1.1, levels, {"s:Consumer Cyclical": [0.1] * 20})["tier"] is None   # 섹터로 안 넓힘
    assert [b for b, _, _ in peer_levels("US", {"i": "Software", "s": "Technology"})] == ["업종", "섹터"]
