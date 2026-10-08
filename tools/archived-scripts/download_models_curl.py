# -*- coding: utf-8 -*-
"""
AiZynthFinder 公共数据下载器（curl 子进程版 · 多 IP 聚合）
================================================================
背景：本机对 zenodo.org 做了 DNS 劫持（解析到 0.0.0.0），figshare/huggingface 被封。
方案：用阿里 DoH 查到 zenodo 真实 IP，再用 curl --resolve 指定 IP 直连；
      单连接被限速 ~17KB/s，用「多 IP × 多连接 × Range 分块」聚合到 ~1.2MB/s。

用法：  python download_models_curl.py <目标目录>
必须用 tools\\venv-retro\\Scripts\\python.exe 运行。
"""
import os
import sys
import time
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

ZENODO_IPS = [
    "137.138.52.235",
    "188.184.98.114",
    "137.138.153.219",
    "188.184.103.118",
    "188.185.48.75",
]

ZENODO_RECORD = "11430881"
FILES = [
    ("uspto_model.onnx",                   "b466a436b6a8eceaba8c14ef5e2a88c8"),
    ("uspto_templates.csv.gz",             "e8fb29d4dcd54073658000e212b7845a"),
    ("uspto_ringbreaker_model.onnx",       "2aa7ee99d29a910369e723a73fc13044"),
    ("uspto_ringbreaker_templates.csv.gz", "a6d0117ee6122e2cca3b7f8efa35541d"),
    ("uspto_filter_model.onnx",            "ab0df54b62a0aeceecd68051f8dc3f2e"),
    ("zinc_stock.hdf5",                    "2888ffca8873e6a11478cbdda7154f03"),
]

CHUNK_SIZE = 1024 * 1024      # 1MB / 块（单连接~17KB/s，1MB≈60s，须小于 TIMEOUT）
MAX_WORKERS = 64              # 并发 curl 进程数
MAX_RETRY = 6
TIMEOUT = 600                 # 单块 curl 超时（秒），要留足余量


def md5_of_file(path, buf=1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(buf), b""):
            h.update(b)
    return h.hexdigest()


def file_url(name):
    return ("https://zenodo.org/records/%s/files/%s?download=1"
            % (ZENODO_RECORD, name))


def curl_head_size(url):
    """用 curl -I 获取文件大小（多 IP 重试）。"""
    for attempt in range(10):
        ip = ZENODO_IPS[attempt % len(ZENODO_IPS)]
        try:
            p = subprocess.run(
                ["curl", "-sIL", "--max-time", "40",
                 "--resolve", "zenodo.org:443:%s" % ip, url],
                capture_output=True, text=True)
            for line in p.stdout.splitlines():
                if line.lower().startswith("content-length:"):
                    return int(line.split(":", 1)[1].strip())
        except Exception:
            pass
    raise RuntimeError("无法获取大小: %s" % url)


def fetch_chunk(url, path, start, end, idx):
    """下载 [start,end] 区间并写入目标文件对应偏移。"""
    expect = end - start + 1
    last = None
    for attempt in range(MAX_RETRY):
        ip = ZENODO_IPS[(idx + attempt) % len(ZENODO_IPS)]
        try:
            p = subprocess.run(
                ["curl", "-s", "-L", "--max-time", str(TIMEOUT),
                 "--resolve", "zenodo.org:443:%s" % ip,
                 "-r", "%d-%d" % (start, end), url],
                capture_output=True)
            data = p.stdout
            if len(data) != expect:
                last = "len %d != %d (rc=%d)" % (len(data), expect, p.returncode)
                time.sleep(1 + attempt)
                continue
            with open(path, "r+b") as f:
                f.seek(start)
                f.write(data)
            return expect
        except Exception as e:
            last = repr(e)
            time.sleep(1 + attempt)
    raise RuntimeError("块 %d 失败(%d-%d): %s" % (idx, start, end, last))


def download_one(dest_dir, name, want_md5):
    path = os.path.join(dest_dir, name)
    print("\n===== %s =====" % name, flush=True)
    if os.path.exists(path) and md5_of_file(path) == want_md5:
        print("  已存在且 md5 正确，跳过", flush=True)
        return True

    url = file_url(name)
    size = curl_head_size(url)
    print("  大小: %d 字节 (%.1f MB)" % (size, size / 1024 / 1024), flush=True)

    with open(path, "wb") as f:
        f.truncate(size)

    ranges, s, idx = [], 0, 0
    while s < size:
        e = min(s + CHUNK_SIZE - 1, size - 1)
        ranges.append((s, e, idx))
        s = e + 1
        idx += 1
    total = len(ranges)
    print("  分块数: %d, 并发: %d" % (total, MAX_WORKERS), flush=True)

    t0 = time.time()
    done_bytes = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fetch_chunk, url, path, a, b, c): c for (a, b, c) in ranges}
        ok = 0
        for fut in as_completed(futs):
            done_bytes += fut.result()
            ok += 1
            if ok % 20 == 0 or ok == total:
                el = time.time() - t0
                print("  进度 %d/%d  用时 %.0fs  速率 %.0f KB/s"
                      % (ok, total, el, done_bytes / el / 1024), flush=True)

    print("  校验 md5 ...", flush=True)
    got = md5_of_file(path)
    if got != want_md5:
        print("  !! md5 不符 got=%s want=%s" % (got, want_md5), flush=True)
        return False
    print("  OK md5 正确 用时 %.0fs" % (time.time() - t0), flush=True)
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python download_models_curl.py <目标目录>")
        sys.exit(1)
    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)
    print("目标目录:", dest, flush=True)
    results = {}
    for name, want in FILES:
        try:
            results[name] = download_one(dest, name, want)
        except Exception as e:
            print("  !! 失败: %s : %s" % (name, e), flush=True)
            results[name] = False
    print("\n=============== 汇总 ===============", flush=True)
    for name, ok in results.items():
        print("  %-38s %s" % (name, "OK" if ok else "失败"), flush=True)
    if not all(results.values()):
        sys.exit(2)


if __name__ == "__main__":
    main()
