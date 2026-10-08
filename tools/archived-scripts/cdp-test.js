// 用 CDP 真实驱动 Edge：等待画板就绪 -> 载入苯环 -> 导出 SMILES -> 截图
// 同时抓取全部网络请求，用于证明"无任何外网请求"
const fs = require('fs');

const CDP_HTTP = 'http://127.0.0.1:9222';
const PAGE_URL = 'http://127.0.0.1:8899/ketcher-test.html';
const SHOT = 'C:/Users/zzl/Desktop/hx/logs/ketcher_test.png';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(CDP_HTTP + '/json/list')).json();
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page && page.webSocketDebuggerUrl) return page;
    } catch (e) { /* 还没起来 */ }
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
      ws.onerror = (e) => reject(new Error('ws error'));
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.id && c.pending.has(msg.id)) {
          const { res, rej } = c.pending.get(msg.id);
          c.pending.delete(msg.id);
          msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
        } else if (msg.method) {
          c.handlers.forEach((h) => h(msg));
        }
      };
    });
  }
  on(fn) { this.handlers.push(fn); }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
  async eval(expression, awaitPromise = true) {
    const r = await this.send('Runtime.evaluate', {
      expression, awaitPromise, returnByValue: true, userGesture: true,
    });
    if (r.exceptionDetails) {
      throw new Error('JS 异常: ' + JSON.stringify(r.exceptionDetails.exception || r.exceptionDetails));
    }
    return r.result.value;
  }
}

(async () => {
  const target = await getTarget();
  const cdp = await Cdp.connect(target.webSocketDebuggerUrl);

  const requests = [];
  const consoleMsgs = [];
  const pageErrors = [];
  cdp.on((msg) => {
    if (msg.method === 'Network.requestWillBeSent') requests.push(msg.params.request.url);
    if (msg.method === 'Runtime.consoleAPICalled') {
      consoleMsgs.push(msg.params.type + ': ' + msg.params.args.map((a) => a.value ?? a.description ?? a.type).join(' '));
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      pageErrors.push(JSON.stringify(msg.params.exceptionDetails.exception || msg.params.exceptionDetails));
    }
  });

  await cdp.send('Network.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');

  // 重新加载，确保从干净状态抓全部请求（加时间戳避免缓存）
  requests.length = 0;      // 从这里开始统计本次页面加载的全部请求
  pageErrors.length = 0;    // 丢掉 Runtime.enable 时回放的旧异常
  consoleMsgs.length = 0;
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const navT0 = Date.now();
  await cdp.send('Page.navigate', { url: PAGE_URL + '?t=' + Date.now() });

  // 等待画板就绪（最多 180s）
  let ready = false;
  const t0 = Date.now();
  for (let i = 0; i < 360; i++) {
    try {
      ready = await cdp.eval('!!(window.__ketcherReady && window.ketcher)');
    } catch (e) { ready = false; }
    if (ready) break;
    if (pageErrors.length) break; // 有异常就立刻停，不空等
    await sleep(500);
  }
  const loadMs = Date.now() - navT0;
  console.log('画板就绪:', ready, ' 实际加载耗时(ms):', loadMs);

  if (!ready) {
    const st = await cdp.eval('document.getElementById("status").textContent');
    console.log('页面状态文本:', st);
    console.log('页面异常:', pageErrors);
    console.log('console:', consoleMsgs.slice(-20));
    process.exit(2);
  }

  // 功能验证 1：把画板内容设为苯环（走 indigo 引擎解析，能证明 WASM 真的在跑）
  await cdp.eval(`(async () => { await window.ketcher.setMolecule('c1ccccc1'); return true; })()`);
  await sleep(1500);
  const smilesFromSet = await cdp.eval(`(async () => await window.ketcher.getSmiles())()`);

  // 功能验证 2：走页面上的「导出 SMILES」按钮（真实用户操作路径）
  await cdp.eval(`document.getElementById('btn-smiles').click()`);
  await sleep(2500);
  const btnText = await cdp.eval(`document.getElementById('smiles').value`);
  const btnStatus = await cdp.eval(`document.getElementById('status').textContent`);

  // 再验证一个稍复杂的结构
  await cdp.eval(`(async () => { await window.ketcher.setMolecule('CC(=O)Oc1ccccc1C(=O)O'); return true; })()`);
  await sleep(1500);
  const smiles2 = await cdp.eval(`(async () => await window.ketcher.getSmiles())()`);

  // 截图
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(SHOT, Buffer.from(shot.data, 'base64'));

  console.log('--- 功能结果 ---');
  console.log('setMolecule(c1ccccc1) 后 getSmiles =', JSON.stringify(smilesFromSet));
  console.log('点击按钮后文本框内容              =', JSON.stringify(btnText));
  console.log('点击按钮后状态文本                =', btnStatus);
  console.log('setMolecule(阿司匹林) 后 getSmiles =', JSON.stringify(smiles2));

  console.log('--- 网络请求（共 ' + requests.length + ' 条） ---');
  const external = requests.filter((u) => !u.startsWith('http://127.0.0.1:8899') && !u.startsWith('data:') && !u.startsWith('blob:'));
  requests.forEach((u) => console.log('  ', u.slice(0, 140)));
  console.log('非本地/非 blob 请求条数 =', external.length);

  console.log('--- 页面 JS 异常 ---', pageErrors.length ? pageErrors : '无');
  console.log('截图已写入:', SHOT);
  process.exit(0);
})().catch((e) => { console.error('测试脚本失败:', e); process.exit(1); });
