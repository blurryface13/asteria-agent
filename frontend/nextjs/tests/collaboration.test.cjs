const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const {JSDOM} = require('jsdom');
const React = require('react');
const {createRoot} = require('react-dom/client');
const {act} = React;

require.extensions['.tsx'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: {jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, esModuleInterop: true},
}).outputText, filename);
require.extensions['.css'] = module => {module.exports = new Proxy({}, {get: (_, key) => key === '__esModule' ? false : String(key)});};
const Progress = require('../components/harness/CollaborationProgress.tsx').default;
const {scenarios} = require('./fixtures/collaboration.cjs');

test('partial results arrive in completion order, survive polling and never imply final acceptance', async () => {
  const dom = new JSDOM('<div id="root"></div>');
  global.window = dom.window; global.document = dom.window.document; global.navigator = dom.window.navigator;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const root = createRoot(document.getElementById('root'));
  const render = (events, active = true) => act(async () => root.render(React.createElement(Progress, {events, active})));
  try {
    await render([]);
    assert.equal(document.querySelector('section'), null);
    await render(scenarios.waiting);
    assert.match(document.body.textContent, /0\/2 项回传/);
    await render(scenarios.partial);
    assert.match(document.body.textContent, /1\/2 项回传/);
    assert.match(document.body.textContent, /阶段结果尚未经最终验收/);
    assert.match(document.body.textContent, /等待调研答复/);
    await render([...scenarios.partial, scenarios.partial.at(-1)]);
    assert.equal(document.querySelectorAll('ol li').length, 1);
    const summary = document.querySelector('.assignments summary');
    await act(async () => summary.click());
    assert.equal(summary.parentElement.open, true);
    await render(scenarios.complete, false);
    assert.match(document.body.textContent, /2\/2 项回传/);
    assert.match(document.querySelectorAll('ol li')[0].textContent, /方法原理/);
    assert.match(document.querySelectorAll('ol li')[1].textContent, /代码核对/);
    assert.match(document.body.textContent, /后续仍需验收/);
    await render(scenarios.cancelled, false);
    assert.match(document.body.textContent, /已取消/);
    assert.match(document.body.textContent, /已停止，未收到完成记录/);
    assert.equal(document.querySelectorAll('ol li').length, 1);
    await render([{...scenarios.partial[0]}, {...scenarios.partial[1], result:{summary:'<script>alert(1)</script>'}}]);
    assert.equal(document.querySelector('script'), null);
  } finally {await act(async () => root.unmount()); dom.window.close();}
});
