"""한국 테마 뉴스 하루 세 번 수집 - 지난번 읽은 데까지 새 기사만 받아 theme_news에 쌓는다.

규칙과 이유는 src/collectors/kr_news_intraday.py. 주간 계산(collect_theme_news.py)은 이 표에 쌓인 기사를 센다.
네이버 키가 없으면 아무것도 하지 않는다(주간 계산은 예전 구글 경로로 돈다).

사용법: python scripts/collect_kr_news_intraday.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from collectors.kr_news_intraday import run_intraday  # noqa: E402
from collectors.theme_news_collector import naver_credentials  # noqa: E402
from src.db.data_store import get_db  # noqa: E402
from src.db.theme_signals import ensure_schema  # noqa: E402


def kr_themes() -> list[dict]:
    raw = yaml.safe_load((ROOT / "config" / "themes.yaml").read_text(encoding="utf-8"))
    return [{"id": t["id"], "keywords_ko": t["keywords_ko"]} for t in raw["themes"]
            if t.get("status") == "active" and "KR" in t.get("markets", []) and t.get("keywords_ko")]


def main() -> int:
    creds = naver_credentials()
    if not creds:
        print("[kr-intraday] 네이버 키 없음 - 건너뜀", flush=True)
        return 0
    conn = get_db()
    ensure_schema(conn)
    stats = run_intraday(conn, kr_themes(), {"X-Naver-Client-Id": creds[0], "X-Naver-Client-Secret": creds[1]},
                         log=lambda m: print(m, flush=True))
    conn.close()
    # 키워드 절반 이상이 조회 실패면 실패로 끝내 알림이 가게 한다(일부 실패는 다음 실행이 이어 읽는다).
    return 1 if stats["failed"] and len(stats["failed"]) * 2 >= stats["keywords"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
