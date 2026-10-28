import re, os, glob, json, pdfplumber
from multiprocessing import Pool
D=os.path.dirname(os.path.abspath(__file__))
N=r"[△\-]?\d[\d,]*(?:\.\d+)?"
ALIAS={"케이만아일랜드":"케이맨제도","케이만제도":"케이맨제도","사우디":"사우디아라비아","룩셈부르그":"룩셈부르크","버진아일랜드":"영국령버진아일랜드"}
num=lambda s: 0.0 if s in("-","0.0") else float(s.replace("△","-").replace(",",""))

def text(path,ym):
    tp=os.path.join(D,"txt",ym+".txt")
    if os.path.exists(tp): return open(tp,encoding="utf-8").read()
    os.makedirs(os.path.dirname(tp),exist_ok=True)
    t="\n".join((p.extract_text() or "") for p in pdfplumber.open(path).pages)
    open(tp,"w",encoding="utf-8").write(t); return t

def parse(path):
    ym=os.path.basename(path)[:7]; mon=int(ym[5:]); t=text(path,ym); r={"ym":ym}
    # 국가별 보유현황 구간: 국가명 + 정수3 + 증감률 + 비중
    a=t.find("국가별 상장주식 보유"); a=max(a,0)
    b=t.find("합 계",a); sec=t[a:b+200] if b>=0 else t[a:]
    cs={}
    for m in re.finditer(rf"([가-힣]{{2,8}})\s+({N})\s+({N})\s+({N})\s+(△?\d+\.\d+)\s+(\d+\.\d+)(?!\d)",sec):
        n=ALIAS.get(m[1],m[1])
        if n!="합계" and n not in cs: cs[n]=num(m[4])
    r["country"]=cs
    m=re.search(rf"합\s*계\s+({N})\s+({N})\s+({N})\s+(△?\d+\.\d+)\s+100\.0+",t)
    r["stock_hold_total"]=num(m[3]) if m else None
    # 주식: 같은 월이 여러 연도 행으로 중복되므로 보유합계(보유현황 표)와 일치하는 후보 채택
    ref=r["stock_hold_total"]; cand=[]
    for m in re.finditer(rf"(?<!\d)(\d{{1,2}})월\s+((?:{N}\s+){{9}})({N})\s*\(\s*\d+\.\d+\)",t):
        if int(m[1])==mon: cand.append((num(re.findall(N,m[2])[8]),num(m[3])))
    for m in re.finditer(rf"(?<!\d)(\d{{1,2}})월\s+({N})\s+({N})\s+({N})\s+({N})\s+({N})\s+(\d+\.\d)",t):
        if int(m[1])==mon: cand.append((num(m[4]),num(m[5])))
    if ref:
        ok=[c for c in cand if abs(c[1]-ref)<=0.003*ref]
        r["stock_hold"]=ref
        if ok: r["stock_net"]=ok[0][0]
    elif cand:
        c=max(cand,key=lambda c:c[1]); r["stock_net"],r["stock_hold"]=c
    # 채권 종류별: [국채, 특수채(통안채 포함), 통안채, 회사채, 지방채, 합계]
    tok=rf"({N}|-)"
    m=re.search(rf"월말\s*보유\s+{tok}\s+{tok}\s+{tok}\s+{tok}\s+{tok}\s+{tok}",t)
    if m: r["bt_hold"]=[num(m[i]) for i in range(1,7)]
    m=re.search(rf"{mon}월중\s*순투자\s+{tok}\s+{tok}\s+{tok}\s+{tok}\s+{tok}\s+{tok}",t)
    if m: r["bt_net"]=[num(m[i]) for i in range(1,7)]
    return r

if __name__=="__main__":
    fs=sorted(glob.glob(os.path.join(D,"pdf","*.pdf")))
    have={os.path.basename(f)[:7] for f in fs}
    from hwp_text import hwp_text   # PDF가 없는 월은 HWP 본문에서 추출(txt 캐시로 저장)
    for h in sorted(glob.glob(os.path.join(D,"hwp_todo","*.hwp"))):
        ym=os.path.basename(h)[:7]
        if ym in have: continue
        tp=os.path.join(D,"txt",ym+".txt"); os.makedirs(os.path.dirname(tp),exist_ok=True)
        if not os.path.exists(tp): open(tp,"w",encoding="utf-8").write(hwp_text(h))
        fs.append(h)
    fs.sort(key=os.path.basename)
    with Pool(6) as p: R=p.map(parse,fs)
    mp=os.path.join(D,"manual.json")   # 이미지 PDF·HWP 등 자동추출 불가 월의 수기 입력
    if os.path.exists(mp):
        man=json.load(open(mp,encoding="utf-8")); R=[man.pop(r["ym"],r) for r in R]+list(man.values()); R.sort(key=lambda r:r["ym"])
    json.dump(R,open(os.path.join(D,"parsed.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    for k in ["stock_hold_total","stock_net","stock_hold","bt_hold","bt_net"]:
        print(k,"missing:",[r["ym"] for r in R if r.get(k) is None])
    print("country<10:",[(r["ym"],len(r["country"])) for r in R if len(r["country"])<10]); print("done")
