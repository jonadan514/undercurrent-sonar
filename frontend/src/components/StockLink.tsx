// 종목 이름을 누르면 기업 기초조사 카드로 (2026-10-20 워치리스트 상세 카드 → 2026-11-05 /company).
// /company?stock=US:MU - 기업 기초조사 카드(2026-11-05). 예전엔 /watchlist?stock=(후보 팝업)였고, 그 주소도 그대로 동작한다.
import type { ReactNode } from "react";

export function stockHref(market: string, symbol: string): string {
  return `/company?stock=${encodeURIComponent(`${market}:${symbol}`)}`;
}

export default function StockLink({ market, symbol, children, className, style }: {
  market: string; symbol: string; children: ReactNode; className?: string; style?: React.CSSProperties;
}) {
  return (
    <a href={stockHref(market, symbol)} className={`hover:underline ${className ?? ""}`} style={style}
      onClick={(e) => e.stopPropagation()} title="종목 상세 보기">
      {children}
    </a>
  );
}

// 후보가 아닌 종목용 외부 시세 페이지
export function externalQuoteUrl(market: string, symbol: string): string {
  return market === "KR"
    ? `https://finance.naver.com/item/main.naver?code=${encodeURIComponent(symbol)}`
    : `https://finance.yahoo.com/quote/${encodeURIComponent(symbol.replace(".", "-"))}`;   // BRK.B -> BRK-B (야후 표기)
}
