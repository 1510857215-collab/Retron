# -*- coding: utf-8 -*-
"""第三批接口验收：正向预测 / 条件推荐 / 起点约束逆合成"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(path, obj, timeout=300):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
    # 1) 正向预测：乙酸酐 + 水杨酸 -> 期望阿司匹林
    print("=== 1) 正向预测（乙酸酐 + 水杨酸）===")
    r = post("/api/forward", {"reactants": "CC(=O)OC(C)=O.O=C(O)c1ccccc1O"})
    print(json.dumps(r, ensure_ascii=False)[:700])
    print()

    # 2) 条件推荐：水杨酸乙酰化
    print("=== 2) 条件推荐（水杨酸 + 乙酸酐 -> 阿司匹林）===")
    r = post("/api/conditions",
             {"reaction": "O=C(O)c1ccccc1O.CC(=O)OC(C)=O>>CC(=O)Oc1ccccc1C(=O)O"})
    print(json.dumps(r, ensure_ascii=False)[:900])
    print()

    # 3) 逆合成 + 起点约束
    print("=== 3) 逆合成（起点=水杨酸，目标=阿司匹林）===")
    r = post("/api/retro",
             {"smiles": "CC(=O)Oc1ccccc1C(=O)O", "max_steps": 3,
              "start_material": "O=C(O)c1ccccc1O"}, timeout=60)
    print("提交:", r)
    if not r.get("ok"):
        return 1
    tid = r["task_id"]
    t0 = time.time()
    st = {}
    while True:
        time.sleep(4)
        st = json.load(urllib.request.urlopen(
            BASE + "/api/retro/status?task_id=" + tid, timeout=60))
        print("  [%.0fs] state=%s" % (time.time() - t0, st.get("state")))
        if st.get("state") != "running":
            break
        if time.time() - t0 > 420:
            print("超时退出")
            return 1
    res = st.get("result") or {}
    print("is_solved:", res.get("is_solved"),
          "| num_routes:", res.get("num_routes"),
          "| start_material_routes:", res.get("start_material_routes"),
          "| hint:", res.get("start_material_hint"))
    routes = res.get("routes") or []
    if routes:
        print("首条路线 with_start:", routes[0].get("with_start"))
    print("=== 全部完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
