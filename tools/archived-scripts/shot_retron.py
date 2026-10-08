# -*- coding: utf-8 -*-
"""给 Retron 窗口拍一张"成品照"（CDP 截图），然后关闭窗口。"""
import base64
import json
import sys
import time
import urllib.request

import websocket

PORT = 9335
BASE = "http://127.0.0.1:8765"


def targets():
    try:
        return json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=5))
    except Exception:
        return None


def main():
    ok = False
    for _ in range(40):
        time.sleep(2)
        t = targets()
        if t and any(x.get("type") == "page" and x.get("url", "").startswith(BASE) for x in t):
            ok = True
            break
    if not ok:
        print("FAIL: 窗口未加载主界面")
        return 1
    page = [x for x in targets() if x.get("type") == "page"][0]
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120,
                                     suppress_origin=True)
    mid = [0]

    def cmd(m, p=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": m, "params": p or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid[0]:
                return r

    time.sleep(5)  # 等画板加载完成
    shot = cmd("Page.captureScreenshot", {"format": "png"})
    data = shot.get("result", {}).get("data", "")
    if data:
        with open(r"C:\Users\zzl\Desktop\hx\logs\retron_window.png", "wb") as f:
            f.write(base64.b64decode(data))
        print("截图已保存: logs/retron_window.png")
    cmd("Runtime.evaluate", {"expression": "window.close()", "returnByValue": True})
    print("已关闭窗口")
    return 0


if __name__ == "__main__":
    sys.exit(main())
