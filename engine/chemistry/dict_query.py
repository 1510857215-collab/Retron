#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dict_query.py —— 中文化合物名称词典查询工具（v2 / 10 万级）

对外接口（与 v1 完全兼容，converter.py 依赖这些）
------------------------------------------------
    find_smiles(name, fuzzy=True, db_path=None)  -> SMILES 字符串 或 None
    search(name, fuzzy=True, db_path=None, limit=20)
                                                 -> [(name, smiles, source, note), ...]
    get_record(name, db_path=None)               -> dict 或 None
    stats(db_path=None)                          -> dict
    _connect(db_path=None)                       -> sqlite3.Connection

查询优先级（命中即返回，不再继续放宽）
--------------------------------------
    ① compounds.name 精确
    ② aliases.alias  精确（覆盖中文名/英文名/俗名/商品名/CAS 号/分子式）
    ③ 前缀匹配（name / alias，走索引）
    ④ 包含匹配（name / alias 模糊，fuzzy=True 时）

数据库：<项目根>/data/中文名字典.sqlite
仅用 Python 标准库。
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_DB = os.path.join(ROOT, "data", "中文名字典.sqlite")

_SELECT = "SELECT c.id, c.name, c.smiles, c.source, c.note FROM %s"


def _has_cjk(text):
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _connect(db_path=None):
    """打开词典数据库（converter.py 也直接调用本函数）。"""
    path = db_path or DEFAULT_DB
    if not os.path.exists(path):
        raise FileNotFoundError(
            "词典数据库不存在：%s\n请先运行 dict_build.py 构建。" % path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------- 核心查询

def _rows(conn, sql, params):
    return conn.execute(sql, params)


def search(name, fuzzy=True, db_path=None, limit=20):
    """返回匹配记录列表 [(中文名/主名, SMILES, source, note), ...]（按匹配优先级排序）。"""
    key = (name or "").strip()
    if not key:
        return []
    conn = _connect(db_path)
    try:
        out, seen = [], set()

        def stage(rows):
            """跑一个查询阶段；只要该阶段产出 >=1 条新记录就算命中。"""
            n0 = len(out)
            for r in rows:
                cid = r[0]
                if cid in seen:
                    continue
                seen.add(cid)
                out.append((r[1], r[2], r[3], r[4]))
                if len(out) >= limit:
                    break
            return len(out) > n0

        # ① 主名精确
        if stage(_rows(conn, _SELECT % "compounds c WHERE c.name=? COLLATE NOCASE", (key,))):
            return out[:limit]

        # ② 别名精确（A 表 join 主表）
        alias_sel = ("SELECT c.id, c.name, c.smiles, c.source, c.note "
                     "FROM aliases a JOIN compounds c ON c.id=a.compound_id "
                     "WHERE a.alias=? COLLATE NOCASE")
        if stage(_rows(conn, alias_sel, (key,))):
            return out[:limit]

        if not fuzzy:
            return out[:limit]

        # ③ 前缀匹配（走 NOCASE 索引）
        if stage(_rows(conn, _SELECT % "compounds c WHERE c.name LIKE ?", (key + "%",))):
            return out[:limit]
        pre = ("SELECT c.id, c.name, c.smiles, c.source, c.note "
               "FROM aliases a JOIN compounds c ON c.id=a.compound_id "
               "WHERE a.alias LIKE ? LIMIT ?")
        if stage(_rows(conn, pre, (key + "%", limit))):
            return out[:limit]

        # ④ 包含匹配（模糊）
        if stage(_rows(conn, _SELECT % "compounds c WHERE c.name LIKE ?", ("%" + key + "%",))):
            return out[:limit]
        con = ("SELECT c.id, c.name, c.smiles, c.source, c.note "
               "FROM aliases a JOIN compounds c ON c.id=a.compound_id "
               "WHERE a.alias LIKE ? LIMIT ?")
        params = ("%" + key + "%", limit)
        # 中文查询优化：先只扫「中文名」别名（2 万行级，走 kind 索引），命中即返回；
        # 否则再退化为对全部别名（数百万行）做包含扫描。
        if _has_cjk(key):
            con_cn = ("SELECT c.id, c.name, c.smiles, c.source, c.note "
                      "FROM aliases a JOIN compounds c ON c.id=a.compound_id "
                      "WHERE a.kind='中文名' AND a.alias LIKE ? LIMIT ?")
            if stage(_rows(conn, con_cn, params)):
                return out[:limit]
        stage(_rows(conn, con, params))
        return out[:limit]
    finally:
        conn.close()


def find_smiles(name, fuzzy=True, db_path=None):
    """便捷接口：返回最佳匹配的 SMILES；无匹配返回 None。"""
    hits = search(name, fuzzy=fuzzy, db_path=db_path)
    for _, smiles, _, _ in hits:
        if smiles:
            return smiles
    return None


def get_record(name, db_path=None):
    """精确查询单条，返回 dict(name, smiles, source, note) 或 None（可命中别名）。"""
    key = (name or "").strip()
    if not key:
        return None
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT c.name, c.smiles, c.source, c.note FROM compounds c "
            "WHERE c.name=? COLLATE NOCASE LIMIT 1", (key,)).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT c.name, c.smiles, c.source, c.note FROM aliases a "
                "JOIN compounds c ON c.id=a.compound_id "
                "WHERE a.alias=? COLLATE NOCASE LIMIT 1", (key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def aliases_of(name, db_path=None, limit=200):
    """列出某个名称（主名或别名）对应化合物的全部别名，便于人工核查。"""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM compounds WHERE name=? COLLATE NOCASE LIMIT 1", (name,)).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT compound_id AS id FROM aliases WHERE alias=? COLLATE NOCASE LIMIT 1",
                (name,)).fetchone()
        if row is None:
            return []
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT alias, kind FROM aliases WHERE compound_id=? LIMIT ?", (row[0], limit))]
    finally:
        conn.close()


