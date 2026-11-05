import json
import math
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATA_DB_PATH", "output/data.db")

# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

_TIMESERIES_TABLES = {
    "data_daily_reports": """
        CREATE TABLE IF NOT EXISTS data_daily_reports (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_risk_alerts": """
        CREATE TABLE IF NOT EXISTS data_risk_alerts (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_prediction_history": """
        CREATE TABLE IF NOT EXISTS data_prediction_history (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "kr_daily_reports": """
        CREATE TABLE IF NOT EXISTS kr_daily_reports (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    # data_regime/kr_regime은 매일 덮어써지는 스냅샷이라 "오늘이 간당간당한 GO인지
    # 여유있는 GO인지"를 추세로 볼 수 없었다. weighted_score+센서별 점수를 날짜별로
    # 따로 쌓아서 이 문제를 해결한다.
    "data_regime_history": """
        CREATE TABLE IF NOT EXISTS data_regime_history (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "kr_regime_history": """
        CREATE TABLE IF NOT EXISTS kr_regime_history (
            date        TEXT PRIMARY KEY,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
}

_SNAPSHOT_TABLES = {
    "data_regime": """
        CREATE TABLE IF NOT EXISTS data_regime (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_market_gate": """
        CREATE TABLE IF NOT EXISTS data_market_gate (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_gbm_predictions": """
        CREATE TABLE IF NOT EXISTS data_gbm_predictions (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_index_prediction": """
        CREATE TABLE IF NOT EXISTS data_index_prediction (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_risk": """
        CREATE TABLE IF NOT EXISTS data_risk (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_performance": """
        CREATE TABLE IF NOT EXISTS data_performance (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "data_costs": """
        CREATE TABLE IF NOT EXISTS data_costs (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "kr_regime": """
        CREATE TABLE IF NOT EXISTS kr_regime (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "kr_market_gate": """
        CREATE TABLE IF NOT EXISTS kr_market_gate (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            payload     TEXT NOT NULL,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    # kr_index_prediction(지수 예측, 2026-08 제거)은 2026-11-05 코드에서 뺐다 - 표 자체는 DROP하지 않는다(원칙 5).
}

# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

class _TransientTursoError(Exception):
    """재시도해도 되는 Turso 오류(서버가 실행하지 않았다고 응답함)."""


# Turso가 "실행하지 않았다"고 알려 주는 일시 오류 - 다시 보내도 두 번 반영될 일이 없어 재시도한다.
# 2026-10-05 한국 뉴스 대량 저장이 `SQLite error: disk I/O error` 한 번에 20분 수집을 통째로 잃었다
# (같은 작업을 다시 돌리면 정상). 응답이 아예 안 온 경우(타임아웃·연결 끊김)는 실제로 반영됐을 수 있어
# 재시도하지 않는다.
TRANSIENT_ERRORS = ("disk I/O error", "database is locked", "SQLITE_BUSY", "SQLITE_IOERR")
TRANSIENT_HTTP = (429, 503)
RETRY_DELAYS = (2, 5, 10)   # 초


def _is_transient(message: str) -> bool:
    return any(t.lower() in message.lower() for t in TRANSIENT_ERRORS)


class _TursoConn:
    """Turso HTTP Pipeline API — sqlite3 호환 최소 래퍼."""

    def __init__(self, url: str, token: str):
        base = url.strip().replace("libsql://", "https://")
        self._url = f"{base}/v2/pipeline"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._rows: list = []

    def _arg(self, v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, bool):
            return {"type": "integer", "value": "1" if v else "0"}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return {"type": "null"}
            # Hrana 프로토콜은 integer는 문자열(64비트 정밀도 손실 방지)을 기대하지만
            # float는 실제 JSON 숫자를 기대한다 — str(v)로 감싸면 "invalid type: string,
            # expected f64" 400 에러가 남 (turso_http.py의 _arg()는 처음부터 올바르게 처리 중).
            return {"type": "float", "value": v}
        return {"type": "text", "value": str(v)}

    def execute(self, sql: str, params=()):
        import time as _time
        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                return self._execute_once(sql, params)
            except _TransientTursoError as e:
                if delay is None:
                    raise ValueError(str(e)) from None
                print(f"[turso] 일시 오류({e}) - {delay}초 뒤 재시도 {attempt + 1}/{len(RETRY_DELAYS)}", flush=True)
                _time.sleep(delay)

    def _execute_once(self, sql: str, params=()):
        import requests as _req
        stmt: dict = {"sql": sql}
        if params:
            stmt["args"] = [self._arg(p) for p in params]
        payload = {"requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]}
        r = _req.post(self._url, headers=self._headers, json=payload, timeout=30)
        if r.status_code in TRANSIENT_HTTP:
            raise _TransientTursoError(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            # raise_for_status()는 응답 본문을 버려 원인 파악이 어려움 — Turso가 돌려준
            # 실제 에러 메시지(어떤 statement/인자가 문제인지)를 그대로 노출한다.
            raise RuntimeError(
                f"Turso HTTP {r.status_code} for statement: {sql[:200]!r}\n"
                f"args: {stmt.get('args')}\n"
                f"response: {r.text[:2000]}"
            )
        data = r.json()
        res = data["results"][0]
        if res["type"] == "error":
            msg = res["error"]["message"]
            if _is_transient(msg):
                raise _TransientTursoError(msg)
            raise ValueError(msg)
        rs = res.get("response", {}).get("result", {})
        self._rows = rs.get("rows", [])
        return self

    def fetchone(self):
        if not self._rows:
            return None
        return tuple(
            v.get("value") if v.get("type") != "null" else None
            for v in self._rows[0]
        )

    def fetchall(self):
        return [
            tuple(v.get("value") if v.get("type") != "null" else None for v in row)
            for row in self._rows
        ]

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __iter__(self):
        return iter(self.fetchall())


def get_db(path: str = DB_PATH) -> sqlite3.Connection:
    turso_url   = os.getenv("TURSO_DATA_URL")
    turso_token = os.getenv("TURSO_DATA_TOKEN")
    if turso_url and turso_token:
        return _TursoConn(turso_url, turso_token)  # type: ignore

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    for ddl in {**_TIMESERIES_TABLES, **_SNAPSHOT_TABLES}.values():
        conn.execute(ddl)
    conn.commit()

# --------------------------------------------------------------------------
# Writes  (Python-side only; frontend reads via SELECT)
# --------------------------------------------------------------------------

def _upsert_snapshot(conn: sqlite3.Connection, table: str, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    conn.execute(
        f"""
        INSERT INTO {table} (id, payload)
        VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET
            payload    = excluded.payload,
            updated_at = datetime('now')
        """,
        (payload,),
    )
    conn.commit()


def upsert_gbm_predictions(conn: sqlite3.Connection, data: dict) -> None:
    _upsert_snapshot(conn, "data_gbm_predictions", data)


def upsert_performance(conn: sqlite3.Connection, data: dict) -> None:
    _upsert_snapshot(conn, "data_performance", data)


def upsert_costs(conn: sqlite3.Connection, data: dict) -> None:
    _upsert_snapshot(conn, "data_costs", data)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def get_snapshot(conn: sqlite3.Connection, table: str) -> dict:
    row = conn.execute(f"SELECT payload FROM {table} WHERE id = 1").fetchone()
    if row is None:
        return {}
    payload = row[0] if not hasattr(row, "keys") else row["payload"]
    return json.loads(payload)
