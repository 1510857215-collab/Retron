# -*- coding: utf-8 -*-
"""探测 v10：KET 旧版文本格式（data.content/pos）加载测试"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9240
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k10"
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

        # 旧格式：data.content 为「字符串化的 lexical JSON」，pos 为 4 角点
        lexical = json.dumps({
            "root": {
                "children": [{
                    "children": [{"text": "条件：室温搅拌2h", "type": "text"}],
                    "type": "paragraph"
                }],
                "type": "root"
            }
        }, ensure_ascii=False)
        ket_old = {
            "ket_version": "2.0.0",
            "root": {"nodes": [{"$ref": "mol0"}, {"$ref": "text0"}],
                     "connections": [], "templates": []},
            "mol0": {"type": "molecule",
                     "atoms": [{"label": "C", "location": [0, 0, 0]},
                               {"label": "O", "location": [1.5, 0, 0]}],
                     "bonds": [{"type": 1, "atoms": [0, 1]}]},
            "text0": {
                "type": "text",
                "data": {
                    "content": lexical,
                    "position": {"x": 0, "y": -3, "z": 0},
                    "pos": [{"x": 0, "y": -3, "z": 0},
                            {"x": 0, "y": -4.2, "z": 0},
                            {"x": 8, "y": -4.2, "z": 0},
                            {"x": 8, "y": -3, "z": 0}]
                }
            }
        }
        arg = json.dumps(json.dumps(ket_old, ensure_ascii=False), ensure_ascii=False)
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'ok';}).catch(function(e){return 'ERR:'+String(e).slice(0,180);})"
               % arg, awaitp=True)
        print("T-A 旧格式加载:", r)
        time.sleep(2)
        back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("回读长度:", len(back))
        print("含 mol:", ('mol0' in back))
        print("含 text:", ('text' in back.lower()))
        if 'text' in back.lower():
            j = back.lower().find('"text"')
            if j < 0:
                j = back.lower().find('text0')
            print("text 片段:", back[max(0, j - 150):j + 700])
        print("getSmiles:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))
        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
