"""OCC(옵션청산공사) 일별 옵션 거래량에서 풋/콜 거래량을 받아 putcall/data.csv에 누적.
지수옵션: SPX(=SPX+SPXW), NDX  /  ETF옵션: SPY, QQQ.  OCC는 최근 2년치만 제공.
사용: python putcall/fetch.py [시작일 YYYY-MM-DD]   (기본: CSV 마지막 날짜 다음날, 없으면 2년 전)"""
import io, os, sys, datetime as dt, time
import pandas as pd, requests
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__)); CSV = os.path.join(D, "data.csv")
SYMS = ["SPX", "SPY", "NDX", "QQQ"]
URL = ("https://marketdata.theocc.com/volume-query?reportDate={d}&format=csv&volumeQueryType=O&symbolType=U"
       "&symbol={s}&reportType=D&accountType=ALL&productKind=ALL&porc=BOTH")

def one(args):
    s, day = args
    for _ in range(3):
        try:
            r = requests.get(URL.format(d=day.strftime("%Y%m%d"), s=s), headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            if not r.text.startswith("quantity"): return None          # 휴장일/조회불가
            df = pd.read_csv(io.StringIO(r.text), index_col=False)
            g = df.groupby("porc").quantity.sum()
            return dict(date=day.date().isoformat(), symbol=s, call=int(g.get("C", 0)), put=int(g.get("P", 0)))
        except Exception:
            time.sleep(1.5)
    return None

def update(start=None):
    old = pd.read_csv(CSV) if os.path.exists(CSV) else pd.DataFrame(columns=["date", "symbol", "call", "put"])
    today = dt.date.today()
    if start is None:
        start = (pd.to_datetime(old["date"].max()).date() + dt.timedelta(days=1)) if len(old) else today - dt.timedelta(days=728)
    days = [d for d in pd.bdate_range(start, today)]
    jobs = [(s, d) for d in days for s in SYMS]
    with ThreadPoolExecutor(6) as ex: rows = [r for r in ex.map(one, jobs) if r and r["call"] + r["put"] > 0]
    new = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(["date", "symbol"], keep="last").sort_values(["date", "symbol"])
    new.to_csv(CSV, index=False); return len(rows), new["date"].max()

if __name__ == "__main__":
    n, last = update(pd.to_datetime(sys.argv[1]).date() if len(sys.argv) > 1 else None)
    print(f"added {n} rows, last date {last}")
