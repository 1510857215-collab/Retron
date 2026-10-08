# -*- coding: utf-8 -*-
"""探测 v6：KET 文本加载矩阵测试（对象/字符串 × 有无文本）"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9236
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k6"
BASE = "http://127.0.0.1:8765"


def make_ket(with_text):
    ket = {
        "root": {
            "nodes": [{"$ref": "mol0"}],
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
        }
    }
    if with_text:
        ket["root"]["nodes"].append({"$ref": "text0"})
        ket["text0"] = {
            "type": "text",
            "selected": False,
            "boundingBox": {"x": 0, "y": -3, "z": 0, "width": 240, "height": 22},
            "paragraphs": [{"parts": [{"text": "条件：室温搅拌 2 小时"}]}]
        }
    return ket


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

        def load_and_read(label, js_arg):
            r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'ok';}).catch(function(e){return 'ERR:'+String(e).slice(0,150);})"
                   % js_arg, awaitp=True)
            time.sleep(1.5)
            back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
            has_mol = ('mol0' in back) or ('"atoms"' in back)
            has_text = ('"text0"' in back) or ('paragraphs' in back)
            print("[%s] 加载=%s | mol=%s | text=%s | 回读长=%d" % (label, r, has_mol, has_text, len(back)))
            if has_text:
                i = back.find('paragraphs')
                print("   text 片段:", back[max(0, i - 200):i + 250])
            return back

        # T1: 对象，仅分子
        k1 = make_ket(False)
        load_and_read("T1 对象/仅mol", json.dumps(k1))
        # T2: 对象，分子+文本（新schema）
        k2 = make_ket(True)
        load_and_read("T2 对象/mol+text", json.dumps(k2))
        # T3: 字符串，仅分子
        k3 = make_ket(False)
        load_and_read("T3 字符串/仅mol", json.dumps(json.dumps(k3)))
        # T4: 字符串，分子+文本
        k4 = make_ket(True)
        load_and_read("T4 字符串/mol+text", json.dumps(json.dumps(k4)))

        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
