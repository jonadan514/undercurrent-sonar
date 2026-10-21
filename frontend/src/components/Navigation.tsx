"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// 사이드바 그룹 — 보는 주기와 흐름 순서 (2026-10-04 재구성)
// 이번 주(월요일 갱신) → 분기(실적 주기) → 종목 → 돌아보기. 가이드는 도움말이라 맨 아래 따로.
// 예전 구성(오늘/시장/종목/관리)은 주간 도구인데 "오늘"이었고, 핵심인 테마 레이더가 섹터 다음에 묻혀
// 있었으며, 매주 보는 화면과 분기마다 보는 화면이 한 그룹에 섞여 있었다.
const NAV_GROUPS = [
  {
    label: "이번 주",
    items: [
      { href: "/",          label: "개요",       emoji: "📊", color: "#ffb020" },
      { href: "/radar",     label: "테마 레이더", emoji: "📡", color: "#ffb020" },
      { href: "/sector",    label: "섹터 분석",   emoji: "🏭", color: "#ffb020" },
      { href: "/briefing",  label: "주간 브리핑", emoji: "📰", color: "#ffb020" },
    ],
  },
  {
    label: "분기",
    items: [
      { href: "/quarterly", label: "분기 리서치", emoji: "🗓️", color: "#ffb020" },
    ],
  },
  {
    label: "종목",
    items: [
      { href: "/watchlist", label: "워치리스트",  emoji: "🔭", color: "#ffb020" },
    ],
  },
  {
    label: "돌아보기",
    items: [
      { href: "/notes",     label: "관찰 노트",  emoji: "📝", color: "#ffb020" },
      { href: "/scorecard", label: "성적표",     emoji: "📈", color: "#ffb020" },
    ],
  },
] as const;

const HELP_ITEM = { href: "/guide", label: "가이드", emoji: "📖", color: "#ffb020" } as const;

// 데이터 상태 요약(2026-10-21) - 정기 수집 20여 개의 마지막 저장 시각(/api/data/health). 누르면 /status.
// 예전에는 옛 표(data_costs) 하나의 날짜를 보고 "Weekly Market Analysis 실행 권장"을 띄웠다 - 지금 화면을 움직이는 수집과 무관했다.
type HealthSummary = { total: number; ok: number; late: number; missing: number };
function healthLabel(h: HealthSummary | null): { label: string; sub: string | null; color: string } {
  if (!h) return { label: "데이터 상태 확인 중", sub: null, color: "#423e33" };
  if (h.late === 0 && h.missing === 0) return { label: `데이터 ${h.total}개 모두 정상`, sub: null, color: "#4ade80" };
  const parts = [h.late > 0 ? `지연 ${h.late}` : null, h.missing > 0 ? `없음 ${h.missing}` : null].filter(Boolean).join(" · ");
  return { label: `데이터 ${h.total}개 중 ${parts}`, sub: "눌러서 어떤 칸인지 보기", color: h.late > 0 ? "#facc15" : "#f87171" };
}

