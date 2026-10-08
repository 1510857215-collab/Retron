# -*- coding: utf-8 -*-
"""探测 v4：UI文本按钮 / CDXML完整回读 / agents段试剂测试"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9234
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k4"
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

        print("=== A) UI 里所有文本相关按钮 ===")
        print(str(ev("(function(){var out=[];document.querySelectorAll('button,[role=\"button\"]').forEach(function(b){var t=(b.getAttribute('title')||'')+'|'+(b.getAttribute('aria-label')||'')+'|'+(b.textContent||'').slice(0,15);if(/文本|Text/i.test(t))out.push(t);});return out.length? out.join(' ;; ') : '(无文本工具)';})()"))[:400])

        print()
        print("=== B) CDXML 带文本完整回读 ===")
        cdxml = ('<CDXML CreationProgram="Ketcher"><page>'
                 '<t p="80 80" LineHeight="24">条件：室温搅拌</t>'
                 '<fragment><n id="1" p="200 200" Element="6"/></fragment>'
                 '</page></CDXML>')
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'cdxml-ok';}).catch(function(e){return 'cdxml-err:'+String(e).slice(0,200);})"
               % json.dumps(cdxml), awaitp=True)
        print("CDXML 加载:", r)
        time.sleep(1)
        ket = ev("Promise.resolve(window.ketcher.getKet())", awaitp=True)
        ket_s = str(ket)
        has_text = ('text' in ket_s.lower())
        print("getKet 长度:", len(ket_s), "| 含 text 节点:", has_text)
        if has_text:
            import re
            m = re.search(r'"text[^}]{0,300}', ket_s)
            print("text 片段:", m.group(0) if m else "?")

        print()
        print("=== C) 三段式反应（agents 段=试剂）===")
        ev("Promise.resolve(window.ketcher.setMolecule(''))", awaitp=True)
        time.sleep(1)
        rxn3 = "CC(=O)OC(C)=O.CC(=O)c1ccccc1>Pyridine>CC(=O)Oc1ccccc1C(=O)O"
        r = ev("Promise.resolve(window.ketcher.addFragment(%s)).then(function(){return 'rxn3-ok';}).catch(function(e){return 'rxn3-err:'+String(e).slice(0,200);})"
               % json.dumps(rxn3), awaitp=True)
        print("三段式加载:", r)
        time.sleep(1)
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
