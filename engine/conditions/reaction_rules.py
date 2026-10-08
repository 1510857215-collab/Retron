# -*- coding: utf-8 -*-
"""反应类型识别（RDKit SMARTS）+ 经验温度/典型条件规则。

USPTO_Condition 数据集不含温度字段，故温度的"经验值"与经典反应的典型
试剂/溶剂由本模块按反应类型给出，与 kNN 先例检索结果互补。
"""
from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

# ---- SMARTS 定义 ----
S = {
    "phenol": Chem.MolFromSmarts("[c][OX2H1]"),
    "aryl_halide": Chem.MolFromSmarts("[c][Cl,Br,I]"),
    "boron": Chem.MolFromSmarts("[#5]"),
    "acid": Chem.MolFromSmarts("[CX3](=[OX1])[OX2H1]"),
    "anhydride": Chem.MolFromSmarts("[CX3](=[OX1])[OX2][CX3](=[OX1])"),
    "acyl_halide": Chem.MolFromSmarts("[CX3](=[OX1])[F,Cl,Br,I]"),
    "sulfonyl_halide": Chem.MolFromSmarts("[SX4](=[OX1])(=[OX1])[F,Cl,Br,I]"),
    "ester": Chem.MolFromSmarts("[CX3](=[OX1])[OX2][#6]"),
    "aryl_ester": Chem.MolFromSmarts("[c][OX2][CX3](=[OX1])"),
    "amide": Chem.MolFromSmarts("[CX3](=[OX1])[NX3]"),
    "sulfonamide": Chem.MolFromSmarts("[SX4](=[OX1])(=[OX1])[NX3]"),
    "alcohol": Chem.MolFromSmarts("[CX4][OX2H1]"),
    "carbonyl": Chem.MolFromSmarts("[CX3]=[OX1]"),
    "nitro": Chem.MolFromSmarts("[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    "aniline": Chem.MolFromSmarts("[c][NX3;H2;!$(N-C=O)]"),
    "aromatic_amine": Chem.MolFromSmarts("[c][NX3;!$(N-C=O),!$(N-S=O)]"),
    "alkene": Chem.MolFromSmarts("[CX3]=[CX3]"),
    "alkyne": Chem.MolFromSmarts("[CX2]#[CX2]"),
    "nitrile": Chem.MolFromSmarts("[NX1]#[CX2]"),
    "azide": Chem.MolFromSmarts("[NX2]=[NX2+]=[NX1-]"),
    "primary_amine": Chem.MolFromSmarts("[NX3;H2;!$(N-C=O),!$(N=*)]"),
}


def _has(mol, key):
    return mol is not None and mol.HasSubstructMatch(S[key])


def _any(mol, keys):
    return any(_has(mol, k) for k in keys)


def _parse(smiles):
    if not smiles:
        return None
    return Chem.MolFromSmiles(smiles)


# 反应物侧常见的"试剂型"小分子：识别反应类型时剔除，避免误判
# （例如 苯 + 硝酸 -> 硝基苯 中的硝酸不应算作底物上的硝基）
_STRIP = {"O=[N+]([O-])O", "O=N[O-]", "O=[N+]([O-])[O-]"}
_STRIP_CANON = set()
for _s in list(_STRIP):
    _m = Chem.MolFromSmiles(_s)
    if _m is not None:
        _STRIP_CANON.add(Chem.MolToSmiles(_m))


def _strip_reagents(reactants_smiles):
    kept = []
    for c in reactants_smiles.split("."):
        c = c.strip()
        if not c:
            continue
        m = Chem.MolFromSmiles(c)
        if m is None:
            continue
        if Chem.MolToSmiles(m) in _STRIP_CANON:
            continue
        kept.append(c)
    return ".".join(kept)


def classify(reactants_smiles, product_smiles):
    """返回 (类别key, 中文名, 规则dict)。规则dict含 temperature/note 及可选
    reagents/solvents/catalysts（中文），以及 match(是否命中具体类型)。"""
    r = _parse(_strip_reagents(reactants_smiles) or reactants_smiles)
    p = _parse(product_smiles)
    if r is None or p is None:
        return ("unknown", "无法解析", {"temperature": "未知", "match": False,
                                        "note": "反应 SMILES 解析失败"})

    # 1. Suzuki 偶联
    if _has(r, "boron") and _has(r, "aryl_halide"):
        return ("suzuki", "Suzuki 偶联（芳基-芳基交叉偶联）", {
            "temperature": "80–100 °C",
            "reagents": ["K2CO3 或 Cs2CO3（碱，2–3 当量）", "Na2CO3/Na3PO4 水溶液"],
            "solvents": ["1,4-二氧六环/H2O（3:1）", "甲苯/乙醇/H2O", "DMF"],
            "catalysts": ["Pd(PPh3)4（2–5 mol%）", "PdCl2(dppf)·DCM", "Pd(OAc)2/SPhos"],
            "note": "典型 Pd 催化交叉偶联，氮气/氩气保护，80–100 °C 反应数小时。",
            "match": True})

    # 2. 硝化
    if _has(p, "nitro") and not _has(r, "nitro"):
        return ("nitration", "芳香族亲电硝化", {
            "temperature": "0–5 °C（冰浴下滴加）",
            "reagents": ["浓硝酸 HNO3", "浓硫酸 H2SO4（混合酸）"],
            "solvents": ["无溶剂（混合酸）", "DCM 或 AcOH 作稀释剂"],
            "catalysts": [],
            "note": "混酸硝化，低温滴加以控制放热与二硝化；产物常为邻/对位混合物。",
            "match": True})

    # 3. 硝基还原（硝基→氨基）
    if _has(r, "nitro") and _has(p, "aniline") and not _has(p, "nitro"):
        return ("nitro_reduction", "硝基还原为芳香伯胺", {
            "temperature": "室温（H2 催化加氢）或 60–80 °C（金属/酸还原）",
            "reagents": ["H2（1–3 atm，催化加氢）", "Fe/NH4Cl（或 SnCl2·2H2O、Zn/HCl）"],
            "solvents": ["MeOH 或 EtOAc", "EtOH/H2O"],
            "catalysts": ["Pd/C（5–10%，催化加氢）"],
            "note": "催化加氢（H2/Pd-C）条件温和；Fe/NH4Cl 适用于对酸/碱敏感底物。",
            "match": True})

    # 4. 酚羟基酰化（如阿司匹林）
    if _has(r, "phenol") and _any(r, ["anhydride", "acyl_halide"]) and _has(p, "aryl_ester"):
        return ("o_acylation", "酚羟基 O-酰化（酯化，如乙酰水杨酸）", {
            "temperature": "室温～60 °C（或 80–100 °C 回流）",
            "reagents": ["乙酸酐 Ac2O（1.1–2 当量）", "无水吡啶（缚酸剂/催化）",
                         "DMAP（催化量）", "或乙酰氯/三乙胺"],
            "solvents": ["无溶剂", "DCM", "吡啶"],
            "catalysts": ["DMAP（4-二甲氨基吡啶，催化量）"],
            "note": "经典乙酰化（阿司匹林合成）：水杨酸+乙酸酐/吡啶或催化 DMAP，"
                    "室温数小时或 60–90 °C；可用 H2SO4 痕量催化。",
            "match": True})

    # 5. 磺酰化
    if _has(r, "sulfonyl_halide") and _has(p, "sulfonamide"):
        return ("sulfonylation", "磺酰化（磺酰胺形成）", {
            "temperature": "0 °C → 室温",
            "reagents": ["对甲苯磺酰氯 TsCl（或 MsCl）", "Et3N 或 吡啶（缚酸剂）",
                         "DMAP（催化量）"],
            "solvents": ["DCM", "吡啶"],
            "catalysts": [],
            "note": "胺与磺酰氯在碱存在下反应；伯胺易双磺酰化。",
            "match": True})

    # 6. Fischer 酯化
    if _has(r, "acid") and _has(r, "alcohol") and _has(p, "ester") and not _has(p, "amide"):
        return ("fischer_esterification", "Fischer 酯化（羧酸 + 醇）", {
            "temperature": "回流（65–110 °C），共沸除水",
            "reagents": ["浓 H2SO4（催化量）", "或 p-TsOH、DCC/DMAP、EDCI/DMAP"],
            "solvents": ["醇过量兼作溶剂", "甲苯（共沸带水）"],
            "catalysts": ["H2SO4 或 p-TsOH（酸催化）"],
            "note": "酸催化可逆酯化，需除水推动平衡；对酸敏感底物改用 DCC/DMAP。",
            "match": True})

    # 7. 酰胺缩合
    if _any(r, ["acid", "acyl_halide", "anhydride"]) and _has(p, "amide"):
        return ("amide_coupling", "酰胺缩合（羧酸/酰氯 + 胺）", {
            "temperature": "0 °C → 室温",
            "reagents": ["HATU 或 EDCI/HOBt（缩合剂）", "DIPEA 或 Et3N（碱，2–3 当量）",
                         "或用酰氯 + 缚酸剂"],
            "solvents": ["DMF", "DCM", "DMAc"],
            "catalysts": ["DMAP（催化量，酰化催化）"],
            "note": "羧酸需先活化（HATU/EDCI）；酰氯路线需缚酸剂并控温抑制消旋。",
            "match": True})

    # 8. 羰基还原（酮/醛 → 醇）
    if _has(r, "carbonyl") and _has(p, "alcohol") and not _has(p, "carbonyl"):
        return ("carbonyl_reduction", "羰基还原为醇", {
            "temperature": "0 °C → 室温",
            "reagents": ["NaBH4（温和，0–25 °C）", "LiAlH4（强还原，0 °C→回流，无水醚类）"],
            "solvents": ["MeOH 或 EtOH（NaBH4）", "无水 THF 或 Et2O（LiAlH4）"],
            "catalysts": [],
            "note": "NaBH4 还原醛/酮；LiAlH4 可还原酯/羧酸，需无水无氧操作。",
            "match": True})

    # 9. 醇/胺氧化
    if _has(r, "alcohol") and _has(p, "carbonyl") and not _has(r, "carbonyl"):
        return ("oxidation", "醇氧化为醛/酮", {
            "temperature": "0 °C → 室温",
            "reagents": ["PCC 或 PDC（DCM 中）", "Swern（草酰氯/DMSO/Et3N，-78 °C）",
                         "Dess-Martin 高碘烷", "TEMPO/NaOCl"],
            "solvents": ["DCM", "DMSO"],
            "catalysts": ["TEMPO（催化氧化）"],
            "note": "PCC/Dess-Martin 温和且停于醛酮；Swern 需低温。",
            "match": True})

    # 10. 加氢还原（烯烃/炔烃）
    if _any(r, ["alkene", "alkyne"]) and not _any(p, ["alkene", "alkyne"]):
        return ("hydrogenation", "不饱和键催化加氢", {
            "temperature": "室温（1–4 atm H2）",
            "reagents": ["H2（1–4 atm）", "或 环己烯/甲酸铵 作氢源转移氢化"],
            "solvents": ["MeOH", "EtOAc", "EtOH"],
            "catalysts": ["Pd/C（5–10%）", "PtO2（Adams）", "Raney Ni"],
            "note": "催化加氢；注意脱苄/脱卤等副反应，可用 Lindlar 控制顺式半加氢。",
            "match": True})

    # 11. Buchwald-Hartwig 胺化
    if _has(r, "aryl_halide") and _has(r, "aromatic_amine") and _has(p, "aromatic_amine"):
        return ("buchwald", "Buchwald–Hartwig C–N 偶联", {
            "temperature": "80–110 °C",
            "reagents": ["Cs2CO3 或 NaOtBu（强碱）", "BINAP 或 Xantphos 配体"],
            "solvents": ["甲苯", "1,4-二氧六环", "DMF"],
            "catalysts": ["Pd(OAc)2 或 Pd2(dba)3（2–5 mol%）"],
            "note": "Pd 催化芳胺化，无水无氧，强碱与双齿膦配体。",
            "match": True})

    # 12. 叠氮还原/Click 相关
    if _has(r, "azide") and _has(p, "primary_amine"):
        return ("azide_reduction", "叠氮还原为伯胺", {
            "temperature": "室温",
            "reagents": ["PPh3/H2O（Staudinger）", "或 H2/Pd-C、NaBH4"],
            "solvents": ["THF/H2O", "MeOH"],
            "catalysts": [],
            "note": "Staudinger 反应温和；亦可用催化加氢。",
            "match": True})

    # 兜底
    tpl = "室温～80 °C（按底物与官能团耐受性调整）"
    return ("unknown", "未识别的转化类型", {
        "temperature": tpl,
        "reagents": [], "solvents": [], "catalysts": [],
        "note": "未匹配到具体命名反应类型，条件主要依据先例检索给出。",
        "match": False})
