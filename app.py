"""
app.py  ─  산업군별 원자재 리스크 대시보드
──────────────────────────────────────────────────
실행 방법:
  1. pip install streamlit pandas numpy plotly
  2. python init_db.py
  3. streamlit run app.py
──────────────────────────────────────────────────
"""

import os
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="산업군 원자재 리스크 대시보드",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "scm_dashboard.db"
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#fff8ef",
    plot_bgcolor="#fffdf7",
    font=dict(color="#4b3b2b"),
    xaxis=dict(gridcolor="#eadfce", zerolinecolor="#eadfce"),
    yaxis=dict(gridcolor="#eadfce", zerolinecolor="#eadfce"),
    margin=dict(l=45, r=24, t=54, b=40),
)

INDUSTRY_MAP = {
    "Automotive": "모빌리티 & 배터리",
    "Pharma": "제약 & 바이오",
    "Energy": "에너지 & IT",
}
INDUSTRY_MAP_REVERSE = {label: code for code, label in INDUSTRY_MAP.items()}
INDUSTRY_TAB_ORDER = ["Automotive", "Pharma", "Energy"]
INDUSTRY_DEFAULTS = {
    "Automotive": ["리튬", "니켈", "구리", "알루미늄"],
    "Pharma": ["API 인덱스", "포장재 알루미늄", "포장재 PVC"],
    "Energy": ["원유", "천연가스", "실리콘 웨이퍼"],
}
COLOR_MAP = {
    "리튬": "#d1841f",
    "니켈": "#4c7fb8",
    "구리": "#2f9e44",
    "알루미늄": "#8e67af",
    "API 인덱스": "#b7654a",
    "포장재 알루미늄": "#6c8c3a",
    "포장재 PVC": "#5f9ea0",
    "에탄올 원료": "#9a7b59",
    "원유": "#d97862",
    "천연가스": "#2f9e44",
    "실리콘 웨이퍼": "#4c7fb8",
    "네온가스": "#c67a2d",
    "열연강판": "#a67c52",
    "갈륨": "#6b5b95",
    "인듐": "#4a6fa5",
}


