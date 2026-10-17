"""다음 실적 발표일 (2026-10-17, 사용자 결정: 주간 브리핑 "이번 주 실적 발표").

출처: yfinance Ticker.info의 earningsTimestampStart/End·isEarningsDateEstimate (종목별 호출, 키 없음).
  - 회사가 날짜를 공지했으면 Start = End, 예상치면 isEarningsDateEstimate=True(보통 Start~End 범위).
  - 시각은 UTC epoch -> 그 시장 시간대 날짜로 바꾼다(미국 장 마감 후 발표가 한국 날짜로 하루 밀리지 않게).
  - 이미 지난 날짜(직전 발표)는 버린다 - "다음" 발표만 남긴다.
날짜는 데이터 그대로 옮길 뿐 만들지 않는다(원칙 2). 없으면 없는 대로 둔다(원칙 5 - 결측은 정상).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

MARKET_TZ = {"US": ZoneInfo("America/New_York"), "KR": ZoneInfo("Asia/Seoul")}


def _ts_to_date(ts, market: str) -> date | None:
    try:
        if ts is None:
            return None
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(MARKET_TZ.get(market, timezone.utc)).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_info(info: dict | None, market: str, today: date) -> dict | None:
    """yfinance info -> {earnings_date, earnings_date_end, is_estimate} 또는 None(다음 발표일 없음).

    Start만 있으면 End = Start. Start가 이미 지났는데 End가 오늘 이후면(예상 범위 안) 그대로 둔다.
    """
    if not info:
        return None
    start = _ts_to_date(info.get("earningsTimestampStart") or info.get("earningsTimestamp"), market)
    end = _ts_to_date(info.get("earningsTimestampEnd"), market) or start
    if start is None:
        return None
    if end < start:
        start, end = end, start
    if end < today:
        return None
    est = info.get("isEarningsDateEstimate")
    return {
        "earnings_date": start.isoformat(),
        "earnings_date_end": end.isoformat(),
        # 값이 없으면 범위로 판단한다 - 하루로 딱 떨어지면 공지, 범위면 예상
        "is_estimate": int(bool(est)) if est is not None else int(end != start),
    }
