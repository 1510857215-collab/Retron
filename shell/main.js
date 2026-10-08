// Retron 桌面外壳 —— 主进程
// 职责：① 启动时在后台静默拉起本地引擎（无任何窗口）
//       ② 打开应用窗口（内嵌界面）
//       ③ 退出时清理引擎进程（含其子进程与上次残留）
//       ④ 运行环境自愈（软件被复制到新电脑/新路径后自动修复）
const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');
const os = require('os');

const PORT = 8765;
const BASE_URL = 'http://127.0.0.1:' + PORT;

let mainWindow = null;
let engineProc = null;    // 仅记录"本窗口亲手启动"的引擎进程
let quitting = false;

// ---------- 定位项目根（含 app/server.py 的目录） ----------
// 严格判据：目录里同时有 app\server.py 与 tools\python311\python.exe
function isRootStrict(dir) {
  try {
    return !!dir &&
      fs.existsSync(path.join(dir, 'app', 'server.py')) &&
      fs.existsSync(path.join(dir, 'tools', 'python311', 'python.exe'));
  } catch (e) { return false; }
}
// 宽松判据（源码仓库 / 调试用）：只要有 app\server.py
function isRootLoose(dir) {
  try {
    return !!dir && fs.existsSync(path.join(dir, 'app', 'server.py'));
  } catch (e) { return false; }
}

function findProjectRoot() {
  const cands = [];
  // 从 exe 所在目录起，向上逐级查找（最多 6 级）——
  // 这样无论外壳被放在项目根下一层，还是整个文件夹被多套了一层，都能找到。
  try {
    let dir = path.dirname(process.execPath);
    for (let i = 0; i < 6 && dir; i++) {
      cands.push(dir);
      const parent = path.dirname(dir);
      if (parent === dir) { break; }
      dir = parent;
    }
  } catch (e) { /* ignore */ }
  // 开发模式：<root>\shell\main.js → root 在上一级
  cands.push(path.dirname(__dirname));
  cands.push(process.cwd());

  for (const c of cands) { if (isRootStrict(c)) { return c; } }
  for (const c of cands) { if (isRootLoose(c)) { return c; } }
  return null;
}

let ROOT = findProjectRoot();

// ---------- 健康检查 ----------
function checkHealth(timeoutMs) {
  return new Promise((resolve) => {
    const req = http.get(BASE_URL + '/api/health', { timeout: timeoutMs || 1500 }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try {
          const j = JSON.parse(data);
          resolve(!!(j && j.service === 'hx-local'));
        } catch (e) { resolve(false); }
      });
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function waitReady(totalMs) {
  const t0 = Date.now();
  return new Promise((resolve) => {
    (function poll() {
      checkHealth().then((ok) => {
        if (ok) { return resolve(true); }
        if (Date.now() - t0 > totalMs) { return resolve(false); }
        setTimeout(poll, 600);
      });
    })();
  });
}

// ---------- 运行环境自愈（软件被复制/安装到新电脑、新路径后自动修复） ----------
function probeVenv() {
  return new Promise((resolve) => {
    if (!ROOT) { return resolve(false); }
    const py = path.join(ROOT, 'tools', 'venv', 'Scripts', 'python.exe');
    if (!fs.existsSync(py)) { return resolve(false); }
    try {
      const p = spawn(py, ['-c', 'pass'], { windowsHide: true, stdio: 'ignore' });
      const t = setTimeout(() => {
        try { p.kill(); } catch (e) { /* ignore */ }
        resolve(false);
      }, 45000);
      p.on('exit', (code) => { clearTimeout(t); resolve(code === 0); });
      p.on('error', () => { clearTimeout(t); resolve(false); });
    } catch (e) { resolve(false); }
  });
}

function repairEnv() {
  return new Promise((resolve) => {
    if (!ROOT) { return resolve(false); }
    const base = path.join(ROOT, 'tools', 'python311', 'python.exe');
    const script = path.join(ROOT, 'tools', 'repair_env.py');
    if (!fs.existsSync(base) || !fs.existsSync(script)) { return resolve(false); }
    try {
      const p = spawn(base, [script, '--quiet'],
        { windowsHide: true, stdio: 'ignore', cwd: ROOT });
      const t = setTimeout(() => {
        try { p.kill(); } catch (e) { /* ignore */ }
        resolve(false);
      }, 600000);
      p.on('exit', (code) => { clearTimeout(t); resolve(code === 0); });
      p.on('error', () => { clearTimeout(t); resolve(false); });
    } catch (e) { resolve(false); }
  });
}

// ---------- 启动引擎（pythonw，无窗口） ----------
function startEngine() {
  return new Promise((resolve, reject) => {
    if (!ROOT) {
      return reject(new Error(
        '找不到程序目录 —— 说明「外壳程序」和「引擎文件夹」没在一起。\n\n' +
        '请把整个 Retron 文件夹完整复制过来（不能只复制 Retron.exe）。\n\n' +
        '正确的目录结构：\n' +
        '  某个文件夹\\\n' +
        '      Retron\\Retron.exe   ← 双击这个\n' +
        '      app\\  web\\  engine\\  data\\  tools\\'));
    }
    const py = path.join(ROOT, 'tools', 'venv', 'Scripts', 'pythonw.exe');
    const server = path.join(ROOT, 'app', 'server.py');
    if (!fs.existsSync(py)) {
      return reject(new Error('找不到运行环境（pythonw.exe）：\n' + py));
    }
    if (!fs.existsSync(server)) {
      return reject(new Error('找不到服务程序：\n' + server));
    }
    engineProc = spawn(py, [server], {
      cwd: ROOT,
      windowsHide: true,
      stdio: 'ignore',
      detached: false
    });
    engineProc.on('exit', () => { engineProc = null; });
    engineProc.on('error', (err) => {
      engineProc = null;
      reject(err);
    });
    resolve();
  });
}

// ---------- 请引擎自己收尾（含其子进程，无论是否本窗口启动） ----------
function requestShutdown() {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    try {
      const req = http.request(BASE_URL + '/api/shutdown',
        { method: 'GET', headers: { 'X-Retron-Shutdown': '1' }, timeout: 3000 },
        (res) => {
          res.resume();
          res.on('end', () => setTimeout(finish, 500));
        });
      req.on('error', finish);
      req.on('timeout', () => { try { req.destroy(); } catch (e) { /* ignore */ } finish(); });
      req.end();
      setTimeout(finish, 4000);   // 总兜底
    } catch (e) { finish(); }
  });
}

