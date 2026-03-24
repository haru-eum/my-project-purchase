import snapshot from "../../../data/snapshot.json";

export type Material = {
  material_id: number;
  name_kr: string;
  category: string;
  unit: string;
};

export type PriceRow = {
  date: string;
  material_id: number;
  name_kr: string;
  category: string;
  price_usd: number;
  exchange_rate: number;
  price_krw: number;
  price_source: string;
};

export type ExchangeRow = {
  date: string;
  usd_krw: number;
};

type SnapshotShape = {
  materials: Material[];
  prices: PriceRow[];
  exchange: ExchangeRow[];
  generated_at: string;
};

const data = snapshot as SnapshotShape;

export function getMaterials(): Material[] {
  return data.materials;
}

export function getDateBounds(): { min_date: string; max_date: string } {
  const dates = data.exchange.map((row) => row.date);
  if (dates.length === 0) {
    const today = new Date().toISOString().slice(0, 10);
    return { min_date: today, max_date: today };
  }
  return { min_date: dates[0], max_date: dates[dates.length - 1] };
}

export function parseMaterialIds(raw: string | null): number[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((v) => Number(v.trim()))
    .filter((v) => Number.isFinite(v));
}

export function filterPrices(params: {
  startDate: string;
  endDate: string;
  materialIds: number[];
}): PriceRow[] {
  const idSet = new Set<number>(params.materialIds);
  return data.prices.filter((row) => {
    const inRange = row.date >= params.startDate && row.date <= params.endDate;
    const idMatch = idSet.size === 0 || idSet.has(row.material_id);
    return inRange && idMatch;
  });
}

export function filterExchange(params: { startDate: string; endDate: string }): ExchangeRow[] {
  return data.exchange.filter((row) => row.date >= params.startDate && row.date <= params.endDate);
}

function pctChange(base: number, next: number): number {
  if (base === 0) return 0;
  return ((next - base) / base) * 100;
}

function dailyReturns(values: number[]): number[] {
  const out: number[] = [];
  for (let idx = 1; idx < values.length; idx += 1) {
    const prev = values[idx - 1];
    const curr = values[idx];
    if (prev !== 0) out.push((curr - prev) / prev);
  }
  return out;
}

function stddev(values: number[]): number {
  if (values.length <= 1) return 0;
  const mean = values.reduce((acc, v) => acc + v, 0) / values.length;
  const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

export function computeMetrics(rows: PriceRow[]): Array<{
  name_kr: string;
  category: string;
  unit: string;
  current_price_krw: number;
  current_price_usd: number;
  exchange_rate: number;
  daily_delta_pct: number;
  period_change_pct: number;
  annualized_volatility_pct: number;
}> {
  const mats = getMaterials();
  const unitById = new Map<number, string>(mats.map((m) => [m.material_id, m.unit]));
  const byMaterial = new Map<number, PriceRow[]>();

  for (const row of rows) {
    if (!byMaterial.has(row.material_id)) byMaterial.set(row.material_id, []);
    byMaterial.get(row.material_id)?.push(row);
  }

  const metrics = [...byMaterial.entries()].map(([materialId, list]) => {
    const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date));
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    const prev = sorted.length >= 2 ? sorted[sorted.length - 2] : last;
    const returns = dailyReturns(sorted.map((v) => v.price_krw));
    const annualizedVol = stddev(returns) * Math.sqrt(252) * 100;

    return {
      name_kr: last.name_kr,
      category: last.category,
      unit: unitById.get(materialId) ?? "",
      current_price_krw: Number(last.price_krw),
      current_price_usd: Number(last.price_usd),
      exchange_rate: Number(last.exchange_rate),
      daily_delta_pct: pctChange(prev.price_krw, last.price_krw),
      period_change_pct: pctChange(first.price_krw, last.price_krw),
      annualized_volatility_pct: annualizedVol,
    };
  });

  return metrics.sort((a, b) => b.period_change_pct - a.period_change_pct);
}

function businessDays(startDate: string, endDate: string): number {
  let count = 0;
  const cursor = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  while (cursor <= end) {
    const day = cursor.getUTCDay();
    if (day !== 0 && day !== 6) count += 1;
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return count;
}

export function computeCoverage(rows: PriceRow[], startDate: string, endDate: string): Array<{
  name_kr: string;
  expected_business_days: number;
  observed_days: number;
  coverage_pct: number;
  status: string;
  note: string;
}> {
  const expected = businessDays(startDate, endDate);
  const byMaterial = new Map<string, Set<string>>();

  for (const row of rows) {
    if (!byMaterial.has(row.name_kr)) byMaterial.set(row.name_kr, new Set<string>());
    byMaterial.get(row.name_kr)?.add(row.date);
  }

  return [...byMaterial.entries()]
    .map(([name, days]) => {
      const observed = days.size;
      const pct = expected > 0 ? (observed / expected) * 100 : 0;
      return {
        name_kr: name,
        expected_business_days: expected,
        observed_days: observed,
        coverage_pct: Number(pct.toFixed(1)),
        status: observed === 0 ? "미수집" : pct >= 80 ? "양호" : "주의",
        note: observed === 0 ? "선택 기간 데이터 없음" : "",
      };
    })
    .sort((a, b) => a.name_kr.localeCompare(b.name_kr, "ko-KR"));
}

export function computeDataSources(rows: PriceRow[]): Array<{ name_kr: string; source: string; row_count: number }> {
  const map = new Map<string, number>();
  for (const row of rows) {
    const key = `${row.name_kr}|||${row.price_source}`;
    map.set(key, (map.get(key) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([key, rowCount]) => {
      const [name, source] = key.split("|||");
      return { name_kr: name, source, row_count: rowCount };
    })
    .sort((a, b) => a.name_kr.localeCompare(b.name_kr, "ko-KR"));
}
