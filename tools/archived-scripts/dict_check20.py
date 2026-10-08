# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, r"C:\Users\zzl\Desktop\hx\engine\chemistry")
from dict_query import search, find_smiles, get_record, stats, aliases_of

st = stats()
print("规模：化合物 %d，含结构 %d，别名 %d，中文主名 %d，中文别名 %d"
      % (st["total"], st["with_smiles"], st.get("aliases", 0),
         st.get("cn_compounds", 0), st.get("cn_aliases", 0)))
print("=" * 78)
QUERIES = ["阿司匹林","乙酰水杨酸","aspirin","扑热息痛","对乙酰氨基酚","氯仿","三氯甲烷",
           "THF","四氢呋喃","冰醋酸","乙酸","DMSO","二甲亚砜","水杨酸","布洛芬",
           "咖啡因","苯","甲苯","乙醇","甲醇"]
ok = 0
t0 = time.time()
for q in QUERIES:
    r = get_record(q)
    smi = find_smiles(q)
    hit = bool(smi)
    ok += hit
    print("%-2s %-10s 主名=%-12s SMILES=%-32s %s" % (
        "OK" if hit else "XX", q, (r["name"] if r else "-"),
        (smi if smi else "-"), (r["source"] if r else "")))
print("=" * 78)
print("命中 %d/%d，20 次查询总耗时 %.3fs（平均 %.1f ms）"
      % (ok, len(QUERIES), time.time()-t0, 1000*(time.time()-t0)/len(QUERIES)))
