import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import requests
import io

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
    "영국 파운드/달러 (GBP/USD)": "GBPUSD=X", "달러 인덱스 (DXY)": "DX-Y.NYB",
    "WTI 원유 ($/배럴)": "CL=F"
}

# 기간 선택에 따른 시작일 계산 헬퍼 함수
def get_start_date(period_option):
    today = datetime.date.today()
    if period_option == "YTD":
        return datetime.date(today.year, 1, 1)
    elif period_option == "1년":
        return today - datetime.timedelta(days=365)
    elif period_option == "3년":
        return today - datetime.timedelta(days=365 * 3)
    elif period_option == "5년":
        return today - datetime.timedelta(days=365 * 5)
    elif period_option == "10년":
        return today - datetime.timedelta(days=365 * 10)
    elif period_option == "20년":
        return today - datetime.timedelta(days=365 * 20)
    else: # Max
        return datetime.date(2000, 1, 1)

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

    win_rate = ((pivot > 0).sum() / pivot.notna().sum()) * 100

    summary = pd.DataFrame([
        avg_all, avg_2000, avg_2010, avg_2020, win_rate
    ], index=['average', '2000년이후', '2010년이후', '2020년이후', '상승확률'])

    full_df = pd.concat([pivot, summary])
    full_df.columns = [f"{c}월" for c in range(1, 13)] + ['연간수익']
    return full_df

@st.cache_data(ttl=3600)
def get_market_data(start_date_str):
    data = {}
    for name, ticker in INDICES.items():
        df = yf.download(ticker, start=start_date_str, progress=False)
        if not df.empty:
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            close = df.iloc[:, 0].dropna()
            if len(close) > 0:
                dd = ((close / close.cummax()) - 1) * 100
                data[name] = pd.DataFrame({'Close': close, 'DD': dd})
    return data

@st.cache_data(ttl=3600)
def get_fx_long_data(tickers_dict, start_date_str):
    data = {}
    for name, ticker in tickers_dict.items():
        if ticker == "SYNTHETIC_CNYKRW":
            df_krw = yf.download("KRW=X", start=start_date_str, progress=False)
            df_cny = yf.download("CNY=X", start=start_date_str, progress=False)
            close_krw = df_krw['Close'].iloc[:, 0] if isinstance(df_krw.columns, pd.MultiIndex) else df_krw['Close']
            close_cny = df_cny['Close'].iloc[:, 0] if isinstance(df_cny.columns, pd.MultiIndex) else df_cny['Close']
            close = (close_krw / close_cny).dropna()
        else:
            df = yf.download(ticker, start=start_date_str, progress=False)
            if df.empty: continue
            df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
            close = df.iloc[:, 0]
            if ticker == "JPYKRW=X": close = close * 100
        if len(close) > 0:
            close = close.dropna()
            dd = ((close / close.cummax()) - 1) * 100
            data[name] = pd.DataFrame({'Close': close, 'DD': dd})
    return data

@st.cache_data(ttl=3600)
def get_macro_correlation_data(start_date_str):
    df_kospi = yf.download("^KS11", start=start_date_str, progress=False)
    df_tnx = yf.download("^TNX", start=start_date_str, progress=False)
    close_kospi = df_kospi['Close'].iloc[:, 0] if isinstance(df_kospi.columns, pd.MultiIndex) else df_kospi['Close']
    close_tnx = df_tnx['Close'].iloc[:, 0] if isinstance(df_tnx.columns, pd.MultiIndex) else df_tnx['Close']
    return pd.DataFrame({'KOSPI': close_kospi, 'US10Y': close_tnx}).dropna()

@st.cache_data(ttl=3600)
def get_kospi_monthly_data():
    df = yf.download("^KS11", start="2000-01-01", progress=False)
    if df.empty:
        return pd.DataFrame()
    close = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
    close = close.iloc[:, 0]
    monthly = close.resample('ME').last()
    result = pd.DataFrame({'KOSPI': monthly})
    result['YearMonth'] = result.index.strftime('%Y-%m')
    return result.reset_index(drop=True)

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

