import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="Market & Macro Dashboard", layout="wide")
st.title("📊 Daily Market & Macro Dashboard")

# 2. 데이터 대상 정의
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
            "최근": name, "2023 종가": val_23, "2024 종가": val_24,
            "2025 종가": val_25, today_str: val_today, "YTD": ytd
        })
    return pd.DataFrame(results), today_str

@st.cache_data(ttl=3600)
def get_kospi_heatmap_data():
    df = yf.download("^KS11", start="1996-12-01", progress=False)
    if df.empty: return pd.DataFrame()
    
    close = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
    close = close.iloc[:, 0]
    
    monthly_close = close.resample('ME').last()
    monthly_ret = monthly_close.pct_change() * 100
    
    yearly_close = close.resample('YE').last()
    yearly_ret = yearly_close.pct_change() * 100
    yearly_ret.index = yearly_ret.index.year
    
    df_ret = pd.DataFrame({'Return': monthly_ret})
    df_ret['Year'] = df_ret.index.year
    df_ret['Month'] = df_ret.index.month
    
    pivot = df_ret.pivot(index='Year', columns='Month', values='Return')
    cols = list(range(1, 13))
    pivot = pivot.reindex(columns=cols)
    pivot['연간수익'] = yearly_ret
    pivot = pivot[pivot.index >= 1997]
    
    avg_all = pivot.mean()
    avg_2000 = pivot[pivot.index >= 2000].mean()
    avg_2010 = pivot[pivot.index >= 2010].mean()
    avg_2020 = pivot[pivot.index >= 2020].mean()
    pos_count = (pivot > 0).sum()
    total_count = pivot.notna().sum()
    win_rate = (pos_count / total_count) * 100
    
    summary = pd.DataFrame([
        avg_all, avg_2000, avg_2010, avg_2020, win_rate
    ], index=['average', '2000년이후', '2010년이후', '2020년이후', '상승확률'])
    
    full_df = pd.concat([pivot, summary])
    full_df.columns = [f"{c}월" for c in range(1, 13)] + ['연간수익']
    return full_df

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

@st.cache_data(ttl=3600)
def get_us_bonds_data():
    bond_tickers = {"5년물": "^FVX", "10년물": "^TNX", "30년물": "^TYX"}
    start_long = "2000-01-01"
    data = {}
    for name, ticker in bond_tickers.items():
        df = yf.download(ticker, start=start_long, progress=False)
        if not df.empty:
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            data[name] = df.iloc[:, 0]
    return data

# 4. 탭 화면 구성 (Page 5 추가)
tab_home, tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏠 Home", "📈 Page 1: 주가지수", "💱 Page 2: 환율", "Page 3: 상관관계", "Page 4: 미국 국채", "⚙️ Page 5: 국내파생 수급"])

