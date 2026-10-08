# -*- coding: utf-8 -*-
"""一次性离线建库脚本：USPTO_Condition -> DRFP 反应指纹 + 条件元数据。

产物（全部落在 data/conditions/index/，供 recommend.py 离线加载）：
  - fp_packed.npy   反应指纹（np.packbits 打包，uint8, shape=(N,256)）
  - meta.parquet    每行条件：canonical_rxn/catalyst1/solvent1/solvent2/reagent1/reagent2
  - meta.json       指纹参数、行数、数据来源

依赖：rdkit, drfp, numpy, pandas, pyarrow, tqdm（均在 tools/venv-conditions）
用法：
  tools/venv-conditions/Scripts/python.exe engine/conditions/build_index.py
"""
import json
import os
import sys
import time
import multiprocessing as mp

import numpy as np
import pandas as pd
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC_DIR = os.path.join(ROOT, "data", "conditions", "source")
OUT_DIR = os.path.join(ROOT, "data", "conditions", "index")

# 指纹参数：必须与 recommend.py 完全一致
DRFP_KW = dict(n_folded_length=2048, min_radius=0, radius=3, rings=True)
CHUNK = 4000


def _valid_rxn(rxn):
    try:
        r, p = rxn.split(">>")
    except ValueError:
        return False
    for side in (r, p):
        for s in side.split("."):
            if s and Chem.MolFromSmiles(s) is None:
                return False
    return True


def _encode_chunk(smiles_list):
    """子进程：编码一个 chunk，返回打包后的 uint8 数组 (n,256)。"""
    from drfp import DrfpEncoder

    arr = np.asarray(DrfpEncoder.encode(smiles_list, **DRFP_KW), dtype=np.uint8)
    return np.packbits(arr, axis=1)


def build():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)

    frames = []
    for name in ("train.csv", "val.csv"):
        fp = os.path.join(SRC_DIR, name)
        if not os.path.exists(fp):
            print(f"[warn] 缺失 {fp}，跳过")
            continue
        df = pd.read_csv(fp, usecols=[
            "canonical_rxn", "catalyst1", "solvent1", "solvent2",
            "reagent1", "reagent2",
        ])
        df["dataset"] = name.split(".")[0]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    print(f"[info] 原始行数 {len(df)}")
    df = df.dropna(subset=["canonical_rxn"])
    df = df.drop_duplicates(subset=["canonical_rxn"]).reset_index(drop=True)
    print(f"[info] 去重后 {len(df)}")

    rxns = df["canonical_rxn"].tolist()
    valid = np.array([_valid_rxn(x) for x in rxns])
    df = df[valid].reset_index(drop=True)
    rxns = df["canonical_rxn"].tolist()
    print(f"[info] RDKit 校验通过 {len(df)}")

    chunks = [rxns[i:i + CHUNK] for i in range(0, len(rxns), CHUNK)]
    nproc = max(1, min(12, (os.cpu_count() or 4) - 1))
    print(f"[info] 并行编码 {len(chunks)} 个 chunk，进程数={nproc}")
    parts = []
    with mp.Pool(nproc) as pool:
        for i, part in enumerate(pool.imap(_encode_chunk, chunks), 1):
            parts.append(part)
            if i % 10 == 0 or i == len(chunks):
                print(f"   编码进度 {i}/{len(chunks)}  ({time.time()-t0:.0f}s)")
    fp_packed = np.vstack(parts).astype(np.uint8)
    assert fp_packed.shape == (len(df), 256), fp_packed.shape

    np.save(os.path.join(OUT_DIR, "fp_packed.npy"), fp_packed)
    df.to_parquet(os.path.join(OUT_DIR, "meta.parquet"), index=False)
    json.dump({
        "count": int(len(df)),
        "fp_params": DRFP_KW,
        "packed_bytes": int(fp_packed.shape[1]),
        "sources": [
            "https://huggingface.co/datasets/weidawang/USPTO_Condition (MIT)",
        ],
        "columns": ["canonical_rxn", "catalyst1", "solvent1", "solvent2",
                    "reagent1", "reagent2", "dataset"],
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)
    print(f"[done] {len(df)} 行，用时 {time.time()-t0:.0f}s -> {OUT_DIR}")


if __name__ == "__main__":
    mp.freeze_support()
    build()
