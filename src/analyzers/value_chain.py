"""테마 가치사슬 구간(2026-11-05, 마스터 플랜 2단계 '가치사슬 시각화').

config/themes.yaml의 value_chain 글에 테마마다 "(1) … (2) …" 구간이 적혀 있다. 소속 기업의 단계(theme_members.stage)는
매핑 때 GPT가 자유롭게 쓴 글이라("Chip Manufacturer", "반도체 제조", "제조") 그대로는 묶을 수 없어, 기업마다 이 구간 번호
하나를 고르게 한다(scripts/classify_value_chain.py). 글을 글로 분류할 뿐 숫자는 다루지 않는다(원칙 2). 순위·점수 없음(원칙 1).
"""
from __future__ import annotations

import hashlib
import re

_SEG = re.compile(r"^\s*\((\d+)\)\s*(.+?)\s*$")
_STOP = ("편입하지 않음", "편입 안 함")


def parse_segments(value_chain: str | None) -> dict:
    """value_chain 글 -> {"intro": 첫 설명, "segments": [{"n": 1, "label": 첫 줄, "detail": 이어진 줄까지}], "exclude": 편입하지 않음 글}.
    구간 번호가 없으면 segments가 빈 목록."""
    intro, segs, exclude = [], [], []
    mode = "intro"
    for raw in (value_chain or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SEG.match(line)
        if m:
            segs.append({"n": int(m.group(1)), "label": m.group(2), "detail": m.group(2)})
            mode = "seg"
        elif line.startswith(_STOP):
            exclude.append(line)
            mode = "exclude"
        elif mode == "seg":
            segs[-1]["detail"] += " " + line
        elif mode == "exclude":
            exclude.append(line)
        else:
            intro.append(line)
    return {"intro": " ".join(intro), "segments": segs, "exclude": " ".join(exclude)}


PROMPT_VERSION = "2"   # 프롬프트를 고치면 올린다 - 지문이 바뀌어 다시 분류한다(예전 행은 그대로 남음)


def chain_hash(segments: list[dict], model: str = "") -> str:
    """분류 기준 지문 - 구간 글·모델·프롬프트 판이 바뀌면 다시 분류하려고 남긴다(2026-11-05 첫 실행 gpt-4o-mini는
    한화에어로스페이스·현대로템을 방산 '구간 밖'으로 두는 등 품질이 낮아 gpt-4o로 다시 돌렸다)."""
    key = "|".join(f"{s['n']}:{s['detail']}" for s in segments) + f"#{model}#{PROMPT_VERSION}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


SYSTEM = ("당신은 기업을 산업 가치사슬 구간에 배정하는 분류기입니다. 주어진 구간 번호 중 하나만 고릅니다.\n"
          "기준:\n"
          "- 이 테마와 관련해 그 회사가 실제로 만들거나 제공하는 제품·서비스가 어느 구간 설명에 해당하는지로 고릅니다.\n"
          "- 여러 사업을 하는 대기업은 회사 전체가 아니라 이 테마와 관련된 사업부를 기준으로 고릅니다"
          "(예: 자주포·장갑차를 만드는 회사는 방산의 무기체계 완제품, 수술 로봇·인공관절을 만드는 회사는 치료·수술 기기).\n"
          "- 구간 설명에 딱 맞는 단어가 없어도 같은 종류의 제품이면 그 구간입니다.\n"
          "- 0(어느 구간에도 안 맞음)은 이 테마의 어떤 구간과도 관련 사업이 없을 때만 씁니다.\n"
          "- 판단 근거는 제공된 회사 이름·업종·매핑 단계·근거 글과 일반적으로 알려진 회사의 주력 제품이며, 없는 사업을 지어내지 않습니다.")


LINKAGE_KO = {"direct": "직접", "partial": "부분", "peripheral": "간접"}


def build_prompt(theme_name: str, chain: dict, members: list[dict]) -> str:
    seg_lines = "\n".join(f"{s['n']}. {s['detail']}" for s in chain["segments"])
    mem_lines = "\n".join(
        f"- {m['ticker']} | {m.get('name') or '-'} | 업종: {m.get('industry') or '-'} | 소속: {LINKAGE_KO.get(m.get('linkage'), '-')} | "
        f"매핑 단계: {m.get('stage') or '-'} | "
        f"근거: {(m.get('evidence') or '-')[:160]}" for m in members)
    return (f"테마: {theme_name}\n설명: {chain['intro']}\n\n가치사슬 구간:\n{seg_lines}\n"
            + (f"\n참고(이 테마에 넣지 않는 것): {chain['exclude']}\n" if chain["exclude"] else "")
            + f"\n기업 목록:\n{mem_lines}\n\n"
            '각 기업에 구간 번호 하나를 정해 JSON으로만 답하세요: {"assign": [{"ticker": "...", "segment": 번호}]} '
            "- 목록의 모든 기업을 한 번씩, 맞는 구간이 없으면 0.")


def validate(parsed: dict, tickers: list[str], n_segments: list[int]) -> dict[str, int]:
    """응답 -> {ticker: 구간 번호}. 목록에 없는 티커·없는 번호는 버린다(빠진 기업은 다음 실행 때 다시 묻는다)."""
    valid = set(n_segments) | {0}
    want = set(tickers)
    out: dict[str, int] = {}
    for it in (parsed or {}).get("assign") or []:
        try:
            t, n = str(it["ticker"]).strip(), int(it["segment"])
        except (KeyError, TypeError, ValueError):
            continue
        if t in want and n in valid and t not in out:
            out[t] = n
    return out
