# -*- coding: utf-8 -*-
"""探测 v7：模拟真人用「添加文本」工具创建文本，导出标准 KET 格式"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9237
PROFILE = r"C:\Users\zzl\Desktop\hx\tools\tmp\edge_cdp_probe_k7"
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

        # 1) 点击「添加文本」按钮
        r = ev("(function(){var bs=document.querySelectorAll('button');"
               "for(var i=0;i<bs.length;i++){var t=(bs[i].getAttribute('title')||'');"
               "if(t.indexOf('添加文本')>=0){bs[i].click();return 'clicked:'+t;}}"
               "return 'not-found';})()")
        print("1) 点击文本工具:", r)
        time.sleep(1)

        # 2) 找画布中心坐标
        rect = ev("(function(){var svg=document.querySelector('svg');if(!svg)return null;"
                  "var r=svg.getBoundingClientRect();"
                  "return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});})()")
        print("2) 画布中心:", rect)
        if not rect or rect == "null":
            print("FAIL: 找不到画布")
            return 1
        pt = json.loads(rect)

        # 3) 真实鼠标点击画布
        cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": pt["x"], "y": pt["y"]})
        cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"],
                                         "button": "left", "clickCount": 1})
        cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"],
                                         "button": "left", "clickCount": 1})
        print("3) 已点击画布")
        time.sleep(1.5)

        # 4) 检查出现的编辑元素
        info = ev("(function(){var el=document.activeElement;"
                  "var out='active='+(el?el.tagName+'|'+String(el.className).slice(0,50)+'|ce='+el.isContentEditable:'none');"
                  "var cands=document.querySelectorAll('textarea,input[type=text],[contenteditable=true]');"
                  "out+=' | 候选元素='+cands.length;"
                  "for(var i=0;i<Math.min(cands.length,4);i++){out+=' ['+cands[i].tagName+'|'+String(cands[i].className).slice(0,40)+']';}"
                  "return out;})()")
        print("4) 编辑元素侦察:", info)

        # 5) 输入文本（尝试 insertText）
        cmd("Input.insertText", {"text": "条件：室温搅拌2h"})
        time.sleep(0.5)
        # 读取当前焦点元素的值
        val = ev("(function(){var el=document.activeElement;if(!el)return 'none';"
                 "return String(el.value!==undefined?el.value:el.textContent).slice(0,80);})()")
        print("5) 输入后焦点元素值:", val)

        # 6) 完成编辑（Escape + 点空白）
        cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
        time.sleep(0.5)
        cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"] + 200, "y": pt["y"] + 150,
                                         "button": "left", "clickCount": 1})
        cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"] + 200, "y": pt["y"] + 150,
                                         "button": "left", "clickCount": 1})
        time.sleep(1)

        # 7) 导出 KET，看真实 text 节点
        back = str(ev("Promise.resolve(window.ketcher.getKet())", awaitp=True))
        print("7) getKet 长度:", len(back))
        j = back.find('"type": "text"')
        if j < 0:
            j = back.find('"text"')
        if j >= 0:
            print("=== 真实 text 节点（标准答案）===")
            print(back[max(0, j - 150):j + 900])
        else:
            print("未发现 text 节点。完整 KET：")
            print(back[:800])
        print("=== 探测结束 ===")
        return 0
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
