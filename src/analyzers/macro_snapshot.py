"""
매크로 스냅샷
- 미국 10년물·30년물 국채금리, 10-2년 금리차, 원/달러 환율, VIX, 달러인덱스, WTI 유가, 구리
- 판단(등급·해석) 없이 원자료(현재값 + 전일/전주 대비 변동)만 저장한다.
- 일별 종가 1년치는 macro_history(date, key, value)에 쌓는다(2026-10-17, 개요 추세선·1년 범위·그래프).
  체제(regime) 판정처럼 가중합산해 등급을 매기는 시스템이 아니다 - 그건
  "단일 종합 점수를 만들지 않는다" 원칙 때문에 이미 삭제됨(0번 기능제거).
"""
import json

import pandas as pd
import yfinance as yf

from src.db.data_store import get_db

TICKERS = {
    "us10y":  "^TNX",
    "us30y":  "^TYX",
    "us2y":   "2YY=F",
    "usdkrw": "KRW=X",
    "vix":    "^VIX",
    "dxy":    "DX-Y.NYB",
    "wti":    "CL=F",
    "copper": "HG=F",   # 2026-10-17 - 구리·전력망·케이블 테마 해석용(달러/파운드)
}

# 프론트에서 쓸 한글 라벨·단위 (us2y는 스프레드 계산용 원자재라 화면엔 안 보여줘도 되지만
# 참고용으로 같이 저장 - 나중에 필요하면 바로 노출 가능하게).
LABELS = {
    "us10y":         "미국 10년물 국채금리",
    "us30y":         "미국 30년물 국채금리",
    "us2y":          "미국 2년물 국채금리",
    "spread_10y_2y": "10년-2년 금리차",
    "usdkrw":        "원/달러 환율",
    "vix":            "VIX 변동성지수",
    "dxy":            "달러인덱스",
    "wti":            "WTI 유가",
    "copper":         "구리",
}
UNITS = {
    "us10y": "%", "us30y": "%", "us2y": "%", "spread_10y_2y": "%p",
    "usdkrw": "원", "vix": "", "dxy": "", "wti": "$", "copper": "$/lb",
}


def _fetch_closes(period: str = "2mo") -> pd.DataFrame:
    tickers = list(TICKERS.values())
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    return closes


def _series_by_key(closes: pd.DataFrame) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for key, ticker in TICKERS.items():
        if ticker in closes.columns:
            out[key] = closes[ticker].dropna()
    # 10년-2년 금리차 - 두 시리즈를 날짜로 정렬해 뺀 새 시리즈(파생값, 뺄셈 그 이상의
    # 해석 없음). pandas가 공통 날짜만 남기고 자동 정렬하므로 거래일이 살짝 다른 상품
    # (국채 vs 선물)이어도 죽지는 않는다. 단, us2y(2YY=F)가 당일 데이터 공백이면
    # us10y·us2y 각각의 "value"는 서로 다른 날짜 기준이 될 수 있어 스프레드가 그 둘을
    # 단순히 뺀 값과 미세하게 안 맞을 수 있음 - 각 값은 자기 날짜 기준으로는 정확하다
    # (드문 경우, 오차는 하루치 변동폭 이내).
    if "us10y" in out and "us2y" in out:
        out["spread_10y_2y"] = (out["us10y"] - out["us2y"]).dropna()
    return out


def _snapshot(s: pd.Series | None) -> dict:
    if s is None or len(s) == 0:
        return {"value": None, "chg_1d": None, "chg_1w": None}
    cur = float(s.iloc[-1])
    prev_1d = float(s.iloc[-2]) if len(s) >= 2 else None
    prev_1w = float(s.iloc[-6]) if len(s) >= 6 else None  # 5거래일 = 1주 (다른 분석기와 동일 관례)
    return {
        "value":  round(cur, 4),
        "chg_1d": round(cur - prev_1d, 4) if prev_1d is not None else None,
        "chg_1w": round(cur - prev_1w, 4) if prev_1w is not None else None,
    }


