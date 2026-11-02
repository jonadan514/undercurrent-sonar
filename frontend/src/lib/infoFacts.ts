import type { getClient } from "@/src/lib/db";

// yfinance 기업 정보(fetch_status.info_payload)에서 꺼내 쓰는 사실 값 (2026-10-05).
// 주간 워치리스트 스크리닝이 받아 둔 값이라 수집 시점(as_of) 기준이다 - 화면에 날짜를 같이 적는다.
// 애널리스트 수: 적을수록 시장이 덜 보는 종목(이 도구의 "아직 조용한 곳"과 같은 방향). 목표가는 판단을 끌고 가는
// 숫자 하나라 일부러 꺼내지 않는다. 52주 위치: 수집 시점 가격의 고점·저점 대비 거리.
export interface InfoFacts {
  analysts: number | null;
  high52: number | null;
  low52: number | null;
  price: number | null;
  from_high: number | null;   // price / high52 - 1 (0 이하)
  from_low: number | null;    // price / low52 - 1
  as_of: string | null;
}

const num = (v: unknown) => (v == null || v === "" || Number.isNaN(Number(v)) ? null : Number(v));

export async function infoFacts(
  client: ReturnType<typeof getClient>, tickers: string[],
): Promise<Record<string, InfoFacts>> {
  const out: Record<string, InfoFacts> = {};
  const uniq = Array.from(new Set(tickers));
  try {
    for (let i = 0; i < uniq.length; i += 200) {
      const chunk = uniq.slice(i, i + 200);
      const res = await client.execute({
        sql: `SELECT ticker,
                     json_extract(info_payload, '$.numberOfAnalystOpinions'),
                     json_extract(info_payload, '$.fiftyTwoWeekHigh'),
                     json_extract(info_payload, '$.fiftyTwoWeekLow'),
                     COALESCE(json_extract(info_payload, '$.currentPrice'), json_extract(info_payload, '$.regularMarketPreviousClose')),
                     last_success_at
              FROM fetch_status WHERE info_payload IS NOT NULL AND ticker IN (${chunk.map(() => "?").join(",")})`,
        args: chunk,
      });
      res.rows.forEach((r) => {
        const high = num(r[2]), low = num(r[3]), price = num(r[4]);
        out[r[0] as string] = {
          analysts: num(r[1]), high52: high, low52: low, price,
          from_high: high && price ? Math.min(0, price / high - 1) : null,
          from_low: low && price ? price / low - 1 : null,
          as_of: r[5] ? String(r[5]).slice(0, 10) : null,
        };
      });
    }
  } catch { /* 표 없음 - 빈 결과 */ }
  return out;
}
