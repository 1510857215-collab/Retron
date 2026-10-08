// 交互探测：依次点击若干工具栏按钮，报告出现的弹窗/浮层文本
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result); pending.delete(m.id); } };
await new Promise((r) => { ws.onopen = r; });
const send = (method, params = {}) => { const i = ++id; ws.send(JSON.stringify({ id: i, method, params })); return new Promise((res) => pending.set(i, { res })); };
const ev = async (e) => (await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true, userGesture: true })).result.value;
const shot = async (p) => { const s = await send('Page.captureScreenshot', { format: 'png' }); (await import('fs')).writeFileSync(p, Buffer.from(s.data, 'base64')); };

// 重新加载
await send('Page.navigate', { url: 'http://127.0.0.1:8765/board.html?t=' + Date.now() });
for (let i = 0; i < 120; i++) { if (await ev('!!(window.__ketcherReady && window.ketcher)')) break; await sleep(500); }
await sleep(1000);

const targets = ['设置', '关于', '结构库', '元素周期表', '扩展表'];
for (const tg of targets) {
  const r = await ev(`(() => {
    const els = [...document.querySelectorAll('[title]')].filter(e => e.getAttribute('title') === ${JSON.stringify(tg)} && e.getBoundingClientRect().width > 0);
    if (!els.length) return 'NO_BTN';
    els[0].click(); return 'ok';
  })()`);
  await sleep(1200);
  const info = await ev(`(() => {
    const layers = [...document.querySelectorAll('div')].filter(e => {
      const r = e.getBoundingClientRect();
      return r.width > 200 && r.height > 150 && (getComputedStyle(e).position === 'fixed' || getComputedStyle(e).position === 'absolute');
    });
    const texts = layers.map(e => (e.innerText || '').trim()).filter(t => t && t.length < 3000);
    const dialogs = [...document.querySelectorAll('[role="dialog"], .MuiDialog-paper, .contexify, [class*="Dialog"], [class*="Popover"], [class*="Settings"]')].map(e => ({
      cls: (e.className||'').toString().slice(0,60), vis: e.getBoundingClientRect().width>0, txt: (e.innerText||'').trim().slice(0,400)
    }));
    return JSON.stringify({ layerTexts: [...new Set(texts)].slice(0,3), dialogs: dialogs.filter(d=>d.vis).slice(0,4) });
  })()`);
  console.log('\n#### 点击 [' + tg + '] -> ' + r);
  console.log(info);
  await shot('C:/Users/zzl/Desktop/hx/logs/probe_' + encodeURIComponent(tg) + '.png');
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', windowsVirtualKeyCode: 27 });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', windowsVirtualKeyCode: 27 });
  await sleep(700);
}
process.exit(0);
