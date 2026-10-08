# -*- coding: utf-8 -*-
"""跨环境调用入口：向 stdout 输出一行 JSON（格式同 recommend() 返回值）。

用法（须使用本引擎独立的解释器）：
    tools/venv-conditions/Scripts/python.exe engine/conditions/recommend_cli.py "反应物>>产物"
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 保证中文以 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main(argv):
    if len(argv) < 2 or not argv[1].strip():
        print(json.dumps({"ok": False, "error": "用法：recommend_cli.py \"反应物>>产物\""},
                         ensure_ascii=False))
        return 2
    rxn = argv[1].strip()
    try:
        from recommend import recommend
        res = recommend(rxn)
    except Exception as e:  # noqa
        res = {"ok": False, "error": f"CLI 执行异常：{type(e).__name__}: {e}"}
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
