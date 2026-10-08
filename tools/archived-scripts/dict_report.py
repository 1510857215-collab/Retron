# -*- coding: utf-8 -*-
"""词典最终自测报告：规模 / 来源分布 / 20 查询用例 / 性能 / 别名样例。"""
import os
import sqlite3
import sys
import time

ROOT = r"C:\Users\zzl\Desktop\hx"
sys.path.insert(0, os.path.join(ROOT, "engine", "chemistry"))
from dict_query import search, find_smiles, get_record, stats, aliases_of  # noqa: E402

DB = os.path.join(ROOT, "data", "中文名字典.sqlite")

print("=" * 82)
print("词典最终自测报告")
print("=" * 82)

st = stats()
print("\n【1. 规模】")
print("  化合物(compounds)        : %d" % st["total"])
print("  带结构(有 SMILES)        : %d" % st["with_smiles"])
print("  别名(aliases)            : %d" % st.get("aliases", 0))
print("  主名为中文的化合物        : %d (%.1f%%)"
      % (st.get("cn_compounds", 0), 100.0 * st.get("cn_compounds", 0) / max(1, st["total"])))
print("  中文名类别名              : %d" % st.get("cn_aliases", 0))
print("  数据库文件大小            : %.1f MB" % (os.path.getsize(DB) / 1048576))

c = sqlite3.connect(DB)
print("\n【2. 别名类别分布】")
for k, n in c.execute("SELECT kind, COUNT(*) FROM aliases GROUP BY kind ORDER BY -COUNT(*)"):
    print("  %-14s %d" % (k, n))
print("\n【3. 别名来源分布】")
for s, n in c.execute(
        "SELECT CASE WHEN source LIKE 'Wikidata%' THEN 'Wikidata(中文名/QID)' "
        "WHEN source LIKE 'PubChem Drug%' THEN 'PubChem Drug-Names(药品名)' "
        "WHEN source='seed清单' THEN 'seed清单(人工)' "
        "ELSE 'PubChem 同义词(英文名/CAS/俗名)' END AS src, COUNT(*) "
        "FROM aliases GROUP BY src ORDER BY -COUNT(*)"):
    print("  %-36s %d" % (s, n))
print("\n【4. 每个化合物的别名数分布】")
row = c.execute(
    "SELECT COUNT(*), AVG(n), MAX(n) FROM (SELECT compound_id, COUNT(*) n "
    "FROM aliases GROUP BY compound_id)").fetchone()
print("  有别名化合物 %d，平均 %.1f 条，最多 %d 条" % row)
c.close()

QUERIES = ["阿司匹林", "乙酰水杨酸", "aspirin", "拜阿司匹灵", "扑热息痛", "对乙酰氨基酚",
           "氯仿", "三氯甲烷", "THF", "四氢呋喃", "冰醋酸", "乙酸", "DMSO", "二甲亚砜",
           "水杨酸", "布洛芬", "咖啡因", "苯", "甲苯", "乙醇", "甲醇"]
print("\n【5. 查询用例（共 %d 个）】" % len(QUERIES))
ok = 0
t0 = time.time()
for q in QUERIES:
    r = get_record(q)
    smi = find_smiles(q)
    ok += bool(smi)
    print("  %-3s %-10s 主名=%-14s %-34s %s"
          % ("OK" if smi else "XX", q, (r["name"] if r else "-"),
             (smi if smi else "-"), (r["source"] if r else "")))
dt = time.time() - t0
print("  -> 命中 %d/%d，共 %.3f s（平均 %.1f ms）" % (ok, len(QUERIES), dt, 1000 * dt / len(QUERIES)))

print("\n【6. 模糊查询性能】")
for q in ["氯", "酸", "醇", "不存在的名字xyzzy", "苯环"]:
    t = time.time()
    r = search(q, limit=20)
    print("  %-16s 命中 %2d 条  %.0f ms" % (q, len(r), 1000 * (time.time() - t)))

print("\n【7. 别名样例：阿司匹林（CID 2244）】")
for a, k in aliases_of("阿司匹林", limit=18):
    print("  %-14s [%s]" % (a, k))

print("\n【8. 别名样例：对乙酰氨基酚（扑热息痛）】")
for a, k in aliases_of("对乙酰氨基酚", limit=15):
    print("  %-14s [%s]" % (a, k))
print("=" * 82)
