# -*- coding: utf-8 -*-
"""
hx 前端端到端测试（CDP 真实时间版）
====================================
用真实浏览器（Edge 无头 + CDP）在"真实时间"下验证三条用户操作通道：
  A. 从画板取结构（点击按钮）
  B. 粘贴图片 -> OCR 识别
  C. 粘贴 MOL 文本 -> SMILES
运行：tools\\venv\\Scripts\\python.exe tools\\tmp\\cdp_e2e.py
"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket  # websocket-client

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9223
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_profile"
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
        print("已打开页面，等待画板加载…")
        time.sleep(12)

        # 等 ketcher 就绪
        ok = None
        for _ in range(45):
            ok = ev("(function(){var d=document.getElementById('board');"
                    "if(!d)return null;var w=d.contentWindow;"
                    "return (w&&w.ketcher)?'ok':null;})()")
            if ok == "ok":
                break
            time.sleep(2)
        print("1) 画板状态:", ok)
        if ok != "ok":
            print("FAIL: 画板未就绪")
            return 1

        # ---- A1：setMolecule + 直读 ----
        r1 = ev("document.getElementById('board').contentWindow.ketcher"
                ".setMolecule('c1ccccc1').then(function(){return 'set-ok';})"
                ".catch(function(e){return 'set-err:'+String(e);})", awaitp=True)
        print("2) setMolecule:", r1)
        time.sleep(3)
        r2 = ev("document.getElementById('board').contentWindow.ketcher.getSmiles()", awaitp=True)
        print("3) 直读画板 SMILES:", repr(r2))

        # ---- A2：点击「从画板取结构」 ----
        ev("document.getElementById('btn-conv-board').click();'clicked'")
        time.sleep(4)
        v = ev("document.getElementById('conv-input').value")
        box = ev("document.getElementById('conv-result').textContent")
        print("4) 按钮后输入框:", repr(v))
        print("   结果区:", repr(str(box)[:120]))

        # ---- B：图片粘贴 ----
        expr_b = (
            "(function(){"
            "return fetch('./runtime/selftest_molecule.png')"
            ".then(function(r){return r.blob();}).then(function(b){"
            "var f=new File([b],'t.png',{type:'image/png'});"
            "var dt=new DataTransfer();dt.items.add(f);"
            "var ta=document.getElementById('retro-input');"
            "var evt=new Event('paste',{bubbles:true,cancelable:true});"
            "Object.defineProperty(evt,'clipboardData',{value:dt});"
            "ta.dispatchEvent(evt);return 'pasted';});})()")
        print("5) 投递图片粘贴:", ev(expr_b, awaitp=True))
        got = None
        for _ in range(60):
            time.sleep(3)
            got = ev("document.getElementById('retro-input').value")
            if got and len(str(got)) > 2:
                break
        print("6) 图片识别结果:", repr(got))

        # ---- C：MOL 粘贴 ----
        mol = ("\n     RDKit          2D\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n"
               "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
               "    1.2990    0.7500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
               "    2.5981   -0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
               "  1  2  1  0\n  2  3  1  0\nM  END\n")
        expr_c = (
            "(function(){"
            "var mol=" + json.dumps(mol) + ";"
            "var dt=new DataTransfer();dt.setData('text/plain',mol);"
            "var ta=document.getElementById('conv-input');ta.value='';"
            "var evt=new Event('paste',{bubbles:true,cancelable:true});"
            "Object.defineProperty(evt,'clipboardData',{value:dt});"
            "ta.dispatchEvent(evt);return 'pasted';})()")
        print("7) 投递 MOL 粘贴:", ev(expr_c))
        time.sleep(4)
        print("8) MOL->SMILES 结果:", repr(ev("document.getElementById('conv-input').value")))

        print("=== 测试结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
