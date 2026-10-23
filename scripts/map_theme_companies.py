"""테마 → 기업 매핑 (Phase A-2).

SPEC: docs/radar/SPEC_theme_company_mapping.md

경로 A(유니버스 제약 선택) + 경로 B(자유 생성)를 합쳐 후보를 만들고, 코드
검증(§4)을 통과한 것만 theme_members에 저장한다. approved=0으로 저장되며
사람이 검토해서 승인하기 전까지는 화면에 반영되지 않는다(§7).

Usage:
  python scripts/map_theme_companies.py                                    # 전체 테마
  python scripts/map_theme_companies.py --theme-id nuclear_smr physical_ai  # 특정 테마만(파일럿용)
  python scripts/map_theme_companies.py --market US                         # 한 시장만(실험·재매핑용)
"""
from __future__ import annotations

import argparse
import json
import re
import os
import random
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.db.data_store import get_db
from src.llm import openai_json as oj
from src.db.theme_mapping import ensure_schema, start_mapping_run, finish_mapping_run, insert_theme_member
from collectors.watchlist_collector import get_us_universe, get_kr_universe, US_MIN_CAP, KR_MIN_CAP

THEMES_YAML = ROOT / "config" / "themes.yaml"
# A/B 측정용 덮어쓰기. None이면 config/models.yaml(또는 환경변수 MODEL_<ROLE>)의 역할별 모델을 쓴다.
# diagnose_mapping_model.py가 여기에 모델 이름을 넣어 팔을 바꾼다. "기본 모델과 같은 이름"이어도
# 덮어쓰기로 취급한다 - 예전에는 기본값과 같으면 덮어쓰기가 없는 것으로 봐서 기준선 팔이 새어나갔다.
MODEL_OVERRIDE: str | None = None
PROMPT_VERSION = "2026-09-15-v7"  # v7: v6 + 미국 후보에도 산업분류·사업요약(400자) 첨부, 업종-테마 불일치 코드 제외, 에너지 테마 유틸리티 경계
UNIVERSE_CHUNK_SIZE = 200  # 청크당 줄 수 상한
# 청크당 글자 수 예산. 줄 길이가 시장마다 달라(US 약 440자, KR 약 170자) 종목 수로 자르면
# 미국 청크만 2만 토큰을 넘는다. 2026-09-15 진단(scripts/diagnose_us_chunk_size.py, 확인된
# 정답 21건, 호출 실패 0): 200종목 16건 / 100종목 17건 / 50종목 19건 적중, 알려진 오답
# 6 / 5 / 4건 - 긴 목록일수록 모델이 중간을 놓쳤다. 24000자 = US 약 55종목, KR 약 140종목.
CHUNK_CHAR_BUDGET = 24000
# 미국 사업요약은 140자로는 부족하다(2026-09-15 확인). 사업부가 여럿인 대기업은
# 첫 문장이 "worldwide manufacturer" 같은 일반론이라 테마와 닿는 사업부가 뒤에
# 나온다 - Deere의 건설장비는 202자, Teradyne의 반도체 테스트는 223자,
# Constellation의 원전은 384자 위치. 한국 요약은 대부분 단일 사업이라 140자 유지.
US_SUMMARY_CHARS = 400
PATH_A_RUNS = 2  # 파일럿에서 경로 A 결과가 회차마다 크게 흔들리는 현상을 발견 —
                 # 반복 실행 후 티커 기준 합집합으로 완화
MIN_EVIDENCE_LEN = 15
BANNED_EVIDENCE_PHRASES = ["관련 사업", "수혜 예상", "테마주", "관련주"]
HALLUCINATION_WARN_RATE = 0.30  # SPEC §4 — 경로 B 폐기율 30% 넘으면 로그로 경고


def _log(msg: str) -> None:
    print(f"[map_theme] {msg}")


def _norm_ticker(m: dict) -> str:
    """LLM이 대소문자를 안 지킬 수 있어 정규화 — KR 코드는 숫자라 upper()가 no-op."""
    return str(m.get("ticker", "")).strip().upper()


