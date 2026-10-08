# -*- coding: utf-8 -*-
"""Electron 外壳验收：窗口加载 / 引擎自启动 / 关闭清理"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

DEBUG_PORT = 9337
BASE = "http://127.0.0.1:8765"


def get_targets():
    try:
        return json.load(urllib.request.urlopen(
            "http://127.0.0.1:%d/json" % DEBUG_PORT, timeout=5))
    except Exception:
        return None


def main():
    print("等待 Electron 调试端口…")
    ok = False
    for _ in range(30):
        time.sleep(2)
        t = get_targets()
        if t:
            ok = True
            break
    if not ok:
        print("FAIL: 调试端口未就绪")
        return 1
    print("目标列表:", json.dumps([{k: x.get(k) for k in ('type', 'title', 'url')} for x in get_targets()],
                                ensure_ascii=False)[:400])

    page = None
    for x in get_targets():
        if x.get("type") == "page" and "devtools" not in x.get("url", ""):
            page = x
            break
    if not page:
        print("FAIL: 没有窗口 target")
        return 1
    print("窗口 URL:", page.get("url"), "| 初始标题:", page.get("title"))

    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120,
                                     suppress_origin=True)
    mid = [0]

    def cmd(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid[0]:
                return msg

    def ev(expr, awaitp=False):
        r = cmd("Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": awaitp})
        res = (r.get("result") or {}).get("result") or {}
        return res.get("value", {"__err__": str(r)[:300]})

    cmd("Runtime.enable")

    # 等页面从 loading 切到主界面（后端就绪后）
    print("等待引擎就绪、窗口加载主界面（最长 3 分钟）…")
    loaded = False
    t0 = time.time()
    while time.time() - t0 < 180:
        time.sleep(4)
        url_now = ""
        for x in get_targets() or []:
            if x.get("type") == "page" and "devtools" not in x.get("url", ""):
                url_now = x.get("url", "")
        if url_now.startswith(BASE):
            loaded = True
            break
        print("  [%ds] 当前 URL: %s" % (int(time.time() - t0), url_now[:60]))
    print("窗口已加载主界面:", loaded)

    # 页面元素检查
    if loaded:
        time.sleep(3)
        r = ev("(function(){return JSON.stringify({title: document.title, tabs: document.querySelectorAll('.tab').length,"
               "board: !!document.getElementById('board'), logo: (document.querySelector('.logo')||{}).textContent});})()")
        print("页面检查:", r)

    # 显示窗口（如果最小化了）
    ev("'ok'")

    # ---- 关闭窗口，验证引擎清理 ----
    print("发送 window.close()，测试退出清理…")
    ev("window.close(); 'closing'")
    time.sleep(6)

    # 检查窗口 target 消失
    tg = get_targets()
    n_windows = len([x for x in (tg or []) if x.get("type") == "page"]) if tg else 0
    print("关闭后剩余窗口数:", n_windows)

    # 检查 8765 是否释放（引擎被杀）
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    busy = (s.connect_ex(("127.0.0.1", 8765)) == 0)
    s.close()
    time.sleep(3)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2.settimeout(2)
    busy2 = (s2.connect_ex(("127.0.0.1", 8765)) == 0)
    s2.close()
    print("8765 端口（关闭 6 秒后）:", "仍在监听" if busy2 else "已释放 ✅")

    # 检查 pythonw 残留
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=30)
        lines = [l for l in (out.stdout or "").splitlines() if l.strip()]
        n = max(0, len(lines) - 1)
        print("pythonw 进程数:", n)
    except Exception as e:
        print("进程检查失败:", e)

    print("=== 验收结束 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
