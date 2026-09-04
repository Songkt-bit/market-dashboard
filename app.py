import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="Market & Macro Dashboard", layout="wide")
st.title("📊 Daily Market & Macro Dashboard")

CURRENT_YEAR = datetime.datetime.now().year
start_date_ytd = f"{CURRENT_YEAR}-01-01"

# 2. 데이터 대상 정의 (Page 1, 2용)
INDICES = {
    "코스피": "^KS11", "코스닥": "^KQ11", "S&P 500": "^GSPC",
    "나스닥 종합": "^IXIC", "다우존스 산업": "^DJI",
    "러셀 2000": "^RUT", "필라델피아 반도체": "^SOX"
}

FX_TICKERS = {
    "미국 달러 (USD/KRW)": "KRW=X", "일본 엔 100 (JPY/KRW)": "JPYKRW=X",
    "유럽연합 유로 (EUR/KRW)": "EURKRW=X", "중국 위안 (CNY/KRW)": "SYNTHETIC_CNYKRW",
    "달러/일본 엔 (USD/JPY)": "JPY=X", "유로/달러 (EUR/USD)": "EURUSD=X",
    "영국 파운드/달러 (GBP/USD)": "GBPUSD=X", "달러 인덱스 (DXY)": "DX-Y.NYB"
}

# ==========================================================
# [NEW] Home 탭용 공통 유틸 + 데이터 수집 함수
# ==========================================================

def _extract_close(df):
    if df.empty:
        return None
    return df['Close'].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df['Close']


def get_yearend_snapshot_yf(ticker, years=(2021, 2022, 2023)):
    """야후파이낸스 티커 기준: 연도별 종가 + 현재값 + YTD% 계산"""
    df = yf.download(ticker, start=f"{min(years)}-01-01", progress=False)
    close = _extract_close(df)
    if close is None or close.empty:
        return {}
    result = {}
    for y in years:
        y_data = close[close.index.year == y]
        if not y_data.empty:
            result[y] = y_data.iloc[-1]
    current = close.iloc[-1]
    this_year_data = close[close.index.year == CURRENT_YEAR]
    if not this_year_data.empty:
        result["ytd"] = (current / this_year_data.iloc[0] - 1) * 100
    result["current"] = current
    result["current_date"] = close.index[-1].strftime("%Y-%m-%d")
    return result


# ----------------------------------------------------------
# [해결책 1] FRED: 야후파이낸스에 없는 미국 국채 3년/20년물
# API 키 불필요, CSV로 바로 다운로드 가능
# ----------------------------------------------------------
def get_yearend_snapshot_fred(series_id, years=(2021, 2022, 2023)):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), parse_dates=["observation_date"])
        df = df.rename(columns={"observation_date": "date", series_id: "value"})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).set_index("date")
    except Exception:
        return {}
    result = {}
    for y in years:
        y_data = df[df.index.year == y]
        if not y_data.empty:
            result[y] = y_data["value"].iloc[-1]
    current_data = df[df.index.year == CURRENT_YEAR]
    if current_data.empty:
        return result
    current = current_data["value"].iloc[-1]
    result["ytd"] = (current / current_data["value"].iloc[0] - 1) * 100
    result["current"] = current
    result["current_date"] = current_data.index[-1].strftime("%Y-%m-%d")
    return result


# ----------------------------------------------------------
# [해결책 2] 한국은행 ECOS Open API: 한국 국고채 3년/10년
# 무료 API 키 필요 → https://ecos.bok.or.kr (오픈API 메뉴에서 신청)
#
# ⚠️ 아래 STAT_CODE / ITEM_CODE는 참고용 예시입니다.
#    ECOS 사이트의 "통계코드검색" → "시장금리" → "국고채수익률"에서
#    최신 통계표코드/항목코드를 직접 확인한 뒤 교체해서 사용하세요.
#    (코드가 바뀌면 데이터가 비어있는 형태로 조용히 실패합니다)
# ----------------------------------------------------------
ECOS_API_KEY = "SD3KP3QMBSUDCP8GK0NM"
ECOS_STAT_CODE = "817Y002"  # 시장금리 통계표코드 (예시, 확인 필요)


def get_ecos_bond_yield(item_code, start="20210101", end=None):
    if end is None:
        end = datetime.datetime.now().strftime("%Y%m%d")
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr/1/10000/"
           f"{ECOS_STAT_CODE}/D/{start}/{end}/{item_code}")
    try:
        r = requests.get(url, timeout=10)
        rows = r.json()["StatisticSearch"]["row"]
        df = pd.DataFrame(rows)
        df["TIME"] = pd.to_datetime(df["TIME"])
        df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        df = df.set_index("TIME").sort_index()
    except Exception:
        return {}
    result = {}
    for y in (2021, 2022, 2023):
        y_data = df[df.index.year == y]
        if not y_data.empty:
            result[y] = y_data["DATA_VALUE"].iloc[-1]
    current_data = df[df.index.year == CURRENT_YEAR]
    if current_data.empty:
        return result
    current = current_data["DATA_VALUE"].iloc[-1]
    result["ytd"] = (current / current_data["DATA_VALUE"].iloc[0] - 1) * 100
    result["current"] = current
    result["current_date"] = current_data.index[-1].strftime("%Y-%m-%d")
    return result


