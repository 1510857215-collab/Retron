import fs from 'fs';

const s = fs.readFileSync('C:/Users/zzl/Desktop/hx/web/ketcher/ketcher-app.js', 'utf8');

// 裸中文
const raw = (s.match(/[\u4e00-\u9fff]/g) || []).length;
console.log('裸中文字符数:', raw);

// \uXXXX 转义
const m = s.match(/\\u[0-9a-fA-F]{4}/g) || [];
console.log('\\uXXXX 转义总数:', m.length);

// 检查 "打"(6253) "开"(5f00)
const esc = '\\u6253\\u5f00';
console.log('查找 ' + esc + ' :', s.split(esc).length - 1);

// 大小写不敏感
console.log('小写 \\u6253 计数:', s.split('\\u6253').length - 1);
console.log('大写 \\u6253 计数:', s.split('\\u6253'.toUpperCase()).length - 1);

// 打印一批 CJK 范围的转义
const cjk = m.filter((x) => {
  const cp = parseInt(x.slice(2), 16);
  return cp >= 0x4e00 && cp <= 0x9fff;
});
console.log('CJK 范围转义数:', cjk.length);
console.log('样本:', [...new Set(cjk)].slice(0, 40).join(' '));
