#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dict_build.py —— 中文化合物名称词典构建工具（v2 / 10 万级）

设计目标
--------
把「中文名 / 英文名 / 俗名 / 商品名 / CAS 号 -> 分子结构」的离线词典
扩到 **10 万级化合物**，并且**有别名俗名的化合物必须收录别名俗名**。

数据来源（全部公开、可查证、可复现；SMILES 一律来自 PubChem，绝不编造）
------------------------------------------------------------------
1. PubChem ``CID-Synonym-filtered.gz``   —— CID -> 全部同义词（英文名/俗名/商品名/CAS 号）
   https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-Synonym-filtered.gz
   【实测】该文件为纯 ASCII，**不含任何中文**，故中文名改用 Wikidata（见 3）。
2. PubChem PUG REST 批量接口             —— CID -> SMILES + MolecularFormula
   POST https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/property/SMILES,MolecularFormula/JSON
   body: ``cid=1,2,3``（form-urlencoded，每批 <=200）—— 结构数据的唯一权威来源。
3. Wikidata（SPARQL）                    —— CID -> 中文名 / 中文别名（QID 可查证）
   P662 = PubChem CID；取 rdfs:label / skos:altLabel 的 zh* 语言值。
   【实测】PubChem 同义词无中文，中文名以 Wikidata 为准。
4. PubChem ``Drug-Names.tsv.gz``         —— 药品名 / 商品名
5. ``engine/chemistry/seed_list.txt``    —— 人工维护的 469 条常用化合物中文名
   （用于**强制主名**，保证「阿司匹林/苯/乙醇」这类高频名不被同义词里的怪名顶掉）

阶段（可单独执行，全部幂等 / 可断点续跑）
--------------------------------------
    seed     解析 seed_list.txt -> 经 PUG REST 名称接口解析出 CID（强制主名）
    wd       汇总 Wikidata 中文名 / 中文别名（按 CID 区间扫描，结果落工作库）
    select   选取目标 CID（有中文名者 + 小 CID 补足）
    syn      扫 PubChem 同义词文件 -> 目标 CID 的完整同义词
    fetch    批量拉 SMILES + 分子式（断点续跑，限速）
    build    组装最终词典库 data/中文名字典.sqlite

    python dict_build.py all                 # 一键全流程
    python dict_build.py --limit 2000 all    # 小批量试跑

