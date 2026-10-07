"""KOSPI200 옵션(월물+위클리) 일별 콜/풋 거래량 → putcall/data.csv (symbol=KOSPI200)

KRX Data Marketplace 로그인이 필요합니다. 자격증명은 아래 순서로 읽으며 출력하지 않습니다.
  1) 환경변수 KRX_ID / KRX_PW
  2) .streamlit/secrets.toml (이 폴더 상위, 저장소 루트, 또는 ~/.streamlit)  — 앱이 쓰는 것과 같은 키

사용법
  python putcall/fetch_kospi.py --probe [YYYYMMDD]   # 종목명 형식·합산 결과만 확인(파일 변경 없음)
  python putcall/fetch_kospi.py [시작일 YYYY-MM-DD]  # 수집·누적 (기본: 마지막 날짜 다음날, 없으면 2년 전)
"""
import os, re, sys, time, datetime as dt
import pandas as pd

D = os.path.dirname(os.path.abspath(__file__)); CSV = os.path.join(D, "data.csv")
PRODS = {"KRDRVOPK2I": "KOSPI200 옵션(월물)", "KRDRVOPWKI": "KOSPI200 위클리옵션"}


def _load_creds():
    if os.environ.get("KRX_ID") and os.environ.get("KRX_PW"):
        return
    try:
        import tomllib
    except ImportError:
        return
    for base in (os.path.dirname(D), os.path.dirname(os.path.dirname(D)), os.path.expanduser("~")):
        p = os.path.join(base, ".streamlit", "secrets.toml")
        if os.path.exists(p):
            s = tomllib.load(open(p, "rb"))
            if s.get("KRX_ID") and s.get("KRX_PW"):
                os.environ["KRX_ID"], os.environ["KRX_PW"] = s["KRX_ID"], s["KRX_PW"]
                return


_load_creds()
if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    raise SystemExit("KRX_ID / KRX_PW 가 설정돼 있지 않습니다 (환경변수 또는 .streamlit/secrets.toml).")
from pykrx.website.krx.future.core import 전종목시세, 파생상품검색  # 임포트 시 로그인 수행


def _num(x):
    try:
        return int(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def day_volume(day, prod, verbose=False):
    df = 전종목시세().fetch(day.strftime("%Y%m%d"), prod)
    if df is None or df.empty:
        return None
    kind = df["ISU_NM"].str.extract(r"\s([CP])\s")[0]
    vol = df["ACC_TRDVOL"].map(_num)
    if verbose:
        print(f"  [{prod}] 컬럼: {list(df.columns)}")
        print("  종목명 샘플:", df["ISU_NM"].head(4).tolist(), "...", df["ISU_NM"].tail(2).tolist())
        print(f"  C/P 인식 행 {kind.notna().sum()} / 전체 {len(df)}")
    return int(vol[kind == "C"].sum()), int(vol[kind == "P"].sum())


def probe(arg):
    day = pd.to_datetime(arg).date() if arg else pd.bdate_range(end=dt.date.today() - dt.timedelta(days=1), periods=1)[0].date()
    print("조회일:", day)
    try:
        print(파생상품검색().fetch().loc[list(PRODS)].to_string())
    except Exception as e:
        print("파생상품검색 실패:", type(e).__name__, str(e)[:120])
    tc = tp = 0
    for p in PRODS:
        try:
            r = day_volume(day, p, verbose=True)
        except Exception as e:
            print(f"  [{p}] 실패:", type(e).__name__, str(e)[:160]); continue
        print(f"  [{p}] 콜/풋 =", r)
        if r: tc += r[0]; tp += r[1]
    print(f"합산 콜 {tc:,}  풋 {tp:,}  P/C = {tp / tc:.2f}" if tc else "합산 불가(휴장일이거나 로그인 실패 — 위 메시지 확인)")


def update(start=None):
    old = pd.read_csv(CSV) if os.path.exists(CSV) else pd.DataFrame(columns=["date", "symbol", "call", "put"])
    mine = old[old["symbol"] == "KOSPI200"]
    today = dt.date.today()
    if start is None:
        start = (pd.to_datetime(mine["date"].max()).date() + dt.timedelta(days=1)) if len(mine) else today - dt.timedelta(days=728)
    rows = []
    for d in pd.bdate_range(start, today):
        c = p = 0
        for prod in PRODS:
            for _ in range(3):
                try:
                    r = day_volume(d, prod); break
                except Exception:
                    r = None; time.sleep(2)
            if r: c += r[0]; p += r[1]
            time.sleep(0.6)
        if c + p > 0:
            rows.append(dict(date=d.date().isoformat(), symbol="KOSPI200", call=c, put=p))
    new = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates(["date", "symbol"], keep="last").sort_values(["date", "symbol"])
    new.to_csv(CSV, index=False)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print("added", update(pd.to_datetime(sys.argv[1]).date() if len(sys.argv) > 1 else None), "rows")
