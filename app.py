import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import requests
import io
import json
import os

# pykrx는 코스피 종목 리스트/시세 조회(Page 10)에만 필요한 선택적 의존성입니다.
# requirements.txt에 pykrx가 없으면 여기서 조용히 꺼두고, 해당 탭에서만 안내 메시지를 띄웁니다.
try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False

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

def parse_dram_pct_change(s):
    """구글 시트의 'Avg Change'/'Low Change' 컬럼(예: '▲13.04 %', '▼2.10 %')을 부호 있는 float로 변환"""
    if pd.isna(s):
        return None
    s = str(s).strip()
    sign = -1 if ('▼' in s or s.startswith('-')) else 1
    num = ''.join(ch for ch in s if (ch.isdigit() or ch == '.'))
    if not num:
        return None
    try:
        return sign * float(num)
    except ValueError:
        return None


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


# ---------------------------------------------------------------------------
# ECOS 즐겨찾기 (지금 주목에 표시할 지표 최대 10개)
# ---------------------------------------------------------------------------
# 처음엔 즐겨찾기한 지표마다 통계표코드를 직접 매핑해서 우리 차트에 스파크라인을
# 그리려 했는데, 지표 하나하나 검색→선택→확인하는 과정이 너무 번거로웠음.
# 대신 한국은행이 이미 만들어둔 '금융·경제 스냅샷'(snapshot.bok.or.kr) 공식
# 차트로 바로 연결하는 쪽으로 바꿈 — 다만 이 사이트는 완전한 JS 앱이라 지표명으로
# 특정 차트에 URL 하나로 바로 딥링크하는 공식 방법은 확인되지 않았고, 그래서
# 지표명을 복사해서 그 사이트 검색창에 붙여넣는 방식으로 감. 이러면 통계표코드를
# 몰라도 되고, 우리가 관리해야 할 매핑도 없어서 훨씬 가볍고 안정적임.
# 즐겨찾기 자체는 로컬 JSON 파일에 지표명만 저장 — 앱을 재배포하면 초기화될 수 있음.
ECOS_FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ecos_favorites.json")
ECOS_FAVORITES_MAX = 10
ECOS_SNAPSHOT_URL = "https://snapshot.bok.or.kr/bookmark/"


