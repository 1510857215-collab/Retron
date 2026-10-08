# -*- coding: utf-8 -*-
"""自测：对 6 张测试图跑 structure_ocr.recognize()，与原始 SMILES 规范化比对。

运行（必须用 venv-vision）：
    "C:\\Users\\zzl\\Desktop\\hx\\tools\\venv-vision\\Scripts\\python.exe" vision_run_tests.py [引擎]

输出：
    data\\vision\\测试\\识别结果_<引擎>.json
    data\\vision\\测试\\识别结果_<引擎>.md
"""
import os
import sys
import json
import time

PROJECT_ROOT = r"C:\Users\zzl\Desktop\hx"
sys.path.insert(0, os.path.join(PROJECT_ROOT, "engine", "vision"))

import structure_ocr  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit import RDLogger  # noqa: E402

RDLogger.DisableLog("rdApp.*")

TEST_DIR = os.path.join(PROJECT_ROOT, "data", "vision", "测试")

# (显示名, 图片文件名, 原始 SMILES)
MOLECULES = [
    ("阿司匹林",     "阿司匹林.png",       "CC(=O)Oc1ccccc1C(=O)O"),
    ("咖啡因",       "咖啡因.png",         "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"),
    ("苯",           "苯.png",             "c1ccccc1"),
    ("布洛芬",       "布洛芬.png",         "CC(C)Cc1ccc(C(C)C(=O)O)cc1"),
    ("对乙酰氨基酚", "对乙酰氨基酚.png",   "CC(=O)NC1=CC=C(O)C=C1"),
    ("水杨酸",       "水杨酸.png",         "O=C(O)c1ccccc1O"),
    ("苯甲酸",       "苯甲酸.png",         "OC(=O)c1ccccc1"),
    ("烟酸",         "烟酸.png",           "OC(=O)c1cccnc1"),
    ("乙酸乙酯",     "乙酸乙酯.png",       "CCOC(C)=O"),
    ("萘",           "萘.png",             "c1ccc2ccccc2c1"),
    ("烟酰胺",       "烟酰胺.png",         "NC(=O)c1cccnc1"),
    ("葡萄糖",       "葡萄糖.png",         "OCC1OC(O)C(O)C(O)C1O"),
]


def canon(smiles: str):
    """用 RDKit 规范化 SMILES；失败返回 None。"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol)
    except Exception:
        return None


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else None

    rows = []
    for name, fname, orig in MOLECULES:
        img = os.path.join(TEST_DIR, fname)
        t0 = time.time()
        res = structure_ocr.recognize(img, engine)
        dt = time.time() - t0

        if res.get("ok"):
            got = res["smiles"]
            c_got = canon(got)
            c_orig = canon(orig)
            match = (c_got is not None and c_got == c_orig)
            rows.append({
                "分子": name, "原SMILES": orig, "识别SMILES": got,
                "规范化后一致": bool(match), "耗时秒": round(dt, 2),
                "错误": "",
            })
        else:
            rows.append({
                "分子": name, "原SMILES": orig, "识别SMILES": "",
                "规范化后一致": False, "耗时秒": round(dt, 2),
                "错误": res.get("error", ""),
            })
        print(f"{name}: ok={res.get('ok')} 一致={rows[-1]['规范化后一致']} "
              f"识别={rows[-1]['识别SMILES']} 错误={rows[-1]['错误']}")

    # 额外：超大图缩放路径测试（仅第一轮跑一次）
    big = os.path.join(TEST_DIR, "阿司匹林_超大图.png")
    if os.path.exists(big):
        t0 = time.time()
        res = structure_ocr.recognize(big, engine)
        dt = time.time() - t0
        got = res.get("smiles", "")
        match = (canon(got) == canon("CC(=O)Oc1ccccc1C(=O)O")) if res.get("ok") else False
        rows.append({
            "分子": "阿司匹林(1600px超大图)", "原SMILES": "CC(=O)Oc1ccccc1C(=O)O",
            "识别SMILES": got, "规范化后一致": bool(match),
            "耗时秒": round(dt, 2), "错误": res.get("error", ""),
        })
        print(f"超大图: ok={res.get('ok')} 一致={match} 识别={got} 错误={res.get('error','')}")

    eng_tag = engine or structure_ocr.DEFAULT_ENGINE
    n_ok = sum(1 for r in rows if r["规范化后一致"])
    print(f"\n=== 汇总[{eng_tag}]：{n_ok}/{len(rows)} 正确 ===")

    out_json = os.path.join(TEST_DIR, f"识别结果_{eng_tag}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"engine": eng_tag, "rows": rows,
                   "correct": n_ok, "total": len(rows)}, f,
                  ensure_ascii=False, indent=2)
    print("已写入", out_json)


if __name__ == "__main__":
    main()
