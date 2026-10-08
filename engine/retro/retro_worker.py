#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
retro_worker.py —— 逆合成常驻 worker（供 app/server.py 调用）
================================================================
作用：把 AiZynthFinder 的模型与化合物库**只加载一次**，之后按行受理请求，
      避免每次搜索都重新加载（加载约 1.3GB，重载非常慢）。

通信协议（JSON Lines）：
  stdin  每行一个请求：{"smiles": "CC(=O)Oc1ccccc1C(=O)O", "max_steps": 3,
                        "start_material": "起点A的SMILES或空"}
  stdout 每行一个响应：{"ok": true, ...}（find_routes 的结果，路线最多保留 5 条）
        特殊：{"action": "ping"} -> {"ok": true, "pong": true}
  启动完成后先输出一行：{"ready": true} 或 {"ready": false, "error": "..."}

【重要】必须用专用环境运行：
  C:\\Users\\zzl\\Desktop\\hx\\tools\\venv-retro\\Scripts\\python.exe
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 原子映射编号清理：[C:1] -> [C]，[cH3:5] -> [cH3]（让展示干净）
_MAP_RE = re.compile(r":\d+\]")


def _clean_smiles_in(obj):
    """递归清理 smiles 字段里的原子映射编号（不动其他原始字段）。"""
    if isinstance(obj, dict):
        s = obj.get("smiles")
        if isinstance(s, str) and ":" in s:
            obj["smiles"] = _MAP_RE.sub("]", s)
        for v in obj.values():
            _clean_smiles_in(v)
    elif isinstance(obj, list):
        for v in obj:
            _clean_smiles_in(v)


def _emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    try:
        from retro_run import find_routes, _get_finder
        _get_finder()  # 预热：加载模型与 1.3GB 化合物库（1~3 分钟）
        _emit({"ready": True})
    except Exception as e:
        _emit({"ready": False, "error": "%s: %s" % (type(e).__name__, e)})
        return

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            _emit({"ok": False, "error": "请求格式错误（非 JSON）"})
            continue

        if req.get("action") == "ping":
            _emit({"ok": True, "pong": True})
            continue

        smiles = (req.get("smiles") or "").strip()
        if not smiles:
            _emit({"ok": False, "error": "缺少 smiles 字段"})
            continue
        try:
            max_steps = int(req.get("max_steps") or 3)
        except Exception:
            max_steps = 3

        save_dir = (req.get("save_dir") or "").strip() or None
        start_material = (req.get("start_material") or "").strip() or None
        try:
            res = find_routes(smiles, max_steps=max_steps, save_dir=save_dir,
                              start_material=start_material)
        except Exception as e:
            res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}

        # 控制响应体积：路线最多保留 5 条；同时清理 smiles 里的原子映射编号
        if isinstance(res, dict) and isinstance(res.get("routes"), list):
            for r in res["routes"]:
                _clean_smiles_in(r)
            res["routes"] = res["routes"][:5]
            res["num_routes_shown"] = len(res["routes"])
            # 起点约束的序号列表需与截断后的 routes 保持一致
            if isinstance(res.get("start_material_routes"), list):
                n = res["num_routes_shown"]
                res["start_material_routes"] = [
                    i for i in res["start_material_routes"] if i < n]

        _emit(res)


if __name__ == "__main__":
    main()