function SidebarInner({
  onClose,
  health,
}: {
  onClose?: () => void;
  health: HealthSummary | null;
}) {
  const pathname = usePathname();
  const { label: freshnessLabel, sub: freshnessSub, color: freshnessColor } = healthLabel(health);

  return (
    <>
      {/* Logo */}
      <div
        className="flex h-20 shrink-0 items-center border-b px-5"
        style={{ borderColor: "var(--border)" }}
      >
        <span className="flex flex-col leading-none" title="Undercurrent Sonar">
          <span className="text-2xl font-black tracking-tight" style={{ color: "#ffb020" }}>
            U-<span style={{ color: "#ece7d8" }}>Sonar</span>
          </span>
          <span className="mt-1 whitespace-nowrap text-[10px] font-semibold tracking-[0.06em]" style={{ color: "#726b58" }}>
            UNDERCURRENT SONAR
          </span>
        </span>
        {onClose && (
          <button
            className="ml-auto p-2 rounded"
            onClick={onClose}
            style={{ color: "#726b58" }}
            aria-label="메뉴 닫기"
          >
            ✕
          </button>
        )}
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto min-h-0 py-3 px-2">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label} className={gi > 0 ? "mt-4" : ""}>
            <p
              className="px-3 mb-1 text-[11px] font-semibold"
              style={{ color: "#726b58" }}
            >
              {group.label}
            </p>
            {group.items.map(({ href, label: itemLabel, emoji, color: itemColor }) => {
              const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className="flex items-center gap-2.5 px-3 py-1.5 text-[13px] transition-all duration-150 relative my-0.5"
                  style={{
                    color: isActive ? "#ece7d8" : "#726b58",
                    background: isActive ? `${itemColor}15` : "transparent",
                    fontWeight: isActive ? 600 : 400,
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = "transparent";
                  }}
                >
                  {isActive && (
                    <span
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4"
                      style={{ background: itemColor }}
                    />
                  )}
                  <span
                    className="shrink-0 text-base leading-none"
                    style={{ opacity: isActive ? 1 : 0.6, transition: "opacity 0.15s" }}
                  >
                    {emoji}
                  </span>
                  <span style={{ letterSpacing: "0.01em" }}>{itemLabel}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* 도움말 - 메뉴 그룹과 분리 */}
      <div className="shrink-0 px-2 pb-2">
        <Link
          href={HELP_ITEM.href}
          className="flex items-center gap-2.5 px-3 py-1.5 text-[13px] transition-all duration-150"
          style={{
            color: pathname.startsWith(HELP_ITEM.href) ? "#ece7d8" : "#726b58",
            background: pathname.startsWith(HELP_ITEM.href) ? `${HELP_ITEM.color}15` : "transparent",
            fontWeight: pathname.startsWith(HELP_ITEM.href) ? 600 : 400,
          }}
        >
          <span className="shrink-0 text-base leading-none" style={{ opacity: pathname.startsWith(HELP_ITEM.href) ? 1 : 0.6 }}>
            {HELP_ITEM.emoji}
          </span>
          <span style={{ letterSpacing: "0.01em" }}>{HELP_ITEM.label}</span>
        </Link>
      </div>

      {/* Bottom: data freshness */}
      <div className="shrink-0 border-t px-3 py-3" style={{ borderColor: "var(--border)" }}>
        <Link
          href="/status"
          onClick={onClose}
          className="px-3 py-2 flex items-center gap-2"
          style={{ background: "#0e0d08", border: "1px solid #262112" }}
        >
          <span
            className="h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ background: freshnessColor, boxShadow: `0 0 5px ${freshnessColor}` }}
          />
          <div className="min-w-0">
            <p className="text-[11px] font-medium truncate" style={{ color: freshnessColor }}>
              {freshnessLabel}
            </p>
            {freshnessSub && (
              <p className="text-[11px] truncate" style={{ color: "#726b58" }}>
                {freshnessSub}
              </p>
            )}
          </div>
        </Link>
      </div>
    </>
  );
}

export default function Navigation() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  // 페이지를 옮길 때마다 다시 읽는다 - 가벼운 조회(표마다 MAX 하나)
  useEffect(() => {
    fetch("/api/data/health")
      .then((r) => r.json())
      .then((d) => setHealth(d.summary ?? null))
      .catch(() => {});
  }, [pathname]);

  // 페이지 이동 시 모바일 메뉴 닫기
  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  return (
    <>
      {/* ── 데스크톱: 고정 사이드바 ── */}
      <aside
        className="hidden md:flex w-56 shrink-0 flex-col border-r h-full overflow-hidden"
        style={{ background: "#0a0a08", borderColor: "var(--border)" }}
      >
        <SidebarInner health={health} />
      </aside>

      {/* ── 모바일: 햄버거 버튼 ── */}
      <button
        className="md:hidden fixed top-0 left-0 z-[60] flex items-center justify-center w-14 h-14"
        onClick={() => setIsOpen(true)}
        aria-label="메뉴 열기"
      >
        <svg width="20" height="16" viewBox="0 0 20 16" fill="none">
          <rect y="0"  width="20" height="2" rx="1" fill="#ece7d8" />
          <rect y="7"  width="20" height="2" rx="1" fill="#ece7d8" />
          <rect y="14" width="20" height="2" rx="1" fill="#ece7d8" />
        </svg>
      </button>

      {/* ── 모바일: 백드롭 ── */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 z-[50] bg-black/60"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* ── 모바일: 슬라이드 드로어 ── */}
      <aside
        className={`md:hidden fixed inset-y-0 left-0 z-[55] flex flex-col w-64 border-r overflow-hidden transition-transform duration-200 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ background: "#0a0a08", borderColor: "var(--border)" }}
      >
        <SidebarInner onClose={() => setIsOpen(false)} health={health} />
      </aside>
    </>
  );
}
