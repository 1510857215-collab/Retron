import fs from 'fs';
const s = fs.readFileSync('node_modules/ketcher-react/dist/index.js', 'utf8');
const j = s.indexOf('_buttonsNameMap$butto = buttonsNameMap === null');
const seg = s.slice(j - 10, j + 300);
console.log(JSON.stringify(seg));
