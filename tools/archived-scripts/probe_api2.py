# -*- coding: utf-8 -*-
"""探测 Ketcher API v2：原型方法 / getKet / KET 文本节点"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9232
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k2"
BASE = "http://127.0.0.1:8765"


def main():
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT,
         "--user-data-dir=" + PROFILE,
         "--no-first-run", "--no-default-browser-check", "about:blank"],
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

        print("=== A) 原型链上的方法 ===")
        lst = ev("Object.getOwnPropertyNames(Object.getPrototypeOf(window.ketcher)).join(', ')")
        print(str(lst)[:800])
        print()
        print("=== B) standalone 对象 ===")
        print(str(ev("window.ketcher.standalone ? Object.keys(window.ketcher.standalone).join(', ') : 'no'"))[:400])
        print()
        print("=== C) getKet 存在性 ===")
        print(ev("typeof window.ketcher.getKet"))

        print()
        print("=== D) getKet 空画板输出格式样例 ===")
        ev("Promise.resolve(window.ketcher.setMolecule('CCO'))", awaitp=True)
        time.sleep(1)
        ket = ev("Promise.resolve(window.ketcher.getKet())", awaitp=True)
        print(str(ket)[:900])

        print()
        print("=== E) 试：构造带文本的 KET 加载 ===")
        ket_try = json.dumps({
            "root": {"nodes": [{"$ref": "mol0"}, {"$ref": "text0"}]},
            "mol0": {"type": "molecule",
                     "atoms": [{"label": "C", "location": [0, 0, 0]},
                               {"label": "O", "location": [1.5, 0, 0]}],
                     "bonds": [{"type": 1, "atoms": [0, 1]}]},
            "text0": {"type": "text", "content": "条件：室温", "position": {"x": 0, "y": -1.5, "z": 0}}
        })
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'ket-ok';}).catch(function(e){return 'ket-err:'+String(e).slice(0,200);})" % json.dumps(ket_try), awaitp=True)
        print("setMolecule(带文本KET):", r)
        time.sleep(1)
        print("回读 getKet:", str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))[:500])
        print("回读 getSmiles:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))
        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
