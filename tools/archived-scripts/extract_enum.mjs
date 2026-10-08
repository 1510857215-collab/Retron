import fs from 'fs';
const s = fs.readFileSync('node_modules/ketcher-react/dist/index.js', 'utf8');
const re = /enumNames:\s*\[([^\]]*)\]/g;
let m;
let n = 0;
while ((m = re.exec(s))) {
  n++;
  const before = s.slice(Math.max(0, m.index - 220), m.index).replace(/\n/g, ' ');
  const inner = m[1].replace(/\s+/g, ' ').trim();
  console.log(`--- #${n} ---`);
  console.log('  ENUM   :', before);
  console.log('  NAMES  :', inner);
}
