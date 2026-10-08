# -*- coding: utf-8 -*-
"""探查 ketcher JS 的漏译项与中文存储格式"""
import re

p = r"C:/Users/zzl/Desktop/hx/web/ketcher/ketcher-app.js"
data = open(p, encoding="utf-8", errors="replace").read()

print("=== 1) 中文存储格式 ===")
print("转义码 u53d6 出现次数:", data.count("u53d6"))
print("转义码 u6d88 出现次数:", data.count("u6d88"))
print("直接中文字符【取消】出现次数:", data.count("取消"))

print()
print("=== 2) Single Bond 上下文 ===")
ms = list(re.finditer("Single Bond", data))
print("出现次数:", len(ms))
for m in ms[:8]:
    i = m.start()
    print(repr(data[max(0, i - 90):i + 90]))
    print("---")

print()
print("=== 3) 其他常用词检查 ===")
for w in ["Double Bond", "Triple Bond", "Charge", "Undo", "Redo", "Add", "Delete"]:
    print("%-14s -> %d" % (w, data.count(w)))
