# -*- coding: utf-8 -*-
"""
hx 逆合成界面端到端测试（CDP 真实时间版）
==========================================
验证：填写目标分子 -> 点「设计路线」-> 等待结果 -> 路线图显示 + 「画到画板」按钮生效
运行：tools\\venv\\Scripts\\python.exe tools\\tmp\\cdp_retro_ui.py
"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9224
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_profile2"
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
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=120)
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

        # 填入目标分子（阿司匹林）并点击「设计路线」
        ev("document.getElementById('retro-input').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('btn-retro').click();'clicked'")
        print("已提交逆合成任务（阿司匹林），等待结果…")

        # 轮询直到出结果（最长 6 分钟）
        final_text = ""
        t0 = time.time()
        while time.time() - t0 < 360:
            time.sleep(6)
            txt = str(ev("document.getElementById('retro-result').textContent") or "")
            if ("找到完整路线" in txt) or ("未找到" in txt) or ("失败" in txt) or ("出错" in txt):
                final_text = txt
                break
            print("  [%ds] 计算中…" % int(time.time() - t0))
        print("结果摘要:", final_text[:160])

        # 检查路线图与按钮
        n_imgs = ev("document.querySelectorAll('#retro-result img').length")
        img_ok = ev("(function(){var a=document.querySelectorAll('#retro-result img');"
                    "var n=0;for(var i=0;i<a.length;i++){if(a[i].naturalWidth>0)n++;}return n;})()")
        n_btns = ev("document.querySelectorAll('#retro-result .mini-btn').length")
        print("路线图数量:", n_imgs, "| 已成功加载:", img_ok, "| 画到画板按钮数:", n_btns)

        # 点击第一个「画到画板」按钮，验证画板变化
        before = ev("document.getElementById('board').contentWindow.ketcher.getSmiles()", awaitp=True)
        ev("(function(){var b=document.querySelector('#retro-result .mini-btn');"
           "if(b){b.click();return 'clicked';}return 'no-btn';})()")
        time.sleep(4)
        after = ev("document.getElementById('board').contentWindow.ketcher.getSmiles()", awaitp=True)
        print("画板内容 前:", repr(before))
        print("画板内容 后:", repr(after))
        print("画到画板:", "PASS" if (after and after != before) else "CHECK")

        print("=== 测试结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
