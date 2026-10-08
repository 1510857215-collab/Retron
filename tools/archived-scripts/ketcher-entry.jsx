import React from 'react';
import { createRoot } from 'react-dom/client';
import { Editor } from 'ketcher-react';
import { StandaloneStructServiceProvider } from 'ketcher-standalone';
import 'ketcher-react/dist/index.css';

// 全离线：Indigo 引擎（WASM）已内嵌在 ketcher-standalone 的打包里，
// 不需要任何网络请求。
const structServiceProvider = new StandaloneStructServiceProvider();

function App() {
  return React.createElement(Editor, {
    staticResourcesUrl: '',
    structServiceProvider,
    disableMacromoleculesEditor: true,
    onInit: (ketcher) => {
      window.ketcher = ketcher;
      window.__ketcherReady = true;
      document.dispatchEvent(new CustomEvent('ketcher-ready'));
    },
  });
}

const container = document.getElementById('ketcher-root');
createRoot(container).render(React.createElement(App));
