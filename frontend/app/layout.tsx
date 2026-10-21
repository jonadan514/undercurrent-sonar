import type { Metadata } from "next";
import { Noto_Sans_KR, Inter } from "next/font/google";
import Navigation from "@/src/components/Navigation";
import TopBar from "@/src/components/TopBar";
import PageMarketTabs from "@/src/components/PageMarketTabs";
import { MarketProvider } from "@/src/contexts/MarketContext";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const notoKr = Noto_Sans_KR({ subsets: ["latin"], variable: "--font-noto-kr", weight: ["400", "500", "700", "900"], display: "swap" });

export const metadata: Metadata = {
  title: "Undercurrent Sonar",
  description: "테마별 물밑 흐름(뉴스·실적·주가)을 따로 보는 주간 리서치 도구",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "U-Sonar",
  },
  icons: {
    apple: "/icon-192.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={`dark ${inter.variable} ${notoKr.variable}`}>
      <body className="flex h-screen overflow-hidden font-sans" style={{ background: "var(--bg-base)" }}>
        <MarketProvider>
          <Navigation />
          {/* Right side: header + content */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Top header bar - 명언은 개요에만(2026-10-21) */}
            <TopBar />
            {/* Page content */}
            {/* 모든 페이지를 같은 1280px 가운데 컨테이너에 둔다(2026-10-04). 예전엔 페이지마다 폭 제한이
                없거나(개요·섹터·성적표) 왼쪽 정렬(브리핑·가이드)이라, 넓은 화면에서 시장 탭과 본문이 어긋났다.
                읽기용 페이지(브리핑·가이드)는 이 안에서 자기 폭(max-w-3xl 등)을 그대로 쓴다. */}
            <main className="flex-1 overflow-y-auto px-4 pt-8 pb-6 md:px-7">
              <div className="mx-auto w-full max-w-[1280px]">
                <PageMarketTabs />
                {children}
              </div>
            </main>
          </div>
        </MarketProvider>
      </body>
    </html>
  );
}
