# -*- coding: utf-8 -*-
"""定量验证：在 USPTO_Condition 留出测试集上评估先例检索的 Top-k 命中率。

索引仅由 train/val 构建（测试集未参与），随机抽样评估。
注意：该数据集按 8:1:1 随机切分，测试集中可能与训练集存在近似重复反应，
故命中率为"乐观估计"，仅用于横向比较与合理性判断。

用法：
  tools/venv-conditions/Scripts/python.exe engine/conditions/validate_retrieval.py [样本数]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
INDEX_DIR = os.path.join(_ROOT, "data", "conditions", "index")
TEST_CSV = os.path.join(_ROOT, "data", "conditions", "source", "test.csv")


def ranks_for(cols, Xu64, popX, react, prod, topk=5):
    from drfp import DrfpEncoder
    q = np.asarray(DrfpEncoder.encode(f"{react}>>{prod}", n_folded_length=2048,
                                      min_radius=0, radius=3, rings=True), dtype=np.uint8)
    q_u64 = np.packbits(q, axis=1).reshape(-1).view(np.uint64)
    popq = int(np.bitwise_count(q_u64).sum())
    inter = np.bitwise_count(Xu64 & q_u64).sum(axis=1).astype(np.int32)
    union = popX + popq - inter
    sim = inter / np.maximum(union, 1)
    k = min(topk, sim.shape[0])
    part = np.argpartition(-sim, k - 1)[:k]
    part = part[np.argsort(-sim[part])]
    return part.tolist(), float(sim[part[0]])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    packed = np.load(os.path.join(INDEX_DIR, "fp_packed.npy"))
    Xu64 = packed.reshape(packed.shape[0], -1, 8).view(np.uint64).reshape(packed.shape[0], -1)
    popX = np.bitwise_count(Xu64).sum(axis=1).astype(np.int32)
    meta = pd.read_parquet(os.path.join(INDEX_DIR, "meta.parquet"))
    cols = {c: meta[c].tolist() for c in ("reagent1", "solvent1", "catalyst1")}
    test = pd.read_csv(TEST_CSV)
    test = test.dropna(subset=["canonical_rxn"]).sample(n=min(n, len(test)), random_state=42)

    m = {"reagent1": [], "solvent1": [], "catalyst1": []}
    hit_any = 0
    sims = []
    for _, row in test.iterrows():
        rxn = row["canonical_rxn"]
        try:
            react, prod = rxn.split(">>")
        except ValueError:
            continue
        idx, tsim = ranks_for(cols, Xu64, popX, react, prod, 5)
        sims.append(tsim)
        got_any = False
        for col in m:
            truth = row[col]
            if pd.isna(truth) or str(truth).strip() == "":
                continue
            cands = [str(cols[col][i]) for i in idx]
            m[col].append(1 if str(truth) in cands else 0)
            if str(truth) in cands:
                got_any = True
        hit_any += 1 if got_any else 0

    out = {"n_eval": int(len(test)), "mean_top1_sim": round(float(np.mean(sims)), 3)}
    for col, vals in m.items():
        out[col + "_hit@5"] = round(float(np.mean(vals)), 3) if vals else None
        out[col + "_n"] = len(vals)
    out["any_condition_hit@5"] = round(hit_any / max(1, len(test)), 3)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    with open(os.path.join(_ROOT, "data", "conditions", "测试", "validate_retrieval.json"),
              "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
