# -*- coding: utf-8 -*-
"""
repair_env.py —— 运行环境自愈（迁移到新位置/新电脑后修复 Python 环境路径）
================================================================
用途：软件文件夹被复制/安装到新的路径后，各引擎的 venv 配置（pyvenv.cfg）
      仍指向制作电脑的旧路径，会导致引擎无法启动。
      本脚本把配置里的路径引用重写为"当前位置"，并逐个探针验证。

原则：只改「路径引用」，不动任何包内容 —— 幂等、可重复运行、出错不影响数据。

用法（必须用项目自带的基准解释器运行）：
    tools\\python311\\python.exe tools\\repair_env.py [--quiet]
退出码：0 = 全部环境可用；1 = 有环境仍不可用（需人工检查）
"""
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))       # <root>\tools
BASE_PY = os.path.join(TOOLS, "python311", "python.exe")
VENVS = ["venv", "venv-retro", "venv-vision", "venv-forward", "venv-conditions"]

HOME_LINE = re.compile(r"^home\s*=.*$", re.M)
EXEC_LINE = re.compile(r"^executable\s*=.*$", re.M)
CMD_LINE = re.compile(r"^command\s*=.*$", re.M)


def probe(py):
    """探针：解释器能否启动。"""
    try:
        r = subprocess.run([py, "-c", "pass"], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def fix_venv(name):
    venv_dir = os.path.join(TOOLS, name)
    cfg = os.path.join(venv_dir, "pyvenv.cfg")
    py = os.path.join(venv_dir, "Scripts", "python.exe")
    result = {"name": name, "cfg": False, "probe_before": None,
              "probe_after": None, "skip": False}

    # 该引擎环境不存在（例如精简安装未包含此功能）→ 跳过，不算失败
    if not os.path.exists(cfg):
        result["skip"] = True
        result["note"] = "未安装（跳过）"
        return result
    if not os.path.exists(py):
        result["skip"] = True
        result["note"] = "无 python.exe（跳过）"
        return result

    result["probe_before"] = probe(py)

    with open(cfg, encoding="utf-8", errors="replace") as f:
        text = f.read()
    new_home = TOOLS + r"\python311"
    new_exe = new_home + r"\python.exe"
    # 注意：替换串里含 Windows 路径（\U、\p 等会被 re 当成转义序列），
    # 因此必须用 lambda 返回字面量，不能直接传字符串。
    new_text = HOME_LINE.sub(lambda m: "home = " + new_home, text)
    new_text = EXEC_LINE.sub(lambda m: "executable = " + new_exe, new_text)
    new_text = CMD_LINE.sub(
        lambda m: "command = " + new_exe + " -m venv " + venv_dir, new_text)
    if new_text != text:
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(new_text)
        result["cfg"] = True

    result["probe_after"] = probe(py)
    return result


def main():
    quiet = "--quiet" in sys.argv
    print("== Retron 运行环境自愈 ==")
    print("工具目录:", TOOLS)
    if not os.path.exists(BASE_PY):
        print("基准解释器缺失:", BASE_PY)
        return 1
    print("基准解释器:", BASE_PY, "(存在)")
    all_ok, fixed, skipped = True, 0, 0
    for name in VENVS:
        r = fix_venv(name)
        if r["skip"]:
            skipped += 1
            if not quiet:
                print("- %-16s %s" % (name, r.get("note", "")))
            continue
        ok = bool(r.get("probe_after"))
        all_ok = all_ok and ok
        if r.get("cfg"):
            fixed += 1
        if not quiet:
            print("- %-16s 修复前:%s 修复后:%s %s" % (
                name,
                "OK" if r.get("probe_before") else "FAIL",
                "OK" if r.get("probe_after") else "FAIL",
                "[已重写配置]" if r.get("cfg") else ""))
    print("== 自愈完成：%s（重写 %d 个配置，跳过 %d 个未安装）==" % (
        "全部环境可用" if all_ok else "有环境仍不可用（请检查）", fixed, skipped))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
