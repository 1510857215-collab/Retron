# -*- coding: utf-8 -*-
"""
engine/forward/predict.py —— 正向反应预测引擎（完全本地、离线可用）
=====================================================================
给反应物（可带条件），预测可能得到的产物。

模型：sagawa/ReactionT5v2-forward-USPTO_MIT
  - 架构：T5-base encoder-decoder（T5ForConditionalGeneration，约 2.2 亿参数）
  - 训练：ReactionT5v2（ORD 预训练）+ USPTO 微调
  - 来源：https://huggingface.co/sagawa/ReactionT5v2-forward-USPTO_MIT   (MIT 协议)
  - 本地目录：data/forward/模型/ReactionT5v2-forward-USPTO_MIT

模型原始输入格式：  "REACTANT:{反应物SMILES}REAGENT:{试剂/催化剂/溶剂SMILES}"
本模块把 predict() 的 reactants → REACTANT，从 conditions 里能解析出的 SMILES → REAGENT。
（★用法要点：本模型把"催化剂/碱/氧化剂"等也当作输入物种。要得到好结果，
  应把它们作为附加 SMILES 一起放进 reactants（点分隔），例如 Suzuki 偶联要带上 Pd 催化剂与碱。

冻结协议：
  predict(reactants: str, conditions: str = None) -> dict
    成功: {"ok": True, "products": [{"smiles": "...", "score": 0.91}, ...], "engine": "..."}
    失败: {"ok": False, "error": "中文错误信息"}
  —— 绝不抛未捕获异常。

【必须用专用环境运行】
  C:\\Users\\zzl\\Desktop\\hx\\tools\\venv-forward\\Scripts\\python.exe
"""
import os
import re
import sys
import math
import threading

# ------------------------------------------------------------------ 离线开关
# 放在 import transformers 之前：任何情况下都不联网（模型已全部落盘）
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

# 模型主目录（可被环境变量 FORWARD_MODEL_DIR 覆盖，便于换模型/换盘）
_MODEL_DIR = os.environ.get(
    "FORWARD_MODEL_DIR",
    os.path.join(_PROJECT_ROOT, "data", "forward", "模型", "ReactionT5v2-forward-USPTO_MIT"),
)

_ENGINE_NAME = "%s (T5, 本地离线)" % os.path.basename(_MODEL_DIR.rstrip("/\\"))

# 生成参数
NUM_BEAMS = 5          # 候选数（beam search）
MAX_LENGTH = 150       # 与模型 config.json 一致

# ------------------------------------------------------------------ 惰性单例
_lock = threading.Lock()
_tok = None
_model = None
_device = None
_rdkit = None
_logging_done = False


def _silence_logging():
    global _logging_done
    if _logging_done:
        return
    try:
        import transformers
        transformers.logging.set_verbosity_error()
        from transformers.utils import logging as _hf_log
        _hf_log.disable_progress_bar()
    except Exception:
        pass
    _logging_done = True


def _lazy_rdkit():
    global _rdkit
    if _rdkit is None:
        from rdkit import Chem, RDLogger
        RDLogger.DisableLog("rdApp.*")
        _rdkit = Chem
    return _rdkit


def _pick_device():
    """优先 GPU，其次 CPU；可用环境变量 FORWARD_DEVICE=cpu|cuda 强制指定。"""
    forced = (os.environ.get("FORWARD_DEVICE") or "").strip().lower()
    import torch
    if forced == "cpu":
        return "cpu"
    if forced == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    """线程安全地加载 tokenizer + 模型（只加载一次）。"""
    global _tok, _model, _device
    if _tok is not None and _model is not None:
        return _tok, _model, _device
    with _lock:
        if _tok is None or _model is None:
            if not os.path.isdir(_MODEL_DIR):
                raise FileNotFoundError("模型目录不存在：%s" % _MODEL_DIR)
            _silence_logging()
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            tok = AutoTokenizer.from_pretrained(_MODEL_DIR)
            model = AutoModelForSeq2SeqLM.from_pretrained(_MODEL_DIR)
            model.eval()
            dev = _pick_device()
            model = model.to(dev)
            _tok, _model, _device = tok, model, dev
    return _tok, _model, _device


# ------------------------------------------------------------------ 工具函数
_SEP_RE = re.compile(r"[\s,;，；、|]+")
_HAS_ATOM_RE = re.compile(r"[A-Za-z0-9]")


def _canonical(smiles):
    """用 rdkit 规范化 SMILES；失败返回 None。"""
    try:
        Chem = _lazy_rdkit()
        m = Chem.MolFromSmiles(smiles)
        if m is None:
            return None
        return Chem.MolToSmiles(m)
    except Exception:
        return None


