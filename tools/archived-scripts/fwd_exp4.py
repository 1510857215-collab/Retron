# -*- coding: utf-8 -*-
import os, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")
M = r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
DEV="cuda" if torch.cuda.is_available() else "cpu"
tok=AutoTokenizer.from_pretrained(M); model=AutoModelForSeq2SeqLM.from_pretrained(M).eval().to(DEV)
def canon(s):
    m=Chem.MolFromSmiles(s); return Chem.MolToSmiles(m) if m else None
def run(r,g,exp):
    inp=tok("REACTANT:%sREAGENT:%s"%(r,g if g else " "),return_tensors="pt").to(DEV)
    with torch.no_grad():
        out=model.generate(**inp,return_dict_in_generate=True,output_scores=True,num_beams=5,num_return_sequences=5,max_length=150)
    seqs=[tok.decode(s,skip_special_tokens=True).replace(" ","").rstrip(".") for s in out["sequences"]]
    expc=canon(exp); hit=lambda s:canon(s)==expc or expc in [canon(x) for x in s.split(".")]
    hs=[i for i,s in enumerate(seqs) if hit(s)]
    return seqs,out["sequences_scores"].tolist(),(hs[0] if hs else None)
PDP="Cl[Pd](Cl)([P](c1ccccc1)(c1ccccc1)c1ccccc1)[P](c1ccccc1)(c1ccccc1)c1ccccc1"
CASES=[
 ("S1 催化剂+碱入REAGENT", "Brc1ccccc1.OB(O)c1ccccc1", PDP+".CC(=O)[O-].[K+]", "c1ccc(-c2ccccc2)cc1"),
 ("S2 全部REACTANT", "Brc1ccccc1.OB(O)c1ccccc1."+PDP+".CC(=O)[O-].[K+]", "", "c1ccc(-c2ccccc2)cc1"),
 ("S3 简单PdCl2", "Brc1ccccc1.OB(O)c1ccccc1.Cl[Pd]Cl.CC(=O)[O-].[K+]", "", "c1ccc(-c2ccccc2)cc1"),
 ("S4 硼酸在前", "OB(O)c1ccccc1.Brc1ccccc1."+PDP+".CC(=O)[O-].[K+]", "", "c1ccc(-c2ccccc2)cc1"),
 ("S5 4-溴甲苯偶联", "Cc1ccc(Br)cc1.OB(O)c1ccccc1."+PDP+".CC(=O)[O-].[K+]", "", "Cc1ccc(-c2ccccc2)cc1"),
 ("S6 碘苯", "Ic1ccccc1.OB(O)c1ccccc1."+PDP+".CC(=O)[O-].[K+]", "", "c1ccc(-c2ccccc2)cc1"),
]
for name,r,g,exp in CASES:
    t=time.time(); seqs,scs,h=run(r,g,exp); print("[%s] %.1fs hit=%s"%(name,time.time()-t,h))
    for i,(s,sc) in enumerate(zip(seqs,scs)): print("    %d %7.3f %s"%(i,sc,s))
