# -*- coding: utf-8 -*-
"""
起点约束 三项测试（单进程串行，避免重复加载 1.3GB 化合物库）
用法: tools/venv-retro/Scripts/python.exe tools/tmp/retro2_test_adjust.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine", "retro"))

from retro_run import find_routes  # noqa: E402

TARGET = "CC(=O)Oc1ccccc1C(=O)O"      # 阿司匹林
START_OK = "O=C(O)c1ccccc1O"          # 水杨酸
START_BAD = "c1ccccc1"                # 苯


def leaf_smiles(route):
    out = []
    stack = [route]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        kids = node.get("children") or []
        if (node.get("is_chemical") or node.get("type") == "mol") and not kids:
            out.append(node.get("smiles"))
        stack.extend(kids)
    return out


def brief(res):
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}
    d = {
        "ok": True,
        "is_solved": res["is_solved"],
        "num_routes": res["num_routes"],
    }
    for k in ("start_material", "num_routes_found",
              "start_material_routes", "start_material_hint"):
        if k in res:
            d[k] = res[k]
    if "routes" in res and res["routes"]:
        d["route0_with_start"] = res["routes"][0].get("with_start")
        d["route0_leaf_smiles"] = leaf_smiles(res["routes"][0])
    return d


def run(title, smiles, start=None, save_dir=None):
    print("=" * 70)
    print("[%s] smiles=%s start_material=%r" % (title, smiles, start))
    res = find_routes(smiles, max_steps=3, save_dir=save_dir,
                      start_material=start)
    print(json.dumps(brief(res), ensure_ascii=False, indent=2))
    return res


def main():
    out = {}

    # a. 回归：不带 start_material
    out["a"] = run("a 回归(无起点)", TARGET,
                   save_dir=os.path.join(ROOT, "data", "retro", "测试结果", "回归_无起点"))

    # b. 起点约束成功：水杨酸 -> 阿司匹林
    out["b"] = run("b 起点成功(水杨酸)", TARGET, START_OK,
                   save_dir=os.path.join(ROOT, "data", "retro", "测试结果", "起点_水杨酸"))

    # c. 起点约束无结果：苯 -> 阿司匹林
    out["c"] = run("c 起点无结果(苯)", TARGET, START_BAD,
                   save_dir=os.path.join(ROOT, "data", "retro", "测试结果", "起点_苯"))

    # 汇总判定
    print("=" * 70)
    print("判定：")
    print("  a 返回多条路线:", out["a"].get("num_routes", 0) > 1)
    b = out["b"]
    one_step_hit = False
    for r in b.get("routes", []):
        ls = leaf_smiles(r)
        if any(l and "c1ccccc1O" in l for l in ls):
            one_step_hit = True
    print("  b 有经起点路线:", bool(b.get("start_material_routes")),
          "| 出现水杨酸叶子:", one_step_hit)
    print("  c 兜底提示存在:", "start_material_hint" in out["c"])

    with open(os.path.join(HERE, "retro2_test_out.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
