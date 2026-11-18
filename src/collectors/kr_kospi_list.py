"""
한국 주요 종목 리스트 (KOSPI 대형주 + 일부 코스닥 대형주)
yfinance 티커 기준 - 거래소에 따라 .KS(코스피)/.KQ(코스닥)를 붙인다.
"""
import pandas as pd

# 코스닥 상장 종목. 나머지는 전부 코스피(.KS).
#
# 2026-09-07 전수 스캔으로 확정 - 그 전까지 이 파일은 전 종목에 .KS를 붙이고
# 있었는데, 코스닥 종목을 .KS로 조회하면 yfinance가 에러 대신 "조용히 잘못된"
# 응답을 준다: 종목명이 "035900.KS,0P0000EQNH,607656" 같은 내부 ID 문자열,
# 섹터·시총·현재가는 None, 그리고 결정적으로 **가격 시계열이 다른 값**이 온다
# (알테오젠 4주 수익률: .KS -1.7% vs .KQ -5.6%, 같은 배치 호출 기준).
# 그래서 화면의 "Unknown 섹터"뿐 아니라 테마 레이더 주가 축까지 조용히
# 틀린 숫자를 쓰고 있었다. 분기 재무제표는 양쪽이 동일해 실적 축은 무영향.
KOSDAQ_CODES = {
    "035900",  # JYP Ent.
    "041510",  # 에스엠
    "058470",  # 리노공업
    "068760",  # 셀트리온제약
    "086520",  # 에코프로
    "196170",  # 알테오젠
    "247540",  # 에코프로비엠
    "263750",  # 펄어비스
}


def yf_suffix(code: str) -> str:
    """야후 파이낸스 조회용 거래소 접미사."""
    return ".KQ" if code in KOSDAQ_CODES else ".KS"


def exchange_of(code: str) -> str:
    return "KOSDAQ" if code in KOSDAQ_CODES else "KOSPI"