# ==========================================
# [Home] 시장 요약 & 코스피 계절성 히트맵
# ==========================================
with tab_home:
    col_left, col_right = st.columns([1, 1.2]) 
    
    with col_left:
        st.subheader("최근 3년 & YTD 글로벌 시장 요약")
        df_summary, today_col = get_summary_table_data()
        def highlight_ytd(val):
            color = '#ffcccc' if val < 0 else '#ccffcc'
            return f'background-color: {color}'
        formatted_df = df_summary.style.format({
            "2023 종가": "{:,.2f}", "2024 종가": "{:,.2f}", "2025 종가": "{:,.2f}",
            today_col: "{:,.2f}", "YTD": "{:+.2f}%"
        }).map(highlight_ytd, subset=['YTD'])
        st.dataframe(formatted_df, use_container_width=True, hide_index=True)
        
    with col_right:
        st.subheader("🔥 코스피 월별/연간 수익률 히트맵 (1997~현재)")
        full_df = get_kospi_heatmap_data()
        formatted_str_df = pd.DataFrame('', index=full_df.index, columns=full_df.columns)
        styles_df = pd.DataFrame('', index=full_df.index, columns=full_df.columns)
        
        for row in full_df.index:
            for col in full_df.columns:
                val = full_df.loc[row, col]
                if pd.isna(val): continue
                formatted_str_df.loc[row, col] = f"{val:.1f}%"
                bg_color = ""
                if row == '상승확률':
                    intensity = min(abs(val - 50) / 50.0, 1.0) if pd.notna(val) else 0
                    if val > 50: bg_color = f'background-color: rgba(255, 99, 71, {intensity}); color: #000;'
                    elif val < 50: bg_color = f'background-color: rgba(100, 149, 237, {intensity}); color: #000;'
                else:
                    intensity = min(abs(val) / 12.0, 1.0)
                    if val > 0: bg_color = f'background-color: rgba(255, 99, 71, {intensity}); color: #000;'
                    elif val < 0: bg_color = f'background-color: rgba(100, 149, 237, {intensity}); color: #000;'
                if row == 'average': bg_color += ' border-top: 3px solid #666 !important;'
                styles_df.loc[row, col] = bg_color
                
        html_table = formatted_str_df.style.apply(lambda _: styles_df, axis=None).to_html()
        target_snippet = ">average<"
        if target_snippet in html_table:
            idx_pos = html_table.find(target_snippet)
            tr_start = html_table.rfind("<tr", 0, idx_pos)
            if tr_start != -1:
                thead_start = html_table.find("<thead>")
                thead_end = html_table.find("</thead>")
                if thead_start != -1 and thead_end != -1:
                    header_content = html_table[thead_start:thead_end+8]
                    header_tr_html = header_content.replace("<thead>", "<tr style='background-color: #f0f2f6; font-weight: bold;'>").replace("</thead>", "</tr>").replace("th>", "td>")
                    html_table = html_table[:tr_start] + header_tr_html + html_table[tr_start:]

        final_custom_css = f"""<style>
.heatmap-container {{ width: 100%; max-height: 700px; overflow-y: auto; overflow-x: auto; border: 1px solid #ddd; border-radius: 5px; }}
.heatmap-container table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; text-align: center; }}
.heatmap-container th, .heatmap-container td {{ padding: 4px 2px !important; border: 1px solid #e0e0e0; white-space: nowrap; }}
.heatmap-container th {{ font-weight: bold; }}
.heatmap-container th:first-child, .heatmap-container td:first-child {{ border-right: 3px solid #666 !important; }}
.heatmap-container th:nth-last-child(2), .heatmap-container td:nth-last-child(2) {{ border-right: 3px solid #666 !important; }}
.heatmap-container th:first-child {{ min-width: 90px !important; text-align: left; padding-left: 8px !important; }}
.heatmap-container thead th {{ position: sticky; top: 0; background-color: #f0f2f6; z-index: 1; }}
@media (prefers-color-scheme: dark) {{ .heatmap-container thead th {{ background-color: #0e1117; }} }}
</style>
<div class="heatmap-container">
{html_table}
</div>"""
        st.markdown(final_custom_css, unsafe_allow_html=True)

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
            fig.update_layout(title=f"<b>{name}</b> ({df['Close'].iloc[-1]:,.2f}) | YTD: {df['YTD'].iloc[-1]:+.2f}% | DD: {df['DD'].iloc[-1]:,.2f}%",
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
            fig.update_layout(title=f"<b>{name}</b> ({df['Close'].iloc[-1]:,.2f}) | YTD: {df['YTD'].iloc[-1]:+.2f}% | DD: {df['DD'].iloc[-1]:,.2f}%",
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

# ==========================================
# [Page 4] 미국 국채 장기 추이
# ==========================================
with tab4:
    st.subheader("미국 국채 만기별 장기 추이 (2000년 ~ 현재)")
    bonds_data = get_us_bonds_data()
    selected_bond = st.radio("확인할 국채 만기를 선택하세요:", options=["5년물", "10년물", "30년물"], horizontal=True)
    if selected_bond in bonds_data:
        df_selected = bonds_data[selected_bond]
        latest_yield = df_selected.iloc[-1]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_selected.index, y=df_selected.values, name=selected_bond, line=dict(color='#ff7f0e', width=2)))
        fig.update_layout(title=f"<b>미국 국채 {selected_bond} 금리</b> (현재: {latest_yield:.3f}%)",
                          height=500, margin=dict(l=20, r=20, t=40, b=20), yaxis_title="수익률 (%)", xaxis_title="연도")
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 5] 국내 파생 수급 & 미결제약정 (데이터 구조화 탭)
# ==========================================
with tab5:
    st.subheader("⚙️ 국내 파생상품 수급 및 미결제약정 분석")
    st.info("💡 만기일 이후의 KRX 파생 데이터를 엑셀(CSV)로 업로드하여 수급과 미결제약정(OI)의 상관관계를 분석하는 공간입니다.")
    
    # CSV 파일 업로더 생성
    uploaded_file = st.file_uploader("KRX/HTS에서 추출한 파생 수급 CSV 파일을 업로드하세요", type=["csv"])
    
    if uploaded_file is not None:
        # 사용자가 파일을 올린 경우
        df_derivatives = pd.read_csv(uploaded_file)
        st.success("데이터가 성공적으로 구조화되었습니다!")
        st.dataframe(df_derivatives.head(), use_container_width=True)
        
        # 데이터 구조 예시 (컬럼 검증 안내)
        # 필수 컬럼: Date, Close(선물가격), Foreign_Net(외인선물누적), Open_Interest(미결제약정)
        if all(col in df_derivatives.columns for col in ['Date', 'Close', 'Foreign_Net', 'Open_Interest']):
            df_derivatives['Date'] = pd.to_datetime(df_derivatives['Date'])
            df_derivatives = df_derivatives.set_index('Date')
            
            # 이중 Y축 차트 (상단: 선물 가격 & 미결제약정 / 하단: 외인 누적 순매수)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, 
                                row_heights=[0.7, 0.3],
                                specs=[[{"secondary_y": True}], [{"secondary_y": False}]])
            
            # 1행 좌측: 선물 가격
            fig.add_trace(go.Scatter(x=df_derivatives.index, y=df_derivatives['Close'], name="코스피200 선물", line=dict(color='black', width=1.5)), row=1, col=1, secondary_y=False)
            # 1행 우측: 미결제약정 (OI)
            fig.add_trace(go.Scatter(x=df_derivatives.index, y=df_derivatives['Open_Interest'], name="미결제약정(OI)", line=dict(color='purple', width=1, dash='dot')), row=1, col=1, secondary_y=True)
            
            # 2행: 외국인 선물 누적 순매수
            fig.add_trace(go.Bar(x=df_derivatives.index, y=df_derivatives['Foreign_Net'], name="외인 선물 누적", marker_color='red'), row=2, col=1)
            
            fig.update_layout(height=650, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
            fig.update_yaxes(title_text="선물 가격", row=1, col=1, secondary_y=False)
            fig.update_yaxes(title_text="미결제약정(계약)", row=1, col=1, secondary_y=True)
            fig.update_yaxes(title_text="외인 누적", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ 업로드하신 파일에 필수 컬럼(`Date`, `Close`, `Foreign_Net`, `Open_Interest`)이 포함되어 있는지 확인해 주세요.")
    else:
        # 파일이 없을 때 보여줄 안내 가이드
        st.markdown("""
        ### 📋 파생 수급 CSV 파일 구조 가이드
        엑셀 파일(`csv`)을 만드실 때 첫 번째 행(컬럼명)을 아래와 같이 맞춰주시면 대시보드가 완벽하게 읽어냅니다.
        * **`Date`**: 날짜 (예: `2026-09-01`)
        * **`Close`**: 코스피200 선물 종가
        * **`Foreign_Net`**: 외국인 선물 누적 순매수 계약 수 (만기일 기준 리셋된 값)
        * **`Open_Interest`**: 시장 전체 미결제약정 수량
        
        > 💡 HTS나 KRX에서 만기일 이후 데이터를 다운받아 이 형식으로 저장해 두면, 버튼 클릭 한 번으로 기관·외인의 진짜 포쇼션을 차트 두 개로 겹쳐서 입체적으로 분석하실 수 있습니다!
        """)
