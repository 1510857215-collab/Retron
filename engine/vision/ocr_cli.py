#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ocr_cli.py —— 图片识别引擎的命令行包装（供 app/server.py 跨环境调用）
======================================================================
【重要】必须用独立环境运行：
    C:\\Users\\zzl\\Desktop\\hx\\tools\\venv-vision\\Scripts\\python.exe

用法:  python ocr_cli.py <图片路径>
输出:  stdout 最后一行 JSON：
    成功 {"ok": true, "smiles": "...", "engine": "..."}
    失败 {"ok": false, "error": "中文错误信息"}
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "缺少图片路径参数"}, ensure_ascii=False))
        return 1
    image_path = sys.argv[1]
    try:
        from structure_ocr import recognize
        res = recognize(image_path)
    except Exception as e:
        res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    if not isinstance(res, dict):
        res = {"ok": False, "error": "识别引擎返回了异常格式"}
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
