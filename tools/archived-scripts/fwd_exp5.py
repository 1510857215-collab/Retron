# -*- coding: utf-8 -*-
import os, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")
M=r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
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
# 验证 SMILES 合法性
for s in ["O[N+](=O)[O-]","O=N(O)O","[N+](=O)(O)[O-]","O=S(=O)(O)O","Br[Fe](Br)Br"]:
    print("valid?", s, canon(s))
print("="*70)
CASES=[
 ("硝化A HNO3合法+H2SO4", "c1ccccc1.O[N+](=O)[O-].O=S(=O)(O)O", "", "O=[N+]([O-])c1ccccc1"),
 ("硝化B 仅HNO3", "c1ccccc1.O[N+](=O)[O-]", "", "O=[N+]([O-])c1ccccc1"),
 ("硝化C HNO3入REAGENT", "c1ccccc1", "O[N+](=O)[O-].O=S(=O)(O)O", "O=[N+]([O-])c1ccccc1"),
 ("卤代A 仅Br2", "c1ccccc1.BrBr", "", "Brc1ccccc1"),
 ("卤代B FeBr3入REAGENT", "c1ccccc1.BrBr", "Br[Fe](Br)Br", "Brc1ccccc1"),
 ("卤代C Br2+Fe", "c1ccccc1.BrBr.[Fe]", "", "Brc1ccccc1"),
 ("卤代D 苯酚+Br2→三溴苯酚", "Oc1ccccc1.BrBr", "", "Oc1c(Br)cc(Br)cc1Br"),
 ("卤代E NBS苄位", "Cc1ccccc1.O=C1CCC(=O)N1Br", "", "BrCc1ccccc1"),
 ("卤代F 苯酚+Br2(2)", "Oc1ccccc1.BrBr", "", "Oc1ccc(Br)cc1"),
]
for name,r,g,exp in CASES:
    t=time.time(); seqs,scs,h=run(r,g,exp); print("[%s] %.1fs hit=%s"%(name,time.time()-t,h))
    for i,(s,sc) in list(enumerate(zip(seqs,scs)))[:5]: print("    %d %7.3f %s"%(i,sc,s))
