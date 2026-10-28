"""금감원 신규 월 → parsed.json 증분 갱신 (GitHub Actions용). PDF는 임시 폴더에만 받고 저장소엔 남기지 않음.
검증을 통과한 달만 추가하고, 하나라도 비정상이면 종료코드 1로 끝내 워크플로를 실패시킨다(잘못된 값 커밋 방지)."""
import json, os, sys, tempfile
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import crawl, parse

PJ = os.path.join(D, "parsed.json")
R = json.load(open(PJ, encoding="utf-8"))
crawl.OUT = tempfile.mkdtemp()
new = crawl.crawl(3, skip={r["ym"] for r in R})      # 최신 3페이지에서 아직 없는 달만 받음

bad = []
for ym in sorted(new):
    r = parse.parse(os.path.join(crawl.OUT, ym + ".pdf"))
    if all(r.get(k) is not None for k in ("stock_hold", "stock_net", "bt_hold", "bt_net")) and len(r["country"]) >= 10:
        R.append(r)
    else:
        bad.append(ym)
if len(R) and new:
    R.sort(key=lambda r: r["ym"])
    json.dump(R, open(PJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("new:", new or "없음", "| 검증 실패:", bad or "없음")
sys.exit(1 if bad else 0)
