# -*- coding: utf-8 -*-
"""用主环境(tools/venv, 含 rdkit)生成 6 张分子结构测试图。
运行: "C:\\Users\\zzl\\Desktop\\hx\\tools\\venv\\Scripts\\python.exe" vision_gen_images.py
"""
import os
from rdkit import Chem
from rdkit.Chem import Draw, AllChem

OUT = r"C:\Users\zzl\Desktop\hx\data\vision\测试"

# 分子清单：文件名, 原始 SMILES, 中文名
MOLECULES = [
    ("阿司匹林",   "CC(=O)Oc1ccccc1C(=O)O",              "阿司匹林"),
    ("咖啡因",     "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",        "咖啡因"),
    ("苯",         "c1ccccc1",                            "苯"),
    ("布洛芬",     "CC(C)Cc1ccc(C(C)C(=O)O)cc1",          "布洛芬"),
    ("对乙酰氨基酚", "CC(=O)NC1=CC=C(O)C=C1",              "对乙酰氨基酚"),
    ("水杨酸",     "O=C(O)c1ccccc1O",                     "水杨酸"),
    # 以下为选型对比补充
    ("苯甲酸",     "OC(=O)c1ccccc1",                      "苯甲酸"),
    ("烟酸",       "OC(=O)c1cccnc1",                      "烟酸"),
    ("乙酸乙酯",   "CCOC(C)=O",                           "乙酸乙酯"),
    ("萘",         "c1ccc2ccccc2c1",                      "萘"),
    ("烟酰胺",     "NC(=O)c1cccnc1",                      "烟酰胺"),
    ("葡萄糖",     "OCC1OC(O)C(O)C(O)C1O",                "葡萄糖（2D 无立体）"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, smi, _zh in MOLECULES:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            print(f"[跳过] {name} SMILES 无效: {smi}")
            continue
        mol = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol)
        mol = Chem.RemoveHs(mol)
        path = os.path.join(OUT, f"{name}.png")
        # 默认 300x300 白底黑线，与论文截图风格接近
        Draw.MolToFile(mol, path, size=(400, 400))
        print(f"[已生成] {path}  原SMILES={smi}")

    # 额外生成一张放大的（1600x1600）用于验证超大图缩放路径
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    AllChem.Compute2DCoords(mol)
    big = os.path.join(OUT, "阿司匹林_超大图.png")
    Draw.MolToFile(mol, big, size=(1600, 1600))
    print(f"[已生成] {big} (1600x1600 用于测缩放)")


if __name__ == "__main__":
    main()
