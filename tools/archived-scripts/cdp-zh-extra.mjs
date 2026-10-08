import fs from 'fs';
const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result); pending.delete(m.id); } };
await new Promise((r) => { ws.onopen = r; });
const send = (m, p = {}) => { const i = ++id; ws.send(JSON.stringify({ id: i, method: m, params: p })); return new Promise((res) => pending.set(i, { res })); };
const ev = async (e) => (await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true, userGesture: true })).result.value;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = async (p) => { const s = await send('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(p, Buffer.from(s.data, 'base64')); };
const esc = async () => { await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', windowsVirtualKeyCode: 27 }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', windowsVirtualKeyCode: 27 }); await sleep(700); };

await send('Page.navigate', { url: 'http://127.0.0.1:8765/board.html?t=' + Date.now() });
for (let i = 0; i < 120; i++) { if (await ev('!!(window.__ketcherReady && window.ketcher)')) break; await sleep(500); }
await sleep(1200);

// 关于
await ev(`(()=>{const e=[...document.querySelectorAll('[title]')].filter(x=>x.getAttribute('title')==='关于'&&x.getBoundingClientRect().width>0);if(e[0])e[0].click();return !!e[0];})()`);
await sleep(1200);
const about = await ev(`(document.querySelector('[class*="About-module_about"]')||{}).innerText || '(无)'`);
console.log('【关于】\n' + about.replace(/\n{2,}/g, '\n'));
await shot('C:/Users/zzl/Desktop/hx/logs/ketcher_zh_about.png');
await esc();

// 结构库按钮（左侧模板库）：先看 DOM 里可见的按钮 title
const libs = await ev(`JSON.stringify([...new Set([...document.querySelectorAll('button[title]')].map(b=>b.getAttribute('title')))]).slice(0,600)`);
console.log('\n可见 button[title]:', libs);

// 打开分子模板/结构库：尝试底部/左侧的“模板库”类按钮
const tryTitles = ['结构库', '模板库', '官能团', '盐和溶剂', '模板'];
for (const tg of tryTitles) {
  const ok = await ev(`(()=>{const e=[...document.querySelectorAll('[title="'+${JSON.stringify(tg)}+'"]')].filter(x=>x.getBoundingClientRect().width>0);if(!e.length)return false;e[0].click();return true;})()`);
  if (!ok) continue;
  await sleep(1500);
  const txt = await ev(`(()=>{const d=[...document.querySelectorAll('[class*="Dialog-module_dialog"], [role="dialog"]')].filter(e=>e.getBoundingClientRect().width>0);return d.length? d.map(e=>e.innerText).join('\\n--\\n').slice(0,900) : '(无弹窗)';})()`);
  console.log(`\n【${tg}】 -> ${txt.replace(/\n{2,}/g, '\n')}`);
  await shot('C:/Users/zzl/Desktop/hx/logs/ketcher_zh_library.png');
  await esc();
  break;
}
process.exit(0);
