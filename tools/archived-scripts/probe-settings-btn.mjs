const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result); pending.delete(m.id); } };
await new Promise((r) => { ws.onopen = r; });
const send = (m, p = {}) => { const i = ++id; ws.send(JSON.stringify({ id: i, method: m, params: p })); return new Promise((res) => pending.set(i, { res })); };
const ev = async (e) => (await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true, userGesture: true })).result.value;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 打开设置
await ev(`[...document.querySelectorAll('[title]')].filter(e=>e.getAttribute('title')==='设置'&&e.getBoundingClientRect().width>0)[0].click()`);
await sleep(1500);
const r = await ev(`JSON.stringify([...document.querySelectorAll('[class*="Settings-module"], [class*="Dialog-module"]')]
  .filter(e=>e.getBoundingClientRect().width>0)
  .flatMap(e=>[...e.querySelectorAll('button')])
  .map(b=>({txt:b.innerText, tid:b.getAttribute('data-testid'), cls:b.className.toString().slice(0,50)})), null, 1)`);
console.log(r);
process.exit(0);
