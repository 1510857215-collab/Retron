# -*- coding: utf-8 -*-
"""实验脚本：比较生成参数/输入格式，覆盖经典反应"""
import os, sys, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from rdkit import Chem, RDLogger
RDLogger.DisableLog("rdApp.*")

M = r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForSeq2SeqLM.from_pretrained(M).eval()

def canon(s):
    m = Chem.MolFromSmiles(s)
    return Chem.MolToSmiles(m) if m else None

def run(text, **kw):
    inp = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inp, return_dict_in_generate=True, output_scores=True, **kw)
    seqs = [tok.decode(s, skip_special_tokens=True).replace(" ", "").rstrip(".") for s in out["sequences"]]
    scs = out["sequences_scores"].tolist() if out.get("sequences_scores") is not None else [0.0]*len(seqs)
    return seqs, scs

CASES = [
    ("乙酰化", "CC(=O)OC(C)=O.O=C(O)c1ccccc1O", None, "CC(=O)Oc1ccccc1C(=O)O"),
    ("酯化",   "CC(=O)O.CCO", None, "CCOC(C)=O"),
    ("Suzuki", "OB(O)c1ccccc1.Brc1ccccc1", None, "c1ccc(-c2ccccc2)cc1"),
    ("硝化",   "c1ccccc1.O=N(O)O", None, "O=[N+]([O-])c1ccccc1"),
    ("还原",   "O=[N+]([O-])c1ccccc1.[H][H]", None, "Nc1ccccc1"),
    ("卤代",   "c1ccccc1.BrBr", None, "Brc1ccccc1"),
]

def show(title, **kw):
    print("="*70); print("SETTING:", title, kw)
    for name, r, c, exp in CASES:
        reag = (" " if not c else c)
        text = "REACTANT:%sREAGENT:%s" % (r, reag)
        t=time.time()
        seqs, scs = run(text, **kw)
        dt=time.time()-t
        expc = canon(exp)
        hit = None
        for i,(s,sc) in enumerate(zip(seqs,scs)):
            c2 = canon(s)
            ok = (c2==expc) or (expc in [canon(x) for x in s.split(".")])
            if ok and hit is None: hit=i
        print("[%s] %.2fs exp=%s hit@%s" % (name, dt, exp, hit))
        for i,(s,sc) in enumerate(zip(seqs,scs)):
            mark = "  <<<" if canon(s)==expc else ("  (含)" if expc in [canon(x) for x in s.split(".")] else "")
            print("    %d %.3f %s%s" % (i, sc, s, mark))

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv)>1 else "all"
    if which in ("all","a"):
        show("beams5 ret5 max150", num_beams=5, num_return_sequences=5, max_length=150)
    if which in ("all","b"):
        show("beams5 ret5 max150 lp0.6", num_beams=5, num_return_sequences=5, max_length=150, length_penalty=0.6)
    if which in ("all","c"):
        show("greedy beams1", num_beams=1, num_return_sequences=1, max_length=150)
