# -*- coding: utf-8 -*-
"""
图片 -> 分子结构（SMILES）识别引擎。

【运行环境 —— 必须遵守】
    本文件必须用独立环境 tools\\venv-vision 的 python 运行，例如：
        tools\\venv-vision\\Scripts\\python.exe
    不要用主环境 tools\\venv（那边没有装识别模型）。

【对外接口】
    recognize(image_path) -> dict
        成功: {"ok": True, "smiles": "...", "engine": "molscribe"}
        失败: {"ok": False, "error": "中文错误信息"}
    保证：任何情况下都不抛未捕获异常。

【识别引擎】
    - molscribe : MolScribe（PyTorch），权重来自 HuggingFace，缓存于 data\\vision\\models  ← 默认
    - decimer   : DECIMER 2.x（TensorFlow），模型来自 Zenodo，缓存于 data\\vision\\pystow
    可用环境变量 HX_VISION_ENGINE 切换（decimer / molscribe），默认见 DEFAULT_ENGINE。
    默认引擎 MolScribe 是"以实际识别效果选型"的结果：本地测试集上 12/13，优于 DECIMER 的 11/13，
    且冷启动更快（约 2 秒 vs 约 50 秒）。默认开启"失败自动换另一个引擎兜底"。

【维护须知（改引擎相关代码前先读）】
    1. MolScribe 包已按本机环境打过补丁，直接放在 venv 的 site-packages/molscribe 下，
       补丁内容：augment.py 兼容 albumentations 2.x、transformer/__init__ 容忍死的 swin 模块导入；
       补丁后的版本已直接应用于运行环境（site-packages）。
    2. venv 的 site-packages/torchtext 是"空桩"，仅为让 OpenNMT-py(2.2.0) 的 import 链通过，
       不含任何真实功能——不要拿它当真正的 torchtext 用。
    3. timm 必须保持 0.4.12（MolScribe 的 vendored swin 依赖它注册 'swin_base'）。
"""

import os
import sys
import tempfile
import traceback

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # engine\vision
PROJECT_ROOT = os.path.dirname(os.path.dirname(THIS_DIR))       # 项目根 hx
DATA_VISION = os.path.join(PROJECT_ROOT, "data", "vision")
TMP_DIR = os.path.join(PROJECT_ROOT, "tools", "tmp")

# 模型缓存位置（全部落在 data\vision 下，保证离线可用）
PYSTOW_HOME = os.path.join(DATA_VISION, "pystow")               # DECIMER 模型目录
MOLSCRIBE_CKPT = os.path.join(
    DATA_VISION, "models", "MolScribe_swin_base_char_aux_1m.pth"
)

# 默认引擎（可被环境变量 HX_VISION_ENGINE 覆盖）。
# 选型依据：本地 12 分子测试集 MolScribe 12/13、DECIMER 11/13，且 MolScribe 冷启动更快 → 取 MolScribe 为默认。
DEFAULT_ENGINE = os.environ.get("HX_VISION_ENGINE", "molscribe").strip().lower()

# 失败时按此顺序换引擎兜底
ENGINE_ORDER = ["molscribe", "decimer"]

# 超大图缩放：最长边超过该值就等比缩小，避免 4K 截图吃爆内存
MAX_SIDE = 2000
# 过小图放大：最长边小于该值就等比放大，提升识别率
MIN_SIDE = 96

# 让 DECIMER(pystow) 把模型下到我们的目录（必须在 import decimer 之前设置）
os.environ.setdefault("PYSTOW_HOME", PYSTOW_HOME)

SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# 模型单例缓存（首次加载后复用，避免每次识别都重新载入）
_decimer_fn = None        # DECIMER 的 predict_SMILES 函数
_molscribe_model = None   # MolScribe 模型对象


# ---------------------------------------------------------------------------
# 图像预处理
# ---------------------------------------------------------------------------
def _prepare_image(image_path: str) -> str:
    """读入图片，统一转 RGB 并按需等比缩放，返回一个临时图片路径。

    做这一步的目的：
      1. 统一格式，避免 RGBA / 调色板 / 16bit 等怪格式让引擎报错；
      2. 超大图（如 4K 截图）缩小，避免内存爆掉；
      3. 过小图放大，提高识别率。
    """
    from PIL import Image  # 延迟导入，避免影响模块导入速度

    img = Image.open(image_path)
    img = img.convert("RGB")  # 统一三通道
    w, h = img.size
    long_side = max(w, h)

    if long_side > MAX_SIDE:
        scale = MAX_SIDE / float(long_side)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    elif long_side < MIN_SIDE:
        scale = MIN_SIDE / float(long_side)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    os.makedirs(TMP_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="vision_src_", suffix=".png", dir=TMP_DIR)
    os.close(fd)
    img.save(tmp_path, format="PNG")
    return tmp_path


