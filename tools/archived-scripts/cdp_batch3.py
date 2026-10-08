# -*- coding: utf-8 -*-
"""
第三批 UI 端到端测试（CDP 真实时间版）
========================================
验证界面上：起点约束提示 / 条件自动补全 / 正向预测卡片 / 顺带截图
运行：tools\\venv\\Scripts\\python.exe tools\\tmp\\cdp_batch3.py
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9225
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_profile3"
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
        if not targets:
            print("FAIL: 调试端口未就绪")
            return 1
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
            if "value" in res:
                return res["value"]
            return {"__err__": str(r)[:300]}

        cmd("Page.enable")
        cmd("Runtime.enable")
        cmd("Page.navigate", {"url": BASE + "/index.html"})
        print("已打开页面…")
        time.sleep(8)

        # ---- 1) 逆合成：带起点 ----
        ev("document.getElementById('retro-input').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('retro-start').value='O=C(O)c1ccccc1O';'ok'")
        ev("document.getElementById('btn-retro').click();'clicked'")
        print("已提交逆合成（起点=水杨酸）…")
        txt = ""
        t0 = time.time()
        while time.time() - t0 < 360:
            time.sleep(6)
            txt = str(ev("document.getElementById('retro-result').textContent") or "")
            if "找到完整路线" in txt or "未找到" in txt or "失败" in txt:
                break
        ok1 = "起点约束生效" in txt
        ok_tag = "经起点" in txt
        print("起点约束提示:", "PASS" if ok1 else "FAIL", "| 路线标签:", "PASS" if ok_tag else "FAIL")

        # ---- 2) 条件自动补全（等 cond-box 出现"建议条件"）----
        print("等待条件自动补全（第一条路线）…")
        cond_ok = False
        t0 = time.time()
        while time.time() - t0 < 120:
            time.sleep(5)
            ct = str(ev("(function(){var b=document.querySelector('#retro-result .cond-box');"
                        "return b? b.textContent : '';})()") or "")
            if "建议条件" in ct:
                cond_ok = True
                print("条件补全:", "PASS ->", ct[:120])
                break
        if not cond_ok:
            ct = str(ev("(function(){var b=document.querySelector('#retro-result .cond-box');"
                        "return b? b.textContent : '(无)';})()") or "")
            print("条件补全: FAIL | 当前:", ct[:120])

        # ---- 3) 正向预测 ----
        ev("document.getElementById('fwd-input').value='CC(=O)OC(C)=O.O=C(O)c1ccccc1O';'ok'")
        ev("document.getElementById('btn-fwd').click();'clicked'")
        time.sleep(3)
        print("  [即时回读]", str(ev("document.getElementById('fwd-result').textContent") or "")[:90])
        print("已提交正向预测…")
        ftxt = ""
        t0 = time.time()
        while time.time() - t0 < 240:
            time.sleep(6)
            ftxt = str(ev("document.getElementById('fwd-result').textContent") or "")
            print("  [%ds] %s" % (int(time.time() - t0), ftxt[:90]))
            if "候选" in ftxt or "失败" in ftxt or "错误" in ftxt:
                break
        fwd_ok = ("候选 1" in ftxt) and ("CC(=O)Oc1ccccc1C(=O)O" in ftxt)
        print("正向预测:", "PASS" if fwd_ok else ("CHECK -> " + ftxt[:180]))

        # ---- 4) 截图（带完整结果的界面）----
        try:
            shot = cmd("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data", "")
            if data:
                with open(r"C:\Users\zzl\Desktop\hx\logs\main_ui_v3.png", "wb") as f:
                    f.write(base64.b64decode(data))
                print("界面截图已保存: logs/main_ui_v3.png")
        except Exception as e:
            print("截图失败:", e)

        print("=== 测试结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
