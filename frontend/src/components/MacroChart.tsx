"use client";

// 개요 매크로 카드의 추세선·1년 범위 막대·큰 그래프 (2026-10-17).
// 판정·색 등급 없이 값의 모양과 1년 안 위치만 보여준다(원칙 1) - 선은 중립색 하나.
import { useMemo, useState } from "react";

export type Point = [string, number];   // [날짜, 값]

const LINE = "var(--num)";

export function lastN(points: Point[], n: number): Point[] {
  return points.length > n ? points.slice(points.length - n) : points;
}

// 1년(약 252거래일) 안에서 현재 값의 위치 0~1. 최저=최고면 null.
export function rangePosition(points: Point[]): { min: number; max: number; pos: number | null } | null {
  if (points.length < 2) return null;
  const vals = points.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const cur = vals[vals.length - 1];
  return { min, max, pos: max > min ? (cur - min) / (max - min) : null };
}

function path(points: Point[], w: number, h: number, pad = 2): string {
  const vals = points.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  return points.map((p, i) => {
    const x = (i / Math.max(points.length - 1, 1)) * w;
    const y = pad + (1 - (p[1] - min) / span) * (h - pad * 2);
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export function Sparkline({ points, height = 28 }: { points: Point[]; height?: number }) {
  if (points.length < 2) return null;
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full block" style={{ height }} aria-hidden>
      <path d={path(points, 100, height)} fill="none" stroke={LINE} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// 실제 데이터 기간 이름 - 1년치가 안 쌓인 지표(국고채 등)를 "1년"이라 부르지 않는다
export function spanLabel(points: Point[]): string {
  if (points.length < 2) return "";
  const days = (Date.parse(points[points.length - 1][0]) - Date.parse(points[0][0])) / 86400000;
  return days >= 330 ? "1년" : `${Math.max(1, Math.round(days / 30.4))}개월`;
}

export function RangeBar({ points, fmt }: { points: Point[]; fmt: (v: number) => string }) {
  const r = rangePosition(points);
  if (!r || r.pos == null) return null;
  const span = spanLabel(points);
  return (
    <div className="mt-1">
      <div className="relative h-1 rounded-full" style={{ background: "var(--border)" }}>
        <div className="absolute top-1/2 w-2 h-2 rounded-full -translate-y-1/2 -translate-x-1/2"
          style={{ left: `${r.pos * 100}%`, background: LINE }} />
      </div>
      {/* 좁은 화면에선 최저·최고 숫자를 빼고 위치(%)만 - 세 칸이 겹친다 */}
      <div className="flex justify-center sm:justify-between text-[10px] mt-0.5" style={{ color: "var(--text-faint)", fontVariantNumeric: "tabular-nums" }}>
        <span className="hidden sm:inline">{fmt(r.min)}</span>
        <span>{span} 범위 {Math.round(r.pos * 100)}%</span>
        <span className="hidden sm:inline">{fmt(r.max)}</span>
      </div>
    </div>
  );
}

const PERIODS = [{ label: "1개월", n: 22 }, { label: "3개월", n: 63 }, { label: "1년", n: 260 }];

export function BigChart({ points, fmt, title, mark, initial = 63 }: {
  points: Point[]; fmt: (v: number) => string; title: string;
  mark?: string;      // 이 날짜부터 끝까지 음영(주간 브리핑: 그 주) - 2026-11-02
  initial?: number;
}) {
  const [n, setN] = useState(initial);
  const [hover, setHover] = useState<number | null>(null);
  const pts = useMemo(() => lastN(points, n), [points, n]);
  if (pts.length < 2) return <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>그래프 데이터가 아직 없습니다.</p>;
  const W = 600, H = 200, padY = 8;
  const vals = pts.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => (i / (pts.length - 1)) * W;
  const y = (v: number) => padY + (1 - (v - min) / span) * (H - padY * 2);
  const first = pts[0][1], last = pts[pts.length - 1][1];
  const h = hover != null ? pts[hover] : null;
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - rect.left) / rect.width) * (pts.length - 1));
    setHover(Math.max(0, Math.min(pts.length - 1, i)));
  };
  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-[13px] font-bold text-white">{title}</span>
        <span className="text-[12px]" style={{ color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
          {h ? `${h[0]} · ${fmt(h[1])}` : `${pts[0][0]} ~ ${pts[pts.length - 1][0]} · ${fmt(first)} → ${fmt(last)}`}
        </span>
        <div className="ml-auto flex gap-1">
          {PERIODS.map((p) => (
            <button key={p.label} onClick={() => { setN(p.n); setHover(null); }}
              className="text-[11px] px-2 py-0.5 rounded"
              style={n === p.n ? { background: "var(--bg-raised)", color: "var(--accent)", border: "1px solid var(--border-ctrl)" }
                : { color: "var(--text-muted)", border: "1px solid var(--border)" }}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full block cursor-crosshair" style={{ height: H }}
          onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)} role="img" aria-label={`${title} ${pts[0][0]}부터 ${pts[pts.length - 1][0]}까지`}>
          {mark && (() => {
            const i = pts.findIndex((p) => p[0] >= mark);
            return i >= 0 ? <rect x={x(Math.max(0, i - 1))} y={0} width={W - x(Math.max(0, i - 1))} height={H} fill="var(--border)" opacity={0.35} /> : null;
          })()}
          {[0, 0.5, 1].map((t) => (
            <line key={t} x1={0} x2={W} y1={padY + t * (H - padY * 2)} y2={padY + t * (H - padY * 2)}
              stroke="var(--border)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          <path d={pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")}
            fill="none" stroke={LINE} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          {hover != null && (
            <>
              <line x1={x(hover)} x2={x(hover)} y1={0} y2={H} stroke="var(--text-faint)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <circle cx={x(hover)} cy={y(pts[hover][1])} r={3.5} fill={LINE} vectorEffect="non-scaling-stroke" />
            </>
          )}
        </svg>
        <div className="flex flex-col justify-between text-[10px] shrink-0 py-0.5" style={{ color: "var(--text-faint)", fontVariantNumeric: "tabular-nums" }}>
          <span>{fmt(max)}</span><span>{fmt((max + min) / 2)}</span><span>{fmt(min)}</span>
        </div>
      </div>
    </div>
  );
}

// 주간 브리핑 매크로 칸의 한 주 흐름(2026-11-02, 사용자 요청) - 그 주(월~일) 구간만 진하게, 앞 3주는 흐리게(맥락).
// 주간 선은 직전 거래일 종가에서 시작한다 - 칸의 '주간 +x'(5거래일 전 대비)와 같은 출발점. 판정·색 등급 없음(원칙 1).
function shiftDay(d: string, days: number): string {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + days);
  return t.toISOString().slice(0, 10);
}

export function weekWindow(week: string): { start: string; end: string } {
  return { start: shiftDay(week, -7), end: shiftDay(week, -1) };   // 브리핑 주차(월요일) = 지난 7일을 돌아본다
}

export function upTo(points: Point[], end: string): Point[] {
  return points.filter((p) => p[0] <= end);
}

export function WeekSpark({ points, week, height = 30 }: { points: Point[]; week: string; height?: number }) {
  const { start, end } = weekWindow(week);
  const ctx = points.filter((p) => p[0] >= shiftDay(start, -21) && p[0] <= end);
  const firstIn = ctx.findIndex((p) => p[0] >= start);
  if (ctx.length < 2 || firstIn < 0) return null;
  const from = Math.max(0, firstIn - 1);            // 직전 거래일 종가부터
  const vals = ctx.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1, pad = 3, W = 100;
  const x = (i: number) => (i / (ctx.length - 1)) * W;
  const y = (v: number) => pad + (1 - (v - min) / span) * (height - pad * 2);
  const d = (a: number, b: number) => ctx.slice(a, b + 1).map((p, i) => `${i ? "L" : "M"}${x(a + i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const last = ctx.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="w-full block" style={{ height }} aria-hidden>
      <rect x={x(from)} y={0} width={W - x(from)} height={height} fill="var(--border)" opacity={0.35} />
      {from > 0 && <path d={d(0, from)} fill="none" stroke={LINE} strokeOpacity={0.35} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />}
      <path d={d(from, last)} fill="none" stroke={LINE} strokeWidth={1.8} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
