// esbuild --inject：把 Node 的 process / Buffer 全局变量替换为浏览器 polyfill 的 import
export { default as process } from 'process';
export { Buffer } from 'buffer';
