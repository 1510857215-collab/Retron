# -*- coding: utf-8 -*-
"""
逆合成路线搜索入口（AiZynthFinder 封装）
====================================================================
【重要】本脚本必须使用专用环境解释器运行：

    tools\\venv-retro\\Scripts\\python.exe

因为 aizynthfinder 及其依赖（onnxruntime / rdkit 等）只装在该 venv 里。

功能：给定目标分子 SMILES，倒推合成路线。
全离线运行——模型与数据均在本机 data\\retro\\ 下，不访问任何在线 API。

对外入口：find_routes(smiles, max_steps=3, ..., start_material=None) -> dict
返回：成功 {"ok": True, "is_solved": bool, "routes": [...], "stats": {...}}
      失败 {"ok": False, "error": "..."}

【起点约束】start_material 为可选参数：传入起始物料 A 的 SMILES 时，
  引擎会把 A 当作"可用原料"注入到化合物库中（不影响 zinc 主库），
  搜索结束后筛选出"经过 A 的路线"优先返回。详见 data\\retro\\起点约束说明.md
"""
import os
import sys
import time
import json

# ---- 路径解析：脚本位于 <项目根>\engine\retro\retro_run.py ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "retro")
_CONFIG_FILE = os.path.join(_DATA_DIR, "config.yml")
# 临时文件目录（起点约束的临时 inchikey 文本库放这里）
_TMP_DIR = os.path.join(_PROJECT_ROOT, "tools", "tmp")

# 全局缓存：加载模型/库（zinc 库 1.3GB）很耗时，同一进程内复用
_FINDER = None
# 基础化合物库选择（进程内固定，通常是 ["zinc"]），用于在注入起点物料后还原
_BASE_STOCK_SELECTION = None

# 起点物料注入到 stock 时使用的键名（下划线前缀避免与配置里的库名冲突）
_START_STOCK_KEY = "_start_material"
_START_STOCK_FILE = os.path.join(_TMP_DIR, "retro2_start_material.inchikey.txt")


def _get_finder():
    """懒加载并缓存 AiZynthFinder 实例（只加载一次模型与化合物库）。"""
    global _FINDER, _BASE_STOCK_SELECTION
    if _FINDER is not None:
        return _FINDER

    # 延迟导入，避免仅 import 本模块时就加载重依赖
    from aizynthfinder.aizynthfinder import AiZynthFinder

    if not os.path.exists(_CONFIG_FILE):
        raise FileNotFoundError("找不到配置文件: %s" % _CONFIG_FILE)

    finder = AiZynthFinder(configfile=_CONFIG_FILE)

    # 选择化合物库（zinc）、扩展策略（uspto，可选 ringbreaker）、过滤策略
    finder.stock.select_all()
    if "uspto" in finder.expansion_policy.items:
        finder.expansion_policy.select("uspto")
    else:
        finder.expansion_policy.select_first()
    finder.filter_policy.select_all()

    # 记录基础库选择（不含起点物料），供后续注入/还原
    _BASE_STOCK_SELECTION = list(finder.stock.selection or [])

    _FINDER = finder
    return finder


# ---------------------------------------------------------------------------
# 起点物料（start_material）相关工具
# ---------------------------------------------------------------------------
def _rdkit_canonical(smiles):
    """用 RDKit 把 SMILES 规范化；失败返回 None。"""
    if not smiles:
        return None
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol)
    except Exception:
        return None


def _strip_atom_map(smiles):
    """去掉原子映射编号，如 [CH3:1] -> [CH3]，便于规范化比对。"""
    import re
    return re.sub(r":\d+\]", "]", smiles)