def load_ecos_favorites() -> list:
    """즐겨찾기한 지표명 리스트. (예전 버전엔 통계표코드 매핑 dict를 저장했었는데,
    그 키만 그대로 가져와서 이름 리스트로 마이그레이션함)"""
    if os.path.exists(ECOS_FAVORITES_FILE):
        try:
            with open(ECOS_FAVORITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return list(data.keys())
            if isinstance(data, list):
                return data
        except Exception:
            return []
    return []


def save_ecos_favorites(favs: list):
    try:
        with open(ECOS_FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def guess_ecos_cycle_label(time_str) -> str:
    """KeyStatisticList의 '시점' 문자열(예: 20230315, 202003, 2023Q1, 2023)로 주기 뱃지 추정"""
    s = str(time_str).upper()
    if "Q" in s:
        return "분기"
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return "일"
    if len(digits) == 6:
        return "월"
    if len(digits) == 4:
        return "년"
    return "-"


# ===========================================================================
# CNN Fear & Greed Index 연동 함수
# ===========================================================================
# CNN이 공식적으로 공개한 API는 아니고, cnn.com/markets/fear-and-greed 페이지가
# 내부적으로 호출하는 엔드포인트를 그대로 쓰는 방식입니다. (다수의 오픈소스
# 트래커/패키지가 동일하게 사용 중인, 잘 알려진 방식이지만 CNN이 구조를 바꾸면
# 예고 없이 깨질 수 있다는 점은 감안해주세요.)
#
# 이 엔드포인트는 현재 스코어뿐 아니라 "전일/1주일 전/1개월 전/1년 전" 값과
# 2011년부터의 일별 히스토리를 한 번에 돌려주기 때문에, 우리가 매일 따로
# 값을 수집/저장하지 않아도 히스토리 추적이 가능합니다.
FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
FNG_EARLIEST_DATE = "2011-01-03"  # CNN이 제공하는 히스토리 시작 시점

FNG_RATING_KR = {
    "extreme fear": "극단적 공포", "fear": "공포", "neutral": "중립",
    "greed": "탐욕", "extreme greed": "극단적 탐욕",
}
FNG_RATING_COLOR = {
    "extreme fear": "#b23b3b", "fear": "#e07b39", "neutral": "#e8c547",
    "greed": "#93c47d", "extreme greed": "#3f9142",
}


def _fng_score_to_rating(score):
    """previous_close 등에는 등급 문자열이 따로 없어서, 점수 구간으로 역산"""
    if score is None or pd.isna(score):
        return None, "#999"
    if score < 25: return "extreme fear", FNG_RATING_COLOR["extreme fear"]
    if score < 45: return "fear", FNG_RATING_COLOR["fear"]
    if score < 55: return "neutral", FNG_RATING_COLOR["neutral"]
    if score < 75: return "greed", FNG_RATING_COLOR["greed"]
    return "extreme greed", FNG_RATING_COLOR["extreme greed"]


FNG_CHUNK_YEARS = 3  # 한 번의 호출에 너무 오래된 시작일(예: 2011년)을 넣으면 CNN이
# 조용히 실패하거나 최근 구간만 담아 응답하는 것으로 보여서(다른 오픈소스 트래커들은
# 4년 안팎의 단일 호출은 문제없이 받아온다고 보고함), 그보다 짧게 몇 년 단위로 나눠
# 여러 번 호출한 뒤 하나로 합치는 방식으로 커버리지를 최대한 확보합니다.


def _fng_fetch_one(url: str, headers: dict):
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.json(), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600)
def get_fear_greed_data(earliest_date_str: str = FNG_EARLIEST_DATE):
    """
    CNN Fear & Greed Index 현재값 + 일별 히스토리를 가져옵니다.
    반환값: (current_dict, history_df, diagnostics_dict)
    diagnostics_dict = {"error": str|None, "chunks_ok": int, "chunks_total": int}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }

    today = datetime.date.today()
    earliest = datetime.date.fromisoformat(earliest_date_str)

    # earliest_date_str부터 오늘까지 FNG_CHUNK_YEARS 단위로 시작일을 잘라 목록 생성
    chunk_starts = []
    cursor = earliest
    while cursor < today:
        chunk_starts.append(cursor)
        cursor = cursor + datetime.timedelta(days=365 * FNG_CHUNK_YEARS)
    # 날짜 없이 호출하는 기본 경로도 마지막에 하나 추가 — 가장 최신 값/최근 데이터를 보장
    urls = [f"{FNG_URL}/{d.strftime('%Y-%m-%d')}" for d in chunk_starts] + [FNG_URL]

    all_points = []
    current = {}
    chunks_ok = 0
    last_err = None

    for url in urls:
        payload, err = _fng_fetch_one(url, headers)
        if payload is None:
            last_err = err
            continue
        chunks_ok += 1
        # 매 호출의 fear_and_greed(현재값)는 항상 "오늘" 기준값이라, 성공한 것 중
        # 가장 마지막(=가장 최신 구간) 응답 값으로 덮어써도 무방합니다.
        if payload.get("fear_and_greed"):
            current = payload["fear_and_greed"]
        pts = (payload.get("fear_and_greed_historical", {}) or {}).get("data", [])
        all_points.extend(pts)

    diagnostics = {
        "error": None if chunks_ok else last_err,
        "chunks_ok": chunks_ok,
        "chunks_total": len(urls),
    }

    if not all_points:
        return (current or None), pd.DataFrame(), diagnostics

    df_hist = pd.DataFrame(all_points).rename(columns={"x": "Timestamp", "y": "Score", "rating": "Rating"})
    df_hist["Date"] = pd.to_datetime(df_hist["Timestamp"], unit="ms").dt.normalize()
    df_hist = df_hist[["Date", "Score", "Rating"]].dropna(subset=["Score"])
    # 여러 구간을 이어붙이면서 겹치는 날짜가 생길 수 있어 중복 제거
    df_hist = df_hist.drop_duplicates(subset="Date").sort_values("Date").set_index("Date")
    return (current or None), df_hist, diagnostics


def render_fng_gauge(score: float):
    """CNN 사이트의 반원형 게이지를 Plotly Indicator로 재현"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={'font': {'size': 44}, 'valueformat': '.0f'},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickvals': [0, 25, 45, 55, 75, 100]},
            'bar': {'color': "rgba(0,0,0,0)"},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 25], 'color': FNG_RATING_COLOR["extreme fear"]},
                {'range': [25, 45], 'color': FNG_RATING_COLOR["fear"]},
                {'range': [45, 55], 'color': FNG_RATING_COLOR["neutral"]},
                {'range': [55, 75], 'color': FNG_RATING_COLOR["greed"]},
                {'range': [75, 100], 'color': FNG_RATING_COLOR["extreme greed"]},
            ],
            'threshold': {'line': {'color': "black", 'width': 5}, 'thickness': 0.85, 'value': score}
        }
    ))
    fig.update_layout(height=300, margin=dict(l=30, r=30, t=30, b=10))
    return fig


