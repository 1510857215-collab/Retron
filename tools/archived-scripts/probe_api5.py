# -*- coding: utf-8 -*-
"""探测 v5：正确 schema 的 KET 文本节点加载测试"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9235
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k5"
BASE = "http://127.0.0.1:8765"


def main():
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT,
         "--user-data-dir=" + PROFILE,
         "--no-first-run", "--no-default-browser-check",
         "--window-size=1680,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        targets = None
        for _ in range(30):
            time.sleep(1)
            try:
                targets = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % PORT, timeout=5))
                if targets:
                    break
            except Exception:
                pass
        page = [t for t in targets if t.get("type") == "page"][0]
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=180)
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
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/board.html"})
        print("打开画板，等 15 秒…")
        time.sleep(15)
        for _ in range(20):
            if ev("typeof window.ketcher") == "object":
                break
            time.sleep(2)

        print("=== 正确 schema 的 KET（mol + text）加载 ===")
        ket = {
            "root": {
                "nodes": [{"$ref": "mol0"}, {"$ref": "text0"}],
                "connections": [],
                "templates": []
            },
            "mol0": {
                "type": "molecule",
                "atoms": [
                    {"label": "C", "location": [0, 0, 0]},
                    {"label": "O", "location": [1.5, 0, 0]}
                ],
                "bonds": [{"type": 1, "atoms": [0, 1]}]
            },
            "text0": {
                "type": "text",
                "boundingBox": {"x": 0, "y": -3, "z": 0, "width": 240, "height": 22},
                "paragraphs": [{"parts": [{"text": "条件：室温搅拌 2 小时（测试文本）"}]}]
            }
        }
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'ok';}).catch(function(e){return 'err:'+String(e).slice(0,200);})"
               % json.dumps(json.dumps(ket)), awaitp=True)
        print("加载:", r)
        time.sleep(2)
        back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("回读 getKet 长度:", len(back))
        print("回读含 text 节点:", ('"text0"' in back) or ('text' in back.lower()))
        idx = back.find('"text"')
        if idx >= 0:
            print("text 片段:", back[idx:idx + 400])
        print("回读 getSmiles:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))

        # 截图确认文本可见
        try:
            shot = cmd("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data", "")
            if data:
                with open(r"C:\Users\zzl\Desktop\hx\logs\ket_text_test.png", "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图: logs/ket_text_test.png")
        except Exception as e:
            print("截图失败:", e)

        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
