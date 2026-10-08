import fs from 'fs';

const files = [
  'node_modules/ketcher-react/dist/index.js',
  'node_modules/ketcher-core/dist/index.js',
];

for (const f of files) {
  const s = fs.readFileSync(f, 'utf8');
  console.log('\n\n########', f, 'len=', s.length);
  for (const prop of ['title', 'label', 'placeholder', 'tooltip', 'children']) {
    const re = new RegExp(prop + ":\\s*(['\"])([^'\"\\\\\\n]{1,90})\\1", 'g');
    const set = new Set();
    let m;
    while ((m = re.exec(s))) set.add(m[2]);
    if (set.size === 0) continue;
    console.log(`\n### ${prop} (${set.size})`);
    console.log([...set].sort().join('\n'));
  }
}