# ----------------------------------------------------------
# Home 표 데이터 조립
# 국고채(KR)는 ECOS 키가 있을 때만 자동 반영, 회사채는 무료 API가
# 마땅치 않아 우선 수동값 자리로 남겨둡니다.
# ----------------------------------------------------------
@st.cache_data(ttl=3600)
def get_home_table():
    rows = []

    yf_items = [
        ("코스피", "^KS11"), ("코스닥", "^KQ11"),
        ("S&P 500", "^GSPC"), ("나스닥", "^IXIC"),
        ("다우존스", "^DJI"), ("항셍", "^HSI"),
        ("니케이225", "^N225"),
        ("미국국채 10년", "^TNX"),
        ("달러/원", "KRW=X"),
    ]
    for name, ticker in yf_items:
        snap = get_yearend_snapshot_yf(ticker)
        if snap:
            rows.append({"항목": name, **snap})

    fred_items = [
        ("미국국채 3년", "DGS3"),
        ("미국국채 20년", "DGS20"),
    ]
    for name, series_id in fred_items:
        snap = get_yearend_snapshot_fred(series_id)
        if snap:
            rows.append({"항목": name, **snap})

    # 국고채 3년/10년: ECOS_API_KEY를 채워 넣으면 자동으로 채워집니다.
    if ECOS_API_KEY != "SD3KP3QMBSUDCP8GK0NM":
        ecos_items = [
            ("국채 3년", "10200000"),   # 예시 항목코드 - 반드시 ECOS에서 확인
            ("국채 10년", "10210000"),  # 예시 항목코드 - 반드시 ECOS에서 확인
        ]
        for name, code in ecos_items:
            snap = get_ecos_bond_yield(code)
            if snap:
                rows.append({"항목": name, **snap})
    else:
        rows.append({"항목": "국채 3년 (ECOS 키 입력 필요)", "current": None})
        rows.append({"항목": "국채 10년 (ECOS 키 입력 필요)", "current": None})

    # 회사채(AA-, BBB-): 무료 실시간 API가 마땅치 않아 수동 입력값 사용
    # → 필요할 때마다 아래 값을 직접 업데이트하세요.
    manual_items = {
        "회사채 3년 AA-": {2021: None, 2022: 5.23, 2023: 3.9, "current": 3.59, "ytd": -7.9},
        "회사채 3년 BBB-": {2021: None, 2022: 11.166, 2023: 10.34, "current": 9.68, "ytd": -6.4},
    }
    for name, vals in manual_items.items():
        rows.append({"항목": name, **vals})

    df = pd.DataFrame(rows).set_index("항목")
    # 컬럼 순서 정리
    ordered_cols = [c for c in [2021, 2022, 2023, "current", "ytd"] if c in df.columns]
    return df[ordered_cols]


def style_home_table(df):
    display_df = df.rename(columns={
        2021: "2021", 2022: "2022", 2023: "2023",
        "current": f"{datetime.datetime.now().strftime('%Y-%m-%d')}",
        "ytd": "YTD(%)"
    })

    def color_ytd(val):
        if pd.isna(val):
            return ""
        color = "#1f4fd6" if val >= 0 else "#d62728"
        return f"color: {color}; font-weight: bold"

    styler = display_df.style.format(precision=2, na_rep="-")
    # pandas >= 2.1: Styler.map, 이전 버전: Styler.applymap (호환 처리)
    if hasattr(styler, "map"):
        styler = styler.map(color_ytd, subset=["YTD(%)"])
    else:
        styler = styler.applymap(color_ytd, subset=["YTD(%)"])
    styled = styler.set_properties(subset=["YTD(%)"], **{"background-color": "#fff8b0"})
    return styled