def _fng_panel_row(label: str, value):
    """오른쪽 패널의 '전일 종가 / 1주일 전 / 1개월 전 / 1년 전' 한 줄"""
    if value is None or pd.isna(value):
        return f"""<div style="display:flex; justify-content:space-between; padding:10px 0;
                    border-bottom:1px solid #eee; color:#aaa;">
                    <span>{label}</span><span>N/A</span></div>"""
    rating, color = _fng_score_to_rating(value)
    rating_kr = FNG_RATING_KR.get(rating, rating or "-")
    return f"""
    <div style="display:flex; justify-content:space-between; align-items:center;
                padding:10px 0; border-bottom:1px solid #eee;">
        <span style="color:#666; font-size:14px;">{label}</span>
        <span style="display:flex; align-items:center; gap:8px;">
            <span style="color:{color}; font-weight:600; font-size:14px;">{rating_kr}</span>
            <span style="background:{color}; color:white; border-radius:50%;
                         display:inline-block; width:30px; height:30px; line-height:30px;
                         text-align:center; font-weight:700; font-size:13px;">{value:.0f}</span>
        </span>
    </div>"""


# ---------------------------------------------------------------------------
# 홈 화면 메모장 (생각날 때마다 하나씩 적어두는 용도)
# ---------------------------------------------------------------------------
# ECOS 즐겨찾기와 같은 방식으로 로컬 JSON 파일에 저장합니다. 앱이 켜져 있는 동안은
# 유지되지만, Streamlit Cloud는 코드를 새로 배포하면 파일시스템이 초기화되니
# 오래 보관해야 할 메모는 가끔 내용을 따로 복사해두는 걸 권장합니다.
MEMO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "home_memos.json")


