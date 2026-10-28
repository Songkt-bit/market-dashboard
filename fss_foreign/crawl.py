"""금감원 '외국인 증권투자 동향' 게시판에서 월별 PDF 수집. 인자: 페이지 수(기본 전체)."""
import re, os, sys, time, requests
from bs4 import BeautifulSoup
B="https://www.fss.or.kr"; H={"User-Agent":"Mozilla/5.0"}
L=B+"/fss/bbs/B0000188/list.do?menuNo=200218&bbsId=&cl1Cd=&pageIndex={p}&sdate=&edate=&searchCnd=1&searchWrd=%EC%99%B8%EA%B5%AD%EC%9D%B8"
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"pdf")

def crawl(maxpage=40, skip=()):
    os.makedirs(OUT,exist_ok=True); new=[]
    for p in range(1,maxpage+1):
        r=requests.get(L.format(p=p),headers=H,timeout=30); r.encoding=r.apparent_encoding
        cur=None; n=0
        for a in BeautifulSoup(r.text,"html.parser").select("table a"):
            t=a.get_text(strip=True); m=re.search(r"(\d{4})년\s*(\d{1,2})월\s*외국인\s*증권투자\s*동향",t)
            if m and "view.do" in a.get("href",""): cur=f"{m[1]}-{int(m[2]):02d}"; n+=1; continue
            if cur and "fileDown" in a.get("href","") and t.lower().endswith(".pdf"):
                f=os.path.join(OUT,cur+".pdf")
                if cur not in skip and not os.path.exists(f):
                    open(f,"wb").write(requests.get(B+a["href"].replace("&amp;","&"),headers=H,timeout=60).content); new.append(cur); time.sleep(.3)
                cur=None
        if n==0: break
    return new

if __name__=="__main__":
    print("new:",crawl(int(sys.argv[1]) if len(sys.argv)>1 else 40))