@st.cache_data(ttl=3600)
def get_dram_csv_data():
    csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRyxRDpITzRJmbQ1XPnJHazHIq0IIr1DpeetgocahZipL64gDJYM_0H3JjFNv91C21t17TdCG9H-AHd/pub?gid=746668639&single=true&output=csv"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(csv_url, headers=headers)
        if response.status_code == 200:
            return pd.read_csv(io.StringIO(response.text))
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_samsung_disparity_data(start_date_str):
    df = yf.download(["005930.KS", "005935.KS"], start=start_date_str, progress=False)
    if df.empty: return pd.DataFrame()
    close_df = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
    common = close_df['005930.KS'] if '005930.KS' in close_df.columns else close_df.iloc[:, 0]
    pref = close_df['005935.KS'] if '005935.KS' in close_df.columns else close_df.iloc[:, 1]
    res_df = pd.DataFrame({'Common': common, 'Preferred': pref}).dropna()
    res_df['Disparity'] = ((res_df['Common'] - res_df['Preferred']) / res_df['Common']) * 100
    return res_df

@st.cache_data(ttl=3600)
def get_auto_macro_calendar():
    events = [
        {"Date": "2026-09-02", "Category": "고용", "Title": "미 ADP 취업자 변동", "Details": "ADP · 08:15 ET", "IsCore": "일반", "Actual": "99K", "Previous": "111K", "Forecast": "115K"},
        {"Date": "2026-09-03", "Category": "경기실물", "Title": "미 ISM 제조업 PMI", "Details": "ISM · 10:00 ET", "IsCore": "일반", "Actual": "47.9", "Previous": "46.8", "Forecast": "47.5"},
        {"Date": "2026-09-04", "Category": "고용", "Title": "월간 비농업 고용보고서 (실업률 포함)", "Details": "미 노동부 · 08:30 ET", "IsCore": "핵심", "Actual": "162K", "Previous": "21K", "Forecast": "55K"},
        {"Date": "2026-09-10", "Category": "고용", "Title": "주간 신규 실업수당 청구 건수", "Details": "미 노동부 · 08:30 ET", "IsCore": "일반", "Actual": "230K", "Previous": "232K", "Forecast": "230K"},
        {"Date": "2026-09-11", "Category": "물가", "Title": "미국 CPI (소비자물가지수)", "Details": "미 노동부 · 08:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "2.9%", "Forecast": "2.6%"},
        {"Date": "2026-09-12", "Category": "물가", "Title": "미국 PPI (생산자물가지수)", "Details": "미 노동부 · 08:30 ET", "IsCore": "일반", "Actual": "-", "Previous": "2.2%", "Forecast": "2.1%"},
        {"Date": "2026-09-15", "Category": "경기실물", "Title": "소매판매", "Details": "미 센서스국 · 08:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "0.1%", "Forecast": "0.3%"},
        {"Date": "2026-09-16", "Category": "통화정책", "Title": "FOMC 금리 결정 및 점도표 공개", "Details": "미 연준 · 14:00 ET (SEP 포함)", "IsCore": "핵심", "Actual": "-", "Previous": "5.50%", "Forecast": "5.25%"},
        {"Date": "2026-09-16", "Category": "통화정책", "Title": "파월 연준 의장 기자회견", "Details": "FOMC 직후 · 14:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "-", "Forecast": "-"},
        {"Date": "2026-09-24", "Category": "경기실물", "Title": "미국 GDP (확정치/속보치)", "Details": "미 상무부 · 08:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "3.0%", "Forecast": "2.9%"},
        {"Date": "2026-09-30", "Category": "물가", "Title": "미국 근원 PCE 물가지수", "Details": "미 상무부 · 08:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "2.6%", "Forecast": "2.5%"},
        {"Date": "2026-10-07", "Category": "통화정책", "Title": "FOMC 회의록 공개", "Details": "미 연준 (3주 전 회의)", "IsCore": "일반", "Actual": "-", "Previous": "-", "Forecast": "-"},
        {"Date": "2026-10-14", "Category": "물가", "Title": "미국 CPI (소비자물가지수)", "Details": "미 노동부 · 08:30 ET", "IsCore": "핵심", "Actual": "-", "Previous": "-", "Forecast": "-"},
    ]
    df = pd.DataFrame(events)
    df['Date_obj'] = pd.to_datetime(df['Date']).dt.date
    today = datetime.date.today()
    df['D-day'] = df['Date_obj'].apply(lambda x: (x - today).days)
    return df

@st.cache_data(ttl=3600)
def get_indicator_history(title):
    if "CPI" in title:
        return pd.DataFrame([
            {"발표일": "2026-08-12", "참고": "Jul", "실제": "2.9%", "이전": "3.0%", "예측치": "3.0%"},
            {"발표일": "2026-07-15", "참고": "Jun", "실제": "3.0%", "이전": "3.3%", "예측치": "3.1%"},
            {"발표일": "2026-06-12", "참고": "May", "실제": "3.3%", "이전": "3.4%", "예측치": "3.4%"}
        ])
    elif "고용보고서" in title or "고용" in title:
        return pd.DataFrame([
            {"발표일": "2026-09-04", "참고": "Aug", "실제": "162K", "이전": "21K", "예측치": "55K"},
            {"발표일": "2026-08-07", "참고": "Jul", "실제": "89K", "이전": "114K", "예측치": "175K"},
            {"발표일": "2026-07-03", "참고": "Jun", "실제": "114K", "이전": "218K", "예측치": "190K"}
        ])
    elif "FOMC" in title or "기자회견" in title or "통화정책" in title:
        return pd.DataFrame([
            {"발표일": "2026-07-29", "참고": "Jul", "실제": "5.50%", "이전": "5.50%", "예측치": "5.50%"},
            {"발표일": "2026-06-12", "참고": "Jun", "실제": "5.50%", "이전": "5.50%", "예측치": "5.50%"},
            {"발표일": "2026-05-01", "참고": "May", "실제": "5.50%", "이전": "5.50%", "예측치": "5.50%"}
        ])
    else:
        return pd.DataFrame([
            {"발표일": "2026-08-15", "참고": "Prior", "실제": "이전 발표", "이전": "직전 수치", "예측치": "시장 컨센서스"}
        ])

# 4. 탭 화면 구성
tab_home, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🏠 Home", "📈 Page 1: 주가지수", "💱 Page 2: 환율 & 원자재", 
    "Page 3: 상관관계", "Page 4: 미국 국채", "📊 Page 5: 반도체(D램)", 
    "📉 Page 6: 삼성전자 괴리율", "📅 Page 7: 금융 캘린더", "🚢 Page 8: 한국 수출데이터"
])

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
        max_annual_abs = full_df['연간수익'].drop(['average', '2000년이후', '2010년이후', '2020년이후', '상승확률'], errors='ignore').abs().max()
        if pd.isna(max_annual_abs) or max_annual_abs == 0: max_annual_abs = 40.0

        for row in full_df.index:
            for col in full_df.columns:
                val = full_df.loc[row, col]
                if pd.isna(val): continue
                formatted_str_df.loc[row, col] = f"{val:.1f}%"
                bg_color = ""
                if row == '상승확률':
                    intensity = min(abs(val - 50) / 50.0, 1.0) if pd.notna(val) else 0
                    bg_color = f'background-color: rgba(255, 99, 71, {intensity}); color: #000;' if val > 50 else f'background-color: rgba(100, 149, 237, {intensity}); color: #000;'
                else:
                    intensity = min(abs(val) / max_annual_abs if col == '연간수익' else abs(val) / 12.0, 1.0)
                    bg_color = f'background-color: rgba(255, 99, 71, {intensity}); color: #000;' if val > 0 else f'background-color: rgba(100, 149, 237, {intensity}); color: #000;'
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
<div class="heatmap-container">{html_table}</div>"""
        st.markdown(final_custom_css, unsafe_allow_html=True)

# ==========================================
# [Page 1] 주가지수 화면
# ==========================================
with tab1:
    st.subheader("글로벌 주요 주가지수 일반 지수 & MDD 추이")
    col_p1, col_s1 = st.columns([2, 1])
    with col_p1:
        period_option_1 = st.radio("조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "20년", "Max", "YTD"], index=0, horizontal=True, key="m_p1")
    with col_s1:
        scale_option_1 = st.radio("차트 축 스케일 선택:", ["선형 축 (Linear)", "로그 축 (Log)"], index=0, horizontal=True, key="m_s1")
    
    start_date_1 = get_start_date(period_option_1)
    market_data = get_market_data(start_date_1.strftime("%Y-%m-%d"))
    is_log_scale = "로그" in scale_option_1
    
    cols1 = st.columns(2)
    for idx, (name, df_m) in enumerate(market_data.items()):
        with cols1[idx % 2]:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df_m.index, y=df_m['Close'], name="지수", line=dict(width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df_m.index, y=df_m['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            latest_close = df_m['Close'].iloc[-1]
            latest_dd = df_m['DD'].iloc[-1]
            ytd_title_part = ""
            if period_option_1 == "YTD":
                ytd_val = ((latest_close / df_m['Close'].iloc[0]) - 1) * 100
                c_name = "red" if ytd_val >= 0 else "blue"
                ytd_title_part = f" | YTD: <span style='color:{c_name};'>{ytd_val:+.2f}%</span>"
            fig.update_layout(title=f"<b>{name}</b> ({latest_close:,.2f}) | DD: {latest_dd:+.2f}%{ytd_title_part}", margin=dict(l=20, r=20, t=40, b=20), height=300, showlegend=False)
            fig.update_yaxes(title_text="지수 (pt)", type="log" if is_log_scale else "linear", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=[-65, 2], secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 2] 환율 & 원자재 화면
# ==========================================
with tab2:
    st.subheader("주요 통화 환율, 달러 인덱스 및 WTI 원유 추이")
    period_option_2 = st.radio("조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "20년", "Max", "YTD"], index=5, horizontal=True, key="fx_p2")
    start_date_2 = get_start_date(period_option_2)
    fx_data_dict = get_fx_long_data(FX_TICKERS, start_date_2.strftime("%Y-%m-%d"))
    
    cols2 = st.columns(2)
    for idx, (name, df_fx) in enumerate(fx_data_dict.items()):
        with cols2[idx % 2]:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            line_color = '#b22222' if "WTI" in name else 'royalblue'
            dd_range = [-60, 5] if "WTI" in name else [-25, 2]
            fig.add_trace(go.Scatter(x=df_fx.index, y=df_fx['Close'], name="가격", line=dict(color=line_color, width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df_fx.index, y=df_fx['DD'], name="Drawdown %", line=dict(color='gray', width=1)), secondary_y=True)
            latest_val = df_fx['Close'].iloc[-1]
            latest_dd = df_fx['DD'].iloc[-1]
            ytd_title_part = ""
            if period_option_2 == "YTD":
                ytd_val = ((latest_val / df_fx['Close'].iloc[0]) - 1) * 100
                c_name = "red" if ytd_val >= 0 else "blue"
                ytd_title_part = f" | YTD: <span style='color:{c_name};'>{ytd_val:+.2f}%</span>"
            fig.update_layout(title=f"<b>{name}</b> ({latest_val:,.2f}) | DD: {latest_dd:+.2f}%{ytd_title_part}", margin=dict(l=20, r=20, t=40, b=20), height=330, showlegend=False)
            fig.update_yaxes(title_text="가격 / 지수", secondary_y=False)
            fig.update_yaxes(title_text="DD (%)", range=dd_range, secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 3] 매크로 상관관계
# ==========================================
with tab3:
    st.subheader("금리와 코스피 장기 추이")
    period_option_3 = st.radio("조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "20년", "Max", "YTD"], index=5, horizontal=True, key="macro_p3")
    start_date_3 = get_start_date(period_option_3)
    df_macro = get_macro_correlation_data(start_date_3.strftime("%Y-%m-%d"))
    
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
    selected_bond = st.radio("확인할 국채 만기를 선택하세요:", ["5년물", "10년물", "30년물"], horizontal=True)
    if selected_bond in bonds_data:
        df_selected = bonds_data[selected_bond]
        latest_yield = df_selected.iloc[-1]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_selected.index, y=df_selected.values, name=selected_bond, line=dict(color='#ff7f0e', width=2)))
        fig.update_layout(title=f"<b>미국 국채 {selected_bond} 금리</b> (현재: {latest_yield:.3f}%)", height=500, margin=dict(l=20, r=20, t=40, b=20), yaxis_title="수익률 (%)", xaxis_title="연도")
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# [Page 5] 반도체(D램) 가격 추이
# ==========================================
with tab5:
    st.subheader("💾 D램 현물 및 고정거래 가격 추이 (구글 시트 연동)")
    st.info("💡 구글 시트에 실실시간 연동된 D램 가격 및 변동성 데이터를 불러와 시각화합니다.")
    df_dram = get_dram_csv_data()
    if not df_dram.empty:
        st.dataframe(df_dram, use_container_width=True)
    else:
        st.warning("구글 시트 데이터를 불러오지 못했습니다.")

# ==========================================
# [Page 6] 삼성전자 괴리율 & 주가 음영 오버레이
# ==========================================
with tab6:
    st.subheader("📉 삼성전자 보통주 vs 우선주 주가 및 괴리율 구간 분석")
    st.markdown("월평균 괴리율 = (보통주 − 우선주) / 보통주 × 100. 배경 음영은 괴리율이 3%p 이상 좁혀진 주요 구간을 나타냅니다[cite: 1].")
    
    period_option_6 = st.radio("조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "20년", "Max", "YTD"], index=3, horizontal=True, key="samsung_p6")
    start_date_6 = get_start_date(period_option_6)
    df_samsung = get_samsung_disparity_data(start_date_6.strftime("%Y-%m-%d"))

    if not df_samsung.empty:
        # 공통 음영 구간 정의 (HTML 소스 기반)[cite: 1]
        episodes = [
            {"start": "2017-04-01", "end": "2018-02-28", "color": "rgba(34,197,94,0.25)"},   # rally (동반상승)
            {"start": "2018-05-01", "end": "2019-01-31", "color": "rgba(249,115,22,0.25)"},  # decline (동반하락)
            {"start": "2019-03-01", "end": "2020-06-30", "color": "rgba(34,197,94,0.25)"},   # rally
            {"start": "2020-09-01", "end": "2020-12-31", "color": "rgba(34,197,94,0.25)"},   # rally
            {"start": "2021-01-01", "end": "2021-08-31", "color": "rgba(249,115,22,0.25)"},  # decline
            {"start": "2023-11-01", "end": "2024-03-31", "color": "rgba(34,197,94,0.25)"},   # rally
            {"start": "2024-07-01", "end": "2024-11-30", "color": "rgba(249,115,22,0.25)"},  # decline
            {"start": "2026-03-01", "end": "2026-04-30", "color": "rgba(34,197,94,0.25)"},   # rally
            {"start": "2026-05-01", "end": "2026-09-30", "color": "rgba(249,115,22,0.25)"}    # decline
        ]

        # 1. 주가 차트 (보통주 vs 우선주)에 음영 오버레이 적용
        fig_price = go.Figure()
        for ep in episodes:
            fig_price.add_vrect(
                x0=ep["start"], x1=ep["end"],
                fillcolor=ep["color"], opacity=1.0,
                layer="below", line_width=0
            )
        fig_price.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Common'], name="보통주 (본주)", line=dict(color='#1f77b4', width=2)))
        fig_price.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Preferred'], name="우선주", line=dict(color='#ff7f0e', width=2)))
        
        latest_common = df_samsung['Common'].iloc[-1]
        latest_pref = df_samsung['Preferred'].iloc[-1]
        latest_disp = df_samsung['Disparity'].iloc[-1]

        fig_price.update_layout(
            title=f"<b>삼성전자 주가 추이 (보통주 vs 우선주) 및 좁혀짐 구간 음영</b> | 보통주: {latest_common:,.0f}원 | 우선주: {latest_pref:,.0f}원",
            margin=dict(l=20, r=20, t=40, b=20),
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        fig_price.update_yaxes(title_text="주가 (원)")
        st.plotly_chart(fig_price, use_container_width=True)

        # 2. 괴리율 차트에 음영 오버레이 적용
        fig_disp = go.Figure()
        for ep in episodes:
            fig_disp.add_vrect(
                x0=ep["start"], x1=ep["end"],
                fillcolor=ep["color"], opacity=1.0,
                layer="below", line_width=0
            )
        fig_disp.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Disparity'], name="괴리율 (%)", line=dict(color='#4f46e5', width=1.5, dash='dot')))
        fig_disp.update_layout(
            title=f"<b>삼성전자 괴리율 (%) 추이 및 좁혀짐 구간</b> | 현재 괴리율: {latest_disp:+.2f}%",
            margin=dict(l=20, r=20, t=40, b=20),
            height=350,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        fig_disp.update_yaxes(title_text="괴리율 (%)")
        st.plotly_chart(fig_disp, use_container_width=True)

        # 범례 설명 표시
        st.markdown("""
        <div style="display: flex; gap: 20px; font-size: 13px; margin-bottom: 20px; flex-wrap: wrap;">
          <div><span style="display:inline-block; width:14px; height:14px; background:rgba(34,197,94,0.35); border:1px solid rgba(21,128,61,0.5); border-radius:3px; vertical-align:middle; margin-right:6px;"></span><b>동반상승</b> — 우선주가 더 가파르게 상승하여 괴리율 축소[cite: 1]</div>
          <div><span style="display:inline-block; width:14px; height:14px; background:rgba(249,115,22,0.35); border:1px solid rgba(194,65,12,0.5); border-radius:3px; vertical-align:middle; margin-right:6px;"></span><b>동반하락</b> — 보통주가 더 가파르게 하락하여 괴리율 축소[cite: 1]</div>
        </div>
        """, unsafe_allow_html=True)

        # 페이지 맨 아래 괴리율 좁혀지는 구간대 분석 표 추가[cite: 1]
        st.markdown("### 📋 괴리율 좁혀짐 구간 상세 표[cite: 1]")
        st.markdown("""
        <style>
          .gap-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; background: white; border-radius: 8px; overflow: hidden; border: 1px solid #e7e5e4; }
          .gap-table th, .gap-table td { padding: 9px 12px; text-align: right; border-bottom: 1px solid #f0efed; }
          .gap-table th:first-child, .gap-table td:first-child { text-align: left; }
          .gap-table th { color: #78716c; font-weight: 600; font-size: 12px; background: #fafaf9; }
          .gap-table .up { color: #16a34a; font-weight: 600; }
          .gap-table .down { color: #ea580c; font-weight: 600; }
          .gap-table .tag { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 600; display: inline-block; }
          .gap-table .tag-rally { background: #dcfce7; color: #15803d; }
          .gap-table .tag-decline { background: #ffedd5; color: #c2410c; }
        </style>
        <table class="gap-table">
          <thead>
            <tr><th>구간</th><th>괴리율</th><th>보통주</th><th>우선주</th><th>유형</th></tr>
          </thead>
          <tbody>
            <tr><td>2017.04 → 2018.02</td><td>27.0%→19.6%</td><td class="up">+13.3%</td><td class="up">+24.8%</td><td><span class="tag tag-rally">동반상승·우선주 급등</span></td></tr>
            <tr><td>2018.05 → 2019.01</td><td>24.3%→18.9%</td><td class="down">-16.0%</td><td class="down">-10.0%</td><td><span class="tag tag-decline">동반하락·보통주 급락</span></td></tr>
            <tr><td>2019.03 → 2020.06</td><td>22.7%→13.3%</td><td class="up">+25.1%</td><td class="up">+40.4%</td><td><span class="tag tag-rally">동반상승·우선주 급등</span></td></tr>
            <tr><td>2020.09 → 2020.12</td><td>16.3%→8.1%</td><td class="up">+24.1%</td><td class="up">+36.3%</td><td><span class="tag tag-rally">동반상승·우선주 급등</span></td></tr>
            <tr><td>2021.01 → 2021.08</td><td>13.6%→8.3%</td><td class="down">-16.0%</td><td class="down">-10.9%</td><td><span class="tag tag-decline">동반하락·보통주 급락</span></td></tr>
            <tr><td>2023.11 → 2024.03</td><td>21.2%→15.0%</td><td class="up">+2.7%</td><td class="up">+10.8%</td><td><span class="tag tag-rally">동반상승·우선주 급등</span></td></tr>
            <tr><td>2024.07 → 2024.11</td><td>22.3%→15.1%</td><td class="down">-30.3%</td><td class="down">-23.8%</td><td><span class="tag tag-decline">동반하락·보통주 급락</span></td></tr>
            <tr><td>2026.03 → 2026.04</td><td>33.9%→28.0%</td><td class="up">+14.0%</td><td class="up">+24.2%</td><td><span class="tag tag-rally">동반상승·우선주 급등</span></td></tr>
            <tr><td>2026.05 → 2026.09*</td><td>36.2%→26.4%</td><td class="down">-14.9%</td><td class="down">-1.9%</td><td><span class="tag tag-decline">동반하락·보통주 급락</span></td></tr>
          </tbody>
        </table>
        <div style="font-size: 12px; color: #78716c; margin-top: 10px; line-height: 1.6; margin-bottom: 30px;">
          * 두 유형 모두 "괴리율 축소 = 우선주의 상대적 강세" 공통점이 있지만, 초록(동반상승)은 둘 다 오르는 국면에서 우선주가 더 빠르게 따라붙은 경우이고, 주황(동반하락)은 둘 다 빠지는 국면에서 보통주가 더 크게 무너진 경우입니다[cite: 1].
        </div>
        """, unsafe_allow_html=True)

        # 3. 괴리율 기간별 평균 (1, 3, 5, 10, 20년) 자동 계산 및 표시
        st.markdown("### 📈 괴리율 기간별 평균 추이")
        latest_idx = df_samsung.index[-1]
        
        avg_1y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=1), 'Disparity'].mean()
        avg_3y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=3), 'Disparity'].mean()
        avg_5y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=5), 'Disparity'].mean()
        avg_10y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=10), 'Disparity'].mean()
        avg_20y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=20), 'Disparity'].mean()

        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        col_m1.metric("1년 평균 괴리율", f"{avg_1y:.2f}%" if pd.notna(avg_1y) else "N/A")
        col_m2.metric("3년 평균 괴리율", f"{avg_3y:.2f}%" if pd.notna(avg_3y) else "N/A")
        col_m3.metric("5년 평균 괴리율", f"{avg_5y:.2f}%" if pd.notna(avg_5y) else "N/A")
        col_m4.metric("10년 평균 괴리율", f"{avg_10y:.2f}%" if pd.notna(avg_10y) else "N/A")
        col_m5.metric("20년 평균 괴리율", f"{avg_20y:.2f}%" if pd.notna(avg_20y) else "N/A")

    else:
        st.warning("삼성전자 주가 데이터를 불러오지 못했습니다.")

# ==========================================
# [Page 7] 금융 소식 캘린더 (TradingEconomics 스타일 고도화)
# ==========================================
with tab7:
    st.subheader("📅 미국 핵심 매크로 캘린더 & 지표별 과거 추이 (TradingEconomics 스타일)")
    st.markdown("""
    <style>
    .event-card { padding: 12px; border-radius: 6px; border: 1px solid #e0e0e0; margin-bottom: 8px; background-color: #fafafa; }
    @media (prefers-color-scheme: dark) { .event-card { background-color: #1e1e1e; border: 1px solid #333; } }
    </style>
    """, unsafe_allow_html=True)

    df_cal = get_auto_macro_calendar()

    col_cal_left, col_cal_right = st.columns([1.5, 1])

    with col_cal_left:
        st.markdown("### 🗓️ 전체 경제 일정 및 발표 결과")
        categories = ["전체", "통화정책", "물가", "고용", "경기실물"]
        selected_cat = st.selectbox("분류 필터:", options=categories, key="cal_filter")

        df_display = df_cal.copy()
        if selected_cat != "전체":
            df_display = df_display[df_display['Category'] == selected_cat]

        df_show = df_display[['Date', 'Category', 'Title', 'Actual', 'Previous', 'Forecast', 'D-day']].rename(
            columns={'Date': '날짜', 'Category': '분류', 'Title': '경제지표명', 'Actual': '실제', 'Previous': '이전', 'Forecast': '예측치'}
        )
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    with col_cal_right:
        st.markdown("### 📊 지표별 과거 발표 추이")
        past_events = df_cal[df_cal['D-day'] <= 0]['Title'].tolist()
        if past_events:
            selected_indicator = st.selectbox("조회할 경제지표 선택:", options=past_events, key="indicator_history_select")

            history_df = get_indicator_history(selected_indicator)
            st.markdown(f"**📌 [{selected_indicator}] 역사적 추이**")
            st.dataframe(history_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("### 🔥 다가오는 핵심 일정 (Key Events)")
            core_events = df_cal[(df_cal['IsCore'] == '핵심') & (df_cal['D-day'] >= 0)].sort_values('D-day').head(3)
            if not core_events.empty:
                for _, row in core_events.iterrows():
                    d_val = row['D-day']
                    d_str = "D-Day" if d_val == 0 else f"D-{d_val}"
                    d_color = "red" if d_val <= 3 else "blue"
                    card_html = f"""
                    <div class="event-card">
                        <b>[{row['Category']}] {row['Title']}</b><br>
                        <span style="color:gray; font-size:12px;">{row['Details']} ({row['Date']})</span><br>
                        <span style="color:{d_color}; font-size:11px; font-weight:bold;">{d_str}</span>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.info("조회할 과거 지표가 없습니다.")

# ==========================================
# [Page 8] 한국 수출입 데이터 (구글 시트 연동)
# ==========================================
with tab8:
    st.subheader("🚢 대한민국 수출입 데이터 시각화 (2000년 ~ 현재)")
    st.info("💡 구글 시트에 연동된 한국은행 ECOS 실시간 데이터를 바탕으로 수출 명목금액 및 전년 동월 대비 증가율(YoY)을 조회합니다.")

    csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT0NA7he4fhkC6nqjWqV5U6ls9Upj96NT_zYOlXeaHtJMifAJ39-T5lnZ8IPD2_WTYhrIP7iUrkhK7T/pub?gid=0&single=true&output=csv"

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(csv_url, headers=headers)
        if response.status_code == 200:
            df_export = pd.read_csv(io.StringIO(response.text))
        else:
            df_export = pd.DataFrame()
    except:
        df_export = pd.DataFrame()

    def parse_yy_mm(d):
        yy, mm = str(d).strip('.').split('.')
        return f"{2000 + int(yy)}-{int(mm):02d}"

    if not df_export.empty:
        df_export['수출액'] = pd.to_numeric(df_export['수출액'], errors='coerce')
        df_export['YoY(%)'] = pd.to_numeric(df_export['YoY(%)'], errors='coerce')

        view_mode = st.radio(
            "조회 지표를 선택하세요:",
            ["전년 동월 대비 증가율 (YoY %)", "수출 명목금액"],
            horizontal=True,
            key="export_view_mode"
        )

        df_table = df_export.copy()
        df_table['수출액'] = df_table['수출액'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
        df_table['YoY(%)'] = df_table['YoY(%)'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")

        st.dataframe(
            df_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn("Date", width="small"),
                "수출액": st.column_config.TextColumn("수출액 (천불)", width="small"),
                "YoY(%)": st.column_config.TextColumn("YoY (%)", width="small"),
            }
        )

        if 'Date' in df_export.columns:
            if view_mode == "전년 동월 대비 증가율 (YoY %)":
                df_chart = df_export.dropna(subset=['YoY(%)']).copy()
                df_chart['YearMonth'] = df_chart['Date'].apply(parse_yy_mm)

                kospi_df = get_kospi_monthly_data()
                merged = pd.merge(df_chart, kospi_df, on='YearMonth', how='inner')

                corr_value = merged['YoY(%)'].corr(merged['KOSPI']) if len(merged) > 1 else None
                corr_text = f" | 상관계수(2000~현재): {corr_value:.3f}" if corr_value is not None else ""

                colors = ['#1f77b4' if v >= 0 else '#ff7f0e' for v in merged['YoY(%)']]
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(
                    x=merged['Date'], y=merged['YoY(%)'], name='수출 YoY (%)',
                    marker_color=colors
                ), secondary_y=False)
                fig.add_trace(go.Scatter(
                    x=merged['Date'], y=merged['KOSPI'], name='코스피 지수',
                    line=dict(color='black', width=2)
                ), secondary_y=True)

                fig.update_layout(
                    title=f"<b>대한민국 월별 수출 증가율(YoY %) vs 코스피 지수</b>{corr_text}",
                    xaxis_title="기간 (YY.MM)",
                    height=450,
                    margin=dict(l=20, r=20, t=40, b=20),
                    bargap=0.1,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
                )
                fig.update_yaxes(title_text="수출 증가율 (%)", secondary_y=False)
                fig.update_yaxes(title_text="코스피 (pt)", tickformat=",", secondary_y=True)
                st.plotly_chart(fig, use_container_width=True)

            else:
                df_chart = df_export
                fig = go.Figure(data=[go.Bar(
                    x=df_chart['Date'],
                    y=df_chart['수출액'],
                    marker_color='#1f77b4',
                    hovertemplate="%{x}<br>수출액: %{y:,.0f} 천불<extra></extra>"
                )])
                fig.update_layout(
                    title="<b>대한민국 월별 수출 명목금액 (천불) - 2000년 이후</b>",
                    xaxis_title="기간 (YY.MM)",
                    yaxis_title="금액 (천불)",
                    height=450,
                    margin=dict(l=20, r=20, t=40, b=20),
                    bargap=0.1,
                )
                fig.update_yaxes(tickformat=",")
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("구글 시트 수출 데이터를 불러오지 못했습니다. '파일 -> 공유 -> 웹에 게시(CSV)' 링크를 확인해주세요.")
