# -*- coding: utf-8 -*-
"""探测 v8：修正画布定位后，模拟真人用文本工具创建文本并导出格式"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9238
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k8"
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

        cmd("Runtime.enable")
        cmd("Page.enable")
        cmd("Page.navigate", {"url": BASE + "/board.html"})
        print("打开画板，等 15 秒…")
        time.sleep(15)
        for _ in range(20):
            if ev("typeof window.ketcher") == "object":
                break
            time.sleep(2)

        # 找最大的可见 svg（主画布）
        rect = ev("(function(){var best=null,bestA=0;"
                  "document.querySelectorAll('svg').forEach(function(s){"
                  "var r=s.getBoundingClientRect();var a=r.width*r.height;"
                  "if(a>bestA){bestA=a;best={x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),w:Math.round(r.width),h:Math.round(r.height)};}});"
                  "return best?JSON.stringify(best):null;})()")
        print("主画布:", rect)
        pt = json.loads(rect)

        # 点文本工具
        r = ev("(function(){var bs=document.querySelectorAll('button');"
               "for(var i=0;i<bs.length;i++){if((bs[i].getAttribute('title')||'').indexOf('添加文本')>=0){bs[i].click();return 'clicked';}}"
               "return 'not-found';})()")
        print("1) 文本工具:", r)
        time.sleep(0.8)

        # 点画布（真实鼠标）
        cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": pt["x"], "y": pt["y"]})
        cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
        cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
        print("2) 已点击画布中心", (pt["x"], pt["y"]))
        time.sleep(1.5)

        # 侦察编辑元素
        info = ev("(function(){var out=[];"
                  "document.querySelectorAll('[contenteditable],textarea,[class*=txt],[class*=text],[class*=lexical]').forEach(function(el){"
                  "var r=el.getBoundingClientRect();"
                  "out.push(el.tagName+'|'+String(el.className).slice(0,70)+'|'+Math.round(r.x)+','+Math.round(r.y)+' '+Math.round(r.width)+'x'+Math.round(r.height));});"
                  "return out.slice(0,8).join(' ;; ');})()")
        print("3) 编辑候选元素:")
        for piece in str(info).split(" ;; "):
            print("   ", piece)

        # 用 insertText 输入
        cmd("Input.insertText", {"text": "条件：室温搅拌2h"})
        time.sleep(0.6)
        # 看看哪个元素接收了文本
        val = ev("(function(){var out=[];"
                 "document.querySelectorAll('[contenteditable],textarea').forEach(function(el){"
                 "var v=String(el.value!==undefined?el.value:el.textContent);"
                 "if(v&&v.length>0)out.push(el.tagName+'|'+String(el.className).slice(0,50)+'|'+v.slice(0,40));});"
                 "return out.join(' ;; ')||'(无接收者)';})()")
        print("4) 输入后承载元素:", val)

        # 完成：Escape
        cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        time.sleep(0.8)
        # 也可能需要点击别处以提交
        cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"] + 260, "y": pt["y"] + 180, "button": "left", "clickCount": 1})
        cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"] + 260, "y": pt["y"] + 180, "button": "left", "clickCount": 1})
        time.sleep(1)

        back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("5) getKet 长度:", len(back))
        j = back.find('"text"')
        if j >= 0:
            print("=== 真实 text 节点格式 ===")
            print(back[max(0, j - 100):j + 900])
        else:
            print("仍未发现 text 节点；KET 开头：", back[:400])
        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
