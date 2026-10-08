#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
converter.py —— 统一转换引擎（第一版）

把已就位的零件（RDKit / 中文名典 / OPSIN）接线成一个统一入口，
供后续本地服务（app/server.py 的 /api/convert）调用。

冻结契约
--------
    convert(input_text: str, input_type: str, target: str) -> dict

    成功：{"ok": True,  "output": "...", "source": "..."}
    失败：{"ok": False, "error": "（中文友好错误信息）"}

本版支持
--------
    input_type : smiles / name_zh / name_en
    target     : smiles / formula / inchi / name_zh

设计要点
--------
1. 一切以「分子」为中心：先把输入解析成 RDKit 分子对象，再算目标。
2. smiles -> name_zh 走**词典反查**，双方 SMILES 一律先经
   Chem.MolToSmiles(Chem.MolFromSmiles(...)) 规范化后再比对，
   杜绝「同一分子、不同写法」导致的漏匹配。
3. formula 作为输入直接拒绝（同分异构体无法唯一确定结构）。
4. 所有失败路径都返回中文错误，绝不抛出未捕获异常。
"""

import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dict_query  # noqa: E402  （同目录的词典查询零件）

from rdkit import Chem                     # noqa: E402
from rdkit.Chem import rdMolDescriptors    # noqa: E402
from rdkit import RDLogger                 # noqa: E402

# RDKit 解析非法 SMILES 时会往 stderr 打日志，静音之——错误由我们自己处理
RDLogger.DisableLog("rdApp.*")

SUPPORTED_INPUT_TYPES = ("smiles", "name_zh", "name_en")
SUPPORTED_TARGETS = ("smiles", "formula", "inchi", "name_zh")


# ============================================================ 底层工具

def _canonical(smiles):
    """把 SMILES 规范化；非法则返回 None。"""
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def _opsin_to_smiles(name):
    """OPSIN：英文系统名 -> SMILES。查不到返回 None。"""
    try:
        from py2opsin import py2opsin
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # OPSIN 对无法解析的名字会 warning，忽略
            res = py2opsin([name], output_format="SMILES")
    except Exception:
        return None
    if not res:
        return None
    s = (res[0] or "").strip()
    return s or None


# 词典反向索引：规范化 SMILES -> (中文名, source)。惰性构建一次后缓存。
_REVERSE_CACHE = None


def _reverse_map():
    """构建/取得「规范化 SMILES -> 中文名」反查表（469 条，构建一次即缓存）。"""
    global _REVERSE_CACHE
    if _REVERSE_CACHE is not None:
        return _REVERSE_CACHE
    table = {}
    conn = dict_query._connect()
    try:
        rows = conn.execute("SELECT name,smiles,source FROM compounds").fetchall()
    finally:
        conn.close()
    for row in rows:
        canon = _canonical(row["smiles"])
        if canon and canon not in table:      # 同一结构多个名，保留首个
            table[canon] = (row["name"], row["source"])
    _REVERSE_CACHE = table
    return table


def _ok(output, source):
    return {"ok": True, "output": output, "source": source}


def _err(msg):
    return {"ok": False, "error": msg}


# ============================================================ 输入解析

def _resolve_smiles(input_text, input_type):
    """
    把输入解析为 (规范化SMILES, 中文名候选, source)；失败抛 ValueError(中文)。
    中文名候选：仅当输入是词典名时给出，供 name_zh -> name_zh 直接用。
    """
    text = (input_text or "").strip()
    if not text:
        raise ValueError("输入为空，请提供待转换的结构、名称或式样。")

    if input_type == "smiles":
        canon = _canonical(text)
        if canon is None:
            raise ValueError("无法识别该结构式（SMILES）：%s，请检查写法是否正确。" % text)
        return canon, None, "RDKit"

    if input_type == "name_zh":
        # 精确优先，其次模糊（search 内部已按优先级排序）
        hits = dict_query.search(text, fuzzy=True)
        if not hits:
            raise ValueError("词典中没有找到「%s」。可试试更通用的名称，或改用结构式（SMILES）。" % text)
        name, smiles, src, _note = hits[0]
        canon = _canonical(smiles)
        if canon is None:
            raise ValueError("词典中「%s」的结构数据无法解析，请改用结构式（SMILES）。" % name)
        exact = (name == text)
        kind = "精确匹配" if exact else "模糊匹配（%s）" % name
        return canon, name, "中文名典 %s（%s）" % (kind, src)

    if input_type == "name_en":
        smi = _opsin_to_smiles(text)
        if not smi:
            raise ValueError("OPSIN 无法解析该英文名「%s」，请检查拼写或改用结构式（SMILES）。" % text)
        canon = _canonical(smi)
        if canon is None:
            raise ValueError("OPSIN 返回的结构无法解析，请改用结构式（SMILES）。")
        return canon, None, "OPSIN"

    raise ValueError("不支持的输入类型：%s（本版支持 smiles / name_zh / name_en）。" % input_type)


# ============================================================ 目标生成

def _to_formula(mol):
    return rdMolDescriptors.CalcMolFormula(mol)


def _to_inchi(mol):
    try:
        inchi = Chem.MolToInchi(mol)
    except Exception:
        inchi = ""
    if not inchi:
        raise ValueError("该结构无法生成 InChI（可能含不支持的特征），请改用其他目标。")
    return inchi


def _to_name_zh(canon, name_hint):
    """规范化 SMILES -> 中文名：词典反查。"""
    if name_hint:
        return name_hint
    hit = _reverse_map().get(canon)
    if not hit:
        raise ValueError("词典中未收录该结构，无法给出中文名。可改用结构式或分子式。")
    name, src = hit
    return name, "中文名典 反向匹配（%s）" % src


# ============================================================ 主入口

def convert(input_text: str, input_type: str, target: str) -> dict:
    """
    统一转换入口。见模块头部「冻结契约」。
    """
    try:
        input_type = (input_type or "").strip().lower()
        target = (target or "").strip().lower()

        # ---- 产品特判：分子式作为输入直接拒绝（本版不做）----
        if input_type == "formula":
            return _err("分子式无法唯一确定结构（同分异构体太多），"
                        "请改用名称或结构式")

        # ---- 参数校验 ----
        if input_type not in SUPPORTED_INPUT_TYPES:
            return _err("不支持的输入类型：%s（本版支持 smiles / name_zh / name_en）。"
                        % (input_type or "空"))
        if target not in SUPPORTED_TARGETS:
            return _err("不支持的目标类型：%s（本版支持 smiles / formula / inchi / name_zh）。"
                        % (target or "空"))

        # ---- 解析输入 -> 规范化 SMILES ----
        canon, name_hint, source = _resolve_smiles(input_text, input_type)

        # ---- name_zh 目标（可能是恒等返回或反查）----
        if target == "name_zh":
            out = _to_name_zh(canon, name_hint)
            if isinstance(out, tuple):
                name, src = out
                return _ok(name, src)
            return _ok(out, source)

        # ---- 其余目标先建分子对象 ----
        mol = Chem.MolFromSmiles(canon)
        if mol is None:  # 理论上 canon 一定合法，防御性兜底
            return _err("结构解析失败，请检查输入。")

        if target == "smiles":
            return _ok(canon, source)
        if target == "formula":
            return _ok(_to_formula(mol), source)
        if target == "inchi":
            return _ok(_to_inchi(mol), source)

        return _err("未处理的目标类型：%s。" % target)

    except ValueError as e:
        return _err(str(e))
    except FileNotFoundError as e:
        return _err("词典不可用：%s" % e)
    except Exception as e:  # 最后一道防线，绝不泄露未捕获异常
        return _err("转换过程中出现异常：%s" % e)


# ============================================================ 演示

def _demo():
    print("=" * 70)
    print("转换引擎 —— 演示")
    print("=" * 70)
    cases = [
        ("阿司匹林", "name_zh", "smiles"),
        ("阿司匹林", "name_zh", "formula"),
        ("苯", "name_zh", "smiles"),
        ("c1ccccc1", "smiles", "name_zh"),
        ("CC(=O)Oc1ccccc1C(=O)O", "smiles", "name_zh"),
        ("CCO", "smiles", "formula"),
        ("2,4-dinitrotoluene", "name_en", "smiles"),
        ("哈哈哈不存在的名字", "name_zh", "smiles"),
        ("C6H6", "formula", "smiles"),
    ]
    for text, it, tg in cases:
        r = convert(text, it, tg)
        if r["ok"]:
            print("%-24s [%s -> %-9s] => %s   <%s>" % (text, it, tg, r["output"], r["source"]))
        else:
            print("%-24s [%s -> %-9s] => 失败：%s" % (text, it, tg, r["error"]))
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(_demo())
