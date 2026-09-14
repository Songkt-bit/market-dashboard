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

# ECOS(한국은행 경제통계시스템) Open API 설정
# 키는 코드에 직접 쓰지 않고 st.secrets로 읽습니다.
# 로컬: 프로젝트 루트에 .streamlit/secrets.toml 파일을 만들고
#   ECOS_API_KEY = "발급받은_인증키"
# 한 줄만 넣으면 됩니다. (.gitignore에 반드시 추가)
# Streamlit Community Cloud 배포 시에는 앱 Settings → Secrets에 동일하게 추가합니다.
ECOS_API_KEY = st.secrets.get("ECOS_API_KEY", "")
ECOS_BASE = "https://ecos.bok.or.kr/api"

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

# ===========================================================================
# ECOS(한국은행 경제통계시스템) Open API 연동 함수
# ===========================================================================

def _ecos_get(url: str) -> dict:
    """ECOS API 공통 호출 + 에러 응답(RESULT.CODE) 처리"""
    try:
        res = requests.get(url, timeout=15)
        data = res.json()
    except Exception as e:
        return {"_error": f"요청 실패: {e}"}
    if "RESULT" in data:
        # 인증키 오류(ERROR-1xx), 데이터 없음(INFO-200) 등
        msg = data["RESULT"].get("MESSAGE", "알 수 없는 오류")
        code = data["RESULT"].get("CODE", "")
        return {"_error": f"[{code}] {msg}"}
    return data


@st.cache_data(ttl=3600)
def get_ecos_key_statistics() -> pd.DataFrame:
    """
    100대 통계지표(KeyStatisticList) — 금리·환율·물가·경기·고용·국제수지 등
    '주요 카테고리 전체'를 통계표코드 하나하나 몰라도 한 번에 받아오는 API.
    한국은행이 분류해 둔 그룹(CLASS_NAME) 그대로 반환하므로, butler.works 대시보드의
    "그룹별 보기"와 거의 동일한 구조로 바로 붙일 수 있음.
    """
    if not ECOS_API_KEY:
        return pd.DataFrame()
    url = f"{ECOS_BASE}/KeyStatisticList/{ECOS_API_KEY}/json/kr/1/100"
    data = _ecos_get(url)
    if "_error" in data or "KeyStatisticList" not in data:
        return pd.DataFrame()
    rows = data["KeyStatisticList"]["row"]
    df = pd.DataFrame(rows).rename(columns={
        "CLASS_NAME": "그룹", "KEYSTAT_NAME": "지표명",
        "DATA_VALUE": "값", "CYCLE": "시점", "UNIT_NAME": "단위",
    })
    df["값"] = pd.to_numeric(df["값"], errors="coerce")
    return df


@st.cache_data(ttl=86400)
def search_ecos_stat_table(keyword: str) -> pd.DataFrame:
    """
    통계표코드 검색(StatisticTableList) — 전체 통계표 목록(약 1,000여 개)을 받아
    이름에 keyword가 들어간 것만 걸러줌. 100대 지표에 없는 세부 지표(예: 선행지수
    순환변동치의 원계열, 특정 만기 국고채 등)를 찾을 때 사용.
    SRCH_YN == 'Y' 인 것만 남기는데, 이게 실제로 StatisticSearch로 시계열을
    조회할 수 있는 '말단' 통계표라는 뜻.
    """
    if not ECOS_API_KEY or not keyword:
        return pd.DataFrame()
    url = f"{ECOS_BASE}/StatisticTableList/{ECOS_API_KEY}/json/kr/1/3000"
    data = _ecos_get(url)
    if "_error" in data or "StatisticTableList" not in data:
        return pd.DataFrame()
    df = pd.DataFrame(data["StatisticTableList"]["row"])
    if df.empty or "STAT_NAME" not in df.columns:
        return pd.DataFrame()
    df = df[df["STAT_NAME"].str.contains(keyword, na=False, regex=False)]
    if "SRCH_YN" in df.columns:
        df = df[df["SRCH_YN"] == "Y"]
    return df[["STAT_CODE", "STAT_NAME", "CYCLE", "ORG_NAME"]].reset_index(drop=True)


