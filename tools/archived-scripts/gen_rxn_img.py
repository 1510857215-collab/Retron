# -*- coding: utf-8 -*-
"""生成一张反应式图片（水杨酸 + 乙酸酐 -> 阿司匹林），用于测试反应图识别。用 tools/venv 运行。"""
from rdkit import Chem
from rdkit.Chem import AllChem, Draw

smarts = "O=C(O)c1ccccc1O.CC(=O)OC(C)=O>>CC(=O)Oc1ccccc1C(=O)O"
rxn = AllChem.ReactionFromSmarts(smarts)
for mol in list(rxn.GetReactants()) + list(rxn.GetProducts()):
    AllChem.Compute2DCoords(mol)

img = Draw.ReactionToImage(rxn, subImgSize=(260, 260))
out = r"C:/Users/zzl/Desktop/hx/tools/tmp/rxn_test.png"
img.save(out)
print("反应图已生成:", out, "尺寸:", img.size)
