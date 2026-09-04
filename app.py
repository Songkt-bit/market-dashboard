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
def get_summary_table_data():
    summary_tickers = {
        "코스피": "^KS11", "코스닥": "^KQ11", "S&P 500": "^GSPC",
        "나스닥 종합": "^IXIC", "다우존스 산업": "^DJI", "항셍": "^HSI",
        "니케이 225": "^N225", "미국 국채 5년": "^FVX",
        "미국 국채 10년": "^TNX", "미국 국채 30년": "^TYX", "달러/원": "KRW=X"
    }
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    results = []
    
    for name, ticker in summary_tickers.items():
        df = yf.download(ticker, start="2023-01-01", progress=False)
        if df.empty: continue
        
        close = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
        close = close.iloc[:, 0]
        
        yearly = close.groupby(close.index.year).last()
        
        val_23 = yearly.get(2023, None)
        val_24 = yearly.get(2024, None)
        val_25 = yearly.get(2025, None)
        val_today = close.iloc[-1]
        
        ytd = ((val_today / val_25) - 1) * 100 if pd.notna(val_25) and val_25 != 0 else 0
            
        results.append({
            "최근": name,
            "2023 종가": val_23,
            "2024 종가": val_24,
            "2025 종가": val_25,
            today_str: val_today,
            "YTD": ytd
        })
        
    return pd.DataFrame(results), today_str

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

@st.cache_data(ttl=3600)
def get_macro_correlation_data():
    start_long = "2000-01-01"
    df_kospi = yf.download("^KS11", start=start_long, progress=False)
    df_tnx = yf.download("^TNX", start=start_long, progress=False)
    
    close_kospi = df_kospi['Close'].iloc[:, 0] if isinstance(df_kospi.columns, pd.MultiIndex) else df_kospi['Close']
    close_tnx = df_tnx['Close'].iloc[:, 0] if isinstance(df_tnx.columns, pd.MultiIndex) else df_tnx['Close']
    
    return pd.DataFrame({'KOSPI': close_kospi, 'US10Y': close_tnx}).dropna()


# 4. 탭 화면 4개로 나누기!
tab_home, tab1, tab2, tab3 = st.tabs(["🏠 Home: 시장 요약", "📈 Page 1: 주가지수", "💱 Page 2: 글로벌 환율", "🇺🇸🇰🇷 Page 3: 매크로 상관관계"])

# ==========================================
# [Home] 연도별 종가 요약 테이블
# ==========================================
with tab_home:
    st.subheader("최근 3년 & YTD 글로벌 시장 요약")
    
    # 💡 [핵심 변경 사항] 화면을 2개의 단(왼쪽, 오른쪽)으로 분할
    col_left, col_right = st.columns(2)
    
    # 표는 왼쪽 단에만 배치
    with col_left:
        df_summary, today_col = get_summary_table_data()
        
        def highlight_ytd(val):
            color = '#ffcccc' if val < 0 else '#ccffcc'
            return f'background-color: {color}'

        formatted_df = df_summary.style.format({
            "2023 종가": "{:,.2f}",
            "2024 종가": "{:,.2f}",
            "2025 종가": "{:,.2f}",
            today_col: "{:,.2f}",
            "YTD": "{:+.2f}%"
        }).map(highlight_ytd, subset=['YTD'])
        
        st.dataframe(formatted_df, use_container_width=True, hide_index=True)
        
    # 오른쪽 단은 향후 위젯을 위해 안내문만 남겨두고 비워둠
    with col_right:
        st.info("💡 나중에 이곳에 새로운 위젯이나 차트를 추가할 수 있습니다.")

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
    fig.add_trace(go.Scatter(x=df_macro.index, y=df_macro['US10Y'], name="미국 국채 10년(좌)", line=dict(color='#1f77b4', width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df_macro.index, y=df_macro['KOSPI'], name="코스피(우)", line=dict(color='black', width=2)), secondary_y=True)
    fig.update_layout(height=600, margin=dict(l=20, r=20, t=40, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
    fig.update_yaxes(title_text="미국 국채 10년 (%)", secondary_y=False)
    fig.update_yaxes(title_text="코스피 (pt)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)