def stats(db_path=None):
    """词典规模统计，返回 dict。"""
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
        with_smiles = conn.execute(
            "SELECT COUNT(*) FROM compounds WHERE smiles IS NOT NULL AND smiles<>''").fetchone()[0]
        out = {"total": total, "with_smiles": with_smiles}
        try:
            out["aliases"] = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            out["cn_compounds"] = conn.execute(
                "SELECT COUNT(*) FROM compounds WHERE name GLOB '*[一-龥]*'").fetchone()[0]
            out["cn_aliases"] = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE kind='中文名'").fetchone()[0]
        except sqlite3.Error:
            pass
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------- 演示

def _demo():
    print("=" * 74)
    print("中文化合物名称词典 —— 查询演示（v2）")
    print("数据库：%s" % DEFAULT_DB)
    try:
        st = stats()
    except FileNotFoundError as e:
        print(e)
        return 1
    print("规模：化合物 %d 条（含结构 %d 条），别名 %d 条，主名为中文 %d 条，中文别名 %d 条"
          % (st["total"], st["with_smiles"], st.get("aliases", 0),
             st.get("cn_compounds", 0), st.get("cn_aliases", 0)))
    print("=" * 74)

    demos = ["阿司匹林", "乙酰水杨酸", "aspirin", "氯仿", "三氯甲烷", "扑热息痛",
             "对乙酰氨基酚", "THF", "四氢呋喃", "冰醋酸"]
    for q in demos:
        hits = search(q)
        rec = get_record(q)
        print("\n[%s]" % q)
        if hits:
            name, smi, src, _ = hits[0]
            print("  主名   : %s" % name)
            print("  SMILES : %s" % smi)
            print("  来源   : %s" % src)
            if rec and rec["name"] != q:
                print("  （命中别名，主名为 %s）" % rec["name"])
            ali = aliases_of(q, limit=6)
            if ali:
                print("  别名   : " + " / ".join("%s(%s)" % (a, k) for a, k in ali))
        else:
            print("  未收录 / 无结构")

    print("\n" + "-" * 74)
    print("模糊查询示例：search('氯') 命中：")
    for name, smiles, src, _ in search("氯", limit=8):
        print("  - %-16s %-28s (%s)" % (name, smiles, src))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(_demo())
