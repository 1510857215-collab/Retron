# -*- coding: utf-8 -*-
"""探测 v11（最终）：CDXML完整版 + UI提交组合拳"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9241
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k11"
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

        def click_at(x, y):
            cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

        def key(k, code, vk, modifiers=0):
            cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": k, "code": code,
                                           "windowsVirtualKeyCode": vk, "modifiers": modifiers})
            cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": k, "code": code,
                                           "windowsVirtualKeyCode": vk, "modifiers": modifiers})

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/board.html"})
        print("打开画板，等 15 秒…")
        time.sleep(15)
        for _ in range(20):
            if ev("typeof window.ketcher") == "object":
                break
            time.sleep(2)

        rect = json.loads(ev("(function(){var best=null,bestA=0;"
                             "document.querySelectorAll('svg').forEach(function(s){"
                             "var r=s.getBoundingClientRect();var a=r.width*r.height;"
                             "if(a>bestA){bestA=a;best={x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};}});"
                             "return JSON.stringify(best);})()"))
        cx, cy = rect["x"], rect["y"]

        # ---------- 部分 1：完整 CDXML ----------
        print("=== 1) 完整 CDXML 测试 ===")
        cdxml = ('<?xml version="1.0" encoding="UTF-8" ?>'
                 '<CDXML CreationProgram="ChemDraw"><page id="1">'
                 '<t id="2" p="80 60" BoundingBox="80 60 300 92">条件：室温搅拌</t>'
                 '<fragment id="3"><n id="4" p="380 80" Element="6"/></fragment>'
                 '</page></CDXML>')
        r = ev("Promise.resolve(window.ketcher.setMolecule(%s)).then(function(){return 'ok';}).catch(function(e){return 'ERR:'+String(e).slice(0,150);})"
               % json.dumps(cdxml), awaitp=True)
        time.sleep(1.5)
        back1 = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("  CDXML加载:", r, "| 回读长:", len(back1), "| 含text:", 'text' in back1.lower())

        # ---------- 部分 2：UI 创建 + 组合提交 ----------
        print("=== 2) UI 创建文本 + 组合提交 ===")
        ev("(function(){var bs=document.querySelectorAll('button');"
           "for(var i=0;i<bs.length;i++){if((bs[i].getAttribute('title')||'').indexOf('添加文本')>=0){bs[i].click();return true;}}return false;})()")
        time.sleep(0.8)
        click_at(cx, cy)
        time.sleep(1.2)
        cmd("Input.insertText", {"text": "条件：室温2h"})
        time.sleep(0.5)

        # 提交尝试 A：Ctrl+Enter
        key("Enter", "Enter", 13, modifiers=2)  # Ctrl
        time.sleep(1)
        backA = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        okA = ('text' in backA.lower()) and len(backA) > 200
        print("  提交A(Ctrl+Enter):", "成功!" if okA else "无效", "| 回读长:", len(backA))

        if not okA:
            # 提交尝试 B：列出所有当前可见按钮（找确认按钮）
            btns = ev("(function(){var out=[];document.querySelectorAll('button').forEach(function(b){"
                      "var r=b.getBoundingClientRect();if(r.width>0&&r.height>0){"
                      "var t=(b.getAttribute('title')||'')+'|'+(b.textContent||'').slice(0,12);"
                      "if(t&&t!=='|')out.push(t);}});return out.slice(0,40).join(' ;; ');})()")
            print("  当前可见按钮:")
            for piece in str(btns).split(" ;; "):
                if piece.strip():
                    print("    ", piece)
            # 切换工具（矩形选择）——切换常触发提交
            ev("(function(){var bs=document.querySelectorAll('button');"
               "for(var i=0;i<bs.length;i++){if((bs[i].getAttribute('title')||'').indexOf('矩形选择')>=0){bs[i].click();return true;}}return false;})()")
            time.sleep(1.2)
            backB = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
            okB = ('text' in backB.lower()) and len(backB) > 200
            print("  提交B(切选择工具):", "成功!" if okB else "无效", "| 回读长:", len(backB))
            if okB:
                j = backB.lower().find('"text"')
                print("  text 片段:", backB[max(0, j - 100):j + 600])

        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
