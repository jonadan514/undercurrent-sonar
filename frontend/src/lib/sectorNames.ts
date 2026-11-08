// 업종 이름 한국어(2026-11-08 화면 점검 - 섹터 분석·워치리스트에 업종이 영어로만 나왔다).
// yfinance 업종(Technology·Consumer Defensive 등)과 SPDR 섹터 ETF 이름(Consumer Staples·Comm. Services 등)을 한 표로.
// 저장 값은 영어 그대로 두고 화면에서만 바꾼다(업종 비교·묶음 코드가 영어 키를 쓴다). 모르는 이름은 그대로.
const SECTOR_KO: Record<string, string> = {
  "Technology": "IT", "Information Technology": "IT",
  "Healthcare": "헬스케어", "Health Care": "헬스케어",
  "Financial Services": "금융", "Financials": "금융",
  "Consumer Cyclical": "경기소비재", "Consumer Discretionary": "경기소비재", "Consumer Disc.": "경기소비재",
  "Consumer Defensive": "필수소비재", "Consumer Staples": "필수소비재",
  "Industrials": "산업재",
  "Basic Materials": "소재", "Materials": "소재",
  "Energy": "에너지",
  "Utilities": "유틸리티",
  "Real Estate": "부동산",
  "Communication Services": "커뮤니케이션", "Comm. Services": "커뮤니케이션",
};

/** "Consumer Staples" -> "필수소비재" (모르는 이름·한국 업종명은 그대로) */
export function sectorKo(name: string | null | undefined): string {
  if (!name) return "";
  return SECTOR_KO[name] ?? name;
}
