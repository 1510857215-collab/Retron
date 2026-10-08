# -*- coding: utf-8 -*-
"""
check_runtime_deps.py —— 运行环境依赖体检（换电脑前必查）
================================================================
用途：扫描 tools 下所有 Python 扩展（.pyd）与动态库（.dll）的 PE 导入表，
      找出"依赖了本机系统库、但目标电脑可能没有"的条目。

判据：凡是导入下列前缀的 dll，都属于 Microsoft Visual C++ 运行库，
      干净的 Windows 上不保证存在 —— 必须随软件一起分发：
        vcruntime140*.dll / msvcp140*.dll / concrt140*.dll / vccorlib140*.dll

用法：
    tools\\python311\\python.exe tools\\check_runtime_deps.py [--dirs tools\\venv,tools\\python311]
输出：缺失清单（应随包分发的 dll 有哪些、当前放在哪里），并在结尾给出结论。
退出码：0 = 依赖齐全；1 = 有需要补的
"""
import os
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 随软件分发即可满足的 MSVC 运行库前缀
MSVC_PREFIX = ("vcruntime140", "msvcp140", "concrt140", "vccorlib140",
               "msvcp_win", "vcruntime")
# 系统自带、任何 Windows 都有的（无需随包）
SYSTEM_OK = (
    "kernel32", "user32", "advapi32", "ole32", "oleaut32", "shell32",
    "shlwapi", "ws2_32", "gdi32", "msvcrt", "ucrtbase", "ntdll", "comdlg32",
    "comctl32", "crypt32", "bcrypt", "secur32", "rpcrt4", "version", "psapi",
    "winmm", "imm32", "netapi32", "userenv", "dbghelp", "setupapi", "cfgmgr32",
    "powrprof", "iphlpapi", "dnsapi", "wintrust", "sspicli", "dwmapi", "uxtheme",
)


def _rva2off(sections, rva):
    for vaddr, vsize, raddr, rsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raddr + (rva - vaddr)
    return None


def imports_of(path):
    """读取 PE 导入表，返回依赖的 dll 名称列表（小写）。失败返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read(1 << 24)
    except Exception:
        return None
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    try:
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            return None
        coff = e_lfanew + 4
        nsec = struct.unpack_from("<H", data, coff + 2)[0]
        opt_size = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", data, opt)[0]
        dd = opt + (96 if magic == 0x10B else 112)
        imp_rva = struct.unpack_from("<I", data, dd + 8)[0]
        if imp_rva == 0:
            return []
        sec_base = opt + opt_size
        sections = []
        for i in range(nsec):
            b = sec_base + i * 40
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, b + 8)
            sections.append((vaddr, vsize, raddr, rsize))
        off = _rva2off(sections, imp_rva)
        if off is None:
            return []
        names = []
        while True:
            if off + 20 > len(data):
                break
            oft, _tds, _fc, name_rva, ft = struct.unpack_from("<IIIII", data, off)
            if oft == 0 and name_rva == 0 and ft == 0:
                break
            no = _rva2off(sections, name_rva)
            if no is None or no >= len(data):
                break
            end = data.find(b"\0", no)
            if end < 0:
                break
            names.append(data[no:end].decode("latin1").lower())
            off += 20
        return names
    except Exception:
        return None


def classify(dep):
    """把依赖名分成：系统自带 / MSVC 运行库 / 其他第三方"""
    stem = dep[:-4] if dep.endswith(".dll") else dep
    if dep.startswith("api-ms-win") or dep.startswith("ext-ms-win"):
        return "system"
    if stem in SYSTEM_OK:
        return "system"
    if stem.startswith("python") or stem.startswith("_") or stem in ("python3",):
        return "internal"
    for p in MSVC_PREFIX:
        if stem.startswith(p):
            return "msvc"
    return "other"


def scan_dir(base, found_msvc, other_deps):
    pyd = dll = 0
    for dirpath, _dirnames, filenames in os.walk(base):
        # 跳过明显的无关大目录，加速
        for fn in filenames:
            low = fn.lower()
            if not (low.endswith(".pyd") or low.endswith(".dll")):
                continue
            ext = low.rsplit(".", 1)[-1]
            if ext == "pyd":
                pyd += 1
            else:
                dll += 1
            full = os.path.join(dirpath, fn)
            deps = imports_of(full)
            if not deps:
                continue
            for d in deps:
                kind = classify(d)
                if kind == "msvc":
                    found_msvc[d].add(os.path.relpath(full, ROOT))
                elif kind == "other":
                    other_deps[d].add(os.path.relpath(full, ROOT))
    return pyd, dll


def main():
    dirs = ["tools/python311", "tools/venv", "tools/venv-retro",
            "tools/venv-vision", "tools/venv-forward", "tools/venv-conditions"]
    if "--dirs" in sys.argv:
        dirs = sys.argv[sys.argv.index("--dirs") + 1].split(",")

    found_msvc = defaultdict(set)
    other_deps = defaultdict(set)
    print("== Retron 运行环境依赖体检 ==")
    print("扫描范围:", ", ".join(dirs))
    tot_pyd = tot_dll = 0
    for d in dirs:
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        a, b = scan_dir(p, found_msvc, other_deps)
        tot_pyd += a
        tot_dll += b
        print("- %-22s pyd %5d / dll %5d" % (d, a, b))
    print("合计: pyd %d, dll %d" % (tot_pyd, tot_dll))

    print("\n[1] 依赖的 MSVC 运行库（必须随软件分发）")
    if not found_msvc:
        print("    （无）")
    for dep in sorted(found_msvc):
        n = len(found_msvc[dep])
        # 检查是否已随包
        have = []
        for cand in ("tools/python311",):
            if os.path.exists(os.path.join(ROOT, cand, dep)):
                have.append(cand + "/" + dep)
        state = ("已随包: " + ", ".join(have)) if have else "**未随包，需补**"
        print("    %-28s 被 %4d 个模块依赖  %s" % (dep, n, state))

    print("\n[2] 其他非系统依赖（信息参考，通常由各包自带）")
    hard = {k: v for k, v in other_deps.items()
            if not any(os.path.exists(os.path.join(ROOT, dd, k))
                       for dd in ("tools/python311", "tools/python311/DLLs"))}
    if not hard:
        print("    （无）")
    for dep in sorted(hard)[:60]:
        print("    %-34s 被 %4d 个模块依赖" % (dep, len(hard[dep])))
    if len(hard) > 60:
        print("    ... 另有 %d 项" % (len(hard) - 60))

    missing = [d for d in found_msvc
               if not os.path.exists(os.path.join(ROOT, "tools/python311", d))]
    print("\n== 结论 ==")
    if missing:
        print("需要补进 tools/python311 的运行库：", ", ".join(sorted(missing)))
        return 1
    print("依赖齐全：所有 MSVC 运行库均已随包，换电脑可正常加载。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
