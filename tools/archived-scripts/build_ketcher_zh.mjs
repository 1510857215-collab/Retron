// Ketcher 画板汉化构建脚本
// ------------------------------------------------------------------
// 背景：ketcher-standalone / ketcher-react / ketcher-core v3.18.0 的官方
// 已编译 dist 里 **没有任何 i18n 运行时**（无 i18next / react-i18next /
// useTranslation / locales 资源），界面文案全部是硬编码英文字面量。
// 因此无法用 {locale:'zh'} 这类初始化参数切换语言。
//
// 本脚本的做法：在 esbuild 打包时，用 onLoad 钩子拦截 ketcher-react /
// ketcher-core 的 dist 源码，把「展示位」(title/label/placeholder/
// tooltip/children) 上出现的英文文案整串精确替换成中文（词典见
// ketcher-zh-dict.json），然后再交给 esbuild 正常打包。
// 只替换这些属性位置且整串匹配，避免误伤内部标识符 / 元素符号。
//
// 用法：node build_ketcher_zh.mjs
// ------------------------------------------------------------------

import * as esbuild from 'esbuild';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dict = JSON.parse(fs.readFileSync(path.join(__dirname, 'ketcher-zh-dict.json'), 'utf8'));

// 只在这些「展示属性」位置做替换
const DISPLAY_PROPS = ['title', 'label', 'placeholder', 'tooltip', 'children'];
const QUOTES = ['"', "'"];

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// 预编译替换规则，提升大文件上的性能
const RULES = [];
for (const [en, zh] of Object.entries(dict)) {
  if (en.startsWith('_')) continue; // 注释字段
  for (const prop of DISPLAY_PROPS) {
    for (const q of QUOTES) {
      RULES.push({
        re: new RegExp(prop + ':\\s*' + q + escapeRe(en) + q, 'g'),
        to: prop + ': ' + q + zh + q,
        en,
      });
    }
  }
}

// 设置面板的下拉项显示名放在 enumNames: [...] 数组里（enum 才是真正的取值），
// 因此只替换 enumNames 括号内的字符串，绝不动 enum 的值，保证逻辑不受影响。
const ENUM_DICT = dict._enumNames || {};

// Dialog 组件的字符串按钮（buttons: ['Cancel','OK'] + buttonsNameMap）。
// 按钮 ID 参与 isButtonOk/exit 等逻辑判断，绝不能改；只把「显示名」兜底替换为中文。
const RAW_RULES = [
  {
    id: 'Dialog 按钮显示名',
    from:
      'value: (_buttonsNameMap$butto = buttonsNameMap === null || buttonsNameMap === void 0 ? void 0 : buttonsNameMap[button]) !== null && _buttonsNameMap$butto !== void 0 ? _buttonsNameMap$butto : button,',
    to:
      'value: (function(){var ZM={OK:"确定",Apply:"应用",Cancel:"取消",Save:"保存",Close:"关闭",Yes:"是",No:"否",Add:"添加"};var v=(_buttonsNameMap$butto = buttonsNameMap === null || buttonsNameMap === void 0 ? void 0 : buttonsNameMap[button]) !== null && _buttonsNameMap$butto !== void 0 ? _buttonsNameMap$butto : button;return ZM[v] || v;})(),',
  },
];

// 环模板名内嵌在 MOL 文件字符串的首行（形如 "Benzene\n  Ketcher ..."），
// 不在 title/label 等展示属性上，需要单独按「整串前缀」替换。
// 源文件里 \n 是字面两字符（反斜杠+n），因此这里用 '\\n' 表达。
const TEMPLATE_RULES = Object.entries(dict._templates || {}).map(([en, zh]) => ({
  from: '"' + en + '\\n  Ketcher',
  to: '"' + zh + '\\n  Ketcher',
  en,
}));

const stats = [];

/** esbuild 插件：把 ketcher 包 dist 源码里的界面文案替换成中文 */
const ketcherZhPlugin = {
  name: 'ketcher-zh',
  setup(build) {
    build.onLoad({ filter: /ketcher-(react|core|standalone)[\\/]dist[\\/].*\.js$/ }, async (args) => {
      let code = await fs.promises.readFile(args.path, 'utf8');
      let hits = 0;
      const seen = new Set();
      for (const rule of RULES) {
        rule.re.lastIndex = 0;
        code = code.replace(rule.re, () => {
          hits++;
          seen.add(rule.en);
          return rule.to;
        });
      }
      for (const t of TEMPLATE_RULES) {
        if (code.includes(t.from)) {
          const n = code.split(t.from).length - 1;
          code = code.split(t.from).join(t.to);
          hits += n;
          seen.add('模板名:' + t.en);
        }
      }
      // enumNames 数组内的显示名翻译
      code = code.replace(/enumNames:\s*\[([^\]]*)\]/g, (full, inner) => {
        const replaced = inner.replace(/(['"])([^'"]{1,60})\1/g, (mm, q, val) => {
          const zh = ENUM_DICT[val];
          if (zh) {
            hits++;
            seen.add('[enum] ' + val);
            return q + zh + q;
          }
          return mm;
        });
        return 'enumNames: [' + replaced + ']';
      });
      // 精确整段替换（Dialog 字符串按钮等）
      for (const r of RAW_RULES) {
        if (code.includes(r.from)) {
          code = code.split(r.from).join(r.to);
          hits++;
          seen.add('[raw] ' + r.id);
        }
      }
      if (hits > 0) {
        stats.push({ file: path.relative(__dirname, args.path), hits, words: [...seen].sort() });
      }
      return { contents: code, loader: 'js' };
    });
  },
};

const outfile = path.resolve(__dirname, '../../web/ketcher/ketcher-app.js');

await esbuild.build({
  entryPoints: [path.join(__dirname, 'ketcher-entry.jsx')],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
  jsx: 'transform',
  define: {
    'process.env.NODE_ENV': '"production"',
    global: 'globalThis',
  },
  inject: [path.join(__dirname, 'inject-shim.js')],
  minify: true,
  legalComments: 'none',
  outfile,
  plugins: [ketcherZhPlugin],
  logLevel: 'info',
});

console.log('\n========== 汉化替换统计 ==========');
let total = 0;
for (const s of stats) {
  total += s.hits;
  console.log(`  ${s.file}: ${s.hits} 处`);
}
console.log(`  合计替换: ${total} 处`);
const allWords = new Set(stats.flatMap((s) => s.words));
console.log(`  命中的不同词条: ${allWords.size} / 词典 ${Object.keys(dict).filter((k) => !k.startsWith('_')).length}`);
const missing = Object.keys(dict).filter((k) => !k.startsWith('_') && !allWords.has(k));
if (missing.length) console.log('  未命中词条(可能不在此包): ' + missing.join(' | '));
console.log('==================================\n');
