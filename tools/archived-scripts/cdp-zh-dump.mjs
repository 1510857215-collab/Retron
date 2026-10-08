// 细查：列出所有 [title] 元素的可见性、标签、类名，判定哪些需要汉化
async function getTarget() {
  const list = await (await fetch('http://127.0.0.1:9333/json/list')).json();
  return list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
}
const t = await getTarget();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res } = pending.get(m.id); pending.delete(m.id); res(m.result); }
};
await new Promise((r) => { ws.onopen = r; });
function send(method, params = {}) { const i = ++id; ws.send(JSON.stringify({ id: i, method, params })); return new Promise((res) => pending.set(i, { res })); }
async function evalx(e) { const r = await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true }); return r.result.value; }

const out = await evalx(`JSON.stringify([...document.querySelectorAll('[title]')].map(e => {
  const r = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  const visible = r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  return { title: e.getAttribute('title'), tag: e.tagName, cls: (e.className && e.className.toString ? e.className.toString() : '').slice(0,40), vid: visible };
}))`);
const arr = JSON.parse(out);
console.log('总 [title] 元素:', arr.length);
const byTitle = new Map();
for (const a of arr) {
  if (!byTitle.has(a.title)) byTitle.set(a.title, { n: 0, vis: 0, tag: a.tag, cls: a.cls });
  const b = byTitle.get(a.title); b.n++; if (a.vid) b.vis++;
}
const rows = [...byTitle.entries()].map(([k, v]) => ({ title: k, ...v }));
const en = rows.filter((r) => !/[\u4e00-\u9fff]/.test(r.title) && /[A-Za-z]{2}/.test(r.title));
console.log('\n仍为英文的 title（含可见性统计）:');
console.log('visible  title  [tag.class]  count');
for (const r of en.sort((a, b) => b.vis - a.vis)) {
  console.log(`  vis=${r.vis}/${r.n}  "${r.title}"  <${r.tag} .${r.cls}>`);
}
process.exit(0);
