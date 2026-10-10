# -*- coding: utf-8 -*-
"""torchtext.vocab 桩模块。"""
from torchtext import _Stub, _make

Vocab = _make("Vocab")
Vectors = _make("Vectors")
GloVe = _make("GloVe")
FastText = _make("FastText")
CharNGram = _make("CharNGram")


def __getattr__(name):
    return _make(name)
