// 종목 이름을 누르면 워치리스트 상세 카드로 (2026-10-20, 사이트 사용성 1번).
// /watchlist?stock=US:MU - 이번 주 후보면 상세 카드가 바로 열리고, 후보가 아니면 외부 시세 링크를 보여준다.
import type { ReactNode } from "react";

export function stockHref(market: string, symbol: string): string {
  return `/watchlist?stock=${encodeURIComponent(`${market}:${symbol}`)}`;
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
