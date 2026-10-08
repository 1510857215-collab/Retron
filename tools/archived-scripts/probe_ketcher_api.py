# -*- coding: utf-8 -*-
"""探测 Ketcher 画板 API：追加能力（addFragment）与文本注释能力"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9231
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k"
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
            return res.get("value", {"__err__": str(r)[:250]})

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/board.html"})
        print("打开画板页，等 15 秒…")
        time.sleep(15)
        for _ in range(20):
            if ev("typeof window.ketcher") == "object":
                break
            time.sleep(2)
        print("ketcher:", ev("typeof window.ketcher"))

        print("=== 1) ketcher 对象的方法清单 ===")
        print(ev("Object.getOwnPropertyNames(window.ketcher).join(', ')"))
        print()
        print("=== 2) 关键方法类型 ===")
        print(ev("['setMolecule','addFragment','getSmiles','getMolfile','getRxn','layout','generateImage','getSelection'].map(function(k){return k+':'+typeof window.ketcher[k];}).join(' | ')"))
        print()
        print("=== 3) 文本/注释相关方法 ===")
        print(ev("Object.getOwnPropertyNames(window.ketcher).filter(function(k){return /text|note|comment|label/i.test(k);}).join(', ') || '(无)'"))
        print("=== 3b) editor 内部对象 ===")
        print(ev("window.ketcher.editor ? Object.getOwnPropertyNames(window.ketcher.editor).slice(0,60).join(', ') : 'no editor'"))
        print("=== 3c) editor 里文本相关 ===")
        print(ev("window.ketcher.editor ? (Object.getOwnPropertyNames(window.ketcher.editor).filter(function(k){return /text|note|comment/i.test(k);}).join(', ') || '(无)') : 'no editor'"))

        print()
        print("=== 4) addFragment 行为试验 ===")
        print("setMolecule CCO:", ev("Promise.resolve(window.ketcher.setMolecule('CCO')).then(function(){return 'ok';})", awaitp=True))
        time.sleep(1)
        print("addFragment 类型:", ev("typeof window.ketcher.addFragment"))
        r = ev("Promise.resolve(window.ketcher.addFragment('c1ccccc1')).then(function(){return 'add-ok';}).catch(function(e){return 'add-err:'+e;})", awaitp=True)
        print("addFragment 调用:", r)
        time.sleep(1)
        print("合并后 SMILES:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))

        # 4b) 再来一次 addFragment 带反应式
        r2 = ev("Promise.resolve(window.ketcher.addFragment('CC(=O)OC(C)=O>>CC(=O)O')).then(function(){return 'add-rxn-ok';}).catch(function(e){return 'add-rxn-err:'+e;})", awaitp=True)
        print("addFragment(反应式):", r2)
        time.sleep(1)
        print("最终 SMILES:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))

        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
