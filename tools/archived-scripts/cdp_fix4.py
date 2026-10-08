# -*- coding: utf-8 -*-
"""
第四批修复验收（CDP 真实时间版）
==================================
覆盖：
  T1 画板加载新文件 ketcher-zh2.js
  T2 画板粘贴图片 -> 识别 -> 画到画板（核心新功能）
  T3 逆合成步骤为"正向合成顺序"（第 1 步=最先的反应）
  T4 A+B -> 补全反应条件（新入口）
  + 截图
运行：tools\\venv\\Scripts\\python.exe tools\\tmp\\cdp_fix4.py
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9228
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_fix4"
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
            return res.get("value", {"__err__": str(r)[:250]})

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/index.html"})
        print("已打开页面…")
        time.sleep(10)

        # ---------- T1: 画板加载新文件 ----------
        t1 = ev("(function(){var iw=document.getElementById('board');"
                "var d=iw&&iw.contentWindow&&iw.contentWindow.document;"
                "if(!d)return 'no-board-doc';"
                "var s=[].map.call(d.querySelectorAll('script[src]'),function(x){return x.getAttribute('src');}).join(',');"
                "return 'scripts='+s+' | ketcher='+(iw.contentWindow.ketcher?'ok':'no');})()")
        print("T1 画板加载:", t1)

        # 等画板就绪
        for _ in range(40):
            ok = ev("(function(){var iw=document.getElementById('board');"
                    "return (iw&&iw.contentWindow&&iw.contentWindow.ketcher)?'ok':'no';})()")
            if ok == "ok":
                break
            time.sleep(2)

        # ---------- T2: 画板粘贴图片 ----------
        print("T2 画板粘贴图片测试（投递到画板区域）…")
        r = ev("(function(){return fetch('./runtime/selftest_molecule.png')"
               ".then(function(r){return r.blob();}).then(function(b){"
               "var f=new File([b],'t.png',{type:'image/png'});"
               "var dt=new DataTransfer();dt.items.add(f);"
               "var bd=document.getElementById('board').contentWindow.document;"
               "var e=new Event('paste',{bubbles:true,cancelable:true});"
               "Object.defineProperty(e,'clipboardData',{value:dt});"
               "bd.dispatchEvent(e);return 'pasted';});})()", awaitp=True)
        print("  投递结果:", r)
        t2_ok = False
        t2_board = ""
        t0 = time.time()
        while time.time() - t0 < 150:
            time.sleep(4)
            st = ev("(function(){var w=document.getElementById('board').contentWindow;"
                    "var s=w.document.getElementById('status');"
                    "return JSON.stringify({t:s?s.textContent:'',c:s?s.className:''});})()")
            try:
                stj = json.loads(st)
            except Exception:
                stj = {"t": str(st), "c": ""}
            if "识别成功" in stj.get("t", ""):
                t2_ok = True
                t2_board = ev("Promise.resolve(document.getElementById('board').contentWindow.ketcher.getSmiles())", awaitp=True)
                print("  状态:", stj.get("t", "")[:120])
                print("  画板内容:", repr(t2_board))
                break
            if "识别失败" in stj.get("t", ""):
                print("  状态(失败):", stj.get("t", "")[:160])
                break
        print("T2 画板粘贴:", "PASS" if t2_ok else "FAIL")

        # ---------- T3: 步骤正向顺序（用阿司匹林，路线批中含多步路线） ----------
        print("T3 逆合成顺序测试（目标=阿司匹林）…")
        ev("document.getElementById('retro-input').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('btn-retro').click();'clicked'")
        txt = ""
        t0 = time.time()
        while time.time() - t0 < 360:
            time.sleep(6)
            txt = str(ev("document.getElementById('retro-result').textContent") or "")
            if "找到完整路线" in txt or "未找到" in txt or "失败" in txt:
                break
        print("  结果:", txt[:100])
        t3_detail = ev("(function(){var routes=document.querySelectorAll('#retro-result .route');"
                       "var out=[];"
                       "for(var i=0;i<Math.min(routes.length,8);i++){"
                       "var blocks=routes[i].querySelectorAll('.step-block');"
                       "var first=blocks.length?blocks[0].getAttribute('data-rxn'):'';"
                       "var last=blocks.length?blocks[blocks.length-1].getAttribute('data-rxn'):'';"
                       "out.push({n:blocks.length,"
                       "first:(first||'').slice(0,75),"
                       "last:(last||'').slice(0,75)});}"
                       "return JSON.stringify(out);})()")
        print("  各路线（步数/第1步/最后一步）:")
        try:
            for item in json.loads(t3_detail):
                print("   ", item)
        except Exception:
            print("   ", t3_detail)

        # ---------- T4: A+B 条件补全 ----------
        print("T4 A+B 条件补全测试…")
        ev("document.getElementById('fwd-input').value='O=C(O)c1ccccc1O.CC(=O)OC(C)=O';'ok'")
        ev("document.getElementById('fwd-product').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('btn-fwd-cond').click();'clicked'")
        ftxt = ""
        t0 = time.time()
        while time.time() - t0 < 90:
            time.sleep(4)
            ftxt = str(ev("document.getElementById('fwd-result').textContent") or "")
            if "建议条件" in ftxt or "失败" in ftxt:
                break
        t4_ok = "建议条件" in ftxt
        print("T4 条件补全:", "PASS" if t4_ok else "FAIL", "|", ftxt[:130])

        # ---------- 截图 ----------
        try:
            shot = cmd("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data", "")
            if data:
                with open(r"C:\Users\zzl\Desktop\hx\logs\main_ui_v4.png", "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图已保存: logs/main_ui_v4.png")
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
