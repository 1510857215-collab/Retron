// 汉化验证：驱动 Edge 打开 board.html，导出全部 [title] 工具提示、页面文本，
// 打开设置弹窗与元素周期表弹窗，截图，并抓取全部网络请求证明无外链。
import fs from 'fs';

const CDP_HTTP = 'http://127.0.0.1:9333';
const PAGE_URL = 'http://127.0.0.1:8765/board.html';
const OUT_DIR = 'C:/Users/zzl/Desktop/hx/logs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(CDP_HTTP + '/json/list')).json();
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch (e) { /* 未就绪 */ }
    await sleep(500);
  }
  throw new Error('CDP target 未就绪');
}

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = []; }
  static connect(url) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const c = new Cdp(ws);
      ws.onopen = () => resolve(c);
      ws.onerror = () => reject(new Error('ws error'));
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.id && c.pending.has(msg.id)) {
          const { res, rej } = c.pending.get(msg.id);
          c.pending.delete(msg.id);
          msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
        } else if (msg.method) c.handlers.forEach((h) => h(msg));
      };
    });
  }
  on(fn) { this.handlers.push(fn); }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (r.exceptionDetails) throw new Error('JS 异常: ' + JSON.stringify(r.exceptionDetails.exception || r.exceptionDetails));
    return r.result.value;
  }
  async shot(path) {
    const s = await this.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path, Buffer.from(s.data, 'base64'));
  }
}

const target = await getTarget();
const cdp = await Cdp.connect(target.webSocketDebuggerUrl);

const requests = [];
const pageErrors = [];
const consoleMsgs = [];
cdp.on((msg) => {
  if (msg.method === 'Network.requestWillBeSent') requests.push(msg.params.request.url);
  if (msg.method === 'Runtime.exceptionThrown') pageErrors.push(JSON.stringify(msg.params.exceptionDetails.exception || msg.params.exceptionDetails));
  if (msg.method === 'Runtime.consoleAPICalled') {
    const lvl = msg.params.type;
    if (lvl === 'error' || lvl === 'warning') consoleMsgs.push(lvl + ': ' + msg.params.args.map((a) => a.value ?? a.description ?? a.type).join(' '));
  }
});

await cdp.send('Network.enable');
await cdp.send('Runtime.enable');
await cdp.send('Page.enable');
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });

requests.length = 0; pageErrors.length = 0; consoleMsgs.length = 0;
const t0 = Date.now();
await cdp.send('Page.navigate', { url: PAGE_URL + '?t=' + Date.now() });

let ready = false;
for (let i = 0; i < 240; i++) {
  try { ready = await cdp.eval('!!(window.__ketcherReady && window.ketcher)'); } catch { ready = false; }
  if (ready || pageErrors.length) break;
  await sleep(500);
}
console.log('画板就绪:', ready, ' 加载耗时(ms):', Date.now() - t0);
if (!ready) {
  console.log('页面异常:', pageErrors);
  process.exit(2);
}

// 让工具提示类元素全部渲染：先让画板稳定
await sleep(1200);

// 1) 导出全部 title 工具提示
const titles = await cdp.eval(`JSON.stringify([...new Set([...document.querySelectorAll('[title]')].map(e=>e.getAttribute('title')).filter(Boolean))].sort())`);
const titleArr = JSON.parse(titles);
console.log('\n===== 界面工具提示 [title] (' + titleArr.length + ' 条) =====');
titleArr.forEach((t) => console.log('  ' + t));

// 2) 统计中文命中
const cjk = titleArr.filter((t) => /[\u4e00-\u9fff]/.test(t));
const ascii = titleArr.filter((t) => !/[\u4e00-\u9fff]/.test(t) && /[A-Za-z]{2}/.test(t));
console.log('\n含中文的 title:', cjk.length, '  仍为英文的 title:', ascii.length);
console.log('仍为英文的 title 列表:', JSON.stringify(ascii));

// 3) 主界面截图
await cdp.shot(OUT_DIR + '/ketcher_zh_test.png');

// 4) 打开「设置」弹窗（按 title=设置 找【可见】按钮）
const openedSettings = await cdp.eval(`(() => {
  const els = [...document.querySelectorAll('[title="设置"]')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  if (!els.length) return '未找到可见的设置按钮';
  els[0].click();
  return 'clicked(可见按钮数=' + els.length + ')';
})()`);
console.log('\n设置弹窗:', openedSettings);
await sleep(1800);
const dialogText = await cdp.eval(`(() => {
  const sel = '[class*="Dialog-module_dialog"], [role="dialog"], .MuiDialog-root, .MuiPopover-root, .contexify';
  const cands = [...document.querySelectorAll(sel)].filter(e => e.getBoundingClientRect().width > 0);
  if (!cands.length) return '(无弹窗)';
  return cands.map(e => e.innerText).join('\\n----\\n').replace(/\\n{2,}/g, '\\n').slice(0, 2500);
})()`);
console.log('----- 设置弹窗文本 -----');
console.log(dialogText);
await cdp.shot(OUT_DIR + '/ketcher_zh_settings.png');

// 关闭弹窗（ESC）
await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', windowsVirtualKeyCode: 27 });
await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', windowsVirtualKeyCode: 27 });
await sleep(800);

// 5) 打开「元素周期表」弹窗
const openedPT = await cdp.eval(`(() => {
  const els = [...document.querySelectorAll('[title="元素周期表"]')].filter(e => e.getBoundingClientRect().width > 0);
  if (!els.length) return '未找到可见的元素周期表按钮';
  els[0].click();
  return 'clicked';
})()`);
console.log('\n元素周期表弹窗:', openedPT);
await sleep(1500);
const ptText = await cdp.eval(`(() => {
  const sel = '[class*="Dialog-module_dialog"], [role="dialog"], .MuiDialog-root';
  const cands = [...document.querySelectorAll(sel)].filter(e => e.getBoundingClientRect().width > 0);
  const titled = [...document.querySelectorAll(sel + ' [title]')].map(e => e.getAttribute('title')).slice(0, 30);
  const txt = cands.map(e => (e.innerText || '').slice(0, 400));
  return JSON.stringify({ dialogs: cands.length, elementTitles: titled, sampleText: txt }, null, 0);
})()`);
console.log('周期表元素标题样例:', ptText);
await cdp.shot(OUT_DIR + '/ketcher_zh_periodic.png');

console.log('\n===== 网络请求（共 ' + requests.length + ' 条） =====');
requests.forEach((u) => console.log('  ' + u.slice(0, 130)));
const external = requests.filter((u) => !u.startsWith('http://127.0.0.1:8765') && !u.startsWith('data:') && !u.startsWith('blob:'));
console.log('非本地/非 blob 请求条数 =', external.length);

console.log('\n===== 页面 JS 异常 =====', pageErrors.length ? pageErrors : '无');
console.log('警告/错误 console =', consoleMsgs.length ? consoleMsgs.slice(-10) : '无');
console.log('\n截图:', OUT_DIR + '/ketcher_zh_test.png , ' + OUT_DIR + '/ketcher_zh_settings.png');
process.exit(0);
