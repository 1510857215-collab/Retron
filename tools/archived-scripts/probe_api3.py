# -*- coding: utf-8 -*-
"""探测 v3：文本工具按钮 / CDXML 文本 / 粘贴纯文本 三条路径"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9233
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k3"
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

        print("=== A) 所有含「文本/Text」的按钮 ===")
        print(str(ev("(function(){var out=[];document.querySelectorAll('button,[role=\"button\"]').forEach(function(b){var t=(b.getAttribute('title')||'')+'|'+(b.getAttribute('aria-label')||'');if(/文本|Text|text/i.test(t))out.push(t);});return out.join(' ;; ');})()"))[:500])

        print()
        print("=== B) 试 CDXML 带文本 ===")
        cdxml = ('<CDXML CreationProgram="Ketcher"><page>'
                 '<t p="100 100" LineHeight="24">条件：室温搅拌</t>'
                 '<fragment><n id="1" p="200 200" Element="6"/></fragment>'
                 '</page></CDXML>')
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'cdxml-ok';}).catch(function(e){return 'cdxml-err:'+String(e).slice(0,200);})"
               % json.dumps(cdxml), awaitp=True)
        print("setMolecule(CDXML):", r)
        time.sleep(1)
        print("回读 getKet:", str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))[:600])

        print()
        print("=== C) 试粘贴纯文本到画板 ===")
        ev("Promise.resolve(window.ketcher.setMolecule(''))", awaitp=True)
        time.sleep(1)
        r = ev("(function(){var dt=new DataTransfer();dt.setData('text/plain','条件：室温搅拌 2 小时');"
               "var e=new Event('paste',{bubbles:true,cancelable:true});"
               "Object.defineProperty(e,'clipboardData',{value:dt});"
               "document.dispatchEvent(e);return 'pasted';})()")
        print("投递粘贴:", r)
        time.sleep(2)
        print("回读 getKet:", str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))[:500])
        print("回读 getSmiles:", ev("Promise.resolve(window.ketcher.getSmiles())", awaitp=True))

        print()
        print("=== D) 若 B/C 有效，截图确认 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
