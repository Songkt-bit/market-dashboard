import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

st.set_page_config(page_title="Daily Market YTD & MDD Dashboard", layout="wide")
st.title("📈 Daily Market YTD & MDD Dashboard")

# 1. 대상 지수 야후 파이낸스 티커 정의
INDICES = {
    "코스피": "^KS11",
    "코스닥": "^KQ11",
    "S&P 500": "^GSPC",
    "나스닥 종합": "^IXIC",
    "다우존스 산업": "^DJI",
    "러셀 2000": "^RUT",
    "필라델피아 반도체": "^SOX"
}

# 2. 데이터 가져오기 (올해 1월 1일부터 현재까지)
start_date = f"{datetime.datetime.now().year}-01-01"

@st.cache_data(ttl=3600)  # 1시간마다 데이터 캐시 갱신
def get_market_data():
    data = {}
    for name, ticker in INDICES.items():
        df = yf.download(ticker, start=start_date, progress=False)
        if not df.empty:
            # MultiIndex 컬럼 정리
            if isinstance(df.columns, pd.MultiIndex):
                df = df['Close']
            else:
                df = df[['Close']]
            
            close = df.iloc[:, 0]
            # YTD 계산 (%)
            ytd = ((close / close.iloc[0]) - 1) * 100
            # MDD (Drawdown) 계산 (%)
            peak = close.cummax()
            dd = ((close / peak) - 1) * 100
            
            data[name] = pd.DataFrame({'Close': close, 'YTD': ytd, 'DD': dd})
    return data

data_dict = get_market_data()

# 3. 7개 지수 차트 그리드 생성 (2열 배치)
cols = st.columns(2)
for idx, (name, df) in enumerate(data_dict.items()):
    with cols[idx % 2]:
        latest_ytd = df['YTD'].iloc[-1]
        latest_dd = df['DD'].iloc[-1]
        latest_close = df['Close'].iloc[-1]
        
        # 서브플롯 생성 (이중 Y축)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 좌측 Y축: YTD 수익률 (%)
        fig.add_trace(
            go.Scatter(x=df.index, y=df['YTD'], name="YTD %", line=dict(width=2)),
            secondary_y=False
        )
        
        # 우측 Y축: Drawdown (%)
        fig.add_trace(
            go.Scatter(x=df.index, y=df['DD'], name="Drawdown %", line=dict(color='gray', width=1)),
            secondary_y=True
        )
        
        fig.update_layout(
            title=f"<b>{name}</b> ({latest_close:,.2f}) | YTD: {latest_ytd:+.2f}% | DD: {latest_dd:.2f}%",
            margin=dict(l=20, r=20, t=40, b=20),
            height=300,
            showlegend=False
        )
        fig.update_yaxes(title_text="YTD (%)", secondary_y=False)
        fig.update_yaxes(title_text="DD (%)", range=[-45, 2], secondary_y=True)
        
        st.plotly_chart(fig, use_container_width=True)