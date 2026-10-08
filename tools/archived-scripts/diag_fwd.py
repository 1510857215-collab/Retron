# -*- coding: utf-8 -*-
"""诊断：为什么正向预测按钮没反应（收集页面 JS 异常 + 元素检查）"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9226
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_diag"
BASE = "http://127.0.0.1:8765"


def main():
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT,
         "--user-data-dir=" + PROFILE,
         "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    events = []
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
                events.append(msg)

        def ev(expr, awaitp=False):
            r = cmd("Runtime.evaluate",
                    {"expression": expr, "returnByValue": True, "awaitPromise": awaitp})
            res = (r.get("result") or {}).get("result") or {}
            return res.get("value", {"__err__": str(r)[:200]})

        def collect_exceptions():
            out = []
            for m in events:
                if m.get("method") == "Runtime.exceptionThrown":
                    d = m.get("params", {}).get("exceptionDetails", {})
                    out.append("%s | %s" % (
                        d.get("text", ""),
                        str((d.get("exception") or {}).get("description", ""))[:400]))
            return out

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/index.html"})
        print("打开页面，等 10 秒…")
        time.sleep(10)

        ids = ("['btn-conv','btn-conv-board','btn-retro','btn-retro-board',"
               "'btn-retro-start-board','btn-fwd','btn-fwd-board','conv-input',"
               "'retro-input','retro-start','retro-steps','fwd-input','fwd-cond',"
               "'fwd-result','retro-result','conv-result']")
        r = ev(ids + ".map(function(id){return id+':'+(document.getElementById(id)?'OK':'MISSING');}).join(' | ')")
        print("元素检查:", r)

        excs = collect_exceptions()
        print("【页面加载期 JS 异常】数量:", len(excs))
        for e in excs[:10]:
            print("  >>", e)

        # 点击 btn-fwd 观察
        ev("document.getElementById('fwd-input').value='CCO';'ok'")
        ev("document.getElementById('btn-fwd').click();'clicked'")
        time.sleep(4)
        print("btn-fwd 点击后 fwd-result 内容:", repr(
            str(ev("document.getElementById('fwd-result').textContent") or "")[:140]))

        excs2 = collect_exceptions()
        print("【累计 JS 异常】数量:", len(excs2))
        for e in excs2[-6:]:
            print("  >>", e)

        print("=== 诊断结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
