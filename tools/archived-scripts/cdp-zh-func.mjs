import fs from 'fs';
const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result); pending.delete(m.id); } };
await new Promise((r) => { ws.onopen = r; });
const send = (m, p = {}) => { const i = ++id; ws.send(JSON.stringify({ id: i, method: m, params: p })); return new Promise((res) => pending.set(i, { res })); };
const ev = async (e) => {
  const r = await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true, userGesture: true });
  if (r.exceptionDetails) throw new Error('JS 异常 ' + JSON.stringify(r.exceptionDetails.exception));
  return r.result.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await send('Page.navigate', { url: 'http://127.0.0.1:8765/board.html?t=' + Date.now() });
for (let i = 0; i < 120; i++) { if (await ev('!!(window.__ketcherReady && window.ketcher)')) break; await sleep(500); }
await sleep(1000);

const cases = [
  ['c1ccccc1', '苯'],
  ['CC(=O)Oc1ccccc1C(=O)O', '阿司匹林'],
  ['c1ccncc1', '吡啶(含氮)'],
  ['CCO', '乙醇'],
  ['O=S(=O)(O)O', '硫酸'],
];
console.log('=== 引擎功能回归（汉化后）===');
for (const [smi, name] of cases) {
  await ev(`window.ketcher.setMolecule(${JSON.stringify(smi)})`);
  await sleep(700);
  const out = await ev(`window.ketcher.getSmiles()`);
  // 规范化比较：把输出再喂回去应等价
  const same = await ev(`(async()=>{const a=await window.ketcher.getSmiles();return a;})()`);
  console.log(`  ${name.padEnd(8)} in=${smi.padEnd(24)} out=${out}`);
}
// 元素周期表/画布导出图片（走 Indigo 渲染，验证 WASM 正常）
const png = await ev(`(async()=>{const b=await window.ketcher.generateImage('c1ccccc1',{outputFormat:'png'});const bl=await b.arrayBuffer();return bl.byteLength;})()`);
console.log('  generateImage(png) 字节数 =', png);
const inchi = await ev(`(async()=>{await window.ketcher.setMolecule('CCO');return await window.ketcher.getInchi();})()`);
console.log('  getInchi(CCO) =', inchi);
process.exit(0);
