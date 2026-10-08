from .decoder import TransformerDecoder
from .embedding import Embeddings
try:  # 这个 vendored swin 是历史遗留死代码（真正用的是 timm.create_model），新版 timm 下导入会失败，容忍之
    from .swin_transformer import swin_base, swin_large
except Exception:
    swin_base = swin_large = None