@st.cache_data(ttl=86400)
def get_ecos_item_list(stat_code: str) -> pd.DataFrame:
    """통계 세부항목 목록(StatisticItemList) — 특정 통계표코드 안의 세부 항목들"""
    if not ECOS_API_KEY or not stat_code:
        return pd.DataFrame()
    url = f"{ECOS_BASE}/StatisticItemList/{ECOS_API_KEY}/json/kr/1/1000/{stat_code}"
    data = _ecos_get(url)
    if "_error" in data or "StatisticItemList" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["StatisticItemList"]["row"])


def _fmt_ecos_date(d: datetime.date, cycle: str) -> str:
    """date 객체를 주기(cycle)에 맞는 ECOS 날짜 문자열로 변환"""
    if cycle == "A":
        return f"{d.year}"
    if cycle == "Q":
        return f"{d.year}Q{(d.month - 1)//3 + 1}"
    if cycle == "M":
        return f"{d.year}{d.month:02d}"
    if cycle == "D":
        return f"{d.year}{d.month:02d}{d.day:02d}"
    return f"{d.year}{d.month:02d}"  # 기본값(월)


@st.cache_data(ttl=3600)
def get_ecos_series(stat_code: str, cycle: str, start: str, end: str,
                     item_code1: str = "", item_code2: str = "") -> pd.DataFrame:
    """
    통계 조회(StatisticSearch) — 실제 시계열 데이터.
    start/end는 이미 주기에 맞게 포맷된 문자열(예: "20200101", "202501", "2025Q1")이어야 함.
    """
    if not ECOS_API_KEY or not stat_code:
        return pd.DataFrame()
    parts = [ECOS_BASE, "StatisticSearch", ECOS_API_KEY, "json", "kr",
              "1", "100000", stat_code, cycle, start, end]
    if item_code1:
        parts.append(item_code1)
    if item_code2:
        parts.append(item_code2)
    url = "/".join(parts)
    data = _ecos_get(url)
    if "_error" in data or "StatisticSearch" not in data:
        return pd.DataFrame()
    df = pd.DataFrame(data["StatisticSearch"]["row"])
    if df.empty:
        return df
    df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    return df


