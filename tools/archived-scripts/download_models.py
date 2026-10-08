# -*- coding: utf-8 -*-
"""
AiZynthFinder 公共数据下载器（离线镜像版）
------------------------------------------------
背景：本机网络对 zenodo.org 做了 DNS 劫持（解析为 0.0.0.0），figshare/huggingface 亦被封禁。
解决：用公共 DoH 获得 zenodo 真实 IP，再用 socket 补丁把 zenodo.org 重定向到该 IP，
      同时用 HTTP Range 分块 + 多线程并发下载（单连接被限速 ~13KB/s，多连接可聚合到 ~900KB/s）。

用法：
  python download_models.py <目标目录>

必须用 tools\\venv-retro\\Scripts\\python.exe 运行（依赖 requests）。
"""
import os
import sys
import time
import hashlib
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ---- zenodo 真实 IP（由阿里 DoH 223.5.5.5 查询得到，多 IP 轮换增强稳定性）----
ZENODO_IPS = [
    "137.138.52.235",
    "188.184.98.114",
    "137.138.153.219",
    "188.184.103.118",
    "188.185.48.75",
]

# ---- 待下载文件清单（来源：zenodo record 11430881，含官方 md5）----
ZENODO_RECORD = "11430881"
FILES = [
    # (文件名, 官方 md5)
    ("uspto_model.onnx",                  "b466a436b6a8eceaba8c14ef5e2a88c8"),
    ("uspto_templates.csv.gz",            "e8fb29d4dcd54073658000e212b7845a"),
    ("uspto_ringbreaker_model.onnx",      "2aa7ee99d29a910369e723a73fc13044"),
    ("uspto_ringbreaker_templates.csv.gz", "a6d0117ee6122e2cca3b7f8efa35541d"),
    ("uspto_filter_model.onnx",           "ab0df54b62a0aeceecd68051f8dc3f2e"),
    ("zinc_stock.hdf5",                   "2888ffca8873e6a11478cbdda7154f03"),
]

CHUNK_SIZE = 2 * 1024 * 1024      # 每个分块 2MB（块越小并发越足）
MAX_WORKERS = 96                  # 并发线程数（多 IP 轮询 + 多连接聚合带宽）
MAX_RETRY = 6                     # 单块最大重试次数
TIMEOUT = 120                     # 单请求超时（秒）


def install_dns_patch():
    """把 zenodo.org 的 DNS 解析重定向到真实 IP，绕过本地 DNS 劫持。

    关键：多个真实 IP 轮询使用——单 IP 会被服务端限流（~150KB/s），
    多 IP × 多连接可聚合到 ~1.2MB/s。
    """
    real_getaddrinfo = socket.getaddrinfo
    counter = {"i": 0}
    lock = threading.Lock()

    def patched(host, port, *args, **kwargs):
        if host == "zenodo.org":
            with lock:
                ip = ZENODO_IPS[counter["i"] % len(ZENODO_IPS)]
                counter["i"] += 1
            return real_getaddrinfo(ip, port, *args, **kwargs)
        return real_getaddrinfo(host, port, *args, **kwargs)

    socket.getaddrinfo = patched


def md5_of_file(path, buf=1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def file_url(name):
    return ("https://zenodo.org/records/%s/files/%s?download=1"
            % (ZENODO_RECORD, name))


def get_size(url):
    """HEAD 获取文件真实大小（多 IP 重试）。"""
    last = None
    for attempt in range(10):
        ip = ZENODO_IPS[attempt % len(ZENODO_IPS)]
        try:
            r = requests.head(url, timeout=30, allow_redirects=True)
            if r.status_code == 200 and "Content-Length" in r.headers:
                return int(r.headers["Content-Length"])
            last = "HTTP %s" % r.status_code
        except Exception as e:
            last = str(e)
    raise RuntimeError("无法获取大小 %s: %s" % (url, last))


_lock = threading.Lock()
_done = {"bytes": 0}


def download_chunk(url, path, start, end, idx):
    """下载 [start, end] 字节区间，写入目标文件的对应偏移（每线程独立句柄）。"""
    expect = end - start + 1
    last_err = None
    for attempt in range(MAX_RETRY):
        ip = ZENODO_IPS[(idx + attempt) % len(ZENODO_IPS)]
        try:
            headers = {"Range": "bytes=%d-%d" % (start, end)}
            r = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
            if r.status_code not in (200, 206):
                last_err = "HTTP %s" % r.status_code
                time.sleep(1 + attempt)
                continue
            buf = bytearray()
            for piece in r.iter_content(chunk_size=256 * 1024):
                buf += piece
            if len(buf) != expect:
                last_err = "长度不符 got=%d want=%d" % (len(buf), expect)
                time.sleep(1 + attempt)
                continue
            # 独立句柄写入指定偏移
            with open(path, "r+b") as f:
                f.seek(start)
                f.write(buf)
            with _lock:
                _done["bytes"] += expect
            return True
        except Exception as e:
            last_err = repr(e)
            time.sleep(1 + attempt)
    raise RuntimeError("分块 %d 下载失败(%d-%d): %s" % (idx, start, end, last_err))


def download_one(dest_dir, name, want_md5):
    path = os.path.join(dest_dir, name)
    print("\n===== %s =====" % name)
    if os.path.exists(path) and md5_of_file(path) == want_md5:
        print("  已存在且 md5 正确，跳过")
        return True

    url = file_url(name)
    size = get_size(url)
    print("  大小: %d 字节 (%.1f MB)" % (size, size / 1024 / 1024))

    # 预分配文件（全 0），随后各线程按偏移写入
    with open(path, "wb") as f:
        f.truncate(size)

    ranges = []
    s = 0
    idx = 0
    while s < size:
        e = min(s + CHUNK_SIZE - 1, size - 1)
        ranges.append((s, e, idx))
        s = e + 1
        idx += 1
    total = len(ranges)
    print("  分块数: %d, 并发: %d" % (total, MAX_WORKERS))

    _done["bytes"] = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(download_chunk, url, path, a, b, c) for (a, b, c) in ranges]
        ok = 0
        for fut in as_completed(futs):
            fut.result()  # 失败会抛异常
            ok += 1
            if ok % 10 == 0 or ok == total:
                el = time.time() - t0
                sp = _done["bytes"] / el if el > 0 else 0
                print("  进度 %d/%d  用时 %.0fs  速率 %.0f KB/s"
                      % (ok, total, el, sp / 1024))
    print("  校验 md5 ...")
    got = md5_of_file(path)
    if got != want_md5:
        print("  !! md5 不符: got=%s want=%s" % (got, want_md5))
        return False
    print("  OK  md5 正确: %s  用时 %.0fs" % (got, time.time() - t0))
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python download_models.py <目标目录>")
        sys.exit(1)
    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)
    install_dns_patch()
    print("目标目录:", dest)
    results = {}
    for name, want in FILES:
        try:
            results[name] = download_one(dest, name, want)
        except Exception as e:
            print("  !! 失败: %s : %s" % (name, e))
            results[name] = False
    print("\n================ 汇总 ================")
    for name, ok in results.items():
        print("  %-38s %s" % (name, "OK" if ok else "失败"))
    if not all(results.values()):
        sys.exit(2)


if __name__ == "__main__":
    main()
