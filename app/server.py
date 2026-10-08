#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hx 有机合成工具 —— 本地服务主程序（外壳）
==========================================
提供：
  1. 本地网页界面（web/ 目录，含 Ketcher 画板、runtime 动态文件）
  2. POST /api/convert —— 结构/名称/分子式 相互转换（RDKit + 中文名典 + OPSIN）
  3. POST /api/retro   —— 逆合成路线设计（AiZynthFinder 常驻 worker，模型只加载一次）
     GET  /api/retro/status?task_id=xxx —— 查询逆合成任务进度
  4. POST /api/ocr     —— 图片识别分子（本地 MolScribe/DECIMER 引擎）
  5. POST /api/mol     —— MOL 文本 -> SMILES（接住其他化学软件复制来的分子）
  6. GET  /api/health  —— 自检

铁律：完全本地运行、断网可用、不访问任何外网。
启动方式（推荐）：项目根目录双击「启动.bat」
手动：tools\\venv\\Scripts\\python.exe app\\server.py
"""
import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------- 路径与常量
HERE = os.path.dirname(os.path.abspath(__file__))            # ...\hx\app
ROOT = os.path.dirname(HERE)                                  # ...\hx
WEB_DIR = os.path.join(ROOT, "web")
RUNTIME_DIR = os.path.join(WEB_DIR, "runtime")                # 动态文件（路线图等）
ENGINE_CHEM_DIR = os.path.join(ROOT, "engine", "chemistry")
RETRO_WORKER = os.path.join(ROOT, "engine", "retro", "retro_worker.py")
RETRO_PYTHON = os.path.join(ROOT, "tools", "venv-retro", "Scripts", "python.exe")
VISION_PYTHON = os.path.join(ROOT, "tools", "venv-vision", "Scripts", "python.exe")
OCR_CLI = os.path.join(ROOT, "engine", "vision", "ocr_cli.py")
FORWARD_PYTHON = os.path.join(ROOT, "tools", "venv-forward", "Scripts", "python.exe")
FORWARD_CLI = os.path.join(ROOT, "engine", "forward", "predict_cli.py")
CONDITIONS_PYTHON = os.path.join(ROOT, "tools", "venv-conditions", "Scripts", "python.exe")
CONDITIONS_CLI = os.path.join(ROOT, "engine", "conditions", "recommend_cli.py")
LOG_DIR = os.path.join(ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "server.log")

PORT = 8765
MAX_IMAGE_BYTES = 40 * 1024 * 1024   # 图片上限 40MB

# 让控制台打印中文不出错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if ENGINE_CHEM_DIR not in sys.path:
    sys.path.insert(0, ENGINE_CHEM_DIR)


# ---------------------------------------------------------------- 日志
_log_lock = threading.Lock()


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with _log_lock:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        print(line)


# ---------------------------------------------------------------- 转换引擎（懒加载）
_converter = None
_converter_lock = threading.Lock()


def get_converter():
    global _converter
    if _converter is None:
        with _converter_lock:
            if _converter is None:
                import converter as _c  # engine/chemistry/converter.py
                _converter = _c
    return _converter


# ---------------------------------------------------------------- 通用 CLI 工具调用
def _run_cli_tool(python_exe, cli_path, args, timeout=120, tag=""):
    """跨环境调用命令行工具：解析 stdout 里最后一行 JSON。"""
    if not os.path.exists(python_exe):
        env_name = os.path.basename(os.path.dirname(os.path.dirname(python_exe)))
        return {"ok": False, "error": "运行环境未就绪（缺少 %s）" % env_name}
    if not os.path.exists(cli_path):
        return {"ok": False, "error": "找不到工具脚本：%s" % cli_path}
    try:
        log("调用 %s 工具：%s" % (tag, " ".join(args)[:140]))
        proc = subprocess.run(
            [python_exe, cli_path] + args,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "计算超时（%d 秒）" % timeout}
    except Exception as e:
        return {"ok": False, "error": "调用失败：%s" % e}
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return {"ok": False, "error": "工具无输出（%s）" % (proc.stderr or "")[:160]}


# 条件推荐缓存（同一反应重复查询秒回）
_COND_CACHE = {}
_COND_CACHE_LOCK = threading.Lock()


# ---------------------------------------------------------------- 逆合成 worker（常驻子进程）
class RetroWorker:
    """管理常驻的 retro_worker 子进程：启动一次、模型只加载一次、请求串行。"""

    def __init__(self):
        self.proc = None
        self.ready = False
        self.error = None
        self.lock = threading.Lock()

    # ---- 内部：读一行（带超时）
    def _read_line(self, timeout):
        if self.proc is None or self.proc.stdout is None:
            return None
        q = queue.Queue()

        def reader():
            try:
                q.put(self.proc.stdout.readline())
            except Exception as e:
                q.put("__ERR__:%s" % e)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            line = q.get(timeout=timeout)
        except queue.Empty:
            return None
        if line in ("", None):
            return None
        return line

    def _reset(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        self.proc = None
        self.ready = False

    def stop(self):
        """停止引擎子进程（供外壳退出时调用，避免留下孤儿进程）。"""
        acquired = False
        try:
            acquired = self.lock.acquire(timeout=3)
        except Exception:
            acquired = False
        try:
            self._reset()
        finally:
            if acquired:
                try:
                    self.lock.release()
                except Exception:
                    pass
        log("逆合成引擎已停止。")

    # ---- 启动并等待 ready（内部已带锁保护）
    def _ensure_ready_locked(self):
        if self.proc is not None and self.proc.poll() is None and self.ready:
            return True
        if not os.path.exists(RETRO_WORKER):
            self.error = "找不到逆合成 worker：%s" % RETRO_WORKER
            return False
        if not os.path.exists(RETRO_PYTHON):
            self.error = "找不到逆合成环境：%s" % RETRO_PYTHON
            return False
        self._reset()
        log("正在启动逆合成引擎（首次需加载模型，可能需要一点时间）…")
        try:
            self.proc = subprocess.Popen(
                [RETRO_PYTHON, RETRO_WORKER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=os.path.dirname(RETRO_WORKER),
            )
        except Exception as e:
            self.error = "逆合成引擎启动失败：%s" % e
            return False
        line = self._read_line(timeout=600)
        if line is None:
            self.error = "逆合成引擎加载超时或异常退出"
            self._reset()
            return False
        try:
            info = json.loads(line)
        except Exception:
            self.error = "逆合成引擎返回异常：%s" % line[:200]
            self._reset()
            return False
        if info.get("ready"):
            self.ready = True
            self.error = None
            log("逆合成引擎已就绪")
            return True
        self.error = info.get("error") or "逆合成引擎加载失败"
        log("逆合成引擎加载失败：%s" % self.error)
        self._reset()
        return False

    # ---- 对外：提交一次搜索（阻塞直到结果或超时）
    def find(self, smiles, max_steps, save_dir=None, start_material=None, timeout=900):
        with self.lock:
            if not self._ensure_ready_locked():
                return {"ok": False, "error": self.error or "逆合成引擎不可用"}
            req = json.dumps(
                {"smiles": smiles, "max_steps": max_steps, "save_dir": save_dir,
                 "start_material": start_material},
                ensure_ascii=False)
            try:
                self.proc.stdin.write(req + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self._reset()
                return {"ok": False, "error": "引擎通信失败：%s" % e}
            line = self._read_line(timeout=timeout)
            if line is None:
                self._reset()
                return {"ok": False, "error": "逆合成计算超时（或引擎无响应），请稍后重试"}
            try:
                return json.loads(line)
            except Exception:
                return {"ok": False, "error": "引擎返回格式异常"}

    def status(self):
        if self.proc is None:
            return "未启动"
        if self.proc.poll() is not None:
            return "已退出"
        return "运行中" + ("（已就绪）" if self.ready else "（加载中）")


RETRO = RetroWorker()

# ---------------------------------------------------------------- 任务表（逆合成异步任务）
TASKS = {}
TASKS_LOCK = threading.Lock()
TASK_TTL = 3600  # 已完成任务保留 1 小时


def _cleanup_tasks():
    now = time.time()
    with TASKS_LOCK:
        dead = [k for k, v in TASKS.items()
                if v.get("finished") and now - v["finished"] > TASK_TTL]
        for k in dead:
            TASKS.pop(k, None)
            # 顺带清掉该任务的路线图目录
            try:
                import shutil
                shutil.rmtree(os.path.join(RUNTIME_DIR, k), ignore_errors=True)
            except Exception:
                pass


def submit_retro(smiles, max_steps, start_material=None):
    _cleanup_tasks()
    tid = uuid.uuid4().hex[:12]
    save_dir = os.path.join(RUNTIME_DIR, tid)   # 路线图与 JSON 落到 web/runtime/<tid>/
    with TASKS_LOCK:
        TASKS[tid] = {
            "state": "running",
            "smiles": smiles,
            "max_steps": max_steps,
            "start_material": start_material,
            "started": time.time(),
            "finished": None,
            "result": None,
            "error": None,
        }

    def run():
        res = RETRO.find(smiles, max_steps, save_dir=save_dir,
                         start_material=start_material)
        with TASKS_LOCK:
            task = TASKS.get(tid)
            if task is None:
                return
            task["finished"] = time.time()
            if res.get("ok"):
                task["state"] = "done"
                task["result"] = res
            else:
                task["state"] = "error"
                task["error"] = res.get("error") or "未知错误"

    threading.Thread(target=run, daemon=True).start()
    return tid


# ---------------------------------------------------------------- HTTP 处理
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".wasm": "application/wasm",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "hx-local/0.2"
    protocol_version = "HTTP/1.1"

    # 静音默认日志，统一走 log()
    def log_message(self, fmt, *args):
        pass

    # ---- 工具
    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _send_file(self, rel_path):
        # 防路径穿越：解析后必须仍在 WEB_DIR 内
        target = os.path.realpath(os.path.join(WEB_DIR, rel_path))
        if not target.startswith(os.path.realpath(WEB_DIR)):
            self._send_json({"ok": False, "error": "非法路径"}, 403)
            return
        if not os.path.isfile(target):
            self._send_json({"ok": False, "error": "文件不存在：%s" % rel_path}, 404)
            return
        ext = os.path.splitext(target)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        try:
            with open(target, "rb") as f:
                data = f.read()
        except Exception as e:
            self._send_json({"ok": False, "error": "读取失败：%s" % e}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Ketcher 大文件与 runtime 图片：本地服务，禁用强缓存，避免改版后页面仍用旧文件
        if rel_path.startswith("ketcher/") or rel_path.startswith("runtime/"):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_IMAGE_BYTES * 2:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    # ---- GET
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/health":
                try:
                    get_converter()
                    conv_ok = True
                    conv_err = None
                except Exception as e:
                    conv_ok = False
                    conv_err = str(e)
                self._send_json({
                    "ok": True,
                    "service": "hx-local",
                    "converter": {"ok": conv_ok, "error": conv_err},
                    "retro": {"process": RETRO.status(), "ready": RETRO.ready,
                              "error": RETRO.error},
                    "vision": {"env": os.path.exists(VISION_PYTHON)},
                })
                return

            if path == "/api/shutdown":
                # 仅本机外壳程序可触发：必须带专用请求头
                # （浏览器地址栏直接访问不会带该头，避免误关服务）
                if self.headers.get("X-Retron-Shutdown") != "1":
                    self._send_json({"ok": False, "error": "未授权"}, 403)
                    return
                self._send_json({"ok": True, "bye": True})

                def _bye():
                    time.sleep(0.4)
                    try:
                        RETRO.stop()
                    except Exception:
                        pass
                    log("收到退出指令，服务停止。")
                    os._exit(0)

                threading.Thread(target=_bye, daemon=True).start()
                return

            if path == "/api/retro/status":
                qs = parse_qs(parsed.query)
                tid = (qs.get("task_id") or [""])[0]
                with TASKS_LOCK:
                    task = TASKS.get(tid)
                    if task is None:
                        self._send_json({"ok": False, "error": "任务不存在或已过期"})
                        return
                    elapsed = round((task["finished"] or time.time()) - task["started"], 1)
                    resp = {
                        "ok": True,
                        "state": task["state"],
                        "elapsed": elapsed,
                        "smiles": task["smiles"],
                    }
                    if task["state"] == "done":
                        resp["result"] = task["result"]
                    elif task["state"] == "error":
                        resp["error"] = task["error"]
                self._send_json(resp)
                return

            # 静态文件
            if path in ("/", ""):
                path = "/index.html"
            self._send_file(path.lstrip("/"))
        except Exception as e:
            log("GET 异常：%s\n%s" % (e, traceback.format_exc()))
            self._send_json({"ok": False, "error": "服务器内部错误：%s" % e}, 500)

    # ---- POST
    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_json_body()
            if body is None:
                self._send_json({"ok": False, "error": "请求格式不合法或内容过大"}, 400)
                return

            # ---------- 转换 ----------
            if path == "/api/convert":
                inp = (body.get("input") or "").strip()
                itype = (body.get("input_type") or "").strip()
                target = (body.get("target") or "").strip()
                try:
                    conv = get_converter()
                except Exception as e:
                    self._send_json({"ok": False, "error": "转换引擎加载失败：%s" % e})
                    return
                res = conv.convert(inp, itype, target)
                self._send_json(res)
                return

            # ---------- 逆合成 ----------
            if path == "/api/retro":
                smiles = (body.get("smiles") or "").strip()
                if not smiles:
                    self._send_json({"ok": False, "error": "请输入目标分子的 SMILES"}, 400)
                    return
                try:
                    max_steps = int(body.get("max_steps") or 3)
                except Exception:
                    max_steps = 3
                max_steps = max(1, min(max_steps, 6))
                start_material = (body.get("start_material") or "").strip() or None
                tid = submit_retro(smiles, max_steps, start_material)
                log("收到逆合成任务 %s：%s（最多 %d 步，起点：%s）"
                    % (tid, smiles, max_steps, start_material or "无"))
                self._send_json({"ok": True, "task_id": tid})
                return

            # ---------- 正向反应预测 ----------
            if path == "/api/forward":
                reactants = (body.get("reactants") or "").strip()
                if not reactants:
                    self._send_json({"ok": False, "error": "请输入反应物 SMILES"}, 400)
                    return
                conditions = (body.get("conditions") or "").strip()
                args = [reactants] + ([conditions] if conditions else [])
                res = _run_cli_tool(FORWARD_PYTHON, FORWARD_CLI, args,
                                    timeout=180, tag="forward")
                self._send_json(res)
                return

            # ---------- 反应条件推荐（带缓存） ----------
            if path == "/api/conditions":
                reaction = (body.get("reaction") or "").strip()
                if not reaction:
                    self._send_json({"ok": False,
                                     "error": "缺少反应（reactants>>product）"}, 400)
                    return
                with _COND_CACHE_LOCK:
                    cached = _COND_CACHE.get(reaction)
                if cached is not None:
                    self._send_json(cached)
                    return
                res = _run_cli_tool(CONDITIONS_PYTHON, CONDITIONS_CLI, [reaction],
                                    timeout=120, tag="conditions")
                if res.get("ok"):
                    with _COND_CACHE_LOCK:
                        if len(_COND_CACHE) > 2000:
                            _COND_CACHE.clear()
                        _COND_CACHE[reaction] = res
                self._send_json(res)
                return

            # ---------- 图片识别 ----------
            if path == "/api/ocr":
                img = body.get("image") or ""
                if not img:
                    self._send_json({"ok": False, "error": "缺少图片数据"}, 400)
                    return
                if img.strip().startswith("data:"):     # 去掉 dataURL 前缀
                    try:
                        img = img.split(",", 1)[1]
                    except Exception:
                        pass
                try:
                    raw = base64.b64decode(img)
                except Exception:
                    self._send_json({"ok": False, "error": "图片数据格式不正确"})
                    return
                if len(raw) > MAX_IMAGE_BYTES:
                    self._send_json({"ok": False,
                                     "error": "图片过大（超过 40MB），请裁剪后再试"})
                    return
                tmp_dir = os.path.join(ROOT, "tools", "tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_path = os.path.join(tmp_dir, "ocr_%s.png" % uuid.uuid4().hex[:10])
                try:
                    with open(tmp_path, "wb") as f:
                        f.write(raw)
                except Exception as e:
                    self._send_json({"ok": False, "error": "图片保存失败：%s" % e})
                    return
                try:
                    if not os.path.exists(VISION_PYTHON):
                        self._send_json({"ok": False,
                                         "error": "识别环境未就绪（缺少 tools/venv-vision）"})
                        return
                    log("收到图片识别请求（%.0f KB）" % (len(raw) / 1024.0))
                    proc = subprocess.run(
                        [VISION_PYTHON, OCR_CLI, tmp_path],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        timeout=180,
                    )
                    res = None
                    for line in reversed((proc.stdout or "").splitlines()):
                        line = line.strip()
                        if line.startswith("{"):
                            try:
                                res = json.loads(line)
                                break
                            except Exception:
                                continue
                    if res is None:
                        res = {"ok": False,
                               "error": "识别引擎无输出（%s）" % (proc.stderr or "")[:160]}
                except subprocess.TimeoutExpired:
                    res = {"ok": False, "error": "识别超时（180 秒），请换一张更清晰的图"}
                except Exception as e:
                    res = {"ok": False, "error": "识别调用失败：%s" % e}
                finally:
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                if res.get("ok"):
                    log("图片识别成功：%s（引擎 %s）" % (res.get("smiles"), res.get("engine")))
                else:
                    log("图片识别失败：%s" % res.get("error"))
                self._send_json(res)
                return

            # ---------- MOL 文本转 SMILES（接住其他软件复制来的分子） ----------
            if path == "/api/mol":
                text = body.get("mol") or ""
                if not text.strip():
                    self._send_json({"ok": False, "error": "MOL 内容为空"}, 400)
                    return
                try:
                    from rdkit import Chem
                    mol = Chem.MolFromMolBlock(text, sanitize=True)
                    if mol is None:
                        mol = Chem.MolFromMolBlock(text, sanitize=False)
                    if mol is None:
                        self._send_json({"ok": False,
                                         "error": "无法解析这段 MOL 文本（可能格式不完整）"})
                        return
                    self._send_json({"ok": True, "smiles": Chem.MolToSmiles(mol)})
                except Exception as e:
                    self._send_json({"ok": False, "error": "解析失败：%s" % e})
                return

            self._send_json({"ok": False, "error": "未知接口：%s" % path}, 404)
        except Exception as e:
            log("POST 异常：%s\n%s" % (e, traceback.format_exc()))
            self._send_json({"ok": False, "error": "服务器内部错误：%s" % e}, 500)


# ---------------------------------------------------------------- 主入口
def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    log("=" * 60)
    log("hx 有机合成工具 本地服务启动中…")
    log("接口：http://127.0.0.1:%d" % PORT)
    log("项目根：%s" % ROOT)

    # 预加载转换引擎（快速，确保 /api/convert 首请求不慢）
    try:
        get_converter()
        log("转换引擎加载完成（RDKit + 中文名典 + OPSIN）")
    except Exception as e:
        log("转换引擎预加载失败（不影响启动，调用时报错）：%s" % e)

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log("服务已就绪：请在浏览器打开 http://127.0.0.1:%d" % PORT)
    log("关闭本窗口即退出服务。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("收到退出信号，服务停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
