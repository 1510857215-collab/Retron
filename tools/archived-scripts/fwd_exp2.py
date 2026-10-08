# -*- coding: utf-8 -*-
"""实验2：输入格式（REACTANT/REAGENT 切分）对经典反应的影响，使用 GPU"""
import os, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")

M = r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
DEV = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForSeq2SeqLM.from_pretrained(M).eval().to(DEV)
print("device", DEV)

def canon(s):
    m = Chem.MolFromSmiles(s)
    return Chem.MolToSmiles(m) if m else None

def run(text, **kw):
    inp = tok(text, return_tensors="pt").to(DEV)
    with torch.no_grad():
        out = model.generate(**inp, return_dict_in_generate=True, output_scores=True,
                             num_beams=5, num_return_sequences=5, max_length=150, **kw)
    seqs = [tok.decode(s, skip_special_tokens=True).replace(" ", "").rstrip(".") for s in out["sequences"]]
    return seqs, out["sequences_scores"].tolist()

def check(name, reactant, reagent, exp):
    text = "REACTANT:%sREAGENT:%s" % (reactant, reagent if reagent else " ")
    t=time.time()
    seqs, scs = run(text)
    expc = canon(exp)
    def ishit(s):
        parts=[canon(x) for x in s.split(".")]
        return (canon(s)==expc) or (expc in parts)
    hits=[i for i,s in enumerate(seqs) if ishit(s)]
    print("  [%s] %.1fs hit=%s" % (name, time.time()-t, hits[0] if hits else "None"))
    for i,(s,sc) in enumerate(zip(seqs,scs)):
        print("     %d  %7.3f  %s%s" % (i, sc, s, "  <<<" if ishit(s) else ""))

# 每个反应给两种切分：(A) 全部放 REACTANT；(B) 底物放 REACTANT，催化剂/碱放 REAGENT
CASES = [
 ("乙酰化", "CC(=O)OC(C)=O.O=C(O)c1ccccc1O", "", "CC(=O)Oc1ccccc1C(=O)O"),
 ("乙酰化B","O=C(O)c1ccccc1O", "CC(=O)OC(C)=O", "CC(=O)Oc1ccccc1C(=O)O"),
 ("酯化",   "CC(=O)O.CCO", "O=S(=O)(O)O", "CCOC(C)=O"),
 ("酯化B",  "CC(=O)O.CCO", "", "CCOC(C)=O"),
 ("Suzuki", "Brc1ccccc1.OB(O)c1ccccc1.Cl[Pd](Cl)([P](c1ccccc1)(c1ccccc1)c1ccccc1)[P](c1ccccc1)(c1ccccc1)c1ccccc1", "CC(=O)[O-].[K+]", "c1ccc(-c2ccccc2)cc1"),
 ("SuzukiB","Brc1ccccc1.OB(O)c1ccccc1", "", "c1ccc(-c2ccccc2)cc1"),
 ("硝化",   "c1ccccc1.O=N(O)O", "O=S(=O)(O)O", "O=[N+]([O-])c1ccccc1"),
 ("还原",   "O=[N+]([O-])c1ccccc1.[H][H]", "Cl[Pd]Cl", "Nc1ccccc1"),
 ("卤代",   "c1ccccc1.BrBr", "Br[Fe](Br)Br", "Brc1ccccc1"),
 ("氧化",   "Cc1ccccc1", "O=[Mn](=O)(=O)[O-].[K+]", "O=C(O)c1ccccc1"),
 ("皂化",   "CC(=O)Oc1ccccc1C(=O)O", "O.O.[Na+].[OH-]", "O=C(O)c1ccccc1O"),
]
import sys
sel = sys.argv[1] if len(sys.argv)>1 else None
for name, r, g, exp in CASES:
    if sel and sel not in name: continue
    check(name, r, g, exp)
