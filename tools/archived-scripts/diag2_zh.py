# -*- coding: utf-8 -*-
"""核实：画板汉化在真实浏览器里的实际状态（读画板 DOM 里的文案）"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9227
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_diag2"
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
            return res.get("value", {"__err__": str(r)[:200]})

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/board.html"})
        print("打开画板页（全新浏览器缓存），等 15 秒…")
        time.sleep(15)

        # 等 ketcher
        for _ in range(20):
            ok = ev("typeof window.ketcher")
            if ok == "object":
                break
            time.sleep(2)
        print("ketcher 状态:", ok)

        # 读取画板里的全部 title 文案（工具提示）
        titles = ev("(function(){var out=[];"
                    "document.querySelectorAll('[title]').forEach(function(el){"
                    "var t=el.getAttribute('title');if(t)out.push(t);});"
                    "return out.slice(0,50).join(' | ');})()")
        print("【画板 title 文案前50条】")
        print(str(titles)[:1500])

        # 中文出现统计
        zh = ev("(function(){var t=document.body.innerHTML;"
                "var m=t.match(/[\\u4e00-\\u9fff]{1,12}/g)||[];"
                "var uniq={};m.forEach(function(x){uniq[x]=1;});"
                "return Object.keys(uniq).slice(0,40).join('、');})()")
        print("【画板页面里的中文片段（前40）】")
        print(str(zh)[:800])

        # 检查中文比例
        stat = ev("(function(){var els=document.querySelectorAll('[title]');"
                  "var n=0,zhN=0;els.forEach(function(el){var t=el.getAttribute('title')||'';"
                  "if(t){n++;if(/[\\u4e00-\\u9fff]/.test(t))zhN++;}});"
                  "return 'title总数='+n+' 中文title数='+zhN;})()")
        print("【统计】", stat)
        print("=== 核实结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