# ---------------------------------------------------------------------------
# 引擎加载（懒加载 + 单例）
# ---------------------------------------------------------------------------
def _load_decimer():
    """加载 DECIMER 引擎，返回 predict_SMILES 函数。首次会触发模型加载。"""
    global _decimer_fn
    if _decimer_fn is not None:
        return _decimer_fn
    # 再确认一次环境变量（保证 pystow 目录正确）
    os.environ.setdefault("PYSTOW_HOME", PYSTOW_HOME)
    # 注意：DECIMER 的包目录/顶层名是「大写」的 DECIMER（PyPI 元数据 top_level=DECIMER）。
    # 官方文档里的 `from decimer import ...` 在大小写敏感或部分 Windows 环境下会导入失败，
    # 所以这里先试小写、再退回大写。
    try:
        from decimer import predict_SMILES  # noqa: E402  首次 import 会加载模型
    except ModuleNotFoundError:
        from DECIMER import predict_SMILES  # noqa: E402
    _decimer_fn = predict_SMILES
    return _decimer_fn


def _load_molscribe():
    """加载 MolScribe 引擎（PyTorch，CPU 推理），返回模型对象。"""
    global _molscribe_model
    if _molscribe_model is not None:
        return _molscribe_model
    if not os.path.exists(MOLSCRIBE_CKPT):
        raise FileNotFoundError(
            f"MolScribe 权重不存在：{MOLSCRIBE_CKPT}"
        )
    import torch
    from molscribe import MolScribe
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _molscribe_model = MolScribe(MOLSCRIBE_CKPT, device=device)
    return _molscribe_model


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def _run_engine(engine: str, prepared_path: str) -> str:
    """真正跑识别，返回 SMILES 字符串。失败抛异常，由上层统一兜底。"""
    if engine == "decimer":
        fn = _load_decimer()
        smiles = fn(prepared_path)
        return str(smiles).strip()

    if engine == "molscribe":
        model = _load_molscribe()
        out = model.predict_image_file(prepared_path)
        return str(out.get("smiles", "")).strip()

    raise ValueError(f"不认识的引擎：{engine}")


def _log_error(engine: str, image_path: str):
    """把详细堆栈写到日志文件，方便排查；失败也不影响对外返回。"""
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
        with open(os.path.join(TMP_DIR, "vision_recognize_err.log"),
                  "a", encoding="utf-8") as f:
            f.write(f"[{engine}] {image_path}\n{traceback.format_exc()}\n\n")
    except Exception:
        pass


def recognize(image_path: str, engine: str = None, allow_fallback: bool = True) -> dict:
    """把结构式图片识别成 SMILES。

    参数:
        image_path    : png/jpg 等图片路径
        engine        : 可选，指定识别引擎（decimer / molscribe）；
                        不传则用 DEFAULT_ENGINE（或环境变量 HX_VISION_ENGINE）
        allow_fallback: 是否允许"首选引擎失败后自动换另一个引擎再试"，默认 True

    返回:
        成功: {"ok": True, "smiles": "...", "engine": "molscribe"}
        失败: {"ok": False, "error": "中文错误信息"}
    """
    engine = (engine or DEFAULT_ENGINE or "molscribe").strip().lower()
    if engine not in ENGINE_ORDER:
        engine = "molscribe"

    tmp_path = None
    try:
        # 1) 基本校验
        if not image_path or not isinstance(image_path, str):
            return {"ok": False, "error": "图片路径为空"}
        if not os.path.exists(image_path):
            return {"ok": False, "error": f"图片不存在：{image_path}"}
        if not os.path.isfile(image_path):
            return {"ok": False, "error": f"不是文件：{image_path}"}
        ext = os.path.splitext(image_path)[1].lower()
        if ext and ext not in SUPPORTED_EXT:
            return {"ok": False, "error": f"不支持的图片格式：{ext}"}

        # 2) 预处理（缩放 + 统一格式；顺带把中文/空格路径换成 ASCII 临时文件，
        #    规避 OpenCV 在 Windows 上读不了中文路径的问题）
        tmp_path = _prepare_image(image_path)

        # 3) 依次尝试引擎（首选 + 兜底）
        order = [engine]
        if allow_fallback:
            order += [e for e in ENGINE_ORDER if e != engine]

        errors = []
        for eng in order:
            try:
                smiles = _run_engine(eng, tmp_path)
                low = str(smiles or "").strip().lower()
                if low and low not in ("<invalid>", "invalid", "none", "null"):
                    return {"ok": True, "smiles": smiles, "engine": eng}
                errors.append(f"{eng}: 结果为空或无效（{str(smiles)[:40]}）")
            except Exception as e:  # noqa: BLE001 —— 单个引擎失败不影响整体兜底
                errors.append(f"{eng}: {type(e).__name__}: {e}")
                _log_error(eng, image_path)

        return {"ok": False, "error": "识别失败；" + " ｜ ".join(errors)}

    except Exception as e:  # noqa: BLE001 —— 对外绝不抛异常
        _log_error(engine, image_path)
        return {"ok": False, "error": f"识别失败：{type(e).__name__}: {e}"}

    finally:
        # 清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 命令行自测入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python structure_ocr.py <图片路径> [引擎]")
        sys.exit(1)
    _img = sys.argv[1]
    _eng = sys.argv[2] if len(sys.argv) > 2 else None
    print(recognize(_img, _eng))
