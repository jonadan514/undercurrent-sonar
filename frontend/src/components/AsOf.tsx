// 화면별 데이터 기준일 표시 통일(2026-10-20, 사용성 점검) - "10/19 기준 · 매주 월요일 아침 갱신".
// 기준일이 갱신 주기보다 많이 지났으면 노란색 + "지연" - 오래된 숫자로 판단하지 않게.
export default function AsOf({ date, cadence, staleDays }: { date: string | null | undefined; cadence: string; staleDays: number }) {
  const d = date ? new Date(date.slice(0, 10) + "T00:00:00") : null;
  if (!d || Number.isNaN(d.getTime())) {
    return <span className="text-[11px]" style={{ color: "var(--text-faint)" }}>기준일 없음 · {cadence} 갱신</span>;
  }
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  const late = Number.isFinite(days) && days > staleDays;
  return (
    <span className="text-[11px] whitespace-nowrap" style={{ color: late ? "#facc15" : "var(--text-faint)" }}
      title={late ? `기준일이 ${days}일 전 - 갱신이 늦어지고 있습니다` : undefined}>
      {d.getMonth() + 1}/{d.getDate()} 기준 · {cadence} 갱신{late ? " · 지연" : ""}
    </span>
  );
}