// ---------- 兜底：杀掉本窗口亲手启动的引擎（整棵进程树） ----------
function killEngine() {
  return new Promise((resolve) => {
    if (!engineProc || !engineProc.pid) { return resolve(); }
    const pid = engineProc.pid;
    engineProc = null;
    try {
      const k = spawn('taskkill', ['/pid', String(pid), '/f', '/t'],
        { windowsHide: true, stdio: 'ignore' });
      k.on('exit', () => resolve());
      k.on('error', () => resolve());
      setTimeout(resolve, 5000);
    } catch (e) { resolve(); }
  });
}

// ---------- 主窗口 ----------
function createWindow() {
  const iconPath = path.join(__dirname, 'icon.ico');
  mainWindow = new BrowserWindow({
    width: 1460,
    height: 920,
    minWidth: 1100,
    minHeight: 700,
    title: 'Retron · 有机合成工作台',
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    backgroundColor: '#0a0d13',
    autoHideMenuBar: true,
    show: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  if (mainWindow.setMenuBarVisibility) { mainWindow.setMenuBarVisibility(false); }
  // 站内链接（如路线图）在新窗口打开时给一个干净的小窗口；站外一律拒绝
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(BASE_URL)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          width: 900, height: 720,
          autoHideMenuBar: true,
          title: 'Retron',
          backgroundColor: '#ffffff'
        }
      };
    }
    return { action: 'deny' };
  });

  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ---------- 启动流程 ----------
async function boot() {
  createWindow();

  // 1) 若已有引擎在跑（上次残留 / 另一个实例），直接复用 —— 二次启动秒开
  if (await checkHealth()) {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadURL(BASE_URL + '/');
    }
    return;
  }

  // 2) 环境自愈：引擎环境若因"复制/迁移到新位置"而失效，先自动修复
  if (!(await probeVenv())) {
    await repairEnv();
    // 修复后仍不可用时继续走启动流程（引擎自身会给出具体错误信息）
  }

  // 3) 启动引擎
  try {
    await startEngine();
  } catch (e) {
    dialog.showErrorBox('Retron 启动失败', String((e && e.message) || e));
    app.quit();
    return;
  }
  const ok = await waitReady(240000);
  if (!ok) {
    dialog.showErrorBox('Retron 启动失败',
      '本地引擎启动超时（已等待 4 分钟）。\n\n' +
      '可以试试：\n' +
      '1. 确认整个文件夹是完整复制的（不能只拷 Retron.exe）\n' +
      '2. 查看日志排查：' +
      (ROOT ? path.join(ROOT, 'logs', 'server.log') : 'logs/server.log'));
    await killEngine();
    app.quit();
    return;
  }

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(BASE_URL + '/');
  }
}

// ---------- 首次运行：自动在桌面创建快捷方式（用系统真实桌面路径） ----------
function ensureDesktopShortcut() {
  try {
    if (process.platform !== 'win32') { return; }
    let desktop = '';
    try {
      desktop = app.getPath('desktop');   // 正确处理 OneDrive 重定向 / 本地化桌面
    } catch (e) { desktop = ''; }
    if (!desktop || !fs.existsSync(desktop)) {
      desktop = path.join(os.homedir(), 'Desktop');
    }
    if (!fs.existsSync(desktop)) { return; }
    const lnkPath = path.join(desktop, 'Retron.lnk');

    // 已有快捷方式：指向本程序就保留；指向别处（如旧的安装位置）就更新它
    if (fs.existsSync(lnkPath)) {
      try {
        const cur = shell.readShortcutLink(lnkPath);
        if (cur && cur.target &&
            path.resolve(cur.target).toLowerCase() === path.resolve(process.execPath).toLowerCase()) {
          return;
        }
      } catch (e) { /* 读取失败 → 当作需要重建 */ }
    }
    shell.writeShortcutLink(lnkPath, fs.existsSync(lnkPath) ? 'replace' : 'create', {
      target: process.execPath,
      cwd: path.dirname(process.execPath),
      description: 'Retron 有机合成工作台',
      icon: process.execPath,
      iconIndex: 0
    });
    console.log('桌面快捷方式已就绪: ' + lnkPath);
  } catch (e) {
    // 创建失败不影响启动
  }
}

// ---------- 退出：先请引擎自己收尾，再兜底清理 ----------
async function shutdownAll() {
  if (quitting) { return; }
  quitting = true;
  await requestShutdown();
  await killEngine();
}

// ---------- 只允许一个实例 ----------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) { mainWindow.restore(); }
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    ensureDesktopShortcut();
    boot();
  });

  app.on('window-all-closed', async () => {
    await shutdownAll();
    app.quit();
  });

  app.on('before-quit', () => {
    shutdownAll();
  });
}