def _extract_smiles_from_text(text):
    """从条件文本里尽力抽取合法的 SMILES 片段（用于模型的 REAGENT 字段）。
    纯自然语言（如“浓硫酸催化，80℃”）里没有 SMILES，则返回空列表。"""
    out = []
    if not text:
        return out
    for piece in _SEP_RE.split(str(text).strip()):
        if not piece or not _HAS_ATOM_RE.search(piece):
            continue
        piece = piece.strip("。.：:()（）[]【】'\"")
        if not piece:
            continue
        if _canonical(piece) is not None:
            out.append(piece)
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _build_input(reactants, reagent_smiles):
    """组装模型要求的输入串 REACTANT:...REAGENT:..."""
    react = ".".join([r for r in reactants.split(".") if r.strip()])
    reag = ".".join(reagent_smiles) if reagent_smiles else " "
    return "REACTANT:%sREAGENT:%s" % (react, reag)


# ------------------------------------------------------------------ 主接口
def predict(reactants: str, conditions: str = None) -> dict:
    """给反应物（+条件），预测可能得到的产物。

    reactants : 点分隔的 SMILES，如 "CC(=O)OC(C)=O.O=C(O)c1ccccc1O"
                催化剂/碱/氧化剂等也建议一并放在这里（本模型把它们当输入物种）。
    conditions: 可选条件描述文本。若其中含合法 SMILES 会被用作模型的试剂(REAGENT)；
                纯自然语言条件模型不支持，将被忽略（不报错）。

    返回 dict，绝不抛未捕获异常。
    """
    try:
        return _predict_impl(reactants, conditions)
    except Exception as e:  # 兜底：任何异常都转成失败字典
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def _predict_impl(reactants, conditions):
    import torch

    # ---- 参数校验 ----
    if reactants is None or not str(reactants).strip():
        return {"ok": False, "error": "反应物为空，请输入点分隔的 SMILES。"}
    reactants = str(reactants).strip()

    valid_parts = []
    for part in reactants.split("."):
        part = part.strip()
        if not part:
            continue
        if _canonical(part) is None:
            return {"ok": False, "error": "反应物 SMILES 无法解析：%s" % part}
        valid_parts.append(part)
    if not valid_parts:
        return {"ok": False, "error": "反应物为空，请输入点分隔的 SMILES。"}

    # ---- 条件 → 试剂 SMILES ----
    reagent_smiles = _extract_smiles_from_text(conditions)
    notes = []
    if conditions and not reagent_smiles:
        notes.append("条件文本为自然语言，模型仅接受 SMILES 形式的试剂，已忽略该条件。")

    # ---- 加载模型 ----
    try:
        tok, model, dev = _load_model()
    except FileNotFoundError as e:
        return {"ok": False, "error": "模型未就绪：%s" % e}
    except Exception as e:
        return {"ok": False, "error": "模型加载失败：%s: %s" % (type(e).__name__, e)}

    text = _build_input(reactants, reagent_smiles)

    # ---- 生成候选 ----
    try:
        enc = tok(text, return_tensors="pt")
        enc = {k: v.to(dev) for k, v in enc.items()}
        with torch.no_grad():
            out = model.generate(
                **enc,
                num_beams=NUM_BEAMS,
                num_return_sequences=NUM_BEAMS,
                max_length=MAX_LENGTH,
                return_dict_in_generate=True,
                output_scores=True,
            )
        seqs = out["sequences"]
        raw_scores = out["sequences_scores"].tolist()
    except Exception as e:
        return {"ok": False, "error": "推理失败：%s: %s" % (type(e).__name__, e)}

    # ---- 解码 / 校验 / 去重（保留模型的候选顺序与分数）----
    cands = []
    seen = set()
    for seq, raw_sc in zip(seqs, raw_scores):
        smi = tok.decode(seq, skip_special_tokens=True).replace(" ", "").rstrip(".")
        if not smi:
            continue
        canon = _canonical(smi)
        if canon is None:
            continue                      # 丢弃无法解析的产物
        if canon in seen:
            continue
        seen.add(canon)
        # sequences_scores 是"长度归一化后的对数概率"，exp() = 平均每 token 概率 ∈ (0,1]
        score = math.exp(float(raw_sc))
        score = max(0.0, min(1.0, score))
        cands.append({"smiles": canon, "score": round(score, 4)})
    if not cands:
        return {"ok": False, "error": "模型未生成合法的产物结构，请检查反应物 SMILES。"}

    cands.sort(key=lambda p: p["score"], reverse=True)

    res = {
        "ok": True,
        "products": cands,
        "engine": _ENGINE_NAME,
        "input_used": text,
        "reagents_used": reagent_smiles,
        "device": dev,
    }
    if notes:
        res["notes"] = notes
    return res


if __name__ == "__main__":
    import json
    r = predict(sys.argv[1] if len(sys.argv) > 1 else "CC(=O)OC(C)=O.O=C(O)c1ccccc1O",
                sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(r, ensure_ascii=False, indent=2))