def load_memos() -> list:
    if os.path.exists(MEMO_FILE):
        try:
            with open(MEMO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            return []
    return []


def save_memos(memos: list):
    try:
        with open(MEMO_FILE, "w", encoding="utf-8") as f:
            json.dump(memos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ===========================================================================
# Page 10: 50일 이동평균선 상회 종목 비율 (Market Breadth)
# ===========================================================================
# "전체 종목 중 종가가 50일 이동평균선 위에 있는 종목의 비율" — 시장 과매수/과매도를
# 가늠하는 대표적인 breadth(시장 호흡) 지표입니다 (스크린샷의 $NYA50R과 같은 개념).
# - S&P500: 위키피디아의 현재 편입종목 리스트 + yfinance 일괄 다운로드로 계산
# - 코스피: pykrx로 코스피200 구성종목 시세를 받아 계산 (전체 코스피보다 가벼움)
# * "현재" 편입종목 리스트를 과거 전체 기간에 그대로 적용하기 때문에 생존편향
#   (survivorship bias)이 있는 단순화된 지표입니다 — 실무에서도 보통 감안하고 씁니다.
# * 500~200개 종목 x 수년치 일별 데이터를 받아오는 작업이라 최초 로딩이 오래 걸릴 수
#   있어서(수십 초~수 분) 하루 단위(ttl=86400)로 캐싱하고, 조회 기간은 최대 10년으로
#   제한해 최초 백필 비용을 억제합니다.
BREADTH_MAX_YEARS = 10
BREADTH_SMA_WINDOW = 50


@st.cache_data(ttl=86400)
def get_sp500_tickers() -> list:
    """위키피디아 S&P500 편입종목 리스트. 야후 파이낸스 형식에 맞춰 '.'을 '-'로 치환(예: BRK.B -> BRK-B)."""
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return sorted(set(tickers))
    except Exception:
        return []


@st.cache_data(ttl=86400)
def get_kospi200_tickers() -> list:
    """코스피200 구성종목 코드 리스트 (pykrx, 6자리 코드)."""
    if not PYKRX_AVAILABLE:
        return []
    for date_arg in (datetime.date.today().strftime("%Y%m%d"), None):
        try:
            codes = pykrx_stock.get_index_portfolio_deposit_file("1028", date_arg) if date_arg \
                else pykrx_stock.get_index_portfolio_deposit_file("1028")
            if codes:
                return sorted(set(codes))
        except Exception:
            continue
    return []


@st.cache_data(ttl=86400, show_spinner="S&P500 약 500개 종목 데이터를 불러오는 중입니다 (최초 로딩은 1~2분 정도 걸릴 수 있어요)...")
def get_sp500_breadth_data(years: int = BREADTH_MAX_YEARS):
    """
    S&P500 종목별 종가를 받아 50일선 상회 비율(%)의 일별 시계열을 계산합니다.
    반환: (breadth_series, coverage_dict)  coverage_dict = {"ok": 성공 종목 수, "total": 전체 종목 수}
    """
    tickers = get_sp500_tickers()
    if not tickers:
        return pd.Series(dtype=float), {"ok": 0, "total": 0}

    start = datetime.date.today() - datetime.timedelta(days=365 * years + 90)
    try:
        raw = yf.download(tickers, start=start.strftime("%Y-%m-%d"), progress=False,
                           group_by="ticker", threads=True)
    except Exception:
        return pd.Series(dtype=float), {"ok": 0, "total": len(tickers)}

    above_frames = []
    ok = 0
    for t in tickers:
        try:
            close = raw[t]["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
        except Exception:
            continue
        close = close.dropna()
        if len(close) < BREADTH_SMA_WINDOW + 5:
            continue
        sma50 = close.rolling(BREADTH_SMA_WINDOW).mean()
        # sma50이 NaN인 구간(워밍업 기간)은 "50일선 아래"가 아니라 "판단 불가"이므로
        # False가 아닌 NaN으로 남겨서 평균 계산(skipna) 시 그 날짜의 분모에서 빠지게 함
        above = (close > sma50).where(sma50.notna())
        above_frames.append(above.rename(t))
        ok += 1

    if not above_frames:
        return pd.Series(dtype=float), {"ok": 0, "total": len(tickers)}

    above_df = pd.concat(above_frames, axis=1)
    breadth = (above_df.mean(axis=1, skipna=True) * 100).dropna()
    breadth.index = pd.to_datetime(breadth.index)
    return breadth, {"ok": ok, "total": len(tickers)}


@st.cache_data(ttl=86400, show_spinner="코스피200 종목 데이터를 불러오는 중입니다 (최초 로딩은 몇 분 정도 걸릴 수 있어요)...")
def get_kospi200_breadth_data(years: int = BREADTH_MAX_YEARS):
    """코스피200 종목별 종가를 pykrx로 받아 50일선 상회 비율(%)의 일별 시계열을 계산합니다."""
    if not PYKRX_AVAILABLE:
        return pd.Series(dtype=float), {"ok": 0, "total": 0}

    codes = get_kospi200_tickers()
    if not codes:
        return pd.Series(dtype=float), {"ok": 0, "total": 0}

    start = datetime.date.today() - datetime.timedelta(days=365 * years + 90)
    start_str = start.strftime("%Y%m%d")
    end_str = datetime.date.today().strftime("%Y%m%d")

    above_frames = []
    ok = 0
    for code in codes:
        try:
            df = pykrx_stock.get_market_ohlcv(start_str, end_str, code)
        except Exception:
            continue
        if df is None or df.empty or "종가" not in df.columns:
            continue
        close = df["종가"].astype(float)
        close = close[close > 0].dropna()
        if len(close) < BREADTH_SMA_WINDOW + 5:
            continue
        sma50 = close.rolling(BREADTH_SMA_WINDOW).mean()
        above = (close > sma50).where(sma50.notna())
        above_frames.append(above.rename(code))
        ok += 1

    if not above_frames:
        return pd.Series(dtype=float), {"ok": 0, "total": len(codes)}

    above_df = pd.concat(above_frames, axis=1)
    breadth = (above_df.mean(axis=1, skipna=True) * 100).dropna()
    breadth.index = pd.to_datetime(breadth.index)
    return breadth, {"ok": ok, "total": len(codes)}


@st.cache_data(ttl=3600)
def get_single_index_close(ticker: str, start_date_str: str):
    """오버레이용 단일 지수 종가 (S&P500/코스피 자체 지수)"""
    df = yf.download(ticker, start=start_date_str, progress=False)
    if df.empty:
        return pd.Series(dtype=float)
    close = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
    return close.iloc[:, 0]


# 4. 탭 화면 구성
tab_home, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "🏠 Home", "📈 Page 1: 주가지수", "💱 Page 2: 환율 & 원자재",
    "Page 3: 상관관계", "Page 4: 미국 국채", "📊 Page 5: 반도체(D램)",
    "📉 Page 6: 삼성전자 괴리율", "🚢 Page 7: 한국 수출데이터",
    "🏦 Page 8: ECOS 매크로 지표", "😨 Page 9: 공포탐욕지수",
    "📶 Page 10: 이평선 상회 비율"
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

    st.divider()
    st.subheader("📝 메모장")
    st.caption("생각날 때마다 가볍게 적어두는 공간입니다. (서버가 재배포되면 초기화될 수 있어요)")

    memos = load_memos()

    with st.form("memo_add_form", clear_on_submit=True):
        new_memo = st.text_area(
            "새 메모", placeholder="예: D램 가격 페이지에 낸드도 추가하기",
            height=80, label_visibility="collapsed"
        )
        submitted = st.form_submit_button("➕ 메모 추가")
        if submitted and new_memo.strip():
            memos.insert(0, {
                "text": new_memo.strip(),
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            save_memos(memos)
            st.rerun()

    if not memos:
        st.caption("아직 메모가 없습니다. 위에 적고 '메모 추가'를 눌러보세요.")
    else:
        for i, memo in enumerate(memos):
            with st.container(border=True):
                col_txt, col_del = st.columns([10, 1])
                with col_txt:
                    st.caption(memo.get("created_at", ""))
                    st.text(memo.get("text", ""))
                with col_del:
                    if st.button("🗑️", key=f"memo_del_{i}", help="삭제"):
                        memos.pop(i)
                        save_memos(memos)
                        st.rerun()

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
    st.subheader("💾 D램 현물 가격 추이 (세대별 대표 SKU · 구글 시트 연동)")
    st.info("💡 구글 시트에 실시간 연동된 D램 세션 평균가를 세대별(DDR5/DDR4/DDR3) 대표 SKU 기준으로 시각화합니다.")
    df_dram = get_dram_csv_data()
    if not df_dram.empty and {'Date', 'Item', 'Session Average'}.issubset(df_dram.columns):
        df_dram['Date'] = pd.to_datetime(df_dram['Date'], errors='coerce')
        df_dram['Session Average'] = pd.to_numeric(df_dram['Session Average'], errors='coerce')

        # 시트가 한 행 = (날짜, SKU 하나) 롱포맷이라 SKU 7종이 다 섞여 있음.
        # 세대별로 하나씩만 대표 SKU를 골라서 비교 가능하게 함.
        # DDR4·DDR3는 업계에서 관행적으로 현물가 벤치마크로 쓰는 '칩(다이)' 단위 SKU를 택했고,
        # DDR5는 시트에 칩 단위 항목이 없어 유일하게 있는 모듈(SO-DIMM) 가격을 그대로 씀.
        # → 원하는 SKU가 다르면 아래 REPRESENTATIVE_ITEMS 값만 바꾸면 됨 (df_dram['Item'].unique()로 전체 목록 확인 가능)
        REPRESENTATIVE_ITEMS = {
            "DDR5": "DDR5 8GB SO-DIMM",
            "DDR4": "DDR4 8Gb 1Gx8",
            "DDR3": "DDR3 4Gb 256Mx16",
        }
        palette = {"DDR5": "#4f46e5", "DDR4": "#ff7f0e", "DDR3": "#16a34a"}

        available_gens = [g for g, item in REPRESENTATIVE_ITEMS.items() if (df_dram['Item'] == item).any()]
        selected_gens = st.multiselect(
            "표시할 세대 선택:", options=available_gens, default=available_gens,
            key="dram_gen_select"
        )

        # 시트에 이미 'Avg Change'(예: ▲13.04 %)가 있으니, 우리가 따로 전일 대비를 계산하지 않고
        # 원본 값을 그대로 최신 카드에 보여줌 (참고했던 다른 시트처럼 가격+변화율을 나란히)
        metric_cols = st.columns(len(selected_gens)) if selected_gens else []
        fig = go.Figure()
        for i, gen in enumerate(selected_gens):
            item_name = REPRESENTATIVE_ITEMS[gen]
            sub = df_dram[df_dram['Item'] == item_name].dropna(subset=['Date', 'Session Average']).sort_values('Date')
            if sub.empty:
                continue
            latest_row = sub.iloc[-1]
            avg_change = parse_dram_pct_change(latest_row.get('Avg Change'))
            with metric_cols[i]:
                st.metric(
                    f"{gen} ({item_name})",
                    f"{latest_row['Session Average']:,.2f}",
                    delta=f"{avg_change:+.2f}%" if avg_change is not None else None,
                    help=f"기준일 {latest_row['Date'].strftime('%Y-%m-%d')}",
                )
            fig.add_trace(go.Scatter(
                x=sub['Date'], y=sub['Session Average'],
                name=f"{gen} ({item_name})", mode='lines+markers',
                line=dict(color=palette[gen], width=2), marker=dict(size=4),
            ))
        fig.update_layout(
            title="<b>D램 현물 평균가(Session Average) 추이</b>",
            height=480, margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        fig.update_yaxes(title_text="가격")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("SKU 7종 전체 원본 데이터 보기"):
            st.dataframe(df_dram, use_container_width=True)
    elif not df_dram.empty:
        st.caption("시트 컬럼 구성이 예상(Date/Item/Session Average)과 달라 자동 차트를 그리지 못했습니다. 아래 원본 표를 확인해주세요.")
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

                favorites = load_ecos_favorites()

                # -----------------------------------------------------
                # 지금 주목 — 즐겨찾기한 지표만 (최대 10개)
                # 자체 스파크라인 대신, 한국은행 공식 '금융·경제 스냅샷' 차트로 바로
                # 연결. 지표명을 복사해서 스냅샷 검색창에 붙여넣으면 공식 차트가 뜸.
                # -----------------------------------------------------
                st.markdown(f"#### 지금 주목 · 즐겨찾기 ({len(favorites)}/{ECOS_FAVORITES_MAX})")
                if not favorites:
                    st.caption("아직 즐겨찾기한 지표가 없습니다. 아래 '그룹별 보기' 표에서 ⭐ 체크박스를 눌러 추가해보세요.")
                else:
                    st.caption("지표명을 복사(아이콘 클릭)해서 스냅샷 검색창에 붙여넣으면 한국은행 공식 추이 차트를 볼 수 있어요.")
                    cols_fav = st.columns(5)
                    for i, name in enumerate(favorites[:ECOS_FAVORITES_MAX]):
                        row_match = df_key[df_key["지표명"] == name]
                        with cols_fav[i % 5]:
                            st.caption(name)
                            if not row_match.empty:
                                r0 = row_match.iloc[0]
                                st.markdown(f"**{r0['값']:,.2f}** {r0['단위']}")
                                st.caption(f"기준 {r0['시점']}")
                            else:
                                st.markdown("**—**")
                            st.code(name, language=None)
                            st.link_button("🔗 스냅샷에서 보기", ECOS_SNAPSHOT_URL, use_container_width=True)
                            if st.button("즐겨찾기 해제", key=f"ecos_unfav_{name}", use_container_width=True):
                                favorites.remove(name)
                                save_ecos_favorites(favorites)
                                st.rerun()

                st.divider()
                st.markdown("#### 그룹별 보기")
                for grp, sub in df_key.groupby("그룹"):
                    with st.expander(f"{grp} ({len(sub)}종)"):
                        disp_df = pd.DataFrame({
                            "즐겨찾기": [name in favorites for name in sub["지표명"]],
                            "지표": sub["지표명"],
                            "최신값": sub["값"],
                            "단위": sub["단위"],
                            "기준시점": sub["시점"],
                            "주기": [guess_ecos_cycle_label(t) for t in sub["시점"]],
                        })

                        edited = st.data_editor(
                            disp_df,
                            column_config={
                                "즐겨찾기": st.column_config.CheckboxColumn("⭐"),
                                "최신값": st.column_config.NumberColumn("최신값", format="%.2f"),
                            },
                            disabled=["지표", "최신값", "단위", "기준시점", "주기"],
                            hide_index=True, use_container_width=True, key=f"ecos_group_{grp}",
                        )

                        changed = False
                        for _, er in edited.iterrows():
                            name = er["지표"]
                            was_fav = name in favorites
                            now_fav = bool(er["즐겨찾기"])
                            if now_fav and not was_fav:
                                if len(favorites) >= ECOS_FAVORITES_MAX:
                                    st.warning(f"즐겨찾기는 최대 {ECOS_FAVORITES_MAX}개까지예요. 먼저 하나를 해제해주세요.")
                                else:
                                    favorites.append(name)
                                    changed = True
                            elif not now_fav and was_fav:
                                favorites.remove(name)
                                changed = True
                        if changed:
                            save_ecos_favorites(favorites)
                            st.rerun()

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

# ==========================================
# [Page 9] CNN Fear & Greed Index
# ==========================================
with tab9:
    st.subheader("😨 CNN Fear & Greed Index")
    st.caption(
        "CNN이 7개 하위 지표(시장 모멘텀, 변동성(VIX), 풋/콜 옵션 비율, 정크본드 수요, "
        "안전자산 수요, 주가 강도/폭 등)를 합성해 매일 발표하는 시장 심리 지수입니다. "
        "0에 가까울수록 극단적 공포(Extreme Fear), 100에 가까울수록 극단적 탐욕(Extreme Greed)을 의미합니다."
    )

    current, df_fng_hist, fng_diag = get_fear_greed_data()

    if not current or current.get("score") is None:
        st.error(f"CNN Fear & Greed 데이터를 불러오지 못했습니다: {fng_diag.get('error') or '알 수 없는 오류'}")
        st.caption("CNN이 페이지 구조를 바꿨거나, 네트워크에서 해당 주소로의 접근이 막혀 있을 수 있습니다.")
    else:
        score = current.get("score")
        rating_raw = (current.get("rating") or "").lower()
        if not rating_raw:
            rating_raw, _ = _fng_score_to_rating(score)
        rating_kr = FNG_RATING_KR.get(rating_raw, rating_raw)
        rating_color = FNG_RATING_COLOR.get(rating_raw, "#333")

        col_gauge, col_panel = st.columns([1.3, 1])

        with col_gauge:
            st.plotly_chart(render_fng_gauge(score), use_container_width=True)
            st.markdown(
                f"<div style='text-align:center; margin-top:-15px;'>"
                f"<span style='font-size:22px; font-weight:700; color:{rating_color};'>{rating_kr.upper()}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
            ts = current.get("timestamp")
            if ts:
                try:
                    ts_fmt = pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts_fmt = str(ts)
                st.caption(f"마지막 업데이트: {ts_fmt} (UTC)")

        with col_panel:
            st.markdown("<div style='padding-top:10px;'>", unsafe_allow_html=True)
            st.markdown(_fng_panel_row("전일 종가 (Previous close)", current.get("previous_close")), unsafe_allow_html=True)
            st.markdown(_fng_panel_row("1주일 전 (1 week ago)", current.get("previous_1_week")), unsafe_allow_html=True)
            st.markdown(_fng_panel_row("1개월 전 (1 month ago)", current.get("previous_1_month")), unsafe_allow_html=True)
            st.markdown(_fng_panel_row("1년 전 (1 year ago)", current.get("previous_1_year")), unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.divider()

        # ---- 일별 추이 히스토리 ----
        st.markdown("### 📈 일별 Fear & Greed 추이")
        if df_fng_hist.empty:
            st.warning("과거 히스토리 데이터를 불러오지 못했습니다.")
        else:
            hist_start = df_fng_hist.index.min().strftime("%Y-%m-%d")
            hist_end = df_fng_hist.index.max().strftime("%Y-%m-%d")
            st.caption(
                f"확보된 히스토리 범위: {hist_start} ~ {hist_end} "
                f"({fng_diag.get('chunks_ok')}/{fng_diag.get('chunks_total')} 구간 요청 성공) · "
                "기간 버튼은 이 범위 안에서 필터링됩니다. 범위가 예상보다 짧다면 CNN 쪽에서 "
                "일부 구간 요청이 막혔을 가능성이 있습니다."
            )
            col_p9, col_o9 = st.columns([3, 1])
            with col_p9:
                period_option_9 = st.radio(
                    "조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "Max", "YTD"],
                    index=0, horizontal=True, key="fng_p9"
                )
            with col_o9:
                show_kospi_9 = st.checkbox("코스피와 함께 보기", value=False, key="fng_kospi_overlay")

            start_date_9 = get_start_date(period_option_9)
            df_plot9 = df_fng_hist[df_fng_hist.index >= pd.to_datetime(start_date_9)]

            fig9 = make_subplots(specs=[[{"secondary_y": True}]])
            fig9.add_trace(
                go.Scatter(x=df_plot9.index, y=df_plot9['Score'], name="Fear & Greed",
                           line=dict(color="#4f46e5", width=1.6)),
                secondary_y=False
            )
            # 극단적 공포 / 극단적 탐욕 구간 배경 음영
            fig9.add_hrect(y0=0, y1=25, fillcolor="rgba(178,59,59,0.10)", line_width=0)
            fig9.add_hrect(y0=75, y1=100, fillcolor="rgba(63,145,66,0.10)", line_width=0)

            if show_kospi_9:
                df_kospi9 = yf.download("^KS11", start=start_date_9.strftime("%Y-%m-%d"), progress=False)
                if not df_kospi9.empty:
                    kclose9 = df_kospi9['Close'] if isinstance(df_kospi9.columns, pd.MultiIndex) else df_kospi9[['Close']]
                    kclose9 = kclose9.iloc[:, 0]
                    fig9.add_trace(
                        go.Scatter(x=kclose9.index, y=kclose9.values, name="코스피",
                                   line=dict(color="black", width=1.3)),
                        secondary_y=True
                    )
                fig9.update_yaxes(title_text="코스피 (pt)", secondary_y=True)

            fig9.update_layout(
                height=450, margin=dict(l=20, r=20, t=30, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
            )
            fig9.update_yaxes(title_text="Fear & Greed Score", range=[0, 100], secondary_y=False)
            st.plotly_chart(fig9, use_container_width=True)

            # 선택 구간 요약 통계 (투자 참고용)
            if len(df_plot9) > 0:
                col_a9, col_b9, col_c9, col_d9 = st.columns(4)
                col_a9.metric("선택 구간 평균", f"{df_plot9['Score'].mean():.1f}")
                col_b9.metric("선택 구간 최저", f"{df_plot9['Score'].min():.1f}")
                col_c9.metric("선택 구간 최고", f"{df_plot9['Score'].max():.1f}")
                extreme_fear_days = int((df_plot9['Score'] < 25).sum())
                extreme_fear_pct = extreme_fear_days / len(df_plot9) * 100
                col_d9.metric("극단적 공포 일수", f"{extreme_fear_days}일 ({extreme_fear_pct:.1f}%)")

            with st.expander("일별 원본 데이터 보기 (CSV 다운로드)"):
                st.dataframe(df_fng_hist.sort_index(ascending=False), use_container_width=True)
                csv_bytes = df_fng_hist.to_csv().encode("utf-8-sig")
                st.download_button(
                    "CSV로 다운로드", data=csv_bytes,
                    file_name="cnn_fear_greed_history.csv", mime="text/csv"
                )

# ==========================================
# [Page 10] 50일 이동평균선 상회 종목 비율 (Market Breadth)
# ==========================================
with tab10:
    st.subheader("📶 50일 이동평균선 상회 종목 비율 — 시장 호흡(Breadth) 지표")
    st.caption(
        "전체 종목 중 종가가 50일 이동평균선 위에 있는 종목의 비율(%)입니다. 통상 30% 아래로 "
        "떨어지면 시장이 과매도 국면에 가깝고, 70~80% 이상이면 과매수 국면으로 해석합니다. "
        "S&P500은 위키피디아 편입종목 + yfinance, 코스피는 코스피200 구성종목 + pykrx로 계산합니다."
    )
    st.caption(
        "⚠️ '현재' 편입종목 리스트를 과거 전체 기간에 그대로 적용하는 방식이라 생존편향이 있는 "
        "단순화된 지표입니다. 또한 종목 수가 많아 최초 로딩이 오래 걸릴 수 있어 하루 단위로 캐싱됩니다."
    )

    if not PYKRX_AVAILABLE:
        st.warning(
            "코스피 데이터를 받아오려면 `pykrx` 패키지가 필요합니다. requirements.txt에 "
            "`pykrx`를 추가하고 재배포해주세요. (S&P500은 pykrx 없이도 조회됩니다.)"
        )

    period_option_10 = st.radio(
        "조회 기간을 선택하세요:", ["1년", "3년", "5년", "10년", "YTD"],
        index=0, horizontal=True, key="breadth_p10"
    )
    start_date_10 = get_start_date(period_option_10)

    sp500_breadth, sp500_cov = get_sp500_breadth_data()
    if PYKRX_AVAILABLE:
        kospi_breadth, kospi_cov = get_kospi200_breadth_data()
    else:
        kospi_breadth, kospi_cov = pd.Series(dtype=float), {"ok": 0, "total": 0}

    def _render_breadth_chart(col, title, breadth_series, coverage, index_ticker, line_color):
        with col:
            if breadth_series.empty:
                st.warning(f"{title} 데이터를 불러오지 못했습니다.")
                return
            plot_series = breadth_series[breadth_series.index >= pd.to_datetime(start_date_10)]
            if plot_series.empty:
                st.warning(f"{title}: 선택한 기간에 해당하는 데이터가 없습니다.")
                return

            latest_val = plot_series.iloc[-1]
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(
                x=plot_series.index, y=plot_series.values, name="50일선 상회 비율(%)",
                line=dict(color=line_color, width=1.8)
            ), secondary_y=False)
            fig.add_hline(y=30, line_dash="dot", line_color="gray", opacity=0.6, secondary_y=False)
            fig.add_hline(y=70, line_dash="dot", line_color="gray", opacity=0.6, secondary_y=False)

            idx_close = get_single_index_close(index_ticker, start_date_10.strftime("%Y-%m-%d"))
            if len(idx_close) > 0:
                fig.add_trace(go.Scatter(
                    x=idx_close.index, y=idx_close.values, name="지수(우)",
                    line=dict(color="black", width=1.3)
                ), secondary_y=True)
            fig.update_yaxes(title_text="지수", secondary_y=True)

            fig.update_layout(
                title=f"<b>{title}</b> ({coverage['ok']}/{coverage['total']}종목 반영) | 현재: {latest_val:.1f}%",
                height=420, margin=dict(l=20, r=20, t=50, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
            )
            fig.update_yaxes(title_text="50일선 상회 비율 (%)", range=[0, 100], secondary_y=False)
            st.plotly_chart(fig, use_container_width=True)

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("현재", f"{latest_val:.1f}%")
            col_m2.metric("선택 구간 최저", f"{plot_series.min():.1f}%")
            col_m3.metric("선택 구간 최고", f"{plot_series.max():.1f}%")

    col10a, col10b = st.columns(2)
    _render_breadth_chart(col10a, "S&P 500", sp500_breadth, sp500_cov, "^GSPC", "#1f77b4")
    _render_breadth_chart(col10b, "코스피 200", kospi_breadth, kospi_cov, "^KS11", "#c0392b")