def _install_start_material(finder, start_smiles):
    """
    把起点物料 A 作为"额外可用原料"注入 finder 的 stock（不破坏 zinc 主库）。

    做法：把 A 的 InChIKey 写成一行文本临时文件（tools\\tmp\\retro2_*），
    用 AiZynthFinder 自带的 InMemoryInchiKeyQuery 载入为一个新 stock
    （键名 _start_material），然后把"基础库 + 起点库"一起选中。

    :return: A 的规范化 SMILES（str）；A 非法时抛 ValueError
    """
    from aizynthfinder.chem import Molecule
    from aizynthfinder.context.stock.queries import InMemoryInchiKeyQuery

    canon = _rdkit_canonical(start_smiles)
    if canon is None:
        raise ValueError("起点物料 SMILES 无法解析: %r" % start_smiles)

    try:
        inchi_key = Molecule(smiles=start_smiles).inchi_key
    except Exception as err:
        raise ValueError("起点物料无法计算 InChIKey: %s" % err)
    if not inchi_key:
        raise ValueError("起点物料无法计算 InChIKey: %r" % start_smiles)

    # 写临时 inchikey 文本库
    os.makedirs(_TMP_DIR, exist_ok=True)
    with open(_START_STOCK_FILE, "w", encoding="utf-8") as f:
        f.write(inchi_key + "\n")

    query = InMemoryInchiKeyQuery(_START_STOCK_FILE)
    finder.stock.load(query, _START_STOCK_KEY)

    # 选中 = 基础库 + 起点库
    base = _BASE_STOCK_SELECTION or list(finder.stock.selection or [])
    selection = list(base)
    if _START_STOCK_KEY not in selection:
        selection.append(_START_STOCK_KEY)
    finder.stock.select(selection)

    return canon


def _restore_stock(finder):
    """还原为基础库选择（去掉起点物料），保证无 start_material 时行为一致。"""
    base = _BASE_STOCK_SELECTION
    if base:
        finder.stock.select(list(base))


def _iter_mol_nodes(node):
    """递归遍历路线 dict 中所有分子节点。"""
    if not isinstance(node, dict):
        return
    if node.get("is_chemical") or node.get("type") == "mol":
        yield node
    for child in node.get("children") or []:
        for sub in _iter_mol_nodes(child):
            yield sub


def _route_leaf_smiles(route_dict):
    """返回路线中所有"叶子分子"（未被继续拆解的分子=原料）的 smiles 列表。"""
    leaves = []
    for mol in _iter_mol_nodes(route_dict):
        if mol.get("children"):
            continue
        smi = mol.get("smiles")
        if isinstance(smi, str) and smi:
            leaves.append(smi)
    return leaves


def _route_has_material(route_dict, target_canon):
    """判断一条路线是否以目标物料 A 作为原料（叶子节点规范化后与 A 比对）。"""
    if target_canon is None:
        return False
    for smi in _route_leaf_smiles(route_dict):
        if _rdkit_canonical(_strip_atom_map(smi)) == target_canon:
            return True
    return False


def find_routes(smiles, max_steps=3, time_limit=120, iteration_limit=100,
                save_dir=None, start_material=None):
    """
    对给定分子做逆合成路线搜索。

    :param smiles: 目标分子 SMILES，例如阿司匹林 'CC(=O)Oc1ccccc1C(=O)O'
    :param max_steps: 最大反应步数（对应 max_transforms）
    :param time_limit: 单次搜索时间上限（秒）
    :param iteration_limit: MCTS 最大迭代次数
    :param save_dir: 若给定，则把结果 JSON 与路线图片保存到该目录
    :param start_material: 可选的起始物料 A 的 SMILES。给定时把 A 视为可用原料，
        并优先返回"经过 A 的路线"；缺省/空字符串时行为与不带此参数完全一致。
    :return: dict，见模块文档
    """
    t0 = time.time()
    start_material = (start_material or "").strip() or None
    try:
        finder = _get_finder()

        # 覆盖搜索参数
        finder.config.search.max_transforms = int(max_steps)
        finder.config.search.time_limit = int(time_limit)
        finder.config.search.iteration_limit = int(iteration_limit)

        # 起点物料：注入 stock（无起点则保证只选基础库）
        start_canon = None
        if start_material:
            try:
                start_canon = _install_start_material(finder, start_material)
            except ValueError as err:
                return {"ok": False, "error": str(err)}
        else:
            _restore_stock(finder)

        # 设置目标并准备搜索树
        try:
            finder.target_smiles = smiles
            finder.prepare_tree()
        except ValueError as err:
            return {"ok": False, "error": "无法初始化搜索: %s" % str(err).lower()}

        # 执行树搜索
        finder.tree_search(show_progress=False)

        # 构建路线并打分
        finder.build_routes()
        finder.routes.compute_scores(*finder.scorers.objects())

        # 统计信息
        stats = finder.extract_statistics()
        stats["wall_time"] = round(time.time() - t0, 1)

        # 路线（含评分与元数据）
        routes = list(finder.routes.dict_with_extra(
            include_scores=True, include_metadata=True))

        result = {
            "ok": True,
            "smiles": smiles,
            "is_solved": bool(stats.get("is_solved", False)),
            "num_routes": len(routes),
            "routes": routes,
            "stats": stats,
        }

        # ---- 起点约束后处理（无 start_material 时走原逻辑，行为完全一致）----
        if start_material:
            result = _apply_start_material(
                result, routes, finder.routes, start_material, start_canon, save_dir)
        elif save_dir:
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, "routes.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            _save_route_images(finder.routes.images, save_dir)

        return result

    except Exception as err:  # 兜底：任何异常都返回结构化错误
        import traceback
        return {"ok": False, "error": "%s: %s" % (type(err).__name__, err),
                "traceback": traceback.format_exc()}


