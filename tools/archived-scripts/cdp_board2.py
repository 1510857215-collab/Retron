# -*- coding: utf-8 -*-
"""画板追加式验收：单步追加不清除 / 整条路线 / 条件记录条"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9242
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_board2"
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

        def board_smiles():
            return ev("Promise.resolve(document.getElementById('board').contentWindow.ketcher.getSmiles())", awaitp=True)

        def steplog_info():
            return ev("(function(){var d=document.getElementById('board').contentWindow.document;"
                      "var items=d.querySelectorAll('#steplog .item');"
                      "var txt=d.getElementById('steplog-body')?d.getElementById('steplog-body').textContent:'';"
                      "return JSON.stringify({n:items.length, text:txt.slice(0,500)});})()")

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/index.html"})
        print("打开页面，等 10 秒…")
        time.sleep(10)
        for _ in range(40):
            ok = ev("(function(){var iw=document.getElementById('board');"
                    "return (iw&&iw.contentWindow&&iw.contentWindow.ketcher)?'ok':'no';})()")
            if ok == "ok":
                break
            time.sleep(2)
        print("画板就绪")

        # 跑逆合成（阿司匹林）
        ev("document.querySelector('.tab[data-tab=\"retro\"]').click();'ok'")
        ev("document.getElementById('retro-input').value='CC(=O)Oc1ccccc1C(=O)O';'ok'")
        ev("document.getElementById('btn-retro').click();'clicked'")
        print("已提交逆合成，等待结果…")
        txt = ""
        t0 = time.time()
        while time.time() - t0 < 300:
            time.sleep(6)
            txt = str(ev("document.getElementById('retro-result').textContent") or "")
            if "找到完整路线" in txt or "未找到" in txt:
                break
        print("结果:", txt[:80])

        # 找一条 ≥2 步的路线
        route_idx = ev("(function(){var rs=document.querySelectorAll('#retro-result .route');"
                       "for(var i=0;i<rs.length;i++){"
                       "if(rs[i].querySelectorAll('.step-block').length>=2)return i;}"
                       "return -1;})()")
        print("多步路线 idx:", route_idx)
        if route_idx == -1 or (isinstance(route_idx, dict)):
            print("没有多步路线，用第 0 条路线测（单步追加验证）")
            route_idx = 0

        n_steps = ev("(function(){var r=document.querySelector('#retro-result .route[data-route-idx=\"%d\"]');"
                     "return r?r.querySelectorAll('.step-block').length:0;})()" % route_idx)
        print("路线步数:", n_steps)

        # ---- 1) 点第 1 步「画到画板」 ----
        ev("document.querySelector('#retro-result .route[data-route-idx=\"%d\"] .step-block:nth-child(1)'? null : null; 'x'" % route_idx)
        ev("(function(){var r=document.querySelector('#retro-result .route[data-route-idx=\"%d\"]');"
           "var bs=r.querySelectorAll('.step-block button[data-board-step]');"
           "if(bs.length){bs[0].click();return 'clicked';}return 'nobtn';})()" % route_idx)
        print("已点第 1 步画到画板，等条件获取…")
        time.sleep(10)
        s1 = board_smiles()
        i1 = steplog_info()
        print("步1后 画板长度:", len(str(s1)))
        print("步1后 记录条:", str(i1)[:300])

        # ---- 2) 点第 2 步「画到画板」（如果有多步） ----
        if int(n_steps) >= 2:
            ev("(function(){var r=document.querySelector('#retro-result .route[data-route-idx=\"%d\"]');"
               "var bs=r.querySelectorAll('.step-block button[data-board-step]');"
               "if(bs.length>1){bs[1].click();return 'clicked';}return 'nobtn';})()" % route_idx)
            print("已点第 2 步，等条件…")
            time.sleep(12)
            s2 = board_smiles()
            i2 = steplog_info()
            print("步2后 画板长度:", len(str(s2)))
            if len(str(s2)) > len(str(s1)):
                print("✅ 关键验证：步骤 1 内容未被清除（画板内容增加了）")
            else:
                print("⚠️ 画板内容没有增加（可能被覆盖！）")
            print("步2后 记录条:", str(i2)[:400])
        else:
            print("（单步路线：跳过步2测试）")

        # ---- 3) 点「整条路线画到画板」 ----
        ev("(function(){var r=document.querySelector('#retro-result .route[data-route-idx=\"%d\"]');"
           "var b=r.querySelector('button[data-board-route]');if(b){b.click();return 'clicked';}return 'nobtn';})()" % route_idx)
        print("已点整条路线，等条件…")
        time.sleep(14)
        s3 = board_smiles()
        i3 = steplog_info()
        print("整条路线后 画板长度:", len(str(s3)))
        print("整条路线后 记录条:", str(i3)[:500])

        # ---- 截图 ----
        try:
            shot = cmd("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data", "")
            if data:
                with open(r"C:\Users\zzl\Desktop\hx\logs\board_append_test.png", "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图: logs/board_append_test.png")
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
