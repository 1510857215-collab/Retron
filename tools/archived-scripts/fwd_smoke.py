# -*- coding: utf-8 -*-
"""冒烟测试：离线从本地目录加载 ReactionT5v2-forward-USPTO_MIT 并预测"""
import os, time, sys
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

print("torch", torch.__version__, "cuda_available", torch.cuda.is_available())
import transformers
print("transformers", transformers.__version__)

MDIR = r"C:\Users\zzl\Desktop\hx\data\forward\模型\ReactionT5v2-forward-USPTO_MIT"
t0 = time.time()
tok = AutoTokenizer.from_pretrained(MDIR)
model = AutoModelForSeq2SeqLM.from_pretrained(MDIR)
model.eval()
print("load ok in %.1fs" % (time.time() - t0))

inp = tok("REACTANT:CC(=O)OC(C)=O.O=C(O)c1ccccc1OREAGENT: ", return_tensors="pt")
out = model.generate(**inp, num_beams=5, num_return_sequences=3, max_length=150, return_dict_in_generate=True, output_scores=True)
for s in out["sequences"]:
    print("  ->", repr(tok.decode(s, skip_special_tokens=True).replace(" ", "").rstrip(".")))
