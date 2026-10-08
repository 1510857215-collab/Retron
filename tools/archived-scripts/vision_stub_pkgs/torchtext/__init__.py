# -*- coding: utf-8 -*-
"""torchtext 桩模块（本机专用，仅供 onmt(OpenNMT-py 2.2.0) 在 PyTorch 2.x 环境下 import 通过）。

背景：MolScribe 的 Transformer 解码器直接复用了 OpenNMT-py 2.2.0 的若干模块（onmt.modules.*、
onmt.decoders.decoder.DecoderBase 等），而 `import onmt` 会连带 import onmt.inputters，
后者依赖已停止维护的 torchtext。我们并不使用 torchtext 的任何真实功能，
因此用这个“空桩”让 import 链走通，避免为 MolScribe 再降级 PyTorch。
"""


class _Stub:
    """万能占位类：可被继承、可被调用、可任意属性访问。"""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *args, **kwargs):
        return _Stub()

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


def _make(name):
    return type(name, (_Stub,), {})


def __getattr__(name):
    # 任何未显式定义的名字都返回一个占位类
    return _make(name)