# 손으로 관리해 온 핵심 리스트. 코스피200에 없는 종목(코스닥 대형주, K-푸드
# 관련주 등)도 여기 들어 있어서 아래 합집합에서 계속 유지된다.
CORE_STOCKS = [
    ("005930", "삼성전자",        "Technology"),
    ("000660", "SK하이닉스",       "Technology"),
    ("373220", "LG에너지솔루션",   "Industrials"),
    ("207940", "삼성바이오로직스", "Healthcare"),
    ("005380", "현대차",           "Consumer Cyclical"),
    ("000270", "기아",             "Consumer Cyclical"),
    ("035420", "NAVER",            "Communication Services"),
    ("051910", "LG화학",           "Basic Materials"),
    ("068270", "셀트리온",         "Healthcare"),
    ("028260", "삼성물산",         "Industrials"),
    ("035720", "카카오",           "Communication Services"),
    ("006400", "삼성SDI",          "Technology"),
    ("003550", "LG",               "Industrials"),
    ("105560", "KB금융",           "Financial Services"),
    ("055550", "신한지주",         "Financial Services"),
    ("086790", "하나금융지주",     "Financial Services"),
    ("032830", "삼성생명",         "Financial Services"),
    ("316140", "우리금융지주",     "Financial Services"),
    ("012330", "현대모비스",       "Consumer Cyclical"),
    ("009150", "삼성전기",         "Technology"),
    ("066570", "LG전자",           "Technology"),
    ("017670", "SK텔레콤",         "Communication Services"),
    ("030200", "KT",               "Communication Services"),
    ("096770", "SK이노베이션",     "Energy"),
    ("034730", "SK",               "Industrials"),
    ("000810", "삼성화재",         "Financial Services"),
    ("010130", "고려아연",         "Basic Materials"),
    ("047050", "포스코인터내셔널", "Industrials"),          # 2026-09-10 정정: 포스코홀딩스(005490) 아님
    ("033780", "KT&G",             "Consumer Defensive"),
    ("015760", "한국전력",         "Utilities"),
    ("009540", "HD한국조선해양",     "Industrials"),
    ("010950", "S-Oil",            "Energy"),
    ("042660", "한화오션",         "Industrials"),
    ("034020", "두산에너빌리티",   "Industrials"),
    ("097950", "CJ제일제당",       "Consumer Defensive"),
    ("028050", "삼성E&A",   "Industrials"),
    ("018880", "한온시스템",       "Consumer Cyclical"),    # 2026-09-10 정정: 한화(000880) 아님
    ("011200", "HMM",              "Industrials"),
    ("021240", "코웨이",           "Consumer Defensive"),
    ("282330", "BGF리테일",        "Consumer Defensive"),
    ("271560", "오리온",           "Consumer Defensive"),
    ("139480", "이마트",           "Consumer Defensive"),
    ("004170", "신세계",           "Consumer Cyclical"),
    ("003490", "대한항공",         "Industrials"),
    ("009830", "한화솔루션",       "Technology"),
    ("402340", "SK스퀘어",         "Technology"),
    ("078930", "GS",               "Energy"),
    ("088350", "한화생명",         "Financial Services"),
    ("032640", "LG유플러스",       "Communication Services"),
    ("034220", "LG디스플레이",     "Technology"),
    ("005300", "롯데칠성",         "Consumer Defensive"),
    ("004990", "롯데지주",         "Consumer Cyclical"),
    ("002790", "아모레퍼시픽홀딩스", "Consumer Defensive"),  # 2026-09-10 정정: 090430과 뒤바뀌어 있었음
    ("051900", "LG생활건강",       "Consumer Defensive"),
    ("161390", "한국타이어앤테크놀로지", "Consumer Cyclical"),
    ("008770", "호텔신라",         "Consumer Cyclical"),
    ("000100", "유한양행",         "Healthcare"),
    ("068760", "셀트리온제약",     "Healthcare"),
    ("196170", "알테오젠",         "Healthcare"),
    ("086520", "에코프로",         "Basic Materials"),
    ("247540", "에코프로비엠",     "Basic Materials"),
    ("036570", "NC",       "Communication Services"),
    ("259960", "크래프톤",         "Communication Services"),
    ("352820", "하이브",           "Communication Services"),
    ("041510", "에스엠",           "Communication Services"),
    ("035900", "JYP Ent.",         "Communication Services"),
    ("079550", "LIG디펜스앤에어로스페이스",        "Industrials"),
    ("004020", "현대제철",         "Basic Materials"),
    ("011780", "금호석유화학",     "Basic Materials"),
    ("000720", "현대건설",         "Industrials"),
    ("006360", "GS건설",           "Industrials"),
    ("024110", "기업은행",         "Financial Services"),
    ("000080", "하이트진로",       "Consumer Defensive"),
    ("001450", "현대해상",         "Financial Services"),
    ("090430", "아모레퍼시픽",     "Consumer Defensive"),   # 2026-09-10 정정: 002790과 뒤바뀌어 있었음
    ("010140", "삼성중공업",       "Industrials"),
    # 003600 -> 285130 교체(2026-09-08). 003600은 yfinance에서 시총·섹터·가격이
    # 전부 None이고 종목명조차 "683186" 같은 내부 ID로 오는 죽은 코드였다
    # (스크리닝의 "데이터부족 1건"이 이것). 실제 SK케미칼은 285130이며
    # 섹터도 Healthcare가 아니라 Basic Materials로 확인됨(SKCHEM, 시총 1.04조).
    # 참고: 034730(SK Inc.)·006120(SK Discovery)은 각각 다른 회사다.
    ("285130", "SK케미칼",         "Basic Materials"),
    ("058470", "리노공업",         "Technology"),
    ("263750", "펄어비스",         "Communication Services"),
    ("180640", "한진칼",           "Industrials"),
    ("010060", "OCI홀딩스",        "Basic Materials"),
    ("001040", "CJ",               "Consumer Defensive"),
    ("000120", "CJ대한통운",       "Industrials"),
    ("011170", "롯데케미칼",       "Basic Materials"),
    ("023530", "롯데쇼핑",         "Consumer Cyclical"),
    ("005490", "POSCO홀딩스",      "Basic Materials"),
    ("018260", "삼성SDS",          "Technology"),
    # 2026-09 추가 - k_beauty/k_food 테마 재매핑용 (기존 유니버스에 후보가
    # 너무 적어 표본 부족 상태였음). yfinance .info의 exchange 필드로 전부
    # KSC(코스피) 확인 후 추가 - .KS 접미사 정확함.
    ("161890", "한국콜마",         "Consumer Defensive"),
    ("192820", "코스맥스",         "Consumer Defensive"),
    ("004370", "농심",             "Consumer Defensive"),
    ("003230", "삼양식품",         "Consumer Defensive"),
    ("001680", "대상",             "Consumer Defensive"),
    # 롯데웰푸드는 1차 재매핑 결과 근거("김치·즉석식품 생산")가 이 회사의
    # 실제 주력 사업(과자·아이스크림·초콜릿)과 안 맞아 보여 제외(사용자 확인).
    ("005180", "빙그레",           "Consumer Defensive"),
    ("007310", "오뚜기",           "Consumer Defensive"),
    ("017810", "풀무원",           "Consumer Defensive"),
    ("005610", "삼립",          "Consumer Defensive"),
    ("018250", "애경산업",         "Consumer Defensive"),
    ("226320", "잇츠한불",         "Consumer Defensive"),
]

try:
    from collectors.kr_kospi200_additions import KOSPI200_ADDITIONS
except ImportError:
    from src.collectors.kr_kospi200_additions import KOSPI200_ADDITIONS


def _union_stocks(*lists) -> list[tuple[str, str, str]]:
    """종목코드 기준 합집합. 먼저 나온 항목(=CORE_STOCKS)이 우선한다 —
    손으로 검수한 이름·섹터를 자동 생성분이 덮어쓰지 않게 하기 위함."""
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for lst in lists:
        for code, name, sector in lst:
            if code in seen:
                continue
            seen.add(code)
            out.append((code, name, sector))
    return out


# 실제로 쓰이는 KR 유니버스. 교체가 아니라 **합집합**인 이유: 코스피200에
# 없지만 계속 보고 싶은 종목이 14개 있다(코스닥 8개 + K-푸드·K-뷰티 관련주).
KOSPI_STOCKS = _union_stocks(CORE_STOCKS, KOSPI200_ADDITIONS)


def get_kospi_list() -> pd.DataFrame:
    rows = [
        {"Symbol": f"{code}{yf_suffix(code)}", "Code": code, "Name": name, "Sector": sector}
        for code, name, sector in KOSPI_STOCKS
    ]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = get_kospi_list()
    print(f"총 {len(df)}개 종목")
    print(df.head())
