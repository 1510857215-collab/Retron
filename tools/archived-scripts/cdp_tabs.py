# -*- coding: utf-8 -*-
"""标签页版界面验收：元素完整性 / JS 异常 / 标签切换 / 快速逆合成回归 + 截图"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9229
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_tabs"
BASE = "http://127.0.0.1:8765"


def main():
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu",
         "--remote-debugging-port=%d" % PORT,
         "--user-data-dir=" + PROFILE,
         "--no-first-run", "--no-default-browser-check",
         "--window-size=1680,950", "about:blank"],
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
            return res.get("value", {"__err__": str(r)[:250]})

        def exceptions():
            out = []
            for m in events:
                if m.get("method") == "Runtime.exceptionThrown":
                    d = m.get("params", {}).get("exceptionDetails", {})
                    out.append("%s | %s" % (d.get("text", ""),
                                            str((d.get("exception") or {}).get("description", ""))[:300]))
            return out

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/index.html"})
        print("已打开页面，等 10 秒…")
        time.sleep(10)

        ids = ("['tab-conv','panel-conv','panel-retro','panel-fwd','conv-input',"
               "'conv-type','conv-target','btn-conv','btn-conv-board','conv-result',"
               "'retro-input','retro-start','retro-start-toggle','retro-start-wrap',"
               "'btn-retro','btn-retro-board','btn-retro-start-board','retro-steps','retro-result',"
               "'fwd-input','fwd-cond','fwd-product','btn-fwd','btn-fwd-board','btn-fwd-cond','fwd-result',"
               "'svc-dot','svc-text','board']")
        r = ev(ids + ".map(function(id){return id+':'+(document.getElementById(id)?'OK':'MISSING');}).join(' | ')")
        print("元素检查:", r)

        tabs_check = ev("document.querySelectorAll('.tab').length + ' tabs | ' + document.querySelectorAll('.panel').length + ' panels'")
        print("标签/面板数:", tabs_check)
        print("默认激活面板:", ev("document.querySelector('.panel.active') ? document.querySelector('.panel.active').id : 'none'"))

        print("【JS 异常】数量:", len(exceptions()))
        for e in exceptions()[:6]:
            print("  >>", e)

        # 标签切换
        ev("document.querySelector('.tab[data-tab=\"retro\"]').click(); 'ok'")
        time.sleep(1)
        a1 = ev("document.querySelector('.panel.active') ? document.querySelector('.panel.active').id : 'none'")
        ev("document.querySelector('.tab[data-tab=\"fwd\"]').click(); 'ok'")
        time.sleep(1)
        a2 = ev("document.querySelector('.panel.active') ? document.querySelector('.panel.active').id : 'none'")
        ev("document.querySelector('.tab[data-tab=\"conv\"]').click(); 'ok'")
        time.sleep(1)
        a3 = ev("document.querySelector('.panel.active') ? document.querySelector('.panel.active').id : 'none'")
        print("切换测试: retro->%s | fwd->%s | conv->%s" % (a1, a2, a3))

        # 快速逆合成回归（切到 retro 并跑阿司匹林）
        print("逆合成回归测试…")
        ev("document.querySelector('.tab[data-tab=\"retro\"]').click(); 'ok'")
        ev("document.getElementById('retro-input').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('btn-retro').click();'clicked'")
        txt = ""
        t0 = time.time()
        while time.time() - t0 < 300:
            time.sleep(6)
            txt = str(ev("document.getElementById('retro-result').textContent") or "")
            if "找到完整路线" in txt or "未找到" in txt or "失败" in txt:
                break
        n_routes = ev("document.querySelectorAll('#retro-result .route').length")
        print("  结果:", txt[:90])
        print("  渲染路线数:", n_routes)

        # 展开起始物料（UI 检查）
        ev("document.getElementById('retro-start-toggle').click();'ok'")
        time.sleep(1)
        vis = ev("document.getElementById('retro-start-wrap').style.display")
        print("起始物料展开后 display:", vis)
        ev("document.getElementById('retro-start-toggle').click();'ok'")

        # 截图
        try:
            shot = cmd("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data", "")
            if data:
                with open(r"C:\Users\zzl\Desktop\hx\logs\main_ui_v5.png", "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图已保存: logs/main_ui_v5.png")
        except Exception as e:
            print("截图失败:", e)

        print("=== 验收结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
