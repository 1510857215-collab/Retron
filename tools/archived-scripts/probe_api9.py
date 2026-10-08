# -*- coding: utf-8 -*-
"""探测 v9：正确的提交动作（点击别处提交 + 切回选择工具）"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9239
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k9"
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
        print("画布中心:", cx, cy)

        # 1) 文本工具
        ev("(function(){var bs=document.querySelectorAll('button');"
           "for(var i=0;i<bs.length;i++){if((bs[i].getAttribute('title')||'').indexOf('添加文本')>=0){bs[i].click();return true;}}"
           "return false;})()")
        time.sleep(0.8)
        # 2) 点画布（创建文本框）
        click_at(cx, cy)
        time.sleep(1.2)
        # 3) 输入
        cmd("Input.insertText", {"text": "条件：室温搅拌2h"})
        time.sleep(0.6)
        # 4) 点击**别处**提交（失焦提交）
        click_at(cx + 320, cy + 200)
        time.sleep(1.2)
        # 5) 切回"矩形选择"工具（退出文本工具模式）
        ev("(function(){var bs=document.querySelectorAll('button');"
           "for(var i=0;i<bs.length;i++){var t=(bs[i].getAttribute('title')||'');"
           "if(t.indexOf('矩形选择')>=0){bs[i].click();return true;}}return false;})()")
        time.sleep(1.5)
        # 6) 提交后可能残留空文本框：按 Escape 清理
        cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        time.sleep(1)

        back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("getKet 长度:", len(back))
        j = back.find('"type": "text"')
        if j < 0:
            j = back.find('text0')
        if j >= 0:
            print("=== 真实 text 节点格式（标准答案）===")
            print(back[max(0, j - 200):j + 1100])
        else:
            print("仍未发现；KET 开头:", back[:500])
        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
