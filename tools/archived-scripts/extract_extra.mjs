import fs from 'fs';

console.log('===== 1) elements.js 中的元素 title =====');
const el = fs.readFileSync('node_modules/ketcher-core/dist/domain/constants/elements.js', 'utf8');
const elTitles = [...new Set([...el.matchAll(/title:\s*'([^']+)'/g)].map((m) => m[1]))];
console.log('数量:', elTitles.length);
console.log(elTitles.join(', '));
// 也看下 elements.js 里 title 的使用形态
const i0 = el.indexOf('title:');
console.log('样本:', el.slice(Math.max(0, i0 - 120), i0 + 160).replace(/\n/g, ' '));

console.log('\n===== 2) ketcher-react 中环模板名（templates 数组首行） =====');
const rx = fs.readFileSync('node_modules/ketcher-react/dist/index.js', 'utf8');
const ti = rx.indexOf('var templates$1');
const seg = rx.slice(ti, ti + 20000);
const names = [...seg.matchAll(/"([A-Za-z][A-Za-z0-9 \-\u00b0']*)\\n  Ketcher/g)].map((m) => m[1]);
console.log('模板名:', [...new Set(names)].join(' | '));

console.log('\n===== 3) 键类型下拉项标题 =====');
const bonds = [...new Set([...rx.matchAll(/title:\s*"([^"]*(?:Bond|bond)[^"]*)"/g)].map((m) => m[1]))];
console.log(bonds.join('\n'));

console.log('\n===== 4) 周期表数据文件定位 =====');
for (const f of ['ketcher-react/dist/index.js', 'ketcher-core/dist/domain/constants/elements.js']) {
  const s = fs.readFileSync('node_modules/' + f, 'utf8');
  console.log(f, '含 title:"Oxygen"?', s.includes('title:"Oxygen"'), ' 含 title: \'Oxygen\'?', s.includes("title: 'Oxygen'"), ' 含 "Oxygen"?', s.includes('Oxygen'));
}
