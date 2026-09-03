import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="Market & Macro Dashboard", layout="wide")
st.title("📊 Daily Market & Macro Dashboard")

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

start_date_ytd = f"{datetime.datetime.now().year}-01-01"

# 3. 데이터 수집 엔진
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
            if df.empty: continue
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            close = df.iloc[:, 0]
            if ticker == "JPYKRW=X": close = close * 100
                
        if len(close) > 0:
            ytd = ((close / close.iloc[0]) - 1) * 100
            dd = ((close / close.cummax()) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
    return data

# [NEW] Page 3 전용: 2000년부터의 장기 매크로 데이터 수집 엔진
@st.cache_data(ttl=3600)
def get_macro_correlation_data():
    start_long = "2000-01-01"
    # ^KS11(코스피), ^TNX(미 국채 10년물 금리)
    df_kospi = yf.download("^KS11", start=start_long, progress=False)
    df_tnx = yf.download("^TNX", start=start_long, progress=False)
    
    close_kospi = df_kospi['Close'].iloc[:, 0] if isinstance(df_kospi.columns, pd.MultiIndex) else df_kospi['Close']
    close_tnx = df_tnx['Close'].iloc[:, 0] if isinstance(df_tnx.columns, pd.MultiIndex) else df_tnx['Close']
    
    # 두 데이터를 하나의 표로 병합 (결측치 제거하여 날짜 맞춤)
    df_merged = pd.DataFrame({'KOSPI': close_kospi, 'US10Y': close_tnx}).dropna()
    return df_merged


# 4. 탭 화면 3개로 나누기!
tab1, tab2, tab3 = st.tabs(["📈 Page 1: 주가지수 대시보드", "💱 Page 2: 글로벌 환율 대시보드", "🇺🇸🇰🇷 Page 3: 매크로 상관관계"])

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
    
    # 이중 Y축 도화지 생성
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 좌측 Y축: 미국 국채 10년물 금리 (파란색 선)
    fig.add_trace(
        go.Scatter(x=df_macro.index, y=df_macro['US10Y'], name="미국 국채 10년(좌)", line=dict(color='#1f77b4', width=2)),
        secondary_y=False
    )
    
    # 우측 Y축: 코스피 지수 (검은색 선)
    fig.add_trace(
        go.Scatter(x=df_macro.index, y=df_macro['KOSPI'], name="코스피(우)", line=dict(color='black', width=2)),
        secondary_y=True
    )
    
    # 차트 디자인 및 범례 설정
    fig.update_layout(
        height=600,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5) # 범례를 위쪽 중앙에 가로로 배치
    )
    
    # 양쪽 Y축 이름 및 범위 설정
    fig.update_yaxes(title_text="미국 국채 10년 (%)", secondary_y=False)
    fig.update_yaxes(title_text="코스피 (pt)", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
