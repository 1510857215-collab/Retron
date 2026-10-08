# -*- coding: utf-8 -*-
"""
engine/forward/predict_cli.py —— 正向反应预测命令行入口（供主服务跨环境调用）
=====================================================================
用法：
  python predict_cli.py "<反应物SMILES>" ["条件文本"]
    反应物SMILES：点分隔，如 "CC(=O)OC(C)=O.O=C(O)c1ccccc1O"
    条件文本：可选

输出：stdout 一行 JSON（同 predict() 返回格式）
  {"ok": true, "products": [{"smiles": "...", "score": 0.91}, ...], "engine": "..."}
  {"ok": false, "error": "..."}

退出码：ok=0；失败=1（JSON 仍会打印到 stdout）

【必须用专用环境运行】
  tools\\venv-forward\\Scripts\\python.exe predict_cli.py ...
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv):
    reactants = argv[1] if len(argv) > 1 else None
    conditions = argv[2] if len(argv) > 2 else None

    # 未给出反应物时，尝试从 stdin 读一行（便于管道调用）
    if not reactants:
        try:
            line = sys.stdin.readline()
            reactants = line.strip() if line else None
        except Exception:
            reactants = None

    if not reactants:
        _emit({"ok": False, "error": "缺少反应物 SMILES。用法：predict_cli.py \"<SMILES>\" [\"条件文本\"]"})
        return 1

    try:
        from predict import predict
        res = predict(reactants, conditions)
    except Exception as e:
        res = {"ok": False, "error": "调用预测引擎失败：%s: %s" % (type(e).__name__, e)}

    if not isinstance(res, dict):
        res = {"ok": False, "error": "预测返回格式异常"}

    _emit(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
