import json, os, pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
D=os.path.dirname(os.path.abspath(__file__))
TYPES=["국채","통안채","특수채(통안채 제외)","회사채·지방채"]
C=["#1f3a5f","#2a9d8f","#e9c46a","#e76f51","#8d99ae","#6a4c93","#f4a261","#457b9d","#b5838d","#588157"]

def load():
    R=json.load(open(os.path.join(D,"parsed.json"),encoding="utf-8"))
    idx=pd.period_range("2015-03",R[-1]["ym"],freq="M").strftime("%Y-%m")
    g=lambda k:pd.Series({r["ym"]:r.get(k) for r in R}).reindex(idx)/1000   # 십억원→조원
    st=pd.DataFrame({"순매수(조원)":g("stock_net"),"보유금액(조원)":g("stock_hold")})
    cs=pd.DataFrame({r["ym"]:r["country"] for r in R}).T.reindex(idx)/1000
    cs=cs[[c for c in cs.iloc[-1].dropna().sort_values(ascending=False).index if c!="기타"][:10]]
    def bt(k):
        rows={r["ym"]:r.get(k) for r in R}
        f=lambda i:pd.Series({m:(v[i] if v else None) for m,v in rows.items()}).reindex(idx)/1000
        return pd.DataFrame({"국채":f(0),"통안채":f(2),"특수채(통안채 제외)":f(1)-f(2),"회사채·지방채":f(3)+f(4),"합계":f(5)})
    miss=[m for m in idx if m not in {r["ym"] for r in R}]
    return idx,st,cs,bt("bt_hold"),bt("bt_net"),miss

def figs():
    idx,st,cs,bh,bn,miss=load()
    L=dict(template="plotly_white",font=dict(family="Malgun Gothic, sans-serif"),hovermode="x unified",height=460,margin=dict(t=60,l=60,r=60,b=40),legend=dict(orientation="h",y=-0.12))
    f1=make_subplots(specs=[[{"secondary_y":True}]])
    f1.add_bar(x=idx,y=st["순매수(조원)"],name="월별 순매수(좌, 조원)",marker_color=["#d1495b" if (v or 0)<0 else "#1f3a5f" for v in st["순매수(조원)"]])
    f1.add_scatter(x=idx,y=st["보유금액(조원)"],name="보유금액(우, 조원)",line=dict(color="#e9a03b",width=2.5),secondary_y=True,connectgaps=True)
    f1.update_layout(title="외국인 월별 상장주식 순매수 및 보유금액 [붙임1]",**L)
    f2=go.Figure()
    for i,c in enumerate(cs.columns): f2.add_scatter(x=idx,y=cs[c],name=c,line=dict(color=C[i],width=2),connectgaps=True)
    f2.update_layout(title="국가별 상장주식 보유규모 추이 (조원, 최근월 상위 10개국) [붙임1]",**L)
    f3=go.Figure()
    for i,c in enumerate(TYPES): f3.add_bar(x=idx,y=bh[c],name=c,marker_color=C[i])
    f3.update_layout(barmode="stack",title="상장채권 종류별 보유규모 (조원) [붙임2]",**L)
    f4=go.Figure()
    for i,c in enumerate(TYPES): f4.add_bar(x=idx,y=bn[c],name=c,marker_color=C[i])
    f4.add_scatter(x=idx,y=bn["합계"],name="합계",mode="lines+markers",line=dict(color="black",width=1.5),marker=dict(size=4))
    f4.update_layout(barmode="relative",title="상장채권 종류별 월별 순투자 (조원, 순매수-만기상환) [붙임2]",**L)
    return [f1,f2,f3,f4],(idx,st,cs,bh,bn,miss)

if __name__=="__main__":
    (f1,f2,f3,f4),(idx,st,cs,bh,bn,miss)=figs()
    with pd.ExcelWriter(os.path.join(D,"외국인증권투자_추이.xlsx")) as w:
        st.to_excel(w,sheet_name="붙임1_주식순매수·보유"); cs.round(1).to_excel(w,sheet_name="붙임1_국가별보유")
        bh.to_excel(w,sheet_name="붙임2_채권보유"); bn.to_excel(w,sheet_name="붙임2_채권순투자")
    h=f"""<!doctype html><meta charset=utf-8><title>외국인 증권투자 동향</title><body style="font-family:Malgun Gothic,sans-serif;max-width:1100px;margin:auto;padding:16px">
<h2>외국인 증권투자 동향 ({idx[0]} ~ {idx[-1]})</h2><p style="color:#666">출처: 금융감독원 월별 「외국인 증권투자 동향」 보도자료 (결제기준). 원자료 미확보로 공란인 월: {', '.join(miss) or '없음'}</p>
<h3>붙임1</h3>{f1.to_html(full_html=False,include_plotlyjs='cdn')}{f2.to_html(full_html=False,include_plotlyjs=False)}
<h3>붙임2</h3>{f3.to_html(full_html=False,include_plotlyjs=False)}{f4.to_html(full_html=False,include_plotlyjs=False)}</body>"""
    open(os.path.join(D,"외국인증권투자_추이.html"),"w",encoding="utf-8").write(h)
    print("built",idx[-1],"missing",miss)
