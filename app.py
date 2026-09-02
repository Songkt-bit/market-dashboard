import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="Market & FX Dashboard", layout="wide")
st.title("📊 Daily Market & FX Dashboard")

# 2. 데이터 대상 정의
INDICES = {
    "코스피": "^KS11",
    "코스닥": "^KQ11",
    "S&P 500": "^GSPC",
    "나스닥 종합": "^IXIC",
    "다우존스 산업": "^DJI",
    "러셀 2000": "^RUT",
    "필라델피아 반도체": "^SOX"
}

# 위안화(CNY/KRW)는 야후 파이낸스 누락 오류 방지를 위해 우회 계산(SYNTHETIC) 태그 적용
FX_TICKERS = {
    "미국 달러 (USD/KRW)": "KRW=X",
    "일본 엔 100 (JPY/KRW)": "JPYKRW=X",
    "유럽연합 유로 (EUR/KRW)": "EURKRW=X",
    "중국 위안 (CNY/KRW)": "SYNTHETIC_CNYKRW", 
    "달러/일본 엔 (USD/JPY)": "JPY=X",
    "유로/달러 (EUR/USD)": "EURUSD=X",
    "영국 파운드/달러 (GBP/USD)": "GBPUSD=X",
    "달러 인덱스 (DXY)": "DX-Y.NYB"
}

start_date = f"{datetime.datetime.now().year}-01-01"

# 3. 데이터 수집 엔진
@st.cache_data(ttl=3600)
def get_market_data():
    data = {}
    for name, ticker in INDICES.items():
        df = yf.download(ticker, start=start_date, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df = df['Close']
            else:
                df = df[['Close']]
            
            close = df.iloc[:, 0]
            ytd = ((close / close.iloc[0]) - 1) * 100
            peak = close.cummax()
            dd = ((close / peak) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
    return data

@st.cache_data(ttl=3600)
def get_fx_data():
    data = {}
    for name, ticker in FX_TICKERS.items():
        if ticker == "SYNTHETIC_CNYKRW":
            # 위안화 직접 조회 시 과거 데이터 누락 버그 해결을 위한 교차 환율 계산 (원/달러 ÷ 위안/달러)
            df_krw = yf.download("KRW=X", start=start_date, progress=False)
            df_cny = yf.download("CNY=X", start=start_date, progress=False)
            
            close_krw = df_krw['Close'].iloc[:, 0] if isinstance(df_krw.columns, pd.MultiIndex) else df_krw['Close']
            close_cny = df_cny['Close'].iloc[:, 0] if isinstance(df_cny.columns, pd.MultiIndex) else df_cny['Close']
            
            close = (close_krw / close_cny).dropna()
        else:
            df = yf.download(ticker, start=start_date, progress=False)
            if df.empty:
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df = df['Close']
            else:
                df = df[['Close']]
                
            close = df.iloc[:, 0]
            if ticker == "JPYKRW=X":  # 일본 엔화는 100엔 기준
                close = close * 100
                
        if len(close) > 0:
            ytd = ((close / close.iloc[0]) - 1) * 100
            peak = close.cummax()
            dd = ((close / peak) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
            
    return data

# 4. 탭 화면 그리기
tab1, tab2 = st.tabs(["📈 Page 1: 주가지수 대시보드", "💱 Page 2: 글로벌 환율 대시보드"])

with tab1:
    st.subheader("글로벌 주요 주가지수 YTD & MDD")
    data_dict_market = get_market_data()
    cols1 = st.columns(2)
    for idx, (name, df) in enumerate(data_dict_market.items()):
        with cols1[idx % 2]:
            latest_ytd = df['YTD'].iloc[-1]
            latest_dd = df['DD'].iloc[-1]
            latest_close = df['Close'].iloc[-1]
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df.index, y=df['YTD'], name="YTD %", line=dict(width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            
            fig.update_layout(title=f"<b>{name}</b> ({latest_close:,.2f}) | YTD: {latest_ytd:+.2f}% | DD: {latest_dd:.2f}%",
                              margin=dict(l=20, r=20, t=40, b=20), height=300, showlegend=False)
            fig.update_yaxes(title_text="YTD (%)", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=[-45, 2], secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("주요 통화 환율 & 달러 인덱스")
    data_dict_fx = get_fx_data()
    cols2 = st.columns(2)
    for idx, (name, df) in enumerate(data_dict_fx.items()):
        with cols2[idx % 2]:
            latest_ytd = df['YTD'].iloc[-1]
            latest_dd = df['DD'].iloc[-1]
            latest_close = df['Close'].iloc[-1]
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df.index, y=df['YTD'], name="YTD %", line=dict(color='royalblue', width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            
            fig.update_layout(title=f"<b>{name}</b> ({latest_close:,.2f}) | YTD: {latest_ytd:+.2f}% | DD: {latest_dd:.2f}%",
                              margin=dict(l=20, r=20, t=40, b=20), height=300, showlegend=False)
            fig.update_yaxes(title_text="YTD (%)", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=[-20, 2], secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)
