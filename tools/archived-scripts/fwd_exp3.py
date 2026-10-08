# -*- coding: utf-8 -*-
"""实验3：为「酯化 / 氧化」寻找模型能答对的经典实例"""
import os, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")
M = r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
DEV = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(M); model = AutoModelForSeq2SeqLM.from_pretrained(M).eval().to(DEV)

def canon(s):
    m = Chem.MolFromSmiles(s); return Chem.MolToSmiles(m) if m else None
def run(reactant, reagent, exp):
    text = "REACTANT:%sREAGENT:%s" % (reactant, reagent if reagent else " ")
    inp = tok(text, return_tensors="pt").to(DEV)
    with torch.no_grad():
        out = model.generate(**inp, return_dict_in_generate=True, output_scores=True,
                             num_beams=5, num_return_sequences=5, max_length=150)
    seqs=[tok.decode(s,skip_special_tokens=True).replace(" ","").rstrip(".") for s in out["sequences"]]
    scs=out["sequences_scores"].tolist()
    expc=canon(exp)
    def hit(s): return canon(s)==expc or expc in [canon(x) for x in s.split(".")]
    hs=[i for i,s in enumerate(seqs) if hit(s)]
    return seqs,scs,(hs[0] if hs else None)

CASES=[
 # 酯化
 ("E1 酰氯+醇", "O=C(Cl)c1ccccc1.CCO", "", "CCOC(=O)c1ccccc1"),
 ("E2 乙酰氯+醇", "CC(=O)Cl.CCO", "", "CCOC(C)=O"),
 ("E3 酸+醇+H2SO4", "CC(=O)O.CCO.O=S(=O)(O)O", "", "CCOC(C)=O"),
 ("E4 苯甲酸+醇", "O=C(O)c1ccccc1.CCO", "O=S(=O)(O)O", "CCOC(=O)c1ccccc1"),
 ("E5 酸酐+醇", "CC(=O)OC(C)=O.CCO", "c1ccncc1", "CCOC(C)=O"),
 # 氧化
 ("O1 环己醇→酮(Jones)", "OC1CCCCC1.O=[Cr](=O)=O.O=S(=O)(O)O", "", "O=C1CCCCC1"),
 ("O2 苯甲醇→酸(KMnO4)", "OCc1ccccc1.O=[Mn](=O)(=O)[O-].[K+]", "", "O=C(O)c1ccccc1"),
 ("O3 苯甲醇→酸(Jones)", "OCc1ccccc1.O=[Cr](=O)=O.O=S(=O)(O)O", "", "O=C(O)c1ccccc1"),
 ("O4 苯乙醇→苯乙酮", "CC(O)c1ccccc1.O=[Cr](=O)=O.O=S(=O)(O)O", "", "CC(=O)c1ccccc1"),
 ("O5 环己醇→酮(KMnO4)", "OC1CCCCC1.O=[Mn](=O)(=O)[O-].[K+]", "", "O=C1CCCCC1"),
 ("O6 苯甲醇→醛(PCC)", "OCc1ccccc1.Cl[Cr](=O)(=O)[O-].[nH+]1ccccc1", "", "O=Cc1ccccc1"),
 ("O7 异丙醇→丙酮", "CC(C)O.O=[Cr](=O)=O.O=S(=O)(O)O", "", "CC(C)=O"),
]
for name,r,g,exp in CASES:
    t=time.time(); seqs,scs,h=run(r,g,exp); dt=time.time()-t
    print("[%s] %.1fs hit=%s" % (name,dt,h))
    for i,(s,sc) in enumerate(zip(seqs,scs)):
        print("    %d %7.3f %s" % (i,sc,s))
