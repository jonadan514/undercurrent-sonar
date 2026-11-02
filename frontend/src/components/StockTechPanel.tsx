"use client";

// 종목 모달 공용: 미니 가격 차트(6개월 종가 + SMA50/200) + 기술 지표 분해
// 워치리스트 상세 팝업에서 사용

import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

interface Point { date: string; close: number; sma50: number | null; sma200: number | null }
interface Indicators {
  rsi14: number | null;
  macd_cross: "golden" | "dead";
  macd_turning: boolean;
  above_sma50: boolean | null;
  above_sma200: boolean | null;
  golden_cross: boolean | null;
  pct_from_52w_high: number;
}
interface ChartData { points: Point[]; indicators: Indicators }

function rsiInfo(v: number | null) {
  if (v == null) return { label: "—", desc: "데이터 없음", color: "#726b58" };
  if (v >= 70) return { label: v.toFixed(0), desc: "과열 — 추격 매수 주의", color: "#fb923c" };
  if (v <= 30) return { label: v.toFixed(0), desc: "과매도 — 반등 관찰", color: "#6fb3b8" };
  return { label: v.toFixed(0), desc: "중립 구간", color: "#4ade80" };
}

export default function StockTechPanel({ market, symbol }: { market: string; symbol: string }) {
  const [data, setData] = useState<ChartData | null>(null);
  const [state, setState] = useState<"loading" | "error" | "ok">("loading");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setData(null);
    fetch(`/api/stock/chart?market=${market}&symbol=${encodeURIComponent(symbol)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { if (!cancelled) { setData(d); setState("ok"); } })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, [market, symbol]);

  if (state === "loading") {
    return <div className="h-40 animate-pulse" style={{ background: "#0e0d08" }} />;
  }
  if (state === "error" || !data) {
    return (
      <p className="text-[12px]" style={{ color: "#a39c88" }}>
        차트 데이터를 불러오지 못했습니다(가격 조회 실패).
      </p>
    );
  }

  const ind = data.indicators;
  const rsi = rsiInfo(ind.rsi14);
  const isKR = market === "KR";
  const fmtPrice = (v: number) => isKR ? `₩${Math.round(v).toLocaleString()}` : `$${v.toFixed(2)}`;
  const first = data.points[0]?.close;
  const last = data.points[data.points.length - 1]?.close;
  const chg6m = first && last ? (last / first - 1) * 100 : null;

  const tiles = [
    {
      label: "RSI (14일)",
      value: rsi.label,
      desc: rsi.desc,
      color: rsi.color,
    },
    {
      label: "MACD",
      value: ind.macd_cross === "golden" ? "골든크로스" : "데드크로스",
      desc: ind.macd_turning ? "최근 전환됨 — 방향 변화 신호" : "상태 지속 중",
      color: ind.macd_cross === "golden" ? "#4ade80" : "#f87171",
    },
    {
      label: "이동평균 위치",
      value: ind.above_sma200 == null ? "—"
        : ind.above_sma50 && ind.above_sma200 ? "50·200일선 위"
        : ind.above_sma200 ? "200일선 위" : "200일선 아래",
      desc: ind.golden_cross ? "50>200 정배열 (장기 상승 구조)" : "역배열 또는 데이터 부족",
      color: ind.above_sma200 ? "#4ade80" : "#f87171",
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-bold text-[#a39c88]">추세 · 모멘텀</p>
        <p className="text-[12px]" style={{ color: "#a39c88" }}>
          최근 6개월{chg6m != null && (
            <span className="ml-1 font-bold" style={{ color: chg6m >= 0 ? "#4ade80" : "#f87171" }}>
              {chg6m >= 0 ? "+" : ""}{chg6m.toFixed(1)}%
            </span>
          )}
          <span className="ml-2">고점 대비 <span style={{ color: ind.pct_from_52w_high > -5 ? "#4ade80" : ind.pct_from_52w_high > -15 ? "#facc15" : "#f87171" }}>{ind.pct_from_52w_high}%</span></span>
        </p>
      </div>

      {/* 미니 차트: 종가 + SMA50 + SMA200 */}
      <div className="p-2" style={{ background: "#0e0d08", border: "1px solid #262112" }}>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={data.points} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <XAxis dataKey="date" hide />
            <YAxis domain={["auto", "auto"]} hide />
            <Tooltip
              contentStyle={{ background: "#111009", border: "1px solid #262112", fontSize: 11 }}
              labelStyle={{ color: "#726b58" }}
              formatter={(value, name) => [
                typeof value === "number" ? fmtPrice(value) : String(value ?? "—"),
                name === "close" ? "종가" : name === "sma50" ? "50일선" : "200일선",
              ]}
            />
            <Line type="monotone" dataKey="close" stroke="#ffb020" strokeWidth={1.8} dot={false} />
            <Line type="monotone" dataKey="sma50" stroke="#facc15" strokeWidth={1} dot={false} strokeDasharray="4 3" connectNulls />
            <Line type="monotone" dataKey="sma200" stroke="#6fb3b8" strokeWidth={1} dot={false} strokeDasharray="4 3" connectNulls />
          </LineChart>
        </ResponsiveContainer>
        <p className="text-[12px] text-center" style={{ color: "#a39c88" }}>
          <span style={{ color: "#ffb020" }}>─ 종가</span>
          <span className="ml-2" style={{ color: "#facc15" }}>┄ 50일선</span>
          <span className="ml-2" style={{ color: "#6fb3b8" }}>┄ 200일선</span>
        </p>
      </div>

      {/* 지표 타일 */}
      <div className="grid grid-cols-3 gap-2">
        {tiles.map(({ label, value, desc, color }) => (
          <div key={label} className="p-2 text-center" style={{ background: "#0e0d08", border: `1px solid ${color}33` }}>
            <p className="text-[12px]" style={{ color: "#a39c88" }}>{label}</p>
            <p className="text-[13px] font-black leading-tight mt-0.5" style={{ color }}>{value}</p>
            <p className="text-[12px] mt-0.5 leading-snug" style={{ color: "#a39c88" }}>{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
