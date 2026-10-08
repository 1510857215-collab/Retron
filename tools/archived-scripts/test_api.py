#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过本地服务 API 端到端测试逆合成（模拟网页点按钮的完整链路）。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=60))


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=60))


def main():
    print("=== 1) 提交逆合成任务（阿司匹林，最多 3 步）===")
    r = post("/api/retro", {"smiles": "CC(=O)Oc1ccccc1C(=O)O", "max_steps": 3})
    print("响应:", r)
    if not r.get("ok"):
        print("提交失败！")
        return 1
    tid = r["task_id"]

    print("=== 2) 轮询任务状态 ===")
    t0 = time.time()
    while True:
        time.sleep(4)
        s = get("/api/retro/status?task_id=" + tid)
        el = round(time.time() - t0, 1)
        print("  [%6.1fs] state = %s" % (el, s.get("state")))
        if s.get("state") != "running":
            break
        if el > 600:
            print("超时退出")
            return 1

    if s.get("state") == "error":
        print("任务出错:", s.get("error"))
        return 1

    res = s.get("result") or {}
    print("=== 3) 结果 ===")
    print("找到完整路线:", res.get("is_solved"))
    print("路线数量:", res.get("num_routes"))
    routes = res.get("routes") or []
    if routes:
        r0 = routes[0]
        print("第 1 条路线的字段:", list(r0.keys())[:12])
        # 打印前两条路线的关键内容（截断展示）
        for i, rt in enumerate(routes[:2]):
            text = json.dumps(rt, ensure_ascii=False)
            print("--- 路线 %d（截断 900 字符）---" % (i + 1))
            print(text[:900])
    print("=== 完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