# 4. 탭 화면 구성
tab_home, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🏠 Home", "📈 Page 1: 주가지수", "💱 Page 2: 환율 & 원자재",
    "Page 3: 상관관계", "Page 4: 미국 국채", "📊 Page 5: 반도체(D램)",
    "📉 Page 6: 삼성전자 괴리율", "🚢 Page 7: 한국 수출데이터",
    "🏦 Page 8: ECOS 매크로 지표"
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
    st.info("💡 구글 시트에 실시간 연동된 D램 가격 및 변동성 데이터를 불러와 시각화합니다.")
    df_dram = get_dram_csv_data()
    if not df_dram.empty:
        # 시트의 실제 컬럼 구성(DDR4/DDR5 등 종류, 변동성 컬럼 개수)을 코드가 미리 알 수 없으므로,
        # 첫 컬럼을 날짜/구간 축으로 보고 나머지 숫자형 컬럼들을 자동으로 시리즈로 인식해서 그림.
        # ('변동' 이 들어간 컬럼명은 변동성으로 보고 보조축 + 점선으로 구분)
        date_col = df_dram.columns[0]
        value_cols = []
        for c in df_dram.columns[1:]:
            numeric = pd.to_numeric(df_dram[c], errors='coerce')
            if numeric.notna().sum() >= max(3, len(df_dram) * 0.3):
                value_cols.append(c)

        if value_cols:
            x_axis = pd.to_datetime(df_dram[date_col], errors='coerce')
            if x_axis.isna().all():
                x_axis = df_dram[date_col]

            vol_cols = [c for c in value_cols if '변동' in c]
            price_cols = [c for c in value_cols if c not in vol_cols]

            selected_cols = st.multiselect(
                "표시할 항목 선택 (DDR 종류/가격 유형별로 켜고 끌 수 있어요):",
                options=value_cols, default=price_cols or value_cols,
                key="dram_series_select"
            )

            palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                       '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            for i, col in enumerate(selected_cols):
                y_vals = pd.to_numeric(df_dram[col], errors='coerce')
                is_vol = col in vol_cols
                fig.add_trace(
                    go.Scatter(
                        x=x_axis, y=y_vals, name=col, mode='lines',
                        line=dict(color=palette[i % len(palette)], width=2, dash='dot' if is_vol else 'solid'),
                    ),
                    secondary_y=is_vol
                )
            fig.update_layout(
                title="<b>D램 가격/변동성 추이</b>",
                height=480, margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
            )
            fig.update_yaxes(title_text="가격", secondary_y=False)
            if vol_cols:
                fig.update_yaxes(title_text="변동성", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("숫자형 데이터 컬럼을 자동으로 인식하지 못했습니다. 아래 원본 표를 확인해주세요.")

        st.dataframe(df_dram, use_container_width=True)
    else:
        st.warning("구글 시트 데이터를 불러오지 못했습니다.")

# ==========================================
# [Page 6] 삼성전자 주가 & 괴리율 통합 차트 (음영 오버레이 완벽 복원)
# ==========================================
with tab6:
    st.subheader("📉 삼성전자 보통주 vs 우선주 주가 및 괴리율 통합 차트")
    st.markdown("월평균 괴리율 = (보통주 − 우선주) / 보통주 × 100. 차트 배경 음영은 괴리율이 3%p 이상 좁혀진 주요 구간을 나타냅니다.")

    period_option_6 = st.radio("조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "20년", "Max", "YTD"], index=3, horizontal=True, key="samsung_p6")
    start_date_6 = get_start_date(period_option_6)
    df_samsung = get_samsung_disparity_data(start_date_6.strftime("%Y-%m-%d"))

    if not df_samsung.empty:
        # 공통 음영 구간 정의 (HTML 소스 기반)
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

        # 단일 차트에 주가(좌측 축)와 괴리율(우측 축) 통합 오버레이 (xref="x", yref="paper" 적용으로 음영 정상 출력)
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        for ep in episodes:
            fig.add_vrect(
                x0=ep["start"], x1=ep["end"],
                fillcolor=ep["color"], opacity=1.0,
                layer="below", line_width=0,
                xref="x", yref="paper", y0=0, y1=1
            )

        fig.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Common'], name="보통주 (본주)", line=dict(color='#1f77b4', width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Preferred'], name="우선주", line=dict(color='#ff7f0e', width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_samsung.index, y=df_samsung['Disparity'], name="괴리율 (%)", line=dict(color='#4f46e5', width=1.5, dash='dot')), secondary_y=True)

        latest_common = df_samsung['Common'].iloc[-1]
        latest_pref = df_samsung['Preferred'].iloc[-1]
        latest_disp = df_samsung['Disparity'].iloc[-1]

        fig.update_layout(
            title=f"<b>삼성전자 주가 및 괴리율 통합 추이</b> | 보통주: {latest_common:,.0f}원 | 우선주: {latest_pref:,.0f}원 | 괴리율: {latest_disp:+.2f}%",
            margin=dict(l=20, r=20, t=40, b=20),
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        fig.update_xaxes(matches='x')
        fig.update_yaxes(title_text="주가 (원)", secondary_y=False)
        fig.update_yaxes(title_text="괴리율 (%)", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

        # 범례 설명 표시
        st.markdown("""
        <div style="display: flex; gap: 20px; font-size: 13px; margin-bottom: 20px; flex-wrap: wrap;">
          <div><span style="display:inline-block; width:14px; height:14px; background:rgba(34,197,94,0.35); border:1px solid rgba(21,128,61,0.5); border-radius:3px; vertical-align:middle; margin-right:6px;"></span><b>동반상승</b> — 우선주가 더 가파르게 상승하여 괴리율 축소</div>
          <div><span style="display:inline-block; width:14px; height:14px; background:rgba(249,115,22,0.35); border:1px solid rgba(194,65,12,0.5); border-radius:3px; vertical-align:middle; margin-right:6px;"></span><b>동반하락</b> — 보통주가 더 가파르게 하락하여 괴리율 축소</div>
        </div>
        """, unsafe_allow_html=True)

        # 괴리율 좁혀지는 구간대 분석 표 추가
        st.markdown("### 📋 괴리율 좁혀짐 구간 상세 표")
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
          * 두 유형 모두 "괴리율 축소 = 우선주의 상대적 강세" 공통점이 있지만, 초록(동반상승)은 둘 다 오르는 국면에서 우선주가 더 빠르게 따라붙은 경우이고, 주황(동반하락)은 둘 다 빠지는 국면에서 보통주가 더 크게 무너진 경우입니다.
        </div>
        """, unsafe_allow_html=True)

        # 괴리율 기간별 평균 ([ 괴리율 X년 평균 ] 형태 적용)
        st.markdown("### 📈 괴리율 기간별 평균 추이")
        latest_idx = df_samsung.index[-1]

        avg_1y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=1), 'Disparity'].mean()
        avg_3y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=3), 'Disparity'].mean()
        avg_5y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=5), 'Disparity'].mean()
        avg_10y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=10), 'Disparity'].mean()
        avg_20y = df_samsung.loc[df_samsung.index >= latest_idx - pd.DateOffset(years=20), 'Disparity'].mean()

        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        col_m1.metric("괴리율 1년 평균", f"{avg_1y:.2f}%" if pd.notna(avg_1y) else "N/A")
        col_m2.metric("괴리율 3년 평균", f"{avg_3y:.2f}%" if pd.notna(avg_3y) else "N/A")
        col_m3.metric("괴리율 5년 평균", f"{avg_5y:.2f}%" if pd.notna(avg_5y) else "N/A")
        col_m4.metric("괴리율 10년 평균", f"{avg_10y:.2f}%" if pd.notna(avg_10y) else "N/A")
        col_m5.metric("괴리율 20년 평균", f"{avg_20y:.2f}%" if pd.notna(avg_20y) else "N/A")

    else:
        st.warning("삼성전자 주가 데이터를 불러오지 못했습니다.")

# ==========================================
# [Page 7] 한국 수출입 데이터 (구글 시트 연동)
# ==========================================
with tab7:
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

        if 'Date' in df_export.columns:
            if view_mode == "전년 동월 대비 증가율 (YoY %)":
                df_chart = df_export.dropna(subset=['YoY(%)']).copy()
                df_chart['YearMonth'] = df_chart['Date'].apply(parse_yy_mm)

                kospi_df = get_kospi_monthly_data()
                merged = pd.merge(df_chart, kospi_df, on='YearMonth', how='inner')

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
                    title="<b>대한민국 월별 수출 증가율(YoY %) vs 코스피 지수</b>",
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

# ==========================================
# [Page 8] ECOS 매크로 지표 (한국은행 Open API)
# ==========================================
with tab8:
    st.subheader("🏦 ECOS 매크로 지표 (한국은행 Open API)")

    if not ECOS_API_KEY:
        st.error(
            "ECOS_API_KEY가 설정되어 있지 않습니다. "
            ".streamlit/secrets.toml (로컬) 또는 앱 Settings → Secrets(클라우드 배포 시)에 "
            'ECOS_API_KEY = "발급받은 키" 를 추가해주세요.'
        )
    else:
        sub_summary, sub_explorer = st.tabs(["📋 100대 통계지표 요약", "🔍 지표 탐색기 (임의 통계표 조회)"])

        # -----------------------------------------------------------------
        # 100대 통계지표 요약 — butler.works의 "지금 주목" + "그룹별 보기"에 대응
        # -----------------------------------------------------------------
        with sub_summary:
            df_key = get_ecos_key_statistics()
            if df_key.empty:
                st.warning("데이터를 불러오지 못했습니다. API 키 또는 네트워크 상태를 확인해주세요.")
            else:
                st.caption(f"한국은행 ECOS '100대 통계지표' 기준 · 총 {len(df_key)}개 항목")

                # 지금 주목: 관심 키워드로 자동 매칭 (통계표코드를 몰라도 이름으로 찾음)
                st.markdown("#### 지금 주목")
                watch_keywords = [
                    "한국은행 기준금리", "국고채", "회사채", "원/달러", "소비자물가",
                    "실업률", "경상수지", "경제성장률", "소비자심리", "지니계수",
                ]
                cols = st.columns(5)
                for i, kw in enumerate(watch_keywords):
                    hit = df_key[df_key["지표명"].str.contains(kw, na=False, regex=False)]
                    with cols[i % 5]:
                        if not hit.empty:
                            row = hit.iloc[0]
                            st.metric(row["지표명"], f"{row['값']:,.2f} {row['단위']}", help=f"기준시점 {row['시점']}")
                        else:
                            st.metric(kw, "—", help="100대 지표에 없음 → 탐색기 탭에서 검색")

                st.divider()
                st.markdown("#### 그룹별 보기")
                for grp, sub in df_key.groupby("그룹"):
                    with st.expander(f"{grp} ({len(sub)}종)"):
                        st.dataframe(
                            sub[["지표명", "값", "단위", "시점"]],
                            use_container_width=True, hide_index=True,
                        )

        # -----------------------------------------------------------------
        # 지표 탐색기 — 100대 지표에 없는 세부 시계열을 직접 찾아 차트로
        # -----------------------------------------------------------------
        with sub_explorer:
            st.markdown("이름으로 통계표를 검색하고, 원하는 항목의 과거 시계열을 바로 차트로 확인합니다.")
            keyword = st.text_input("통계표 이름 검색 (예: 국고채, 소비자심리, 선행지수, 가계신용)", "")

            if keyword:
                df_tables = search_ecos_stat_table(keyword)
                if df_tables.empty:
                    st.info("검색 결과가 없습니다. 다른 키워드로 시도해보세요.")
                else:
                    table_label = df_tables.apply(
                        lambda r: f"[{r['STAT_CODE']}] {r['STAT_NAME']} ({r['CYCLE']}, {r['ORG_NAME']})", axis=1
                    )
                    sel_idx = st.selectbox(
                        "통계표 선택:", options=range(len(df_tables)),
                        format_func=lambda i: table_label.iloc[i],
                    )
                    stat_code = df_tables.iloc[sel_idx]["STAT_CODE"]

                    df_items = get_ecos_item_list(stat_code)
                    item_code1 = ""
                    cycle = df_tables.iloc[sel_idx]["CYCLE"]
                    if not df_items.empty and "ITEM_CODE" in df_items.columns:
                        item_label = df_items.apply(
                            lambda r: f"{r['ITEM_NAME']} ({r.get('START_TIME','')}~{r.get('END_TIME','')})", axis=1
                        )
                        item_idx = st.selectbox(
                            "세부 항목 선택:", options=range(len(df_items)),
                            format_func=lambda i: item_label.iloc[i],
                        )
                        item_code1 = df_items.iloc[item_idx]["ITEM_CODE"]
                        cycle = df_items.iloc[item_idx].get("CYCLE", cycle)

                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        start_date = st.date_input("시작일", datetime.date(2015, 1, 1), key="ecos_start")
                    with col_d2:
                        end_date = st.date_input("종료일", datetime.date.today(), key="ecos_end")

                    if st.button("조회하기", type="primary"):
                        start_str = _fmt_ecos_date(start_date, cycle)
                        end_str = _fmt_ecos_date(end_date, cycle)
                        df_series = get_ecos_series(stat_code, cycle, start_str, end_str, item_code1)

                        if df_series.empty:
                            st.warning("조회된 데이터가 없습니다. 기간이나 항목을 다시 확인해주세요.")
                        else:
                            latest = df_series.iloc[-1]
                            unit_val = df_series["UNIT_NAME"].iloc[0] if "UNIT_NAME" in df_series.columns else ""
                            st.metric(
                                df_series["STAT_NAME"].iloc[0] if "STAT_NAME" in df_series.columns else stat_code,
                                f"{latest['DATA_VALUE']:,.2f} {unit_val}",
                                help=f"시점: {latest['TIME']}",
                            )
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=df_series["TIME"], y=df_series["DATA_VALUE"],
                                mode="lines", line=dict(color="#4f46e5", width=2),
                            ))
                            fig.update_layout(height=420, margin=dict(l=20, r=20, t=30, b=20))
                            st.plotly_chart(fig, use_container_width=True)
                            st.dataframe(df_series[["TIME", "DATA_VALUE"]], use_container_width=True, hide_index=True)
