"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";

type DateBounds = { min_date: string; max_date: string };
type Material = { material_id: number; name_kr: string; category: string };
type PriceRow = {
  date: string;
  name_kr: string;
  category: string;
  price_usd: number;
  exchange_rate: number;
  price_krw: number;
  price_source: string;
};
type MetricRow = {
  name_kr: string;
  category: string;
  unit: string;
  current_price_krw: number;
  current_price_usd: number;
  exchange_rate: number;
  daily_delta_pct: number;
  period_change_pct: number;
  annualized_volatility_pct: number;
};
type ExchangeRow = { date: string; usd_krw: number };
type CoverageRow = {
  name_kr: string;
  expected_business_days: number;
  observed_days: number;
  coverage_pct: number;
  status: string;
  note: string;
};
type DataSourceRow = { name_kr: string; source: string; row_count: number };

const API_BASE = "";
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const INDUSTRY_LABEL: Record<string, string> = {
  Automotive: "모빌리티 & 배터리",
  Pharma: "제약 & 바이오",
  Energy: "에너지 & IT",
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API 오류: ${res.status}`);
  return (await res.json()) as T;
}

function movingAverage(values: number[], window: number): number[] {
  return values.map((_, idx) => {
    const start = Math.max(0, idx - window + 1);
    const slice = values.slice(start, idx + 1);
    const sum = slice.reduce((acc, n) => acc + n, 0);
    return slice.length > 0 ? sum / slice.length : 0;
  });
}

export default function Page() {
  const [bounds, setBounds] = useState<DateBounds | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [exchange, setExchange] = useState<ExchangeRow[]>([]);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [dataSources, setDataSources] = useState<DataSourceRow[]>([]);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [activeMenu, setActiveMenu] = useState<"summary" | "deep-dive" | "quality">("summary");
  const [activeIndustryTab, setActiveIndustryTab] = useState<"summary" | "Automotive" | "Pharma" | "Energy">(
    "Automotive"
  );
  const [selectedMaterial, setSelectedMaterial] = useState<string>("");

  useEffect(() => {
    async function run(): Promise<void> {
      try {
        setLoading(true);
        const b = await fetchJson<DateBounds>("/api/date-bounds");
        const m = await fetchJson<Material[]>("/api/materials");
        const ids = m.map((x) => x.material_id).join(",");
        const [p, mt, ex, cv, ds] = await Promise.all([
          fetchJson<PriceRow[]>(`/api/prices?start_date=${b.min_date}&end_date=${b.max_date}&material_ids=${ids}`),
          fetchJson<MetricRow[]>(`/api/metrics?start_date=${b.min_date}&end_date=${b.max_date}&material_ids=${ids}`),
          fetchJson<ExchangeRow[]>(`/api/exchange?start_date=${b.min_date}&end_date=${b.max_date}`),
          fetchJson<CoverageRow[]>(`/api/coverage?start_date=${b.min_date}&end_date=${b.max_date}&material_ids=${ids}`),
          fetchJson<DataSourceRow[]>(
            `/api/data-sources?start_date=${b.min_date}&end_date=${b.max_date}&material_ids=${ids}`
          ),
        ]);
        setBounds(b);
        setMaterials(m);
        setPrices(p);
        setMetrics(mt);
        setExchange(ex);
        setCoverage(cv);
        setDataSources(ds);
      } catch (e) {
        setError(e instanceof Error ? e.message : "알 수 없는 오류");
      } finally {
        setLoading(false);
      }
    }
    run().catch(() => {
      setError("초기 로딩 실패");
      setLoading(false);
    });
  }, []);

  const latestRows = useMemo(() => {
    const map = new Map<string, PriceRow>();
    for (const row of prices) {
      const prev = map.get(row.name_kr);
      if (!prev || row.date > prev.date) map.set(row.name_kr, row);
    }
    return [...map.values()].sort((a, b) => b.price_krw - a.price_krw);
  }, [prices]);

  const latestFx = useMemo(() => (exchange.length > 0 ? exchange[exchange.length - 1] : null), [exchange]);
  const exchangeChange = useMemo(() => {
    if (exchange.length < 2) return 0;
    const first = exchange[0].usd_krw;
    const last = exchange[exchange.length - 1].usd_krw;
    return first !== 0 ? ((last - first) / first) * 100 : 0;
  }, [exchange]);
  const top5 = useMemo(() => metrics.slice(0, 5), [metrics]);

  const industrySeries = useMemo(() => prices.filter((x) => x.category === activeIndustryTab), [prices, activeIndustryTab]);
  const industryMetrics = useMemo(
    () => metrics.filter((x) => x.category === activeIndustryTab).slice(0, 4),
    [metrics, activeIndustryTab]
  );
  const industryMaterials = useMemo(() => [...new Set(industrySeries.map((x) => x.name_kr))], [industrySeries]);
  useEffect(() => {
    if (industryMaterials.length === 0) {
      setSelectedMaterial("");
      return;
    }
    if (!industryMaterials.includes(selectedMaterial)) {
      setSelectedMaterial(industryMaterials[0]);
    }
  }, [industryMaterials, selectedMaterial]);

  const detailSeries = useMemo(
    () =>
      industrySeries
        .filter((x) => x.name_kr === selectedMaterial)
        .sort((a, b) => a.date.localeCompare(b.date)),
    [industrySeries, selectedMaterial]
  );
  const detailMa20 = useMemo(() => movingAverage(detailSeries.map((x) => x.price_krw), 20), [detailSeries]);
  const detailMa60 = useMemo(() => movingAverage(detailSeries.map((x) => x.price_krw), 60), [detailSeries]);
  const detailMetric = useMemo(() => metrics.find((m) => m.name_kr === selectedMaterial), [metrics, selectedMaterial]);

  return (
    <main>
      <section className="hero">
        <h1>🌤️ 산업군별 원자재 리스크 관리 대시보드</h1>
        <p>
          조회기간: {bounds ? `${bounds.min_date} ~ ${bounds.max_date}` : "-"} | 영업일 {exchange.length}일 | 선택 산업군:
          {` ${Object.values(INDUSTRY_LABEL).join(", ")}`}
        </p>
      </section>

      <section className="card" style={{ marginTop: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className={activeMenu === "summary" ? "tab-btn active" : "tab-btn"} onClick={() => setActiveMenu("summary")}>
            📊 종합 요약
          </button>
          <button
            className={activeMenu === "deep-dive" ? "tab-btn active" : "tab-btn"}
            onClick={() => setActiveMenu("deep-dive")}
          >
            🏭 산업별 상세 분석
          </button>
          <button className={activeMenu === "quality" ? "tab-btn active" : "tab-btn"} onClick={() => setActiveMenu("quality")}>
            ⚙️ 데이터 무결성 및 설정
          </button>
        </div>
      </section>

      {loading && <section className="card" style={{ marginTop: 12 }}>불러오는 중...</section>}
      {error && <section className="card" style={{ marginTop: 12, color: "#d94841" }}>{error}</section>}

      {!loading && !error && activeMenu === "summary" && (
        <>
          <section className="card" style={{ marginTop: 12 }}>
            <h3>전체 변동률 Top 5 및 환율 요약</h3>
            <div className="row" style={{ marginTop: 10 }}>
              <div>
                <table>
                  <thead>
                    <tr>
                      <th>원자재</th>
                      <th>전일 대비(%)</th>
                      <th>기간 변동(%)</th>
                      <th>연환산 변동성(%)</th>
                      <th>산업군</th>
                    </tr>
                  </thead>
                  <tbody>
                    {top5.map((m) => (
                      <tr key={m.name_kr}>
                        <td>{m.name_kr}</td>
                        <td>{m.daily_delta_pct.toFixed(2)}</td>
                        <td>{m.period_change_pct.toFixed(2)}</td>
                        <td>{m.annualized_volatility_pct.toFixed(1)}</td>
                        <td>{INDUSTRY_LABEL[m.category] ?? m.category}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <Plot
                  data={[
                    {
                      x: exchange.map((x) => x.date),
                      y: exchange.map((x) => x.usd_krw),
                      type: "scatter" as const,
                      mode: "lines" as const,
                      line: { color: "#4c7fb8", width: 2 },
                      fill: "tozeroy",
                      fillcolor: "rgba(76,127,184,0.12)",
                      name: "USD/KRW",
                    },
                  ]}
                  layout={{
                    margin: { l: 40, r: 20, t: 60, b: 40 },
                    paper_bgcolor: "#fffdf8",
                    plot_bgcolor: "#fffdf8",
                    font: { color: "#4b3b2b" },
                    height: 320,
                    title: { text: "USD/KRW 환율 추이", font: { size: 15 }, y: 0.96 },
                  }}
                  style={{ width: "100%" }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </div>
            <div className="metric-strip">
              <div className="metric-card">
                <div className="metric-title">주요 환율 정보</div>
                <div className="metric-value">
                  USD/KRW {latestFx ? latestFx.usd_krw.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : "-"}
                </div>
                <div className={exchangeChange >= 0 ? "metric-up" : "metric-down"}>
                  기간 변동 {exchangeChange >= 0 ? "+" : ""}
                  {exchangeChange.toFixed(2)}%
                </div>
              </div>
            </div>
          </section>
        </>
      )}

      {!loading && !error && activeMenu === "deep-dive" && (
        <>
          <section className="tab-nav" style={{ marginTop: 12 }}>
            {(["Automotive", "Pharma", "Energy"] as const).map((tab) => (
              <button
                key={tab}
                className={activeIndustryTab === tab ? "tab-btn active" : "tab-btn"}
                onClick={() => setActiveIndustryTab(tab)}
              >
                {INDUSTRY_LABEL[tab]} ({tab})
              </button>
            ))}
          </section>

          <section className="card" style={{ marginTop: 12 }}>
            <h3>{INDUSTRY_LABEL[activeIndustryTab]} 핵심 지표</h3>
            <div className="metric-grid">
              {industryMetrics.map((m) => (
                <div key={m.name_kr} className="metric-card">
                  <div className="metric-title">
                    {m.name_kr} ({m.unit})
                  </div>
                  <div className="metric-value">₩{m.current_price_krw.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}</div>
                  <div className={m.daily_delta_pct >= 0 ? "metric-up" : "metric-down"}>
                    전일 대비 {m.daily_delta_pct >= 0 ? "+" : ""}
                    {m.daily_delta_pct.toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="card" style={{ marginTop: 12 }}>
            <h3>가격 변동 라인 차트</h3>
            <Plot
              data={industryMaterials
                .map((mat) => {
                  const rows = industrySeries
                    .filter((x) => x.name_kr === mat)
                    .sort((a, b) => a.date.localeCompare(b.date));
                  const ma20 = movingAverage(rows.map((r) => r.price_krw), 20);
                  return [
                    {
                      x: rows.map((r) => r.date),
                      y: rows.map((r) => r.price_krw),
                      type: "scatter" as const,
                      mode: "lines" as const,
                      name: mat,
                    },
                    {
                      x: rows.map((r) => r.date),
                      y: ma20,
                      type: "scatter" as const,
                      mode: "lines" as const,
                      name: `${mat} MA20`,
                      showlegend: false,
                      line: { width: 1, dash: "dot" as const },
                    },
                  ];
                })
                .flat()}
              layout={{
                margin: { l: 40, r: 20, t: 24, b: 40 },
                paper_bgcolor: "#fffdf8",
                plot_bgcolor: "#fffdf8",
                font: { color: "#4b3b2b" },
                height: 430,
                hovermode: "x unified",
              }}
              style={{ width: "100%" }}
              config={{ responsive: true }}
            />
          </section>

          <section className="card" style={{ marginTop: 12 }}>
            <h3>상세 분석 원자재</h3>
            <div style={{ marginBottom: 10 }}>
              <select
                value={selectedMaterial}
                onChange={(e) => setSelectedMaterial(e.target.value)}
                style={{
                  border: "1px solid #eadcc8",
                  borderRadius: 8,
                  padding: "8px 10px",
                  background: "#fffdf8",
                  color: "#4b3b2b",
                  minWidth: 220,
                }}
              >
                {industryMaterials.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <Plot
              data={[
                {
                  x: detailSeries.map((x) => x.date),
                  y: detailSeries.map((x) => x.price_krw),
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "KRW",
                  line: { width: 2.4, color: "#d1841f" },
                },
                {
                  x: detailSeries.map((x) => x.date),
                  y: detailMa20,
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "MA20",
                  line: { width: 1.8, color: "#4c7fb8" },
                },
                {
                  x: detailSeries.map((x) => x.date),
                  y: detailMa60,
                  type: "scatter" as const,
                  mode: "lines" as const,
                  name: "MA60",
                  line: { width: 1.8, color: "#2f9e44" },
                },
              ]}
              layout={{
                margin: { l: 40, r: 20, t: 24, b: 40 },
                paper_bgcolor: "#fffdf8",
                plot_bgcolor: "#fffdf8",
                font: { color: "#4b3b2b" },
                height: 360,
                hovermode: "x unified",
              }}
              style={{ width: "100%" }}
              config={{ responsive: true }}
            />
            <p style={{ marginTop: 8, fontSize: 12, color: "#8b7258" }}>
              * MA는 이동평균선(Moving Average)입니다. MA20은 최근 20일 평균, MA60은 최근 60일 평균 가격으로
              단기/중기 추세를 함께 보기 위한 보조선입니다.
            </p>
            {detailMetric && (
              <div className="detail-metrics">
                <div>
                  <div className="detail-label">현재가(KRW)</div>
                  <div className="detail-value">
                    {detailMetric.current_price_krw.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div>
                  <div className="detail-label">전일 대비</div>
                  <div className="detail-value">{detailMetric.daily_delta_pct.toFixed(2)}%</div>
                </div>
                <div>
                  <div className="detail-label">연환산 변동성</div>
                  <div className="detail-value">{detailMetric.annualized_volatility_pct.toFixed(1)}%</div>
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {!loading && !error && activeMenu === "quality" && (
        <>
          <section className="card" style={{ marginTop: 12 }}>
            <h3>데이터 적용 방식·공신력(필독)</h3>
            <p style={{ margin: 0, lineHeight: 1.7 }}>
              - 조회 구간은 DB에 존재하는 날짜만 사용합니다.<br />
              - 기본 시드는 통계 모형 기반 더미(DUMMY)이며 시장 가격을 대체하지 않습니다.<br />
              - update_market_data.py 실행 시 FRED/EIA/BOK/yfinance 출처가 반영됩니다.<br />
              - crawl_market_data.py는 보조 수집이며 사이트 정책 준수는 운영 책임입니다.
            </p>
          </section>

          <section className="card" style={{ marginTop: 12 }}>
            <div className="row">
              <div>
                <h4 style={{ marginTop: 0 }}>기간 적합성 점검</h4>
                <table>
                  <thead>
                    <tr>
                      <th>원자재</th>
                      <th>영업일(기대)</th>
                      <th>관측일수</th>
                      <th>커버율(%)</th>
                      <th>판정</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverage.map((c) => (
                      <tr key={c.name_kr}>
                        <td>{c.name_kr}</td>
                        <td>{c.expected_business_days}</td>
                        <td>{c.observed_days}</td>
                        <td>{c.coverage_pct}</td>
                        <td>{c.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h4 style={{ marginTop: 0 }}>데이터 출처별 행수 집계</h4>
                <table>
                  <thead>
                    <tr>
                      <th>원자재</th>
                      <th>출처</th>
                      <th>행수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dataSources.map((s, i) => (
                      <tr key={`${s.name_kr}-${s.source}-${i}`}>
                        <td>{s.name_kr}</td>
                        <td>{s.source}</td>
                        <td>{s.row_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
