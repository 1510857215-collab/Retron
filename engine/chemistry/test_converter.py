#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_converter.py —— 转换引擎自测脚本

不依赖任何测试框架，纯标准库断言，直接用项目 venv 运行：

    tools\\venv\\Scripts\\python.exe test_converter.py

覆盖 convert() 的每个方向（≥2 用例/方向）与错误分支，合计 ≥12 个用例。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from converter import convert  # noqa: E402

# (说明, 输入, input_type, target, 期望输出 或 None 表示只检查 ok=True；error_kw 检查 ok=False 的提示关键词)
CASES = [
    # ---- name_zh -> smiles ----
    ("阿司匹林 -> smiles", "阿司匹林", "name_zh", "smiles", "CC(=O)Oc1ccccc1C(=O)O", None),
    ("苯 -> smiles", "苯", "name_zh", "smiles", "c1ccccc1", None),
    ("乙醇 -> smiles", "乙醇", "name_zh", "smiles", "CCO", None),
    # ---- name_zh -> formula ----
    ("阿司匹林 -> formula", "阿司匹林", "name_zh", "formula", "C9H8O4", None),
    ("乙醇 -> formula", "乙醇", "name_zh", "formula", "C2H6O", None),
    # ---- name_zh -> inchi ----
    ("乙醇 -> inchi", "乙醇", "name_zh", "inchi", None, None),  # 只验 ok
    # ---- smiles -> formula ----
    ("CCO -> formula", "CCO", "smiles", "formula", "C2H6O", None),
    ("苯 -> formula", "c1ccccc1", "smiles", "formula", "C6H6", None),
    # ---- smiles -> inchi ----
    ("CCO -> inchi", "CCO", "smiles", "inchi", None, None),
    # ---- smiles -> name_zh（规范化反查）----
    ("苯结构 -> name_zh", "c1ccccc1", "smiles", "name_zh", "苯", None),
    ("阿司匹林结构(异构写法) -> name_zh", "CC(=O)Oc1ccccc1C(=O)O", "smiles", "name_zh", "阿司匹林", None),
    ("阿司匹林结构(PubChem写法) -> name_zh", "CC(=O)OC1=CC=CC=C1C(=O)O", "smiles", "name_zh", "阿司匹林", None),
    # ---- name_en -> smiles（OPSIN 通路；OPSIN 只认系统命名，不认 aspirin 这类俗名）----
    ("2,4-dinitrotoluene -> smiles", "2,4-dinitrotoluene", "name_en", "smiles", None, None),
    ("2-methylbutane -> smiles", "2-methylbutane", "name_en", "smiles", "CCC(C)C", None),
    ("acetylsalicylic acid -> smiles", "acetylsalicylic acid", "name_en", "smiles",
     "CC(=O)Oc1ccccc1C(=O)O", None),
    # ---- name_en -> name_zh（OPSIN 出结构，再走词典反查）----
    ("acetylsalicylic acid -> name_zh", "acetylsalicylic acid", "name_en", "name_zh", "阿司匹林", None),
    ("benzoic acid -> name_zh", "benzoic acid", "name_en", "name_zh", "苯甲酸", None),
    # ---- 错误分支 ----
    ("不存在的名字", "哈哈不存在的名字", "name_zh", "smiles", None, "没有找到"),
    ("分子式输入被拒", "C6H6", "formula", "smiles", None, "分子式"),
    ("非法 SMILES", "C(((", "smiles", "formula", None, "无法识别"),
    ("OPSIN 无法解析", "zzzznotaname", "name_en", "smiles", None, "OPSIN 无法解析"),
    ("不支持的目标", "CCO", "smiles", "name_en", None, "不支持的目标"),
]


def main():
    total = passed = 0
    print("=" * 78)
    print("转换引擎自测")
    print("=" * 78)

    for desc, text, it, tg, expect, err_kw in CASES:
        total += 1
        r = convert(text, it, tg)
        ok = True
        detail = ""

        if err_kw is not None:
            # 期望失败
            if r.get("ok"):
                ok = False
                detail = "期望失败，却返回成功：%r" % r
            elif err_kw not in r.get("error", ""):
                ok = False
                detail = "错误提示未含关键词 %r：%s" % (err_kw, r.get("error"))
            else:
                detail = "失败(符合预期)：%s" % r["error"]
        else:
            if not r.get("ok"):
                ok = False
                detail = "期望成功，却返回失败：%s" % r.get("error")
            elif expect is not None and r["output"] != expect:
                ok = False
                detail = "输出不符：得到 %r 期望 %r" % (r["output"], expect)
            else:
                detail = "%s   <%s>" % (r["output"], r["source"])

        passed += 1 if ok else 0
        print("[%s] %-34s : %s" % ("PASS" if ok else "FAIL", desc, detail))

    print("-" * 78)
    print("合计 %d 项，通过 %d 项，失败 %d 项" % (total, passed, total - passed))
    print("=" * 78)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