# ==========================================================
# 3. 데이터 수집 엔진 (Page 1, 2, 3 — 기존 그대로)
# ==========================================================
@st.cache_data(ttl=3600)
def get_market_data():
    data = {}
    for name, ticker in INDICES.items():
        df = yf.download(ticker, start=start_date_ytd, progress=False)
        if not df.empty:
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            close = df.iloc[:, 0]
            ytd = ((close / close.iloc[0]) - 1) * 100
            dd = ((close / close.cummax()) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
    return data


@st.cache_data(ttl=3600)
def get_fx_data():
    data = {}
    for name, ticker in FX_TICKERS.items():
        if ticker == "SYNTHETIC_CNYKRW":
            df_krw = yf.download("KRW=X", start=start_date_ytd, progress=False)
            df_cny = yf.download("CNY=X", start=start_date_ytd, progress=False)
            close_krw = df_krw['Close'].iloc[:, 0] if isinstance(df_krw.columns, pd.MultiIndex) else df_krw['Close']
            close_cny = df_cny['Close'].iloc[:, 0] if isinstance(df_cny.columns, pd.MultiIndex) else df_cny['Close']
            close = (close_krw / close_cny).dropna()
        else:
            df = yf.download(ticker, start=start_date_ytd, progress=False)
            if df.empty:
                continue
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            close = df.iloc[:, 0]
            if ticker == "JPYKRW=X":
                close = close * 100

        if len(close) > 0:
            ytd = ((close / close.iloc[0]) - 1) * 100
            dd = ((close / close.cummax()) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
    return data


@st.cache_data(ttl=3600)
def get_macro_correlation_data():
    start_long = "2000-01-01"
    df_kospi = yf.download("^KS11", start=start_long, progress=False)
    df_tnx = yf.download("^TNX", start=start_long, progress=False)

    close_kospi = df_kospi['Close'].iloc[:, 0] if isinstance(df_kospi.columns, pd.MultiIndex) else df_kospi['Close']
    close_tnx = df_tnx['Close'].iloc[:, 0] if isinstance(df_tnx.columns, pd.MultiIndex) else df_tnx['Close']

    df_merged = pd.DataFrame({'KOSPI': close_kospi, 'US10Y': close_tnx}).dropna()
    return df_merged


# ==========================================================
# 4. 탭 화면 4개로 구성 (Home 탭 추가)
# ==========================================================
tab0, tab1, tab2, tab3 = st.tabs([
    "🏠 Home",
    "📈 Page 1: 주가지수 대시보드",
    "💱 Page 2: 글로벌 환율 대시보드",
    "🇺🇸🇰🇷 Page 3: 매크로 상관관계"
])

# ==========================================
# [Home] 최근 3개년 + 현재 요약 테이블
# ==========================================
with tab0:
    st.subheader("최근 지표 요약 (2021~2023 연말 + 현재 + YTD)")
    home_df = get_home_table()
    st.dataframe(style_home_table(home_df), use_container_width=True, height=560)
    st.caption(
        "국고채 3년/10년은 ECOS_API_KEY를 입력해야 자동으로 채워집니다. "
        "회사채(AA-, BBB-)는 현재 코드에 수동으로 입력된 값입니다."
    )

# ==========================================
# [Page 1] 주가지수 화면
# ==========================================
with tab1:
    st.subheader("글로벌 주요 주가지수 YTD & MDD")
    cols1 = st.columns(2)
    for idx, (name, df) in enumerate(get_market_data().items()):
        with cols1[idx % 2]:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df.index, y=df['YTD'], name="YTD %", line=dict(width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            fig.update_layout(title=f"<b>{name}</b> ({df['Close'].iloc[-1]:,.2f}) | YTD: {df['YTD'].iloc[-1]:+.2f}% | DD: {df['DD'].iloc[-1]:.2f}%",
                              margin=dict(l=20, r=20, t=40, b=20), height=300, showlegend=False)
            fig.update_yaxes(title_text="YTD (%)", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=[-45, 2], secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 2] 환율 화면
# ==========================================
with tab2:
    st.subheader("주요 통화 환율 & 달러 인덱스")
    cols2 = st.columns(2)
    for idx, (name, df) in enumerate(get_fx_data().items()):
        with cols2[idx % 2]:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df.index, y=df['YTD'], name="YTD %", line=dict(color='royalblue', width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            fig.update_layout(title=f"<b>{name}</b> ({df['Close'].iloc[-1]:,.2f}) | YTD: {df['YTD'].iloc[-1]:+.2f}% | DD: {df['DD'].iloc[-1]:.2f}%",
                              margin=dict(l=20, r=20, t=40, b=20), height=300, showlegend=False)
            fig.update_yaxes(title_text="YTD (%)", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=[-20, 2], secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 3] 매크로 상관관계 (코스피 vs 국채금리)
# ==========================================
with tab3:
    st.subheader("금리와 코스피 장기 추이 (2000년 ~ 현재)")

    df_macro = get_macro_correlation_data()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(x=df_macro.index, y=df_macro['US10Y'], name="미국 국채 10년(좌)", line=dict(color='#1f77b4', width=2)),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(x=df_macro.index, y=df_macro['KOSPI'], name="코스피(우)", line=dict(color='black', width=2)),
        secondary_y=True
    )

    fig.update_layout(
        height=600,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )

    fig.update_yaxes(title_text="미국 국채 10년 (%)", secondary_y=False)
    fig.update_yaxes(title_text="코스피 (pt)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)
