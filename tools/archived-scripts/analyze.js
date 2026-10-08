const fs = require('fs');
const s = fs.readFileSync(process.argv[2], 'utf8');
console.log('size =', s.length);
console.log('--- head 600 ---');
console.log(s.slice(0, 600));
console.log('--- tail 300 ---');
console.log(s.slice(-300));
const marks = [
  'AGFzbQ', '.wasm', 'WebAssembly', 'indigo-ketcher', 'worker', 'Worker',
  'createObjectURL', 'Blob', 'import(', 'require(', 'data:application/wasm',
];
for (const m of marks) {
  let c = 0, i = -1;
  while ((i = s.indexOf(m, i + 1)) !== -1) c++;
  console.log(String(c).padStart(6), m);
}
// 找最长 base64 段
let best = 0, bestAt = -1, cur = 0, start = 0;
for (let i = 0; i < s.length; i++) {
  const ch = s.charCodeAt(i);
  const ok = (ch >= 65 && ch <= 90) || (ch >= 97 && ch <= 122) || (ch >= 48 && ch <= 57) || ch === 43 || ch === 47 || ch === 61;
  if (ok) { if (cur === 0) start = i; cur++; if (cur > best) { best = cur; bestAt = start; } }
  else cur = 0;
}
console.log('最长 base64-like 段:', best, '@', bestAt);
if (bestAt >= 0) console.log('片段开头:', JSON.stringify(s.substr(bestAt, 80)));
