"""테마 소속 자동 점검 규칙 (docs/radar/PROGRESS.md 2026-10-23).

2026-10-16(미국)·10-22(한국) 테마 정의를 손으로 대조해 뺀 소속과 판정 원장의 제외 판정은 반복되는
유형이었다. 그 유형을 규칙으로 만들어, 분기 자동 매핑 때 사람이 볼 후보를 추린다.

**판정이 아니라 검토 후보다.** 규칙에 걸린 행을 자동으로 빼지 않는다 - 사업정보 요약이 짧거나
사업부 하나를 빠뜨린 경우가 있다. 원장에 사람 판정(keep/hold)이 있는 행은 호출부가 건너뛴다.
LLM을 쓰지 않는다(원칙 2와 같은 취지 - 판단 근거가 재현돼야 한다). 네트워크·DB 접근 없음.

규칙 코드:
  industry   산업분류상 이 테마에 들어갈 수 없는 업종(보험사가 2차전지에, 식품사가 구리에 등)
  utility    발전·송배전을 함께 하는 규제 전력회사가 에너지 테마에(2026-09-15 사용자 결정으로 제외)
  holding    같은 테마에 상장 자회사가 따로 있는 지주사(매핑 공통 기준: 자회사를 고른다)
  support    사업정보(산업분류 + 긴 요약)에 테마 근거 단어가 하나도 없음(config/theme_evidence_keywords.yaml)
  no_profile 사업정보 자체가 없어 support를 판단할 수 없음(규칙 적용 불가 - 데이터부족, 원칙 4)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KEYWORDS_YAML = ROOT / "config" / "theme_evidence_keywords.yaml"

# 산업분류상 들어갈 수 있는 테마가 정해진 업종. 여기 걸리는 업종의 기업이 목록 밖
# 테마로 편입되면 걸린다(LLM 판단과 무관한 사실 기준).
#
# 근거(2026-09-15 사람 판정 원장 대조): KR에서 사람이 틀린 편입으로 확정한 116건 중
# 21건이 이런 업종 불일치였다 - 현대해상이 배터리·구리·석유화학에, 코리안리(재보험)가
# AI반도체에, 빙그레가 구리에, 코스맥스(화장품 ODM)가 게임에. 같은 규칙으로 사람이 정상
# 판정한 행은 한 건도 걸리지 않았다. US 오류는 이런 유형이 없었다(경계 판단 오류뿐).
#
# 넣지 않은 업종과 이유: 항공사(대한항공은 항공우주 사업부가 실재), 리츠(데이터센터
# 리츠), 가구·가전(코웨이 등 경계 모호), 통신(데이터센터·AI 사업), 보안(한화비전).
# 산업분류가 없거나 틀린 종목은 규칙이 적용되지 않는다(조선사 보정은 kr_profile_overrides).
# (2026-10-23 scripts/map_theme_companies.py에서 옮겨 옴 - 매핑과 점검이 같은 목록을 쓴다.)
INDUSTRY_THEME_ALLOW: list[tuple[tuple[str, ...], frozenset[str]]] = [
    (("Insurance", "Banks", "Capital Markets", "Asset Management", "Credit Services",
      "Financial Data", "Shell Companies"), frozenset()),
    (("Packaged Foods", "Beverages", "Confectioners", "Food Distribution", "Farm Products",
      "Grocery Stores", "Tobacco", "Restaurants"), frozenset({"k_food"})),
    (("Household & Personal Products",), frozenset({"k_beauty"})),
    (("Apparel", "Footwear", "Luxury Goods"), frozenset()),
    (("Lodging", "Resorts & Casinos", "Travel Services"), frozenset({"travel_airline"})),
    (("Electronic Gaming & Multimedia",), frozenset({"game"})),
    (("Entertainment",), frozenset({"k_content"})),
]


def industry_theme_conflict(theme_id: str, ticker: str, profiles: dict[str, dict]) -> str | None:
    """산업분류상 이 테마에 들어갈 수 없는 기업이면 그 산업분류를, 아니면 None."""
    industry = (profiles.get(ticker) or {}).get("industry") or ""
    if not industry:
        return None
    for prefixes, allowed in INDUSTRY_THEME_ALLOW:
        if industry.startswith(prefixes):
            return None if theme_id in allowed else industry
    return None


# 규제 전력회사 - 에너지 테마에서 제외(themes.yaml 유지보수 규칙 6, 2026-09-15 사용자 결정).
# 가스 테마는 정의 (1)이 도시가스사를 편입하므로 "Regulated Gas"는 lng_gas에서만 허용한다.
ENERGY_THEMES = frozenset({"power_grid", "nuclear_smr", "renewable_energy", "energy_storage",
                           "lng_gas", "datacenter_power"})
UTILITY_INDUSTRIES = ("Utilities - Regulated Electric", "Utilities - Diversified", "Utilities - Regulated Gas")


def utility_conflict(theme_id: str, industry: str) -> str | None:
    if theme_id not in ENERGY_THEMES or not industry.startswith(UTILITY_INDUSTRIES):
        return None
    if theme_id == "lng_gas" and industry.startswith("Utilities - Regulated Gas"):
        return None
    return industry


# 지주사 이름 끝말. "홀딩스"가 없어도(대웅·넥센) 같은 테마에 "이름 + 무엇"인 회사가 있으면 걸린다.
HOLDING_SUFFIXES = ("홀딩스", "지주", " Holdings", " Holding")


def _base_name(name: str) -> str:
    for s in HOLDING_SUFFIXES:
        if name.endswith(s):
            return name[: -len(s)].strip()
    return name.strip()


def holding_conflict(name: str, peer_names: list[str]) -> str | None:
    """같은 테마 안에 상장 자회사로 보이는 회사가 있으면 그 이름을.

    - "농심홀딩스"와 "농심": 이름에서 홀딩스를 뗀 "농심"이 다른 소속 이름에 들어 있다.
    - "대웅"과 "대웅제약": 다른 소속 이름이 이 이름으로 시작하고 더 길다(그쪽이 홀딩스면 제외 -
      반대 방향이므로).
    이름이 2자 미만이면 판단하지 않는다(우연한 포함을 막는다)."""
    if not name:
        return None
    is_holding_name = name.endswith(HOLDING_SUFFIXES)
    base = _base_name(name)
    if len(base) < 2:
        return None
    for peer in peer_names:
        if not peer or peer == name:
            continue
        if is_holding_name and base in peer:
            return peer
        if not is_holding_name and peer.startswith(name) and len(peer) > len(name) \
                and not peer.endswith(HOLDING_SUFFIXES):
            return peer
    return None


def load_keyword_patterns(path: Path = KEYWORDS_YAML) -> dict[str, list[re.Pattern]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {theme: [re.compile(p, re.IGNORECASE) for p in pats] for theme, pats in raw.items()}


def profile_text(profile: dict | None) -> str:
    if not profile:
        return ""
    return " ".join(str(profile.get(k) or "") for k in ("industry", "summary_long", "summary"))


def support_conflict(theme_id: str, profile: dict | None,
                     patterns: dict[str, list[re.Pattern]]) -> str | None:
    """사업정보에 테마 근거가 하나도 없으면 "support", 사업정보가 없으면 "no_profile", 근거가 있으면 None.
    테마 단어 목록이 없으면 판단하지 않는다(None)."""
    pats = patterns.get(theme_id)
    if not pats:
        return None
    text = profile_text(profile)
    if not text.strip():
        return "no_profile"
    return None if any(p.search(text) for p in pats) else "support"


def check_member(theme_id: str, ticker: str, name: str, profiles: dict[str, dict],
                 peer_names: list[str], patterns: dict[str, list[re.Pattern]]) -> list[tuple[str, str]]:
    """한 소속 행에 걸린 규칙 [(코드, 설명)]. 빈 목록이면 걸린 것 없음."""
    out: list[tuple[str, str]] = []
    profile = profiles.get(ticker)
    industry = (profile or {}).get("industry") or ""
    ind = industry_theme_conflict(theme_id, ticker, profiles)
    if ind:
        out.append(("industry", f"산업분류 '{ind}'는 이 테마에 들어갈 수 없는 업종"))
    util = utility_conflict(theme_id, industry)
    if util:
        out.append(("utility", f"규제 전력회사('{util}') - 에너지 테마 제외 기준"))
    peer = holding_conflict(name, peer_names)
    if peer:
        out.append(("holding", f"같은 테마에 상장 자회사로 보이는 '{peer}'가 있음"))
    sup = support_conflict(theme_id, profile, patterns)
    if sup == "support":
        out.append(("support", "사업정보(산업분류·요약)에 테마 근거 단어가 없음"))
    elif sup == "no_profile":
        out.append(("no_profile", "사업정보가 없어 근거를 확인할 수 없음"))
    return out