def load_themes(theme_ids: list[str] | None) -> list[dict]:
    with open(THEMES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    themes = [t for t in data["themes"] if t.get("status") == "active"]
    if theme_ids:
        wanted = set(theme_ids)
        themes = [t for t in themes if t["id"] in wanted]
    return themes


def build_universe_and_names() -> tuple[list[dict], dict[str, str]]:
    """유니버스(경로 A 제약용)와 티커→회사명 매핑을 만든다.

    US 이름은 sp500_list.csv + sp400_list.csv에서, KR은 get_kr_universe()가 이미 포함.

    sp400을 빼먹으면 안 된다: 유니버스에는 중형주 400종목이 들어오는데 이름이
    없으면 LLM이 티커만 보고 판단하게 된다("MP"가 MP Materials인지 알 수 없다).
    중형주를 넣은 이유가 얇은 테마를 채우는 것이었으므로, 정작 그 종목들의
    이름이 빠지면 편입 효과가 통째로 사라진다(docs/SPEC_us_universe_sp400.md).
    """
    us_items = get_us_universe()
    kr_items = get_kr_universe()

    names: dict[str, str] = {}
    for csv_name in ("sp500_list.csv", "sp400_list.csv"):
        path = ROOT / "data" / csv_name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        sym_col = next((c for c in df.columns if "symbol" in c.lower() or "ticker" in c.lower()), df.columns[0])
        name_col = next((c for c in df.columns if c.lower() in ("security", "name")), None)
        if not name_col:
            continue
        for _, row in df.iterrows():
            sym = str(row[sym_col]).replace(".", "-")
            names[sym] = str(row[name_col])

    for it in kr_items:
        if it.get("name"):
            names[it["symbol"]] = it["name"]

    return us_items + kr_items, names


# 호출 실패 누적 수. 실패한 청크는 결과가 비어 그 청크의 기업이 조용히 빠진다 - run 단위로
# 집계해 요약·통계에 남긴다(2026-09-15 v7 US 실행에서 429 63회로 편입이 무작위로 빠졌는데
# 로그 중간에만 찍혀 결과를 측정에 쓸 뻔했다).
CALL_FAILURES = 0


def active_model(role: str = "theme_mapping") -> str:
    """이 역할의 호출에 실제로 쓸 모델. mapping_runs 기록도 이 값을 쓴다(기록과 호출이 어긋나지 않게)."""
    return MODEL_OVERRIDE or oj.model_for(role)


def _openai_json(prompt: str, system: str, api_key: str, temperature: float = 0.2,
                 role: str | None = None) -> dict | None:
    """공통 호출(src/llm/openai_json.py)의 매핑용 래퍼: 실패하면 None을 돌려주고 실패 수를 센다.

    재시도·모델 계열별 파라미터는 공통 모듈이 처리한다. 매핑은 청크 하나가 실패해도 다음
    청크로 계속 가야 하므로 예외를 None으로 바꾼다(감사는 예외를 그대로 쓴다).
    role은 config/models.yaml의 역할 이름 - 비판 패스는 mapping_critic, 나머지는 theme_mapping.
    모델은 active_model()이 고른다: MODEL_OVERRIDE(A/B 측정용)가 있으면 그것, 없으면 역할별 설정.
    """
    global CALL_FAILURES
    model = active_model(role or "theme_mapping")
    try:
        return oj.call_json(model, system, prompt, api_key=api_key,
                            max_output_tokens=2000, temperature=temperature, timeout=90)
    except oj.OpenAICallError as e:
        CALL_FAILURES += 1
        _log(f"  OpenAI 호출 실패(최종): {e}")
        return None


def begin_run(conn) -> str:
    """mapping_runs에 실행 시작을 적고 run_id를 돌려준다. 모델은 호출에 실제로 쓰는 값을 남긴다."""
    run_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    start_mapping_run(conn, run_id, datetime.utcnow().isoformat(),
                      active_model("theme_mapping"), PROMPT_VERSION)
    return run_id


def _theme_description(theme: dict) -> str:
    """테마명 + 키워드 + 가치사슬 정의(value_chain). 운영 메모(note)는 보내지 않는다.

    SPEC_theme_company_mapping §3.1은 "이 테마 회사"가 아니라 가치사슬 위치를 묻고
    그 정의를 프롬프트에 넣으라고 정했지만, 실제로 정의가 있던 테마는 physical_ai
    하나뿐이었다. 나머지는 note에 "한국 전용." 같은 운영 메모가 있었고, 2026-09-15
    이전에는 그 메모가 키워드 대신 정의로 들어갔다. 경계 사례를 모델도 검토자도
    일관되게 판단하지 못한 근본 원인이다.

    value_chain에는 편입 단계와 "편입하지 않음" 경계를 함께 적는다. 경계 항목은
    검토에서 반복된 오편입(해운사->조선, 철강->구리 등)과 사용자가 정한 경계
    결정(게임 분리, HBM 후공정 동시 소속, 건설 분리, 자율주행은 차량만)이다."""
    lines = [f"테마명: {theme['name_ko']} ({theme['name_en']})"]
    kws = ", ".join(theme.get("keywords_ko", []))
    if kws:
        lines.append(f"관련 키워드: {kws}")
    if theme.get("value_chain"):
        lines.append("가치사슬 정의(이 단계에 명확히 속하는 기업만 편입):")
        lines.append(str(theme["value_chain"]).strip())
    lines.append("공통 기준: 해당 사업을 하는 상장 자회사가 목록에 따로 있으면 지주사 대신 "
                 "자회사를 고르시오(같은 회사가 이중으로 집계되지 않게).")
    return "\n".join(lines)


def load_all_profiles() -> dict[str, dict]:
    """KR+US 기업의 산업분류·영문 사업요약. 근거 감사와 같은 값을 보도록 공용 로더를
    쓴다(KR은 industry 보정 포함 - data/kr_profile_overrides.json). KR 코드(숫자 6자리)와
    US 티커(영문)는 겹치지 않아 한 dict로 합친다. 각 레코드에 market을 표시해 둔다."""
    try:
        from collectors.kr_profiles import load_profiles as _load
    except ImportError:
        from src.collectors.kr_profiles import load_profiles as _load
    merged: dict[str, dict] = {}
    for market in ("KR", "US"):
        try:
            for sym, prof in _load(market).items():
                merged[sym] = {**prof, "market": market}
        except Exception as e:
            _log(f"{market} 사업정보 읽기 실패 {type(e).__name__}: {e} - 이름만으로 매핑한다")
    return merged


def _profile_text(prof: dict | None) -> tuple[str, str]:
    """(산업분류, 사업요약). 미국은 긴 요약에서 US_SUMMARY_CHARS만큼 쓴다."""
    if not prof:
        return "", ""
    summary = prof.get("summary") or ""
    if prof.get("market") == "US" and prof.get("summary_long"):
        summary = prof["summary_long"][:US_SUMMARY_CHARS]
    return prof.get("industry") or "", summary


# 업종-테마 규칙은 src/analyzers/mapping_rules.py로 옮겼다(2026-10-23) - 매핑과 자동 점검
# (scripts/check_mapping_rules.py)이 같은 목록을 쓰게. 여기서는 이름만 다시 내보낸다.
from src.analyzers.mapping_rules import INDUSTRY_THEME_ALLOW, industry_theme_conflict  # noqa: E402,F401


def _candidate_line(symbol: str, market: str, names: dict[str, str],
                    profiles: dict[str, dict]) -> str:
    """후보 한 줄. 산업분류와 사업요약을 붙인다.

    왜 필요한가(2026-09-14 A/B 실측): 이름만 주면 모델이 사명의 형태로 사업을
    추측하고 근거를 지어냈다 - '레인보우로보틱스'(협동로봇)·'휴림로봇'(산업용
    로봇)을 "수술 로봇을 개발"한다며 의료기기 direct로 편입. 산업·요약을 붙이자
    이 둘이 빠지고 클래시스(미용 레이저)·엘앤씨바이오 등 실제 의료기기 기업이
    들어왔다.

    미국은 v6까지 "모델이 사명으로 이미 안다"며 붙이지 않았다. 그러나 2026-09-15
    검토에서 사람이 되살린 누락(General Dynamics 조선, Quanta·EMCOR 인프라 건설,
    Teradyne 반도체장비, Deere 건설기계, First Solar 재생에너지 등)이 전부 사업정보에
    적혀 있었다 - 모델이 회사를 알아도 200종목을 한 번에 훑을 땐 사업부 단위로
    떠올리지 못한다. v7부터 미국에도 붙인다."""
    line = f"- {symbol} ({market}) {names.get(symbol, '')}"
    industry, summary = _profile_text(profiles.get(symbol))
    if industry:
        line += f" [{industry}]"
    if summary:
        line += f" {summary}"
    return line


MEMBER_FIELDS_INSTRUCTION = """각 기업에 대해 다음 필드를 답하시오:
- ticker: 정확한 티커/코드
- name: 회사명
- market: "US" 또는 "KR"
- value_chain_stage: 이 기업이 테마 내에서 어떤 역할·위치인지 (한 단어~짧은 구)
- evidence: 왜 이 테마에 속하는지 구체적 근거 한 문장 (막연한 표현 금지, 구체적 제품·사업부 명시.
  15자 이상. 반드시 한국어 문장으로 쓸 것 - 회사명·제품명 등 고유명사만 영어 표기 허용)
- linkage: "direct"(주력 사업) / "partial"(일부 사업부) / "peripheral"(간접 노출) 중 하나

명확히 속하지 않으면 포함하지 마시오. 반드시 아래 JSON 형식으로만 답하시오:
{"members": [{"ticker": "...", "name": "...", "market": "US|KR", "value_chain_stage": "...", "evidence": "...", "linkage": "direct|partial|peripheral"}]}"""


def _chunk_lines(lines: list[str]) -> list[list[str]]:
    """후보 줄을 글자 수 예산(CHUNK_CHAR_BUDGET)과 줄 수 상한(UNIVERSE_CHUNK_SIZE) 안에서 순서대로 묶는다."""
    chunks: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for line in lines:
        if cur and (size + len(line) > CHUNK_CHAR_BUDGET or len(cur) >= UNIVERSE_CHUNK_SIZE):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append(cur)
    return chunks


def path_a_universe_constrained(theme: dict, universe: list[dict], names: dict[str, str],
                                api_key: str, profiles: dict[str, dict] | None = None) -> list[dict]:
    """유니버스를 청크로 나눠 그 안에서만 고르게 한다 — 환각 티커 원천 차단."""
    profiles = profiles or {}
    results: list[dict] = []
    desc = _theme_description(theme)
    chunks = _chunk_lines([_candidate_line(it["symbol"], it["market"], names, profiles) for it in universe])
    for ci, lines in enumerate(chunks):
        listing = "\n".join(lines)
        prompt = f"""{desc}

아래 상장기업 목록에서 위 테마에 실제로 속하는 기업만 고르시오. 목록에 없는
기업은 절대 답하지 마시오.

기업 뒤의 대괄호는 산업분류, 그 뒤 문장은 영문 사업요약이다. 근거(evidence)는
이 정보와 모순되지 않게 쓰시오. 사명에 들어간 단어(예: '로봇', '바이오')만 보고
사업 내용을 추측하지 마시오 - 산업분류·요약이 없는 기업은 사업 내용을 확실히 알
때만 포함하시오.

목록:
{listing}

{MEMBER_FIELDS_INSTRUCTION}"""
        parsed = _openai_json(prompt, "당신은 신중한 산업 분석가입니다. 주어진 목록에 없는 기업은 답하지 않습니다.", api_key)
        if parsed and isinstance(parsed.get("members"), list):
            results.extend(parsed["members"])
        _log(f"  경로 A 청크 {ci + 1}/{len(chunks)} 완료 ({len(lines)}종목)")
        time.sleep(0.5)
    return results


def path_a_stable(theme: dict, universe: list[dict], names: dict[str, str], api_key: str,
                  profiles: dict[str, dict] | None = None) -> list[dict]:
    """경로 A를 PATH_A_RUNS회 반복해 티커 기준 합집합으로 합친다.

    파일럿에서 동일 프롬프트·낮은 temperature(0.2)에도 청크 호출 결과가
    회차마다 크게 흔들리는 걸 발견함(physical_ai 국내 대형주 7개가 한 번은
    전부 잡히고 한 번은 전부 빠짐). 한 번이라도 잡히면 포함되도록 반복 후
    합쳐서 누락 확률을 낮춘다.
    """
    merged: dict[str, dict] = {}
    for run in range(PATH_A_RUNS):
        raw = path_a_universe_constrained(theme, universe, names, api_key, profiles)
        _log(f"  경로 A 실행 {run + 1}/{PATH_A_RUNS}: {len(raw)}개")
        for m in raw:
            ticker = _norm_ticker(m)
            if ticker and ticker not in merged:
                merged[ticker] = m
    return list(merged.values())


def path_b_free_generation(theme: dict, api_key: str) -> list[dict]:
    """목록 없이 자유 생성 — 유니버스 밖 신규 상장 종목 포착용. 결과는 §4 검증을 반드시 통과해야 함.

    34개 테마 전체 실행(2026-09-01)에서 경로 B 환각 폐기율이 34개 중 23개
    테마(68%)에서 30% 기준을 넘는 걸 확인 — 프롬프트를 더 보수적으로 손봄.
    확인된 실패 패턴 두 가지를 직접 겨냥함:
    1) 존재 자체가 불확실한 회사/티커를 지어냄
    2) 실존 대기업인데 "이 회사의 한 사업부가 XX를 한다"는, 확인하기 어렵고
       특히 틀리기 쉬운 사업부 단위 주장을 근거로 씀 (예: "Boeing 방산 부문이
       군함을 만든다" — 사실이 아닌데도 그럴듯하게 답한 실제 사례)
    temperature도 0.2 → 0.1로 낮춰 좀 더 보수적으로 만듦.
    """
    desc = _theme_description(theme)
    prompt = f"""{desc}

위 테마에 해당하는 실제 상장기업(미국 또는 한국 증시)을 아는 대로 답하시오.

반드시 지킬 것:
- 회사의 **주력 사업**으로서 이 테마에 속한다고 확실히 아는 경우만 답하시오.
  "이 회사의 한 사업부가 관련 있을 것"이라는 추측은 특히 틀리기 쉽다 —
  사업부 단위 주장은 그 사업부가 그 회사의 잘 알려진 핵심 사업일 때만 쓰시오.
- 회사명·티커의 존재 자체가 불확실하면 절대 포함하지 마시오.
- 확신이 없으면 억지로 채우지 말고 빈 목록을 반환하시오. 개수를 채우는 것보다
  정확한 게 훨씬 중요하다.

{MEMBER_FIELDS_INSTRUCTION}"""
    parsed = _openai_json(
        prompt,
        "당신은 매우 신중한 산업 분석가입니다. 사업부 단위의 막연한 추측으로 "
        "회사를 포함시키지 않으며, 확신이 없으면 빈 목록을 반환합니다.",
        api_key,
        temperature=0.1,
    )
    if parsed and isinstance(parsed.get("members"), list):
        return parsed["members"]
    return []


_KR_CODE_RE = re.compile(r"^[0-9][0-9A-Z]{5}$")
_NAME_NORM_RE = re.compile(r"[\s().·\-]")


def _norm_name(x: str) -> str:
    return _NAME_NORM_RE.sub("", x or "")


def _evidence_subject_mismatch(ticker: str, evidence: str, names: dict[str, str]) -> str | None:
    """근거 문장의 주어가 이 티커가 아닌 다른 회사면 그 회사명을 돌려준다.

    2026-09-15 실측: 모델이 한 회사의 근거를 쓰면서 티커를 다른 회사로 적는
    경우가 있었다 - 000660(SK하이닉스)의 battery 근거가 "SK이노베이션은 전기차용
    2차전지를...", 005380(현대차)의 근거가 "LG화학은 양극재...". 티커 실재 검증은
    통과하므로 SK하이닉스가 배터리 테마에 승인돼 있었다.

    주어(문장 첫머리)만 본다 - 근거 중간에 고객사명이 나오는 정상 사례
    ("삼성전자에 HBM을 공급")까지 걸면 오탐이 난다. 3글자 미만 사명(LG, SK,
    KT)은 다른 사명의 접두어로 흔해 비교하지 않는다."""
    own = _norm_name(names.get(ticker, ""))
    ev = _norm_name(evidence)
    if not own or ev.startswith(own):
        return None
    best = None
    for code, nm in names.items():
        n = _norm_name(nm)
        if code == ticker or len(n) < 3 or n == own or own.startswith(n):
            continue
        if ev.startswith(n) and (best is None or len(n) > len(_norm_name(best))):
            best = nm
    return best


def validate_members(raw_a: list[dict], raw_b: list[dict], valid_tickers: set[str],
                      cap_lookup: dict[str, float],
                      names: dict[str, str] | None = None,
                      universe_market: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """SPEC §4 코드 검증. (통과 목록, 통계) 반환.

    universe_market({티커: 시장})을 주면 시장은 **유니버스 기준으로 확정**한다. LLM이 답한
    market은 쓰지 않는다(2026-09-21 수정). 시가총액 하한이 시장마다 통화가 달라서
    (US 20억 **달러**, KR 2000억 **원**) LLM이 시장을 잘못 답하면 엉뚱한 기준으로 걸러진다.
      KR 종목을 US로 오판 - 원화 시총이 달러 하한보다 늘 커서 통과한다(무해)
      US 종목을 KR로 오판 - 30억 달러짜리가 2000억 "원" 하한에 걸려 부당 탈락한다(위험)
    전에는 저장 직전에 시장 라벨만 보정했는데, 그때는 이미 탈락 판정이 끝난 뒤라
    잘못 떨어진 기업은 되돌아오지 않았다.

    재무 데이터(fundamentals_cache) 존재 여부는 여기서 탈락시키지 않는다 — 그건
    나중에 실적 축 계산(Phase A-4)이 그 시점 캐시로 판단할 몫이고, 매핑 단계는
    "테마에 속하는 기업 목록"만 정하는 단계라서(SPEC §4 step3 의도: 없으면
    insufficient_data로 "구분"하되 탈락은 아님 — theme_members 자체엔 그 상태를
    담는 컬럼이 없으므로 그냥 포함시켜 후속 단계에서 자연히 데이터부족으로
    처리되게 한다).
    """
    tickers_a = {_norm_ticker(m) for m in raw_a}
    tickers_b = {_norm_ticker(m) for m in raw_b}
    merged_by_ticker: dict[str, dict] = {}
    for m in raw_a + raw_b:
        t = _norm_ticker(m)
        if t and t not in merged_by_ticker:
            merged_by_ticker[t] = m

    names = names or {}
    stats = {"입력": len(merged_by_ticker), "티커실재실패": 0, "시가총액미달": 0,
              "evidence품질실패": 0, "근거주어불일치": 0, "통과": 0}
    out = []

    for ticker, m in merged_by_ticker.items():
        if ticker not in valid_tickers:
            stats["티커실재실패"] += 1
            continue

        # 유니버스에 있는 티커면 그 시장이 사실이다. 유니버스 정보가 없을 때만(단위 테스트 등)
        # 코드 모양으로 판단한다 - isdigit()만 쓰면 0126Z0(삼성에피스홀딩스) 같은 영문 포함
        # KR 코드가 US로 분류되므로 정규식을 쓴다. LLM이 답한 market은 신뢰하지 않는다.
        market = (universe_market or {}).get(ticker) or ("KR" if _KR_CODE_RE.match(ticker) else "US")
        # KR은 사실상 이 하한이 발동하지 않는다 - valid_tickers 자체가 이미
        # get_kr_universe()(5000억 이상만) 로 구성되므로, 여기까지 온 candidate는
        # 이미 5000억을 넘는다. KR_MIN_CAP(2000억)은 watchlist 스크리닝용 하한이지
        # 매핑 유니버스 하한이 아니다 - 값이 다르다고 버그는 아니다(2026-09-15 확인).
        min_cap = US_MIN_CAP if market == "US" else KR_MIN_CAP
        cap = cap_lookup.get(ticker)
        if cap is not None and cap < min_cap:
            stats["시가총액미달"] += 1
            continue

        evidence = str(m.get("evidence", "")).strip()
        if len(evidence) < MIN_EVIDENCE_LEN:
            stats["evidence품질실패"] += 1
            continue
        other = _evidence_subject_mismatch(ticker, evidence, names)
        if other:
            _log(f"  근거 주어 불일치 제외: {ticker} {names.get(ticker, '')} <- 근거는 '{other}' 이야기")
            stats["근거주어불일치"] += 1
            continue
        flagged = any(p in evidence for p in BANNED_EVIDENCE_PHRASES)

        linkage = m.get("linkage")
        if linkage not in ("direct", "partial", "peripheral"):
            linkage = "partial"

        out.append({
            "ticker": ticker,
            "market": market,
            "stage": m.get("value_chain_stage"),
            "evidence": evidence,
            "linkage": linkage,
            "confidence": "high" if ticker in tickers_a and ticker in tickers_b else "normal",
            "flagged": flagged,
        })
        stats["통과"] += 1

    # 경로 B 환각 폐기율 — 유니버스에 아예 없는 티커 비율 (§4 "1번 폐기율 로그" 요구사항)
    b_not_in_universe = sum(1 for t in tickers_b if t and t not in valid_tickers)
    stats["경로B_폐기율"] = round(b_not_in_universe / len(tickers_b) * 100, 1) if tickers_b else 0.0

    return out, stats


def critique_pass(theme: dict, members: list[dict], names: dict[str, str], api_key: str,
                  profiles: dict[str, dict] | None = None) -> dict[str, str]:
    """SPEC §3.4 2차 비판 패스. 1차 통과 목록을 같은 LLM에게 다시 보여주고 근거가
    약한 후보를 지적하게 한다. 삭제하지 않고 flagged=1만 세팅해 사람 검토 우선순위를
    올린다 (§7). 반환값은 {ticker: reason}."""
    if not members:
        return {}
    desc = _theme_description(theme)
    # 실제 사업 정보를 함께 준다. 이전에는 모델이 자기가 쓴 근거를 사실 확인
    # 수단 없이 다시 읽기만 해서, 지어낸 근거("레인보우로보틱스가 수술 로봇을
    # 개발")를 걸러낼 방법이 없었다.
    profiles = profiles or {}

    def _fact(tk: str) -> str:
        parts = [x for x in _profile_text(profiles.get(tk)) if x]
        return f"\n    (실제 사업정보: {' / '.join(parts)})" if parts else ""

    listing = "\n".join(
        f"- {m['ticker']} ({names.get(m['ticker'], '')}): {m['evidence']}{_fact(str(m['ticker']))}"
        for m in members
    )
    prompt = f"""{desc}

아래는 위 테마의 1차 통과 후보 목록과 각각의 근거다.

{listing}

이 중 해당 테마 관련 매출이 전체의 10% 미만일 것으로 보이는 기업, 또는 근거가
막연하거나 사실관계가 의심스러워 제외를 검토해야 할 기업을 지적하시오. 확실히
문제없는 기업은 포함하지 마시오.

"실제 사업정보"가 붙은 기업은 근거가 그 정보와 모순되는지 반드시 대조하시오.
근거에 적힌 제품·사업이 실제 사업정보에 없거나 어긋나면 지어낸 근거일 가능성이
높으니 반드시 지적하시오.

반드시 아래 JSON 형식으로만 답하시오:
{{"flag": [{{"ticker": "...", "reason": "..."}}]}}"""
    parsed = _openai_json(
        prompt,
        "당신은 까다로운 산업 분석가입니다. 근거가 약하거나 사실과 다른 후보를 엄격히 지적합니다.",
        api_key,
        role="mapping_critic",
    )
    if not parsed or not isinstance(parsed.get("flag"), list):
        return {}
    out: dict[str, str] = {}
    for item in parsed["flag"]:
        ticker = _norm_ticker(item)
        if ticker:
            out[ticker] = str(item.get("reason", "")).strip()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme-id", nargs="*", default=None, help="특정 테마만 (비우면 전체)")
    parser.add_argument("--market", choices=["US", "KR"], default=None,
                        help="한 시장만 매핑 (비우면 양쪽). 승인은 approve --only-market과 짝을 맞출 것")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        _log("OPENAI_API_KEY 미설정")
        sys.exit(1)

    themes = load_themes(args.theme_id)
    if args.market:
        themes = [t for t in themes if args.market in (t.get("markets") or ["US", "KR"])]
    if not themes:
        _log("대상 테마 없음")
        sys.exit(1)
    _log(f"대상 테마 {len(themes)}개: {', '.join(t['id'] for t in themes)}")

    universe, names = build_universe_and_names()
    if args.market:
        universe = [it for it in universe if it["market"] == args.market]
    valid_tickers = {it["symbol"].upper() for it in universe}
    universe_market = {it["symbol"].upper(): it["market"] for it in universe}

    profiles = load_all_profiles()
    for mk in ("US", "KR"):
        syms = [it["symbol"] for it in universe if it["market"] == mk]
        if not syms:
            continue
        covered = sum(1 for c in syms if (profiles.get(c) or {}).get("industry"))
        _log(f"{mk} 사업정보 커버리지 {covered}/{len(syms)} "
             f"- 나머지는 이름만으로 판단(사명 기반 추측 위험 남음)")
    _log(f"유니버스 {len(universe)}종목 (경로 A 제약용)")

    conn = get_db()
    ensure_schema(conn)

    # 시가총액 확인은 Phase 0이 이미 캐시해둔 info_payload를 재사용 (SPEC §4 step2)
    cap_lookup: dict[str, float] = {}
    for ticker, info_payload in conn.execute("SELECT ticker, info_payload FROM fetch_status").fetchall():
        if not info_payload:
            continue
        try:
            cap = json.loads(info_payload).get("marketCap")
            if cap:
                cap_lookup[ticker] = float(cap)
        except (TypeError, ValueError):
            continue
    _log(f"시가총액 캐시 {len(cap_lookup)}종목")

    run_id = begin_run(conn)

    overall_stats: dict[str, dict] = {}
    for theme in themes:
        theme_id = theme["id"]
        _log(f"=== {theme_id} ({theme['name_ko']}) ===")
        failures_before = CALL_FAILURES

        raw_a = path_a_stable(theme, universe, names, api_key, profiles)
        _log(f"  경로 A 후보({PATH_A_RUNS}회 합집합): {len(raw_a)}개")
        raw_b = path_b_free_generation(theme, api_key)
        _log(f"  경로 B 후보: {len(raw_b)}개")

        validated, stats = validate_members(raw_a, raw_b, valid_tickers, cap_lookup, names,
                                            universe_market)
        blocked = []
        for m in validated:
            ind = industry_theme_conflict(theme_id, m["ticker"], profiles)
            if ind:
                blocked.append(m["ticker"])
                _log(f"  업종 불일치 제외: {m['ticker']} {names.get(m['ticker'], '')} [{ind}]")
        if blocked:
            validated = [m for m in validated if m["ticker"] not in blocked]
        stats["업종불일치"] = len(blocked)
        stats["통과"] = len(validated)

        # (시장 확정은 validate_members가 유니버스 기준으로 이미 끝냈다 - 2026-09-21)
        _log(f"  검증 결과: {stats}")
        if stats["경로B_폐기율"] > HALLUCINATION_WARN_RATE * 100:
            _log(f"  ⚠ 경로 B 환각 폐기율 {stats['경로B_폐기율']}% — 30% 초과, 프롬프트 재검토 필요")

        critique = critique_pass(theme, validated, names, api_key, profiles)
        newly_flagged = 0
        for m in validated:
            if m["ticker"] in critique:
                if not m["flagged"]:
                    newly_flagged += 1
                m["flagged"] = True
                _log(f"  비판 패스 flagged: {m['ticker']} — {critique[m['ticker']]}")
        stats["비판패스_flagged"] = len(critique)
        stats["호출실패"] = CALL_FAILURES - failures_before
        if stats["호출실패"]:
            _log(f"  ⚠ 호출 실패 {stats['호출실패']}회 - 이 테마 결과는 불완전(빠진 청크의 기업 누락)")
        overall_stats[theme_id] = stats

        created_at = datetime.utcnow().isoformat()
        for m in validated:
            insert_theme_member(conn, theme_id, m["ticker"], m["market"], m["stage"],
                                 m["evidence"], m["linkage"], m["confidence"], m["flagged"],
                                 run_id, created_at)

    finish_mapping_run(conn, run_id, datetime.utcnow().isoformat(), overall_stats)
    conn.close()

    print("\n" + "=" * 60)
    print(f"  테마 매핑 완료 — run_id={run_id}")
    if CALL_FAILURES:
        bad = [t for t, st in overall_stats.items() if st.get("호출실패")]
        print(f"  ⚠ 재시도 후에도 실패한 호출 {CALL_FAILURES}회 - 불완전한 테마 {bad}. 승인·측정에 쓰지 말 것")
    print("=" * 60)
    for theme_id, stats in overall_stats.items():
        print(f"  {theme_id:25s} 통과 {stats['통과']:>3d}  "
              f"(티커실패 {stats['티커실재실패']} / 시총미달 {stats['시가총액미달']} / "
              f"evidence탈락 {stats['evidence품질실패']} / 경로B폐기율 {stats['경로B_폐기율']}% / "
              f"비판패스flagged {stats.get('비판패스_flagged', 0)})")
    print("=" * 60)
    print("이 run은 approved=0 상태입니다 — 사람이 검토 후 승인해야 테마 보드에 반영됩니다.")


if __name__ == "__main__":
    main()
