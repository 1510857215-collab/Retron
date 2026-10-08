import fs from 'fs';

const dict = JSON.parse(fs.readFileSync('ketcher-zh-dict.json', 'utf8'));
const known = new Set(Object.keys(dict).filter((k) => !k.startsWith('_')));
const enumKnown = new Set(Object.keys(dict._enumNames || {}));

const files = [
  'node_modules/ketcher-react/dist/index.js',
  'node_modules/ketcher-react/dist/index.modern-55d8e3ef.js',
  'node_modules/ketcher-core/dist/index.js',
  'node_modules/ketcher-core/dist/application/settings/schema.modern.js',
];
const PROPS = ['title', 'label', 'placeholder', 'tooltip', 'children'];

const missing = new Set();
for (const f of files) {
  const s = fs.readFileSync(f, 'utf8');
  for (const p of PROPS) {
    const re = new RegExp(p + ":\\s*(['\"])([^'\"\\\\\\n]{2,90})\\1", 'g');
    let m;
    while ((m = re.exec(s))) {
      const v = m[2];
      if (!/[A-Za-z]{2}/.test(v)) continue;          // 纯符号/数字
      if (known.has(v)) continue;
      if (/^M[0-9. ]/.test(v)) continue;              // SVG path
      missing.add(v);
    }
  }
  // enumNames 未收录
  const re2 = /enumNames:\s*\[([^\]]*)\]/g; let m2;
  while ((m2 = re2.exec(s))) {
    for (const q of m2[1].matchAll(/'([^']*)'|"([^"]*)"/g)) {
      const v = q[1] ?? q[2];
      if (v && /[A-Za-z]{2}/.test(v) && !enumKnown.has(v)) missing.add('[enum] ' + v);
    }
  }
}
const arr = [...missing].sort();
console.log('未收录展示位文案 (' + arr.length + '):');
console.log(arr.join('\n'));