def _apply_start_material(result, routes, routes_obj, start_material, start_canon,
                          save_dir):
    """
    起点约束的核心后处理：
      1) 给每条路线的根节点打上 with_start 标记；
      2) 把含 A 的路线排到前面；
      3) 若有含 A 的路线，routes 只保留它们；否则全部保留并给出提示字段。
      4) 可选落盘。

    新增字段（顶层）：
      start_material        : 起点 A 的规范化 SMILES
      start_material_routes : 返回的 routes 中"经起点 A"的序号列表（0 基）
      num_routes_found      : 搜索得到的原始路线总数
      start_material_hint   : 仅当无经 A 的路线时出现，提示为普通路线
    新增字段（每条路线根节点）：
      with_start            : 该路线是否经过起点 A
    """
    num_found = len(routes)
    flags = [_route_has_material(r, start_canon) for r in routes]

    # 稳定排序：含 A 的在前
    order = sorted(range(num_found), key=lambda i: (not flags[i], i))
    if any(flags):
        # 只保留经起点 A 的路线
        keep = [i for i in order if flags[i]]
        hint = None
    else:
        keep = order
        hint = "未找到经起点 A 的路线，以下为普通路线"

    routes_out = []
    for i in keep:
        r = dict(routes[i])          # 浅拷贝，避免改动 finder 内部对象
        r["with_start"] = bool(flags[i])
        routes_out.append(r)

    result["routes"] = routes_out
    result["num_routes"] = len(routes_out)
    result["start_material"] = start_canon
    result["num_routes_found"] = num_found
    result["start_material_routes"] = [i for i in range(len(routes_out))
                                       if routes_out[i]["with_start"]]
    if hint:
        result["start_material_hint"] = hint

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        with open(os.path.join(save_dir, "routes.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        # 图片按保留下来的原始路线下标取（仅在需要落盘时才生成图片）
        all_images = list(routes_obj.images)
        _save_route_images([all_images[i] for i in keep], save_dir)

    return result


def _save_route_images(images, save_dir):
    """把每条路线画成 PNG 保存（依赖 rdkit/PIL，已随核心包安装）。"""
    if not images:
        return
    for i, img in enumerate(images):
        if img is None:
            continue
        img.save(os.path.join(save_dir, "route_%d.png" % (i + 1)))


def _main():
    """命令行自测：python retro_run.py "SMILES" [max_steps] [start_material]"""
    smiles = sys.argv[1] if len(sys.argv) > 1 else "CC(=O)Oc1ccccc1C(=O)O"
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    start_material = sys.argv[3] if len(sys.argv) > 3 else None
    print("目标分子:", smiles, "| 最大步数:", max_steps,
          "| 起点物料:", start_material)

    out_dir = os.path.join(_DATA_DIR, "测试结果")
    res = find_routes(smiles, max_steps=max_steps, save_dir=out_dir,
                      start_material=start_material)

    if not res["ok"]:
        print("失败:", res["error"])
        if "traceback" in res:
            print(res["traceback"])
        sys.exit(1)

    print("是否找到完整路线:", res["is_solved"])
    print("路线条数:", res["num_routes"])
    if "start_material" in res:
        print("起点物料(规范化):", res["start_material"])
        print("经起点路线序号:", res["start_material_routes"])
        print("原始路线总数:", res["num_routes_found"])
        if "start_material_hint" in res:
            print("提示:", res["start_material_hint"])
    for k, v in res["stats"].items():
        print("  %s: %s" % (k, v))
    print("结果已保存到:", out_dir)


if __name__ == "__main__":
    _main()