st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+KR:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans KR', sans-serif; }
.stApp { background: #fffaf3; color: #4b3b2b; }
[data-testid="stSidebar"] { background: #fff6ea !important; border-right: 1px solid #eadcc8; }
[data-testid="stSidebar"] * { color: #5a4532 !important; }
.hero {
    background: linear-gradient(135deg, #fff7e8 0%, #ffedd3 100%);
    border: 1px solid #eadcc8;
    border-left: 4px solid #e89a2b;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
}
.hero h1 { margin: 0 0 4px 0; color: #5a4532; font-size: 1.5rem; }
.hero p { margin: 0; color: #8b7258; font-size: 0.82rem; }
.metric-card {
    background: #fffdf8; border: 1px solid #eadcc8; border-radius: 10px;
    padding: 14px 16px; min-height: 96px;
}
.metric-title { color: #8b7258; font-size: 0.75rem; margin-bottom: 6px; }
.metric-value { color: #5a4532; font-size: 1.25rem; font-weight: 700; }
.metric-delta-up { color: #2f9e44; font-size: 0.80rem; }
.metric-delta-down { color: #d94841; font-size: 0.80rem; }
.metric-delta-flat { color: #8b7258; font-size: 0.80rem; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        st.error(f"DB 파일({DB_PATH})이 없습니다. `python init_db.py`를 먼저 실행하세요.")
        st.stop()
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def ensure_material_category_integrity() -> None:
    """
    과거 DB 초기화 버그(컬럼 순서 꼬임)로 category 값이 숫자로 저장된 경우를
    앱 시작 시 자동 보정한다.
    """
    conn = get_connection()
    cur = conn.cursor()
    current_categories = [row[0] for row in cur.execute("SELECT DISTINCT category FROM RawMaterials").fetchall()]
    has_expected_category = any(cat in INDUSTRY_TAB_ORDER for cat in current_categories)
    if has_expected_category:
        return

    # init_db.py 기준: 1~4 Automotive, 5~7 Energy, 8~10 Pharma, 11 Automotive, 12~13 Energy
    migration_map = {
        1: "Automotive",
        2: "Automotive",
        3: "Automotive",
        4: "Automotive",
        5: "Energy",
        6: "Energy",
        7: "Energy",
        8: "Pharma",
        9: "Pharma",
        10: "Pharma",
        11: "Automotive",
        12: "Energy",
        13: "Energy",
    }
    for material_id, category in migration_map.items():
        cur.execute(
            "UPDATE RawMaterials SET category = ? WHERE material_id = ?",
            (category, material_id),
        )
    conn.commit()


@st.cache_data(ttl=300)
def get_date_bounds() -> tuple[date, date] | None:
    conn = get_connection()
    row = pd.read_sql(
        """
        SELECT MIN(rate_date) AS min_date, MAX(rate_date) AS max_date
        FROM v_exchange_daily_best
        """,
        conn,
    ).iloc[0]
    if row["min_date"] is None or row["max_date"] is None:
        return None
    return (
        pd.to_datetime(row["min_date"]).date(),
        pd.to_datetime(row["max_date"]).date(),
    )


@st.cache_data(ttl=300)
def load_materials() -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql(
        """
        SELECT material_id, name_kr, name_en, unit, category, base_price_usd
        FROM RawMaterials
        ORDER BY category, material_id
        """,
        conn,
    )


@st.cache_data(ttl=300)
def load_price_data(start_date: str, end_date: str, material_ids: list[int]) -> pd.DataFrame:
    if not material_ids:
        return pd.DataFrame()
    conn = get_connection()
    placeholders = ",".join("?" * len(material_ids))
    query = f"""
    SELECT
        ph.price_date AS 날짜,
        rm.material_id AS material_id,
        rm.name_kr AS 원자재,
        rm.name_en AS name_en,
        rm.category AS category,
        rm.unit AS 단위,
        ROUND(ph.price_usd, 3) AS 가격_USD,
        er.usd_krw AS 환율_KRW_raw,
        COALESCE(ph.source, 'DUMMY') AS 데이터_출처,
        COALESCE(er.source, 'DUMMY') AS 환율_출처
    FROM v_price_daily_best ph
    JOIN RawMaterials rm ON rm.material_id = ph.material_id
    LEFT JOIN v_exchange_daily_best er ON er.rate_date = ph.price_date
    WHERE ph.price_date BETWEEN ? AND ?
      AND ph.material_id IN ({placeholders})
    ORDER BY ph.price_date, rm.material_id
    """
    params: list[object] = [start_date, end_date] + material_ids
    frame = pd.read_sql(query, conn, params=params)
    frame["날짜"] = pd.to_datetime(frame["날짜"])

    # 환율 보간: 날짜 기준 환율 테이블을 별도로 만들어 ffill한 뒤 매핑
    # (원자재별 데이터가 섞여 다른 원자재의 환율이 유입되는 것을 방지)
    exchange_raw = pd.read_sql(
        "SELECT rate_date AS 날짜, usd_krw FROM v_exchange_daily_best WHERE rate_date BETWEEN ? AND ? ORDER BY rate_date",
        conn,
        params=[start_date, end_date],
    )
    exchange_raw["날짜"] = pd.to_datetime(exchange_raw["날짜"])

    # 가격 데이터에 존재하는 모든 날짜를 포괄하는 환율 맵 생성
    all_dates = frame[["날짜"]].drop_duplicates().sort_values("날짜")
    exchange_map = all_dates.merge(exchange_raw, on="날짜", how="left").sort_values("날짜")
    exchange_map["usd_krw"] = exchange_map["usd_krw"].ffill().bfill()
    exchange_map["usd_krw"] = exchange_map["usd_krw"].round(2)
    date_to_rate = dict(zip(exchange_map["날짜"], exchange_map["usd_krw"]))

    frame["환율_KRW"] = frame["날짜"].map(date_to_rate)
    frame["가격_KRW"] = (frame["가격_USD"] * frame["환율_KRW"]).round(0)
    frame.drop(columns=["환율_KRW_raw"], inplace=True)
    return frame


def make_period_range(preset: str, min_day: date, max_day: date) -> tuple[date, date]:
    if preset == "최근 3년":
        start = max(max_day - timedelta(days=365 * 3), min_day)
        return start, max_day
    if preset == "최근 10개월":
        start = max(max_day - timedelta(days=30 * 10), min_day)
        return start, max_day
    if preset == "최근 1년":
        start = max(max_day - timedelta(days=365), min_day)
        return start, max_day
    if preset == "최근 6개월":
        start = max(max_day - timedelta(days=30 * 6), min_day)
        return start, max_day
    return min_day, max_day


def count_business_days(start_d: date, end_d: date) -> int:
    """영업일(월~금) 일수."""
    n = 0
    d = start_d
    while d <= end_d:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def build_period_coverage_report(
    price_df: pd.DataFrame,
    query_start: date,
    query_end: date,
    selected_material_ids: list[int],
    id_to_kr: dict[int, str],
) -> pd.DataFrame:
    """선택 기간·원자재별로 DB에 실제로 존재하는 관측일 수를 점검한다."""
    expected = count_business_days(query_start, query_end)
    rows: list[dict[str, object]] = []
    for mid in sorted(selected_material_ids):
        kr = id_to_kr.get(mid, str(mid))
        if "material_id" in price_df.columns:
            sub = price_df[price_df["material_id"] == mid]
        else:
            sub = price_df[price_df["원자재"] == kr]
        n_obs = int(sub["날짜"].dt.normalize().nunique()) if not sub.empty else 0
        ratio = (n_obs / expected * 100.0) if expected > 0 else 0.0
        if n_obs == 0:
            status = "없음"
            note = "해당 기간·환율 JOIN 조건으로 표시할 가격 행이 없습니다."
        elif ratio < 50.0:
            status = "부분"
            note = "스냅샷·월별·누락일 등으로 영업일 대비 관측이 적습니다."
        elif ratio < 90.0:
            status = "부분"
            note = "대부분 채워졌으나 일부 영업일 누락 가능."
        else:
            status = "양호"
            note = ""
        rows.append(
            {
                "원자재": kr,
                "영업일_기대": expected,
                "관측일수": n_obs,
                "커버율_%": round(ratio, 1),
                "판정": status,
                "비고": note,
            }
        )
    return pd.DataFrame(rows)


def normalize_industry_values(values: list[str]) -> list[str]:
    """
    멀티셀렉트 session_state에 코드/라벨이 혼재할 수 있어
    DB 필터 전 표준 코드(Automotive/Pharma/Energy)로 정규화한다.
    """
    normalized: list[str] = []
    for value in values:
        if value in INDUSTRY_TAB_ORDER:
            normalized.append(value)
            continue
        code = INDUSTRY_MAP_REVERSE.get(value)
        if code:
            normalized.append(code)
    # 중복 제거 + 순서 유지
    deduped = list(dict.fromkeys(normalized))
    return deduped


def compute_metrics(price_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for material, group in price_df.groupby("원자재"):
        sub = group.sort_values("날짜").copy()
        if sub.empty:
            continue
        latest = sub.iloc[-1]
        prev = sub.iloc[-2] if len(sub) > 1 else latest
        prev_krw = float(prev["가격_KRW"]) if pd.notna(prev["가격_KRW"]) else 0.0
        latest_krw = float(latest["가격_KRW"]) if pd.notna(latest["가격_KRW"]) else 0.0
        daily_delta = float((latest_krw - prev_krw) / prev_krw * 100) if prev_krw != 0 else 0.0
        start_px = float(sub.iloc[0]["가격_KRW"]) if pd.notna(sub.iloc[0]["가격_KRW"]) else 0.0
        end_px = latest_krw
        period_change = ((end_px - start_px) / start_px * 100) if start_px != 0 else 0.0
        vol = float(sub["가격_KRW"].pct_change().dropna().std() * np.sqrt(252) * 100) if len(sub) > 2 else 0.0
        rows.append(
            {
                "원자재": material,
                "category": latest["category"],
                "단위": latest["단위"],
                "현재가_KRW": end_px,
                "현재가_USD": float(latest["가격_USD"]),
                "환율_KRW": float(latest["환율_KRW"]),
                "전일대비_%": daily_delta,
                "기간변동_%": period_change,
                "연환산변동성_%": vol,
            }
        )
    return pd.DataFrame(rows).sort_values("기간변동_%", ascending=False)


def build_exchange_chart(exchange_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=exchange_df["날짜"],
            y=exchange_df["환율_KRW"],
            mode="lines",
            name="USD/KRW",
            line=dict(color="#4c7fb8", width=2.2),
            fill="tozeroy",
            fillcolor="rgba(76,127,184,0.13)",
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>환율: %{y:,.1f}<extra></extra>",
        )
    )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text="USD/KRW 환율 추이", font=dict(size=15, color="#5a4532")),
        yaxis_title="KRW / USD",
        height=280,
    )
    return fig


def build_industry_line_chart(industry_df: pd.DataFrame, industry_label: str) -> go.Figure:
    fig = go.Figure()
    for material in industry_df["원자재"].unique():
        sub = industry_df[industry_df["원자재"] == material].sort_values("날짜").copy()
        sub["MA20"] = sub["가격_KRW"].rolling(20, min_periods=1).mean()
        color = COLOR_MAP.get(material, "#d1841f")
        fig.add_trace(
            go.Scatter(
                x=sub["날짜"],
                y=sub["가격_KRW"],
                mode="lines",
                line=dict(color=color, width=2),
                name=material,
                customdata=np.stack([sub["원자재"]], axis=-1),
                hovertemplate="<b>%{customdata[0]}</b><br>날짜: %{x|%Y-%m-%d}<br>KRW: %{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sub["날짜"],
                y=sub["MA20"],
                mode="lines",
                line=dict(color=color, width=1, dash="dot"),
                name=f"{material} MA20",
                showlegend=False,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text=f"{industry_label} 원자재 가격 추이 (KRW 환산)", font=dict(size=15, color="#5a4532")),
        yaxis_title="가격 (KRW)",
        hovermode="x unified",
        height=420,
    )
    return fig


def build_detail_chart(material_df: pd.DataFrame, material_name: str) -> go.Figure:
    sub = material_df.sort_values("날짜").copy()
    sub["MA20"] = sub["가격_KRW"].rolling(20, min_periods=1).mean()
    sub["MA60"] = sub["가격_KRW"].rolling(60, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["날짜"], y=sub["가격_KRW"], mode="lines", name="KRW", line=dict(color="#d1841f", width=2.4)))
    fig.add_trace(go.Scatter(x=sub["날짜"], y=sub["MA20"], mode="lines", name="MA20", line=dict(color="#4c7fb8", width=1.8)))
    fig.add_trace(go.Scatter(x=sub["날짜"], y=sub["MA60"], mode="lines", name="MA60", line=dict(color="#2f9e44", width=1.8)))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=dict(text=f"{material_name} 상세 분석 (MA20/MA60)", font=dict(size=14, color="#5a4532")),
        yaxis_title="가격 (KRW)",
        height=330,
    )
    return fig


def render_metric_cards(metrics_df: pd.DataFrame, top_n: int = 4) -> None:
    if metrics_df.empty:
        st.info("표시할 지표가 없습니다.")
        return
    show_df = metrics_df.head(top_n)
    cols = st.columns(len(show_df))
    for col, (_, row) in zip(cols, show_df.iterrows()):
        delta = float(row["전일대비_%"])
        cls_name = "metric-delta-up" if delta > 0 else "metric-delta-down" if delta < 0 else "metric-delta-flat"
        col.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">{row['원자재']} ({row['단위']})</div>
                <div class="metric-value">₩{row['현재가_KRW']:,.0f}</div>
                <div class="{cls_name}">전일 대비 {delta:+.2f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_clickable_chart(fig: go.Figure, key: str) -> str | None:
    """
    Streamlit 버전별 on_select 지원 차이를 흡수하기 위한 래퍼.
    클릭 이벤트가 지원되면 마지막 클릭 원자재명을 반환한다.
    """
    selected_material: str | None = None
    try:
        event = st.plotly_chart(fig, use_container_width=True, key=key, on_select="rerun")
        if isinstance(event, dict):
            selection = event.get("selection", {})
            points = selection.get("points", [])
            if points:
                point_data = points[-1]
                customdata = point_data.get("customdata")
                if isinstance(customdata, list) and customdata:
                    selected_material = str(customdata[0])
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, key=key)
    return selected_material


ensure_material_category_integrity()
load_materials.clear()
load_price_data.clear()
get_date_bounds.clear()
materials_df = load_materials()
_bounds = get_date_bounds()
if _bounds is None:
    st.warning(
        "데이터베이스에 환율 데이터가 없습니다. "
        "`python init_db.py` 또는 `python update_market_data.py`를 먼저 실행하세요."
    )
    st.stop()
min_date, max_date = _bounds
# DB에 실제로 있는 날짜 범위(min_date~max_date). 달력은 오늘까지 선택 가능(미보유 구간은 조회 시 자동 보정)
today = date.today()
calendar_max = today
ref_end = min(max_date, today)

with st.sidebar:
    st.markdown("### ⚙️ 조회 설정")
    st.markdown("---")
    period_preset = st.selectbox("환율/가격 추적 기간 프리셋", ["전체", "최근 3년", "최근 10개월", "최근 1년", "최근 6개월"], index=2)
    preset_start, preset_end = make_period_range(period_preset, min_date, ref_end)
    col_l, col_r = st.columns(2)
    with col_l:
        start_date = st.date_input(
            "시작일",
            value=preset_start,
            min_value=min_date,
            max_value=calendar_max,
        )
    with col_r:
        end_date = st.date_input(
            "종료일",
            value=preset_end,
            min_value=min_date,
            max_value=calendar_max,
        )
    st.caption(f"DB 보유 데이터: {min_date} ~ {max_date} (갱신: `python init_db.py` 또는 `python update_market_data.py`)")
    st.markdown("---")
    selected_groups = st.multiselect(
        "산업군 선택",
        options=INDUSTRY_TAB_ORDER,
        default=INDUSTRY_TAB_ORDER,
        format_func=lambda code: INDUSTRY_MAP.get(code, code),
    )
    selected_groups = normalize_industry_values(selected_groups)
    st.caption("모든 가격은 USD/KRW 환율과 JOIN하여 KRW 환산가 기준으로 표시됩니다.")

if start_date > end_date:
    st.error("시작일이 종료일보다 늦습니다. 기간을 다시 선택하세요.")
    st.stop()

# 실제 조회 구간: DB에 있는 날짜로만 제한(달력에서 오늘을 골라도 DB가 예전이면 여기서 맞춤)
query_start = max(start_date, min_date)
query_end = min(end_date, max_date)
if query_start > query_end:
    st.error(
        f"선택한 기간과 DB 데이터가 겹치지 않습니다. DB 보유: {min_date} ~ {max_date}."
    )
    st.stop()
if start_date < min_date or end_date > max_date:
    st.info(
        f"조회 구간을 DB에 있는 범위로 조정했습니다: {query_start} ~ {query_end} "
        f"(DB 최신일까지 쓰려면 DB를 갱신하세요.)"
    )

if not selected_groups:
    st.warning("최소 1개 산업군을 선택하세요.")
    st.stop()

selected_ids = materials_df[materials_df["category"].isin(selected_groups)]["material_id"].tolist()
if not selected_ids:
    st.warning("산업군 필터값이 일시적으로 꼬여 전체 산업군으로 자동 보정했습니다.")
    selected_groups = INDUSTRY_TAB_ORDER.copy()
    selected_ids = materials_df[materials_df["category"].isin(selected_groups)]["material_id"].tolist()
full_df = load_price_data(str(query_start), str(query_end), selected_ids)
if full_df.empty:
    st.error("선택한 조건에 해당하는 데이터가 없습니다.")
    st.stop()

id_to_kr = dict(
    zip(
        materials_df["material_id"].tolist(),
        materials_df["name_kr"].tolist(),
    )
)
coverage_df = build_period_coverage_report(
    full_df, query_start, query_end, selected_ids, id_to_kr
)
st.subheader("기간 적합성 점검")
st.caption(
    "선택한 조회 구간의 **영업일 수** 대비, 환율 JOIN까지 통과한 **가격 관측일 수**입니다. "
    "크롤링 스냅샷(리튬 등)은 관측이 1일뿐일 수 있습니다."
)
st.dataframe(coverage_df, use_container_width=True, hide_index=True)
if (coverage_df["관측일수"] == 0).any():
    st.warning(
        "일부 원자재는 위 기간에서 데이터를 찾지 못했습니다. "
        "`python crawl_market_data.py` 또는 `python update_market_data.py`로 갱신·범위를 확인하세요."
    )

metrics_df = compute_metrics(full_df)
exchange_df = full_df[["날짜", "환율_KRW"]].drop_duplicates().sort_values("날짜")

st.markdown(
    f"""
    <div class="hero">
        <h1>🌤️ 산업군별 원자재 리스크 관리 대시보드</h1>
        <p>조회기간: {query_start} ~ {query_end} | 영업일 {full_df['날짜'].nunique()}일 | 선택 산업군: {', '.join([INDUSTRY_MAP[g] for g in selected_groups])}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("데이터 적용 방식·공신력(필독)", expanded=False):
    st.markdown(
        """
        - **조회 구간**: 위 기간은 `PriceHistory`·`ExchangeRates`에 **실제로 존재하는 날짜**만 사용합니다(없는 날은 JOIN에서 빠짐).
        - **기본 시드**: `python init_db.py`로 넣은 값은 **통계 모형 기반 더미(DUMMY)** 이며, 시장 가격을 **대체·증명**하지 않습니다.
        - **실데이터 반영**: `python update_market_data.py` 실행 시 FRED·EIA·한국은행(ECOS)·yfinance(보조) 등이 들어오면 행 단위 `source`가 갱신됩니다(같은 날짜는 업서트).
        - **공신력**: FRED/EIA/BOK은 공식·준공식 통계에 가깝고, yfinance는 비공식이며 **참고용**으로 두는 것이 안전합니다.
        - **크롤링**: 앱 UI는 크롤링하지 않습니다. 배치로 **`python crawl_market_data.py`** 를 실행하면 Investing/USGS/Asian Metal 등 보조 수집 후 DB에 업서트합니다(이용약관 준수는 운영 책임).
        """
    )
    if "데이터_출처" in full_df.columns:
        src_df = (
            full_df.groupby(["원자재", "데이터_출처"], as_index=False)
            .size()
            .rename(columns={"size": "행수"})
        )
        st.caption("선택 기간·원자재별 가격 행의 출처(혼재 시 둘 이상 표시될 수 있음)")
        st.dataframe(src_df, use_container_width=True, hide_index=True)

tab_summary, tab_auto, tab_pharma, tab_energy = st.tabs(
    ["대시보드 개요 (Summary)", "모빌리티 & 배터리 (Automotive)", "제약 & 바이오 (Pharmaceutical)", "에너지 & IT (Energy/Tech)"]
)

with tab_summary:
    st.subheader("전체 변동률 Top 5 및 환율 요약")
    top5 = metrics_df.sort_values("기간변동_%", ascending=False).head(5)[["원자재", "category", "전일대비_%", "기간변동_%", "연환산변동성_%"]].copy()
    top5["산업군"] = top5["category"].map(lambda x: INDUSTRY_MAP.get(str(x), str(x)))
    top5 = top5.drop(columns=["category"]).rename(
        columns={
            "전일대비_%": "전일 대비(%)",
            "기간변동_%": "기간 변동(%)",
            "연환산변동성_%": "연환산 변동성(%)",
        }
    )
    col_a, col_b = st.columns([1.1, 1.4])
    with col_a:
        st.dataframe(top5, use_container_width=True, hide_index=True)
    with col_b:
        st.plotly_chart(build_exchange_chart(exchange_df), use_container_width=True)

    latest_rate = float(exchange_df.iloc[-1]["환율_KRW"])
    rate_change = float((exchange_df.iloc[-1]["환율_KRW"] - exchange_df.iloc[0]["환율_KRW"]) / exchange_df.iloc[0]["환율_KRW"] * 100)
    st.markdown(
        f"""
        <div class="metric-card" style="margin-top:10px;">
            <div class="metric-title">주요 환율 정보</div>
            <div class="metric-value">USD/KRW {latest_rate:,.1f}</div>
            <div class="{'metric-delta-up' if rate_change > 0 else 'metric-delta-down' if rate_change < 0 else 'metric-delta-flat'}">
                기간 변동 {rate_change:+.2f}%
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_industry_tab(industry_code: str, tab_key: str) -> None:
    industry_name = INDUSTRY_MAP[industry_code]
    industry_df = full_df[full_df["category"] == industry_code].copy()
    if industry_df.empty:
        st.info(f"{industry_name} 데이터가 없습니다.")
        return

    industry_metrics = compute_metrics(industry_df)
    st.subheader(f"{industry_name} 핵심 지표")
    render_metric_cards(industry_metrics, top_n=min(4, len(industry_metrics)))

    st.markdown("##### 가격 변동 라인 차트 (라인 클릭 시 상세 분석)")
    fig = build_industry_line_chart(industry_df, industry_name)
    clicked_material = show_clickable_chart(fig, key=f"chart_{tab_key}")

    if clicked_material:
        st.session_state[f"selected_{tab_key}"] = clicked_material

    selectable = list(industry_df["원자재"].drop_duplicates())
    default_name = st.session_state.get(f"selected_{tab_key}", selectable[0])
    if default_name not in selectable:
        default_name = selectable[0]
    chosen = st.selectbox(
        "상세 분석 원자재",
        options=selectable,
        index=selectable.index(default_name),
        key=f"detail_sel_{tab_key}",
    )

    detail_df = industry_df[industry_df["원자재"] == chosen].copy()
    st.plotly_chart(build_detail_chart(detail_df, chosen), use_container_width=True, key=f"detail_{tab_key}")

    summary_row = industry_metrics[industry_metrics["원자재"] == chosen].iloc[0]
    col_l, col_r, col_m = st.columns(3)
    col_l.metric("현재가(KRW)", f"{summary_row['현재가_KRW']:,.0f}")
    col_r.metric("전일 대비", f"{summary_row['전일대비_%']:+.2f}%")
    col_m.metric("연환산 변동성", f"{summary_row['연환산변동성_%']:.1f}%")


with tab_auto:
    render_industry_tab("Automotive", "auto")

with tab_pharma:
    render_industry_tab("Pharma", "pharma")

with tab_energy:
    render_industry_tab("Energy", "energy")

st.markdown("<br>", unsafe_allow_html=True)
st.caption(
    "SCM 리스크 관리 데모 | 시드 DUMMY 가능 | update_market_data.py(API) · crawl_market_data.py(크롤) 병행 | "
    "앱은 크롤 자동 미실행"
)