仅用 Python 标准库。
"""

import argparse
import gzip
import http.client
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ---------------------------------------------------------------- 路径常量
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")
TMP_DIR = os.path.join(ROOT, "tools", "tmp")

SEED_FILE = os.path.join(HERE, "seed_list.txt")
DB_FILE = os.path.join(DATA_DIR, "中文名字典.sqlite")

SYN_FILE = os.path.join(TMP_DIR, "dict_synonyms.gz")        # PubChem 同义词大文件
DRUG_FILE = os.path.join(TMP_DIR, "dict_drugnames.tsv.gz")  # PubChem 药品名
WORK_DB = os.path.join(TMP_DIR, "dict_work.sqlite")         # 中间工作库
SMILES_JSONL = os.path.join(TMP_DIR, "dict_smiles.jsonl")   # SMILES 抓取缓存
SEED_JSON = os.path.join(TMP_DIR, "dict_seed_cids.json")    # seed 英文名 -> CID

PUBCHEM_HOST = "pubchem.ncbi.nlm.nih.gov"
PUBCHEM_PROP_PATH = "/rest/pug/compound/cid/property/SMILES,MolecularFormula/JSON"
PUBCHEM_PROP_URL = "https://" + PUBCHEM_HOST + PUBCHEM_PROP_PATH
PUBCHEM_NAME_PATH = "/rest/pug/compound/name/%s/cids/JSON"
USER_AGENT = "hx-local-chemdict/2.0 (offline organic-synthesis toolkit)"

SYN_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-Synonym-filtered.gz"
DRUG_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/Drug-Names.tsv.gz"

PROXY = os.environ.get("HX_PROXY", "http://127.0.0.1:7890")

# 目标规模
TARGET_TOTAL = 200000      # 主表目标化合物数（>= 10 万，留足余量）
BATCH_SIZE = 200           # PUG REST 每批 CID 数
FETCH_WORKERS = 4          # 并发连接数（每连接 <1.3 请求/秒，总 <5 请求/秒，符合 PubChem 策略）

# Wikidata 中文名扫描区间（CID 覆盖 1..2.5 亿；区间宽度按产出调优，避免查询超时）
WD_RANGES = [
    (1, 100000), (100000, 200000), (200000, 400000), (400000, 600000),
    (600000, 800000), (800000, 1000000), (1000000, 2000000), (2000000, 3000000),
    (3000000, 4000000), (4000000, 5000000), (5000000, 10000000), (10000000, 20000000),
    (20000000, 40000000), (40000000, 60000000), (60000000, 90000000),
    (90000000, 120000000), (120000000, 180000000), (180000000, 250000000),
]
WD_LANGS = '("zh","zh-hans","zh-hant","zh-cn","zh-tw","zh-hk")'
WD_WORKERS = 3

WD_TMPL = """SELECT ?item ?cid ?v ?kind WHERE {
  { ?item wdt:P662 ?cid ; rdfs:label ?v . BIND("label" AS ?kind) }
  UNION
  { ?item wdt:P662 ?cid ; skos:altLabel ?v . BIND("alias" AS ?kind) }
  FILTER(lang(?v) IN %s)
  FILTER(xsd:integer(?cid) >= %d && xsd:integer(?cid) < %d)
} LIMIT 300000"""


# ---------------------------------------------------------------- 工具函数

def _is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff"


def has_cjk(text):
    """是否含中文（CJK 统一表意文字）。"""
    for ch in text:
        if _is_cjk(ch):
            return True
    return False


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def _open_work():
    os.makedirs(TMP_DIR, exist_ok=True)
    conn = sqlite3.connect(WORK_DB)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def _http_conn():
    return http.client.HTTPSConnection(PUBCHEM_HOST, timeout=60)


# ---------------------------------------------------------------- 阶段 1：seed 清单

def load_seed(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n").rstrip("\r")
            if not line or line.lstrip().startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                print("  [!] 跳过格式异常行 %d: %r" % (lineno, line))
                continue
            cn, en = parts[0], parts[1]
            cat = parts[2] if len(parts) > 2 and parts[2] else "未分类"
            remark = parts[3] if len(parts) > 3 and parts[3] else ""
            rows.append((cn, en, cat, remark))
    return rows


def stage_seed(args):
    """把 seed_list.txt 的英文名经 PUG REST 解析成 CID（结果缓存）。"""
    seed = load_seed(SEED_FILE)
    cache = {}
    if os.path.exists(SEED_JSON) and not args.no_cache:
        try:
            with open(SEED_JSON, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    todo = [r for r in seed if r[1].lower() not in cache]
    _log("seed 清单 %d 条，待联网解析 %d 条" % (len(seed), len(todo)))

    if todo:
        conn = _http_conn()
        ok = 0
        for i, (cn, en, cat, remark) in enumerate(todo, 1):
            res = None
            for attempt in range(3):
                try:
                    conn.request("GET", PUBCHEM_NAME_PATH % urllib.parse.quote(en),
                                 headers={"User-Agent": USER_AGENT})
                    r = conn.getresponse()
                    data = r.read()
                    if r.status == 200:
                        res = json.loads(data).get("IdentifierList", {}).get("CID", [])
                        break
                    if r.status in (404, 400):
                        res = []
                        break
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = _http_conn()
                    time.sleep(1.0 * (attempt + 1))
            if res is None:
                res = []
            cache[en.lower()] = res
            if res:
                ok += 1
            if i % 100 == 0 or i == len(todo):
                _log("  seed 进度 %d/%d，命中 %d" % (i, len(todo), ok))
        try:
            conn.close()
        except Exception:
            pass

    with open(SEED_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    hit = sum(1 for r in seed if cache.get(r[1].lower()))
    _log("seed 解析完成：%d/%d 条解析到 CID" % (hit, len(seed)))
    return 0


def _seed_cid_map():
    """返回 {cid: (中文名, 类别, 英文名, 备注)}（同 CID 取 seed 文件中最先出现者）。"""
    if not os.path.exists(SEED_JSON):
        return {}
    with open(SEED_JSON, "r", encoding="utf-8") as f:
        cache = json.load(f)
    out = {}
    for cn, en, cat, remark in load_seed(SEED_FILE):
        cids = cache.get(en.lower()) or []
        if not cids:
            continue
        cid = int(cids[0])
        if cid not in out:
            out[cid] = (cn, cat, en, remark)
    return out


# ---------------------------------------------------------------- 阶段 2：Wikidata 中文名

_WD_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def _wd_sparql(query, timeout=150, retries=3):
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={
        "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
    last = None
    for a in range(retries):
        try:
            with _WD_OPENER.open(req, timeout=timeout) as f:
                return json.loads(f.read().decode("utf-8"))["results"]["bindings"]
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(2.5 * (a + 1))
    raise last


WD_SCHEMA = """
DROP TABLE IF EXISTS wd_names;
CREATE TABLE wd_names(cid INTEGER, item TEXT, name TEXT, kind TEXT);
"""


def stage_wd(args):
    """扫描 Wikidata（按 CID 区间）汇总中文名与中文别名 -> wd_names。"""
    conn = _open_work()
    conn.executescript(WD_SCHEMA)
    ranges = WD_RANGES
    if args.limit:
        ranges = WD_RANGES[:2]          # 试跑只扫前两个区间
    _log("扫描 Wikidata 中文名，共 %d 个 CID 区间（并发 %d）" % (len(ranges), WD_WORKERS))

    lock = threading.Lock()
    st = {"done": 0, "rows": 0, "cids": 0, "fail": 0}
    all_rows = []
    t0 = time.time()

    def fetch_range(lo, hi, depth=0):
        """查询 [lo,hi)；失败（超时 / 响应被截断）时对半细分重试。"""
        try:
            return _wd_sparql(WD_TMPL % (WD_LANGS, lo, hi))
        except Exception:                            # noqa: BLE001
            if depth < 4 and hi - lo > 20000:
                mid = (lo + hi) // 2
                return fetch_range(lo, mid, depth + 1) + fetch_range(mid, hi, depth + 1)
            raise

    def work(rng):
        lo, hi = rng
        try:
            b = fetch_range(lo, hi)
        except Exception as e:                       # noqa: BLE001
            return rng, None, str(e)
        return rng, b, None

    with ThreadPoolExecutor(max_workers=WD_WORKERS) as ex:
        for rng, b, err in ex.map(work, ranges):
            with lock:
                st["done"] += 1
                if err:
                    st["fail"] += 1
                    _log("  区间 %s 失败：%s" % (rng, err[:60]))
                else:
                    for x in b:
                        all_rows.append((int(x["cid"]["value"]),
                                         x["item"]["value"].rsplit("/", 1)[-1],
                                         x["v"]["value"], x["kind"]["value"]))
                    n_cid = len(set(r[0] for r in all_rows))
                    _log("  区间 [%d,%d) -> 累计行 %d，累计 CID %d（%d/%d）"
                         % (rng[0], rng[1], len(all_rows), n_cid,
                            st["done"], len(ranges)))
    if all_rows:
        conn.executemany("INSERT INTO wd_names VALUES(?,?,?,?)", all_rows)
    conn.execute("CREATE INDEX idx_wd_cid ON wd_names(cid)")
    conn.commit()

    n_rows = conn.execute("SELECT COUNT(*) FROM wd_names").fetchone()[0]
    n_cid = conn.execute("SELECT COUNT(DISTINCT cid) FROM wd_names").fetchone()[0]
    n_cn = conn.execute(
        "SELECT COUNT(DISTINCT cid) FROM wd_names "
        "WHERE name GLOB '*[^ -~]*'").fetchone()[0]
    conn.close()
    _log("Wikidata 完成：命中 CID %d 个（含非 ASCII 名 %d 个），记录 %d 条，失败区间 %d，用时 %.1f 分钟"
         % (n_cid, n_cn, n_rows, st["fail"], (time.time() - t0) / 60))
    return 0


# ---------------------------------------------------------------- 阶段 3：选取目标 CID

def stage_select(args):
    conn = _open_work()
    total_target = args.limit or TARGET_TOTAL

    wd_set = set(r[0] for r in conn.execute(
        "SELECT DISTINCT cid FROM wd_names WHERE name GLOB '*[^ -~]*'"))
    seed_map = _seed_cid_map()
    seed_cids = sorted(seed_map)

    conn.executescript("""
    DROP TABLE IF EXISTS targets;
    CREATE TABLE targets(cid INTEGER PRIMARY KEY, has_cn INTEGER, prio INTEGER);
    """)

    chosen = {}                                   # cid -> (has_cn, prio)
    for c in seed_cids:                           # ① seed（最高优先）
        chosen[c] = (1, 1000000 + c)

    if args.limit:
        # 试跑模式：seed + 最小的 N 个 CID（覆盖常见化合物），保证可快速验证全流程
        c = 1
        while len(chosen) < total_target and c <= total_target * 4:
            chosen.setdefault(c, (1 if c in wd_set else 0, 2000000 + c))
            c += 1
    else:
        for c in sorted(wd_set):                  # ② 有 Wikidata 中文名
            chosen.setdefault(c, (1, 2000000 + c))
        need = total_target - len(chosen)
        if need > 0:                              # ③ 小 CID 补足
            c = 1
            while len(chosen) < total_target and c <= need * 6 + 5000:
                chosen.setdefault(c, (1 if c in wd_set else 0, 3000000 + c))
                c += 1

    conn.executemany("INSERT OR IGNORE INTO targets(cid,has_cn,prio) VALUES(?,?,?)",
                     [(c, v[0], v[1]) for c, v in chosen.items()])
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
    n_cn = conn.execute("SELECT COUNT(*) FROM targets WHERE has_cn=1").fetchone()[0]
    conn.close()
    _log("目标 CID：%d 个（其中含 Wikidata 中文名 %d 个，seed %d 个）"
         % (n, n_cn, len(seed_cids)))
    return 0


# ---------------------------------------------------------------- 阶段 4：PubChem 同义词

SYN_SCHEMA = """
DROP TABLE IF EXISTS synonyms;
CREATE TABLE synonyms(cid INTEGER, seq INTEGER, alias TEXT);
DROP TABLE IF EXISTS drugs;
CREATE TABLE drugs(cid INTEGER, drug TEXT);
"""


def stage_syn(args):
    if not os.path.exists(SYN_FILE):
        _log("缺少同义词文件：%s\n  下载：curl -C - --ssl-no-revoke -x %s -o \"%s\" \"%s\""
             % (SYN_FILE, PROXY, SYN_FILE, SYN_URL))
        return 1
    conn = _open_work()
    keep = set(r[0] for r in conn.execute("SELECT cid FROM targets"))
    _log("扫描 PubChem 同义词文件，收集 %d 个目标 CID 的全部同义词……" % len(keep))
    t0 = time.time()
    conn.executescript(SYN_SCHEMA)

    buf, buf2 = [], []
    seen = set()
    n_lines = 0
    with gzip.open(SYN_FILE, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            n_lines += 1
            tab = line.find("\t")
            if tab <= 0:
                continue
            cid_s = line[:tab]
            if not cid_s.isdigit():
                continue
            cid = int(cid_s)
            if cid not in keep:
                continue
            syn = line[tab + 1:].rstrip("\r\n")
            if not syn:
                continue
            key = (cid, syn)
            if key in seen:
                continue
            seen.add(key)
            buf.append((cid, n_lines, syn))
            if len(buf) >= 300000:
                conn.executemany("INSERT INTO synonyms VALUES(?,?,?)", buf)
                buf = []
                seen = set()
    if buf:
        conn.executemany("INSERT INTO synonyms VALUES(?,?,?)", buf)

    if os.path.exists(DRUG_FILE):
        with gzip.open(DRUG_FILE, "rt", encoding="utf-8", errors="replace") as f:
            head = True
            for line in f:
                if head:
                    head = False
                    if line.startswith("#"):
                        continue
                p = line.rstrip("\r\n").split("\t")
                if len(p) < 3 or not p[2].isdigit():
                    continue
                cid = int(p[2])
                if cid in keep and p[1].strip():
                    buf2.append((cid, p[1].strip()))
        if buf2:
            conn.executemany("INSERT INTO drugs VALUES(?,?)", buf2)

    conn.execute("CREATE INDEX idx_syn_cid ON synonyms(cid)")
    conn.execute("CREATE INDEX idx_drug_cid ON drugs(cid)")
    conn.commit()
    n_syn = conn.execute("SELECT COUNT(*) FROM synonyms").fetchone()[0]
    n_drug = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
    conn.close()
    _log("同义词收集完成：%d 条（药品名 %d 条），用时 %.1fs" % (n_syn, n_drug, time.time() - t0))
    return 0


# ---------------------------------------------------------------- 阶段 5：抓 SMILES

def _load_fetched():
    done = {}
    if os.path.exists(SMILES_JSONL):
        with open(SMILES_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                done[o["cid"]] = o
    return done


_TL = threading.local()


class _RateLimiter:
    """全局限速器（所有线程共享），保证总请求速率不超过 PubChem 的 5 次/秒建议值。"""

    def __init__(self, rate):
        self.interval = 1.0 / float(rate)
        self.lock = threading.Lock()
        self.next_t = 0.0

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            wait = max(0.0, self.next_t - now)
            self.next_t = max(now, self.next_t) + self.interval
        if wait > 0:
            time.sleep(wait)


_FETCH_RATE = _RateLimiter(4.0)      # 4 请求/秒（< PubChem 5/秒上限）

# PubChem PUG REST 走的 opener（可选经代理；直连 IP 被限流时可走代理出口）
def _build_opener(proxy):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


_OPENER = None
_OPENER_DIRECT = None
_OPENER_LOCK = threading.Lock()


def _opener():
    global _OPENER
    if _OPENER is None:
        with _OPENER_LOCK:
            if _OPENER is None:
                _OPENER = _build_opener(PROXY)
    return _OPENER


def _opener_direct():
    global _OPENER_DIRECT
    if _OPENER_DIRECT is None:
        with _OPENER_LOCK:
            if _OPENER_DIRECT is None:
                _OPENER_DIRECT = urllib.request.build_opener()
    return _OPENER_DIRECT


def _parse_props(data):
    props = json.loads(data)["PropertyTable"]["Properties"]
    out = []
    for p in props:
        smi = p.get("SMILES") or p.get("CanonicalSMILES") \
            or p.get("ConnectivitySMILES") or ""
        out.append({"cid": p.get("CID"), "smiles": smi or None,
                    "formula": p.get("MolecularFormula")})
    return out


def _do_request(op, req):
    with op.open(req, timeout=60) as resp:
        return resp.read()


def _fetch_batch(cids, retries=4):
    """取一批 CID 的 SMILES + 分子式。

    返回 (ok, payload)：
        ok=True  -> payload 为 dict 列表（该批已定论；<200 条说明其余 CID 不存在）
        ok=False -> 网络/限流失败，payload 为错误字符串（调用方应稍后重试，不得写缓存）
    """
    body = urllib.parse.urlencode({"cid": ",".join(str(c) for c in cids)}).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT}
    err = "unknown"
    for attempt in range(retries):
        _FETCH_RATE.acquire()
        req = urllib.request.Request(PUBCHEM_PROP_URL, data=body, headers=headers)
        try:
            return True, _parse_props(_do_request(_opener(), req))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return True, []                       # 该批都不存在
            err = "http_%d" % e.code
        except Exception as e:                        # noqa: BLE001
            err = type(e).__name__
            # 代理不通时退回直连再试一次（反之亦然）
            try:
                return True, _parse_props(_do_request(_opener_direct(), req))
            except urllib.error.HTTPError as e2:
                if e2.code in (400, 404):
                    return True, []
                err = "direct_http_%d" % e2.code
            except Exception as e2:                   # noqa: BLE001
                err = type(e2).__name__
        time.sleep(min(45.0, 4.0 * (2 ** attempt)))   # 503/5xx 指数退避
    return False, err


def _write_smiles(fh, batch, res):
    """把一批的抓取结果写入缓存文件（未返回的 CID 记为 not_found）。返回写入的结构条数。"""
    n = 0
    got = set()
    for o in res:
        fh.write(json.dumps(o, ensure_ascii=False) + "\n")
        got.add(o["cid"])
        n += 1
    for c in batch:
        if c not in got:
            fh.write(json.dumps({"cid": c, "smiles": None, "formula": None,
                                 "err": "not_found"}, ensure_ascii=False) + "\n")
    return n


def stage_fetch(args):
    conn = _open_work()
    targets = [r[0] for r in conn.execute("SELECT cid FROM targets ORDER BY cid")]
    conn.close()

    done = {} if args.no_cache else _load_fetched()
    todo = [c for c in targets if c not in done]
    if args.limit:
        todo = todo[:args.limit]
    _log("待抓取 %d 个 CID（已有缓存 %d，目标共 %d）" % (len(todo), len(done), len(targets)))
    if not todo:
        _log("无需抓取。")
        return 0

    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    _log("共 %d 批 × %d 个/批，%d 并发连接，限速 %.0f 请求/秒"
         % (len(batches), BATCH_SIZE, FETCH_WORKERS, 1.0 / _FETCH_RATE.interval))

    lock = threading.Lock()
    out_f = open(SMILES_JSONL, "a", encoding="utf-8")
    stats = {"batch": 0, "cid": 0, "fail": 0}
    t0 = time.time()
    pending = []          # 失败的批，稍后重试

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        for b, (ok, payload) in ex.map(lambda b: (b, _fetch_batch(b)), batches):
            with lock:
                if ok:
                    stats["cid"] += _write_smiles(out_f, b, payload)
                else:
                    stats["fail"] += 1
                    pending.append(b)
                stats["batch"] += 1
                if stats["batch"] % 100 == 0 or stats["batch"] == len(batches):
                    out_f.flush()
                    el = time.time() - t0
                    rate = stats["batch"] / el if el else 0
                    eta = (len(batches) - stats["batch"]) / rate if rate else 0
                    _log("  批次 %d/%d  已入库 CID %d  待重试批 %d  用时 %.0fs  剩余约 %.0fs"
                         % (stats["batch"], len(batches), stats["cid"], len(pending), el, eta))

    # ---- 失败批次重试（最多 3 轮，逐批串行，避免再次被限流）----
    for rnd in range(3):
        if not pending:
            break
        _log("第 %d 轮重试 %d 个失败批次……" % (rnd + 1, len(pending)))
        time.sleep(15 * (rnd + 1))
        still = []
        for i, b in enumerate(pending, 1):
            ok, payload = _fetch_batch(b, retries=5)
            if ok:
                stats["cid"] += _write_smiles(out_f, b, payload)
            else:
                still.append(b)
            if i % 20 == 0:
                out_f.flush()
                _log("  重试 %d/%d，仍失败 %d" % (i, len(pending), len(still)))
        pending = still
        out_f.flush()

    if pending:
        _log("⚠ 仍有 %d 个批次抓取失败（未写入缓存，下次运行会自动重试）" % len(pending))
    out_f.close()
    _log("抓取完成：成功 CID %d，用时 %.1f 分钟" % (stats["cid"], (time.time() - t0) / 60))
    return 0


# ---------------------------------------------------------------- 阶段 6：组装最终库

FINAL_SCHEMA = """
DROP TABLE IF EXISTS compounds;
DROP TABLE IF EXISTS aliases;
CREATE TABLE compounds (
    id      INTEGER PRIMARY KEY,   -- 优先级号（越小越优先，反查时先命中）
    cid     INTEGER,               -- PubChem CID（可查证）
    name    TEXT,                  -- 主名：中文名优先，无中文名则用英文名
    smiles  TEXT,                  -- PubChem SMILES
    formula TEXT,                  -- 分子式
    source  TEXT,                  -- 例：PubChem CID 2244
    note    TEXT                   -- 主名来源 / 类别 / 同义词数等
);
CREATE TABLE aliases (
    compound_id INTEGER,           -- 指向 compounds.id
    alias       TEXT,              -- 别名（中文名/英文名/俗名/商品名/CAS 号/分子式）
    kind        TEXT,              -- 类别
    source      TEXT               -- 来源（含 CID / QID，可查证）
);
"""

_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
_FORM_RE = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")


def _classify(alias):
    """给同义词打类别标签（启发式，仅按字符串形态）。"""
    if has_cjk(alias):
        return "中文名"
    a = alias.strip()
    if _CAS_RE.match(a):
        return "CAS号"
    if 2 <= len(a) <= 30 and a[0].isupper() and any(c.isdigit() for c in a) and _FORM_RE.match(a):
        return "分子式"
    return "英文名"


def _pick_cn_name(names):
    """从候选中文名里挑主名：偏好短、无拉丁字母、无过多标点。"""
    def score(n):
        s = len(n) * 1.0
        s += (n.count("(") + n.count("（")) * 4
        s += (n.count(",") + n.count("，")) * 3
        s += (n.count("-") + n.count("－")) * 2
        s += sum(1 for c in n if "a" <= c.lower() <= "z") * 2
        s += sum(1 for c in n if c.isdigit()) * 2
        return s
    return sorted(names, key=score)[0]


def stage_build(args):
    conn = _open_work()
    seed_map = _seed_cid_map()
    target_cids = [r[0] for r in conn.execute("SELECT cid FROM targets")]
    target_set = set(target_cids)

    # ---- Wikidata 中文名 / 中文别名（label 优先作主名） ----
    wd_label = {}      # cid -> (name, qid)
    wd_alias = {}      # cid -> [(name, qid), ...]
    for cid, item, name, kind in conn.execute(
            "SELECT cid,item,name,kind FROM wd_names ORDER BY cid, kind DESC, name"):
        if cid not in target_set or not has_cjk(name):
            continue
        if kind == "label":
            wd_label.setdefault(cid, (name, item))
        else:
            wd_alias.setdefault(cid, []).append((name, item))
    for cid, (name, item) in wd_label.items():
        wd_alias.setdefault(cid, []).append((name, item))

    # ---- PubChem 同义词 ----
    first_syn, syn_count = {}, {}
    for cid, cnt, mn in conn.execute(
            "SELECT cid, COUNT(*), MIN(seq) FROM synonyms GROUP BY cid"):
        syn_count[cid] = cnt
    for cid, alias in conn.execute(
            "SELECT s.cid, s.alias FROM synonyms s JOIN "
            "(SELECT cid, MIN(seq) ms FROM synonyms GROUP BY cid) t "
            "ON s.cid=t.cid AND s.seq=t.ms"):
        first_syn[cid] = alias

    drug_by_cid = {}
    for cid, drug in conn.execute("SELECT cid, drug FROM drugs"):
        drug_by_cid.setdefault(cid, []).append(drug)

    props = _load_fetched()
    usable = [c for c in target_cids if props.get(c, {}).get("smiles")]
    _log("目标 %d 个 CID，其中成功取到 SMILES 的 %d 个" % (len(target_cids), len(usable)))

    # ---- 主名 & 排序：seed > Wikidata 中文名 > PubChem 英文名 ----
    def sort_key(c):
        if c in seed_map:
            return (0, c)
        if c in wd_label:
            return (1, c)
        return (2, c)
    usable.sort(key=sort_key)

    _log("组装最终库……")
    t0 = time.time()
    out = sqlite3.connect(DB_FILE)
    out.executescript(FINAL_SCHEMA)
    cur = out.cursor()

    comp_buf, cid_to_id, main_by_cid = [], {}, {}
    seed_extra = {}                                # cid -> [额外中文名(别名)]
    n_cn_main = 0
    for idx, cid in enumerate(usable, 1):
        p = props[cid]
        seed = seed_map.get(cid)
        if seed:
            cn_full, cat, en, remark = seed
            names = [x.strip() for x in cn_full.replace("；", ";").replace("／", ";").split(";")
                     if x.strip()]
            main = names[0]
            if len(names) > 1:
                seed_extra[cid] = names[1:]
            name_src = "seed清单; 英文名:%s" % en
        elif cid in wd_label:
            main, qid = wd_label[cid]
            cat = remark = ""
            name_src = "Wikidata"
        else:
            main = first_syn.get(cid) or "CID %d" % cid
            cat = remark = ""
            name_src = "英文同义词"

        cid_to_id[cid] = idx
        main_by_cid[cid] = main
        if has_cjk(main):
            n_cn_main += 1

        note_bits = ["主名来源:%s" % name_src]
        if cat:
            note_bits.append("类别:%s" % cat)
        if cid in wd_label:
            note_bits.append("Wikidata:%s" % wd_label[cid][1])
        fs = first_syn.get(cid)
        if fs and not has_cjk(fs):
            note_bits.append("英文名:%s" % fs)
        if p.get("formula"):
            note_bits.append("分子式:%s" % p["formula"])
        note_bits.append("同义词:%d" % syn_count.get(cid, 0))
        if remark:
            note_bits.append(remark)

        comp_buf.append((idx, cid, main, p["smiles"], p.get("formula"),
                         "PubChem CID %d" % cid, "; ".join(note_bits)))
        if len(comp_buf) >= 50000:
            cur.executemany("INSERT INTO compounds VALUES(?,?,?,?,?,?,?)", comp_buf)
            comp_buf = []
    if comp_buf:
        cur.executemany("INSERT INTO compounds VALUES(?,?,?,?,?,?,?)", comp_buf)
    out.commit()
    _log("compounds 写入完成（%d 条，主名为中文 %d 条），开始写 aliases……"
         % (len(cid_to_id), n_cn_main))

    # ---- 别名 ----
    # 内存策略：不保留全局 (compound, alias) 去重集（全量可达千万级），
    # 改为「每个 CID 一个小集合」——中文名/药品名/seed 名的集合只覆盖
    # 这些来源涉及的 CID（约数万），PubChem 同义词按 cid 排序流式处理，
    # 每个 CID 用完即弃。
    alias_buf = []
    pre = {}                       # cid -> 已写入别名集合（仅 wd/drug/seed 相关 CID）
    stat = {"中文名": 0, "药品名/商品名": 0, "other": 0}
    cap = max(0, args.alias_cap)
    n_capped = 0

    def flush():
        if alias_buf:
            cur.executemany("INSERT INTO aliases VALUES(?,?,?,?)", alias_buf)
            alias_buf.clear()

    def add(cid, name, kind, source):
        i = cid_to_id.get(cid)
        if not i:
            return
        name = name.strip()
        if not name or name == main_by_cid.get(cid):
            return
        s = pre.setdefault(cid, set())
        if name in s:
            return
        s.add(name)
        alias_buf.append((i, name, kind, source))
        stat[kind if kind in ("中文名",) else ("药品名/商品名" if kind == "药品名/商品名" else "other")] += 1

    # ⓪ seed 清单里用「;」分隔的额外中文名
    for cid, names in seed_extra.items():
        for name in names:
            add(cid, name, "中文名", "seed清单")
    flush()

    # ① Wikidata 中文名 / 中文别名
    for cid, lst in wd_alias.items():
        for name, qid in lst:
            add(cid, name, "中文名", "Wikidata %s" % qid)
    flush()

    # ② PubChem 药品名 / 商品名
    for cid, lst in drug_by_cid.items():
        for d in lst:
            add(cid, d, "药品名/商品名", "PubChem Drug-Names")
    flush()

    # ③ PubChem 全部同义词（英文名 / 俗名 / 商品名 / CAS 号 / 分子式）
    #    每 CID 按文件顺序（"最好的名字在前"）最多保留 alias_cap 条
    cur_cid = None
    cur_seen = set()
    cur_n = 0
    for cid, alias in conn.execute("SELECT cid, alias FROM synonyms ORDER BY cid, seq"):
        i = cid_to_id.get(cid)
        if not i:
            continue
        if cid != cur_cid:
            cur_cid = cid
            cur_seen = set(pre.get(cid) or ())
            cur_seen.add(main_by_cid.get(cid))
            cur_n = 0
        a = alias.strip()
        if not a or a in cur_seen:
            continue
        if cap and cur_n >= cap:
            n_capped += 1
            continue
        cur_seen.add(a)
        cur_n += 1
        alias_buf.append((i, a, _classify(a), "PubChem CID %d 同义词" % cid))
        stat["other"] += 1
        if len(alias_buf) >= 200000:
            flush()
            out.commit()
    flush()
    out.commit()
    conn.close()
    if n_capped:
        _log("（PubChem 同义词每 CID 上限 %d，跳过 %d 条超长尾部）" % (cap, n_capped))

    _log("建索引……")
    out.executescript("""
    CREATE INDEX idx_compounds_name  ON compounds(name COLLATE NOCASE);
    CREATE INDEX idx_compounds_cid   ON compounds(cid);
    CREATE INDEX idx_aliases_alias   ON aliases(alias COLLATE NOCASE);
    CREATE INDEX idx_aliases_comp    ON aliases(compound_id);
    CREATE INDEX idx_aliases_kind    ON aliases(kind);
    ANALYZE;
    """)
    out.commit()

    n_comp = out.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
    n_al = out.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    out.close()
    _log("最终库完成：化合物 %d 条，别名 %d 条（中文名 %d，药品/商品名 %d，其他 %d），"
         "主名为中文 %d 条，用时 %.1fs"
         % (n_comp, n_al, stat["中文名"], stat["药品名/商品名"], stat["other"],
            n_cn_main, time.time() - t0))
    return 0


# ---------------------------------------------------------------- 主入口

STAGES = ("seed", "wd", "select", "syn", "fetch", "build")


def main(argv=None):
    global DB_FILE, PROXY
    ap = argparse.ArgumentParser(description="中文化合物名称词典构建（v2 / 10 万级）")
    ap.add_argument("stage", nargs="?", default="all",
                    choices=list(STAGES) + ["all"], help="要执行的阶段（默认 all）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（调试用）")
    ap.add_argument("--no-cache", action="store_true", help="忽略本地缓存，重新抓取")
    ap.add_argument("--alias-cap", type=int, default=100,
                    help="每个 CID 最多收录多少条 PubChem 同义词（0=不限，默认 100）；"
                         "中文名/药品名不受此限")
    ap.add_argument("--proxy", default=PROXY,
                    help="访问 PubChem PUG REST 用的 HTTP 代理（默认 %s；传空串走直连）" % PROXY)
    ap.add_argument("--db", default=DB_FILE, help="最终数据库路径")
    args = ap.parse_args(argv)
    DB_FILE = args.db
    PROXY = args.proxy

    print("=" * 72)
    print("中文化合物名称词典构建（v2）   stage=%s  limit=%s" % (args.stage, args.limit or "无"))
    print("  工作目录 : %s" % TMP_DIR)
    print("  同义词   : %s" % SYN_FILE)
    print("  最终库   : %s" % args.db)
    print("  代理     : %s" % (args.proxy or "（直连）"))
    print("  时间     : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    todo = list(STAGES) if args.stage == "all" else [args.stage]
    for st in todo:
        _log("=== 阶段 %s 开始 ===" % st)
        rc = globals()["stage_" + st](args)
        if rc:
            _log("阶段 %s 失败（rc=%s），中止" % (st, rc))
            return rc
        _log("=== 阶段 %s 完成 ===" % st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
