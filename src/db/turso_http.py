"""Turso(libSQL) HTTP Pipeline API 공용 클라이언트.

market_fit_scorer.py, run_watchlist_screen.py, generate_narratives.py,
generate_weekly_briefing.py, send_telegram_digest.py 각자에 거의 동일하게
복사되어 있던 urllib 기반 Turso 접근 코드(`_turso_val`/`turso_query`/
`turso_exec`/`turso_pipeline`)를 하나로 합친 것.

data_store.py의 `_TursoConn`(requests 기반, sqlite3 커서 흉내)과는 별개다 —
그쪽은 `get_db()`를 통해 sqlite3-호환 인터페이스가 필요한 코드용이고,
여기는 (SELECT → dict 행 리스트) 또는 (여러 statement 일괄 실행) 형태로
직접 쓰던 스크립트들을 위한 것이라 인터페이스를 그대로 유지했다.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request


class TursoError(RuntimeError):
    """Turso 자격증명 미설정 또는 API 에러 응답."""


def get_credentials() -> tuple[str, str] | None:
    """(url, token) 튜플, 미설정 시 None."""
    url = os.environ.get("TURSO_DATA_URL", "").strip().replace("libsql://", "https://")
    token = os.environ.get("TURSO_DATA_TOKEN", "").strip()
    if not url or not token:
        return None
    return url, token


def _arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return {"type": "null"}
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def pipeline(statements: list[tuple[str, list | None]], timeout: int = 30) -> list[dict]:
    """(sql, args) 튜플 리스트를 한 번의 HTTP 요청으로 실행.

    Raises:
        TursoError: 자격증명 미설정, 또는 응답에 error 타입 결과 포함.
        urllib.error.HTTPError / URLError: 전송 레벨 실패.
    """
    creds = get_credentials()
    if not creds:
        raise TursoError("TURSO_DATA_URL / TURSO_DATA_TOKEN 미설정")
    url, token = creds

    requests_list = []
    for sql, args in statements:
        stmt: dict = {"sql": sql}
        if args:
            stmt["args"] = [_arg(a) for a in args]
        requests_list.append({"type": "execute", "stmt": stmt})

    body = json.dumps({"requests": requests_list}).encode()
    req = urllib.request.Request(
        f"{url}/v2/pipeline", data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        results = json.loads(resp.read()).get("results", [])

    for res in results:
        if res.get("type") == "error":
            raise TursoError(res.get("error", {}).get("message", "unknown Turso error"))
    return results


def as_bool(v) -> bool:
    """DB의 0/1 칸을 참·거짓으로(2026-11-05). Hrana는 INTEGER를 문자열로 돌려주는데 bool("0")은 True라,
    그대로 쓰면 '계획 매수'·'예상 날짜' 같은 표시가 전부 켜진다(실제로 그랬다)."""
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true")
    return bool(v)


def _rows_from_result(result: dict) -> list[dict]:
    cols = [c["name"] for c in result.get("cols", [])]
    rows = []
    for raw in result.get("rows", []):
        row = {}
        for col, cell in zip(cols, raw):
            row[col] = cell.get("value") if isinstance(cell, dict) else cell
        rows.append(row)
    return rows


def query(sql: str, args: list | None = None, timeout: int = 30) -> list[dict]:
    """SELECT 실행 → 컬럼명 키의 dict 행 리스트. 결과 없으면 빈 리스트."""
    results = pipeline([(sql, args)], timeout=timeout)
    if not results or results[0].get("type") != "ok":
        return []
    return _rows_from_result(results[0]["response"]["result"])


def execute(sql: str, args: list | None = None, timeout: int = 30) -> None:
    """단일 쓰기문(INSERT/UPDATE/DELETE/CREATE/DROP...) 실행."""
    pipeline([(sql, args)], timeout=timeout)


def execute_many(statements: list[tuple[str, list | None]], timeout: int = 60) -> None:
    """여러 statement를 한 번의 HTTP 요청으로 실행 (배치 upsert 등)."""
    pipeline(statements, timeout=timeout)