HISTORY_PERIOD = "1y"   # 개요 카드 추세선·1년 범위·큰 그래프용(2026-10-17)
SETTLE_DAYS = 5         # 최근 며칠 종가는 아직 바뀔 수 있다(선물·환율은 장중 값이 먼저 잡힘) - 이 기간만 다시 쓴다
INSERT_CHUNK = 200


def history_rows(series: dict[str, pd.Series]) -> list[tuple[str, str, float]]:
    """{지표: 일별 시리즈} -> [(날짜, 지표, 값)]. NaN은 뺀다."""
    out = []
    for key, s in series.items():
        for idx, v in s.items():
            if v == v:
                out.append((pd.Timestamp(idx).strftime("%Y-%m-%d"), key, round(float(v), 4)))
    return out


def split_settled(rows: list[tuple[str, str, float]], as_of: str, settle_days: int = SETTLE_DAYS):
    """(굳은 행, 최근 행). 굳은 행은 INSERT OR IGNORE(이력, 덮어쓰지 않음 - 원칙 5),
    최근 settle_days(달력일) 안의 행은 장중 값이 잡혔을 수 있어 INSERT OR REPLACE."""
    cutoff = (pd.Timestamp(as_of) - pd.Timedelta(days=settle_days)).strftime("%Y-%m-%d")
    return [r for r in rows if r[0] <= cutoff], [r for r in rows if r[0] > cutoff]


def _save_history(rows: list[tuple[str, str, float]], as_of: str) -> None:
    settled, recent = split_settled(rows, as_of)
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS macro_history (
                date  TEXT NOT NULL,
                key   TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY (date, key)
            )
        """)
        for verb, batch in (("INSERT OR IGNORE", settled), ("INSERT OR REPLACE", recent)):
            # 한 번에 여러 행 - Turso HTTP는 문장마다 왕복이라 1년치(약 2,300행)를 한 행씩 넣으면 느리다
            for i in range(0, len(batch), INSERT_CHUNK):
                chunk = batch[i:i + INSERT_CHUNK]
                con.execute(f"{verb} INTO macro_history (date, key, value) VALUES "
                            + ",".join(["(?, ?, ?)"] * len(chunk)),
                            tuple(v for r in chunk for v in r))


def analyze() -> dict:
    closes = _fetch_closes(HISTORY_PERIOD)
    series = _series_by_key(closes)

    # 스크립트가 실행된 오늘 날짜가 아니라, 실제로 데이터가 있는 마지막 거래일을
    # 기준일로 삼는다 - 주말/공휴일에 돌아도(매일 크론) 그날 날짜를 금요일 종가에
    # 잘못 붙이지 않기 위함(주간 브리핑의 week_start 처리와 같은 원칙).
    as_of = closes.index[-1].strftime("%Y-%m-%d")

    keys = list(TICKERS.keys()) + ["spread_10y_2y"]
    items = {key: {**_snapshot(series.get(key)), "label": LABELS[key], "unit": UNITS[key]} for key in keys}

    result = {"date": as_of, "items": items}
    _save(result)
    rows = history_rows(series)
    _save_history(rows, as_of)
    print("[macro] 이력 " + f"{len(rows)}행 · " + ", ".join(f"{k} {len(v)}일" for k, v in series.items()), flush=True)
    return result


def _save(data: dict):
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS macro_snapshot (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT NOT NULL UNIQUE,
                payload    TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            INSERT OR REPLACE INTO macro_snapshot (date, payload, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (data["date"], json.dumps(data, ensure_ascii=False)))


if __name__ == "__main__":
    r = analyze()
    for key, item in r["items"].items():
        print(f"{item['label']:14s} {item['value']} {item['unit']}  (1d {item['chg_1d']}, 1w {item['chg_1w']})")
