"""기업 카드 사업 요약 한국어판(2026-11-05) - yfinance 영문 원문을 GPT(gpt-4o-mini)가 2~3문장으로 옮긴다.

원문을 옮길 뿐 새 사실을 보태지 않게 하고, 숫자(연도·직원 수·매장 수·금액·비율)는 쓰지 않게 한다 - 그래도 들어온 숫자 문장은
뒷손질로 뺀다(원칙 2: LLM이 만든 숫자를 화면에 두지 않는다). 'K9'·'G9 NAND'·'8-K'처럼 숫자가 든 이름은 단위가 없어 남는다.
"""
from __future__ import annotations

import hashlib
import re

SYSTEM = ("당신은 영문 회사 소개를 한국어로 옮기는 편집자입니다. 원문에 있는 내용만 쓰고 새 사실을 보태지 않습니다. "
          "숫자(연도, 직원 수, 매장 수, 국가 수, 금액, 비율)는 쓰지 않습니다. 평가·전망·투자 의견을 쓰지 않습니다.")

# 연도·개수·금액·비율이 든 문장(단위가 붙은 숫자). 제품 이름 속 숫자(K9, G9, 13F)는 단위가 없어 남는다.
_NUM = re.compile(r"\d{4}\s*년|\d[\d,]*(\.\d+)?\s*(%|명|개국|개사|개|곳|달러|억|조|만|천|배|년|년대|분기|위)|\$\s?\d")


def src_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:10]


def build_prompt(items: list[tuple[str, str, str]]) -> str:
    """items: (symbol, 회사 이름, 영문 요약)"""
    body = "\n\n".join(f"[{sym}] {name or sym}\n{en}" for sym, name, en in items)
    return ("아래 회사 소개를 각각 한국어 2~3문장(200자 안팎)으로 요약하세요. 무엇을 만들거나 제공하는지, 주요 사업 부문과 고객을 중심으로. "
            "문장은 '~한다/~이다'로 끝내고, 회사 이름은 한국에서 쓰는 이름이 있으면 그것으로(모르면 영문 그대로). "
            "숫자는 쓰지 마세요.\n\n"
            f"{body}\n\n"
            'JSON으로만 답하세요: {"items": [{"symbol": "...", "ko": "..."}]} - 위 목록의 모든 회사를 한 번씩.')


def clean(text: str) -> str:
    """숫자 문장 빼기 + 공백 정리. 다 빠지면 빈 문자열."""
    parts = re.split(r"(?<=[.!?다])\s+", (text or "").strip())
    kept = [p.strip() for p in parts if p.strip() and not _NUM.search(p)]
    return " ".join(kept)


def validate(parsed: dict, symbols: list[str]) -> dict[str, str]:
    want, out = set(symbols), {}
    for it in (parsed or {}).get("items") or []:
        try:
            sym, ko = str(it["symbol"]).strip(), clean(str(it["ko"]))
        except (KeyError, TypeError):
            continue
        if sym in want and ko and sym not in out:
            out[sym] = ko
    return out
