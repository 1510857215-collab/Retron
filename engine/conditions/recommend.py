# -*- coding: utf-8 -*-
"""反应条件推荐引擎（本地、离线）。

思路：
  1) 反应类型识别（RDKit SMARTS）——提供经验温度与经典反应典型条件；
  2) 先例检索（DRFP 反应指纹 + Tanimoto 近邻）——在 USPTO_Condition
     （约 52 万条带条件的专利反应）中检索最相似的反应，按相似度加权投票
     给出试剂/溶剂/催化剂；
  3) 二者融合，输出人类可读的条件。

对外接口（冻结协议）：
    recommend(reaction_smiles: str) -> dict
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except Exception:
    pass

INDEX_DIR = os.path.join(_ROOT, "data", "conditions", "index")
NAMES_PATH = os.path.join(_ROOT, "data", "conditions", "names.json")

ENGINE_NAME = "USPTO_Condition-DRFP-kNN + 反应类型规则（本地离线）"

_TOP_K = 40          # 检索近邻数
_MIN_SIM = 0.30      # 采用 kNN 结果的最低最高相似度
_CAT_MIN_SIM = 0.35  # 催化剂更保守

_state = {"loaded": False, "ok": False, "err": None,
          "Xu64": None, "popX": None, "cols": None, "names": {}}


# ----------------------------------------------------------------------------
def _load():
    if _state["loaded"]:
        return _state["ok"]
    _state["loaded"] = True
    try:
        import numpy as np
        import pandas as pd

        fp_path = os.path.join(INDEX_DIR, "fp_packed.npy")
        meta_path = os.path.join(INDEX_DIR, "meta.parquet")
        if not (os.path.exists(fp_path) and os.path.exists(meta_path)):
            _state["err"] = "先例索引缺失（data/conditions/index）"
            return False
        packed = np.load(fp_path)
        _state["Xu64"] = packed.reshape(packed.shape[0], -1, 8).view(np.uint64).reshape(packed.shape[0], -1)
        _state["popX"] = np.bitwise_count(_state["Xu64"]).sum(axis=1).astype(np.int32)
        meta = pd.read_parquet(meta_path)
        _state["cols"] = {c: meta[c].tolist() for c in
                          ("reagent1", "reagent2", "solvent1", "solvent2", "catalyst1")}
        if os.path.exists(NAMES_PATH):
            with open(NAMES_PATH, "r", encoding="utf-8") as f:
                nm = json.load(f)
            _state["names"] = {k: v for k, v in nm.items() if not k.startswith("_")}
        _state["ok"] = True
        return True
    except Exception as e:  # noqa
        _state["err"] = f"{type(e).__name__}: {e}"
        return False


def _name(smiles):
    if smiles is None:
        return None
    s = str(smiles).strip()
    if not s or s.lower() == "nan":
        return None
    return _state["names"].get(s, s)


def _split_rxn(rxn):
    if rxn.count(">") == 2:
        a, _agents, b = rxn.split(">")
        return a, b
    if ">>" in rxn:
        a, b = rxn.split(">>", 1)
        return a, b
    return None, None


def _canon(smiles_side):
    from rdkit import Chem
    parts = []
    for s in smiles_side.split("."):
        s = s.strip()
        if not s:
            continue
        m = Chem.MolFromSmiles(s)
        if m is None:
            return None
        parts.append(Chem.MolToSmiles(m))
    return ".".join(sorted(parts)) if parts else ""


def _top_conditions(cols, idx, w, col_a, col_b=None, n=3):
    """按相似度加权投票，返回 [(name, weight)] 前 n 个。"""
    score = {}
    for i, wi in zip(idx, w):
        for col in (col_a, col_b):
            if not col:
                continue
            nm = _name(cols[col][i])
            if nm:
                score[nm] = score.get(nm, 0.0) + float(wi)
    tot = sum(score.values()) or 1.0
    items = sorted(score.items(), key=lambda x: -x[1])[:n]
    return [(nm, sc / tot) for nm, sc in items]


def recommend(reaction_smiles: str) -> dict:
    """reaction_smiles: "reactants>>product"（多反应物用 . 分隔）。
    成功: {"ok": True, "conditions": {reagents, solvents, catalysts, temperature, text}, "engine": ...}
    失败: {"ok": False, "error": "中文错误信息"}   绝不抛未捕获异常。
    """
    try:
        if not reaction_smiles or not isinstance(reaction_smiles, str):
            return {"ok": False, "error": "输入为空，需要形如\"反应物>>产物\"的反应 SMILES"}

        react_raw, prod_raw = _split_rxn(reaction_smiles.strip())
        if react_raw is None or not react_raw.strip() or not prod_raw.strip():
            return {"ok": False, "error": "反应 SMILES 格式错误，应形如\"反应物>>产物\"（多反应物用 . 分隔）"}

        react = _canon(react_raw)
        prod = _canon(prod_raw)
        if react is None or prod is None:
            return {"ok": False, "error": "反应 SMILES 中存在无法解析（RDKit）的分子"}

        # ---- 反应类型规则 ----
        try:
            from reaction_rules import classify
        except ImportError:
            from .reaction_rules import classify
        cls_key, cls_name, rule = classify(react, prod)

        # ---- 先例检索 ----
        knn_reagents = knn_solvents = knn_catalysts = []
        top_sim = 0.0
        n_evid = 0
        index_ok = _load()
        if index_ok:
            import numpy as np
            from drfp import DrfpEncoder

            q = np.asarray(DrfpEncoder.encode(f"{react}>>{prod}", **{"n_folded_length": 2048, "min_radius": 0, "radius": 3, "rings": True}), dtype=np.uint8)
            q_packed = np.packbits(q, axis=1).reshape(1, -1)
            q_u64 = q_packed.view(np.uint64).reshape(-1)
            popq = int(np.bitwise_count(q_u64).sum())
            inter = np.bitwise_count(_state["Xu64"] & q_u64).sum(axis=1).astype(np.int32)
            union = _state["popX"] + popq - inter
            sim = inter / np.maximum(union, 1)

            k = min(_TOP_K, sim.shape[0])
            part = np.argpartition(-sim, k - 1)[:k]
            part = part[np.argsort(-sim[part])]
            idx = part.tolist()
            w = np.clip(sim[part], 0.03, 1.0)
            top_sim = float(sim[part[0]])
            n_evid = int(np.sum(sim[part] >= 0.30)) or 1
            meta = _state["cols"]
            knn_reagents = _top_conditions(meta, idx, w, "reagent1", "reagent2", 4)
            knn_solvents = _top_conditions(meta, idx, w, "solvent1", "solvent2", 3)
            knn_catalysts = _top_conditions(meta, idx, w, "catalyst1", None, 3)

        # ---- 融合策略 ----
        # 识别为具体命名反应时，采用该反应的典型（curated）条件；否则采用先例检索。
        rule_matched = bool(rule.get("match"))
        knn_ok = index_ok and top_sim >= _MIN_SIM and (knn_reagents or knn_solvents or knn_catalysts)

        def _fmt(items):
            return [nm for nm, _sc in items]

        if rule_matched:
            reagents = list(rule.get("reagents", []))
            solvents = list(rule.get("solvents", []))
            catalysts = list(rule.get("catalysts", []))
            mode = "rule"
        elif knn_ok:
            reagents = _fmt(knn_reagents) or list(rule.get("reagents", []))
            solvents = _fmt(knn_solvents) or list(rule.get("solvents", []))
            catalysts = _fmt(knn_catalysts) or list(rule.get("catalysts", []))
            mode = "knn"
        else:
            reagents = list(rule.get("reagents", []))
            solvents = list(rule.get("solvents", []))
            catalysts = list(rule.get("catalysts", []))
            mode = "rule"

        temperature = rule.get("temperature", "未知")

        # ---- 人类可读摘要 ----
        if mode == "rule" and rule_matched:
            head = "反应类型：%s（已识别命名反应，采用典型条件）" % cls_name
            if index_ok:
                head += "；先例检索 %d 条相似反应（最高相似度 %.2f）佐证" % (n_evid, top_sim)
        elif mode == "knn":
            head = "反应类型：%s；依据 %d 条相似先例检索（最高相似度 %.2f）" % (cls_name, n_evid, top_sim)
        else:
            head = "反应类型：%s；未检索到足够相似先例，给出经验条件" % cls_name
        parts = [head + "。"]
        if reagents:
            parts.append("试剂：" + "、".join(reagents) + "。")
        if solvents:
            parts.append("溶剂：" + "、".join(solvents) + "。")
        if catalysts:
            parts.append("催化剂：" + "、".join(catalysts) + "。")
        parts.append("温度：" + temperature + "。")
        if rule.get("note"):
            parts.append(rule["note"])
        text = "".join(parts)

        return {
            "ok": True,
            "conditions": {
                "reagents": reagents,
                "solvents": solvents,
                "catalysts": catalysts,
                "temperature": temperature,
                "text": text,
            },
            "engine": ENGINE_NAME,
        }
    except Exception as e:  # noqa
        return {"ok": False, "error": f"条件推荐失败：{type(e).__name__}: {e}"}


if __name__ == "__main__":
    for a in sys.argv[1:] or ["CC(=O)OC(C)=O.O=C(O)c1ccccc1O>>CC(=O)Oc1ccccc1C(=O)O"]:
        print(json.dumps(recommend(a), ensure_ascii=False))
