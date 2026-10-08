# -*- coding: utf-8 -*-
import os, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
M=r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
tok=AutoTokenizer.from_pretrained(M); model=AutoModelForSeq2SeqLM.from_pretrained(M).eval()
inp=tok("REACTANT:CC(=O)OC(C)=O.O=C(O)c1ccccc1OREAGENT: ", return_tensors="pt")
for be in (1,5):
    t=time.time()
    out=model.generate(**inp,num_beams=be,num_return_sequences=be,max_length=150)
    print("beams=%d time=%.2fs" % (be, time.time()-t))
