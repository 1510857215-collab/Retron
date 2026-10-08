# -*- coding: utf-8 -*-
"""
make_dist.py —— 生成可分发的完整版文件夹（便携版）
================================================================
把工作区里"运行必需"的部分，复制成一个干净、可直接拷到别的电脑的文件夹。

包含：Retron(exe 外壳) / app / web / engine / data / tools / 文档
排除：开发脚本、临时文件、缓存、运行时产物、Python 缓存

用法：
    tools\\python311\\python.exe tools\\make_dist.py [目标目录]
默认目标：桌面\\Retron-完整版
退出码：0 = 成功
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
DEFAULT_DIST = os.path.join(HOME, "Desktop", "Retron-完整版")

# 顶层目录（顺序即复制顺序）
DIRS = ["Retron", "app", "web", "engine", "data", "tools"]
FILES = ["使用说明.md", "蓝图.md", "首次使用必读.txt"]

# 精确排除：源路径 -> 该路径下要排除的子项
EXCLUDE = {
    "tools": ["tmp", "archived-scripts", "opsin"],
    "web": ["runtime"],
    "data": ["测试"],
}
# 全层级排除的目录名
XD_ALL = ["__pycache__", ".workbuddy", ".ipynb_checkpoints"]
# 排除的文件后缀
XF = ["*.pyc", "*.pyo", "*.log", "Thumbs.db", ".DS_Store"]


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f TB" % n


def dir_size(path):
    total = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def robocopy(src, dst, extra_xd=()):
    """用系统自带 robocopy 多线程复制（比 shutil 快得多）。"""
    os.makedirs(dst, exist_ok=True)
    args = ["robocopy", src, dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
            "/R:1", "/W:1", "/MT:8"]
    for d in list(XD_ALL) + list(extra_xd):
        args += ["/XD", d]
    args += ["/XF"] + XF
    try:
        r = subprocess.run(args, capture_output=True, timeout=7200)
        return r.returncode < 8          # robocopy: 0-7 都算成功
    except Exception as e:
        print("    robocopy 异常：%s" % e)
        return False


def main():
    dist = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIST
    dist = os.path.abspath(dist)

    print("== Retron 分发版打包 ==")
    print("源目录:", ROOT)
    print("目标目录:", dist)

    if os.path.exists(dist):
        print("目标已存在，先清空…")
        shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(dist, exist_ok=True)

    t0 = time.time()
    ok = True
    for d in DIRS:
        src = os.path.join(ROOT, d)
        if not os.path.isdir(src):
            print("- %-10s 不存在，跳过" % d)
            continue
        dst = os.path.join(dist, d)
        extra = EXCLUDE.get(d, [])
        print("- %-10s 复制中…%s" % (d, ("（排除 " + "、".join(extra) + "）") if extra else ""))
        if not robocopy(src, dst, extra):
            ok = False
            print("    复制失败！")
        else:
            print("    完成，%s" % human(dir_size(dst)))

    for f in FILES:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dist, f))
            print("- %s 已复制" % f)

    print("\n耗时 %.1f 分钟" % ((time.time() - t0) / 60.0))
    print("分发版总大小：%s" % human(dir_size(dist)))

    # 关键校验
    checks = [
        ("Retron/Retron.exe", "主程序"),
        ("app/server.py", "本地服务"),
        ("web/index.html", "主界面"),
        ("engine/chemistry/converter.py", "转换引擎"),
        ("data/中文名字典.sqlite", "化合物词典"),
        ("data/retro/zinc_stock.hdf5", "可购买化合物库"),
        ("tools/python311/python.exe", "基准解释器"),
        ("tools/venv/Scripts/python.exe", "主环境"),
        ("tools/venv-forward/Scripts/python.exe", "预测环境"),
        ("tools/repair_env.py", "环境自愈脚本"),
    ]
    print("\n== 关键文件校验 ==")
    allok = True
    for rel, desc in checks:
        p = os.path.join(dist, rel)
        good = os.path.exists(p)
        allok = allok and good
        print("  %s %-40s %s" % ("[OK]" if good else "[缺失]", rel, desc))

    print("\n== 结论 ==")
    if ok and allok:
        print("分发版生成成功：%s" % dist)
        return 0
    print("分发版生成有问题，请检查上面标出的项。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
