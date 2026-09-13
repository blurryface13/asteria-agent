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
require.extensions['.css'] = module => { module.exports = new Proxy({}, {get: (_, key) => key === '__esModule' ? false : String(key)}); };
const EntityActions = require('../components/harness/EntityActions.tsx').default;

test('entity deletion: confirmation, failure, success, busy and keyboard behavior', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost'});
  global.window = dom.window; global.document = dom.window.document; global.navigator = dom.window.navigator;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  dom.window.HTMLDialogElement.prototype.showModal = function () {this.open = true;};
  dom.window.HTMLDialogElement.prototype.close = function () {this.open = false;};
  const root = createRoot(document.getElementById('root'));
  let calls = 0;
  const click = async element => {assert.ok(element); await act(async () => element.click());};
  const render = async props => act(async () => root.render(React.createElement(EntityActions, {kind:'任务',title:'测试',onOpen:()=>{},...props})));
  try {
    await render({onDelete:async () => {calls++; throw new Error('正在运行');}});
    await click(document.querySelector('[aria-haspopup="menu"]'));
    assert.equal(document.activeElement.textContent, '打开任务');
    await act(async () => document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true})));
    assert.equal(document.activeElement.textContent, '删除任务');
    await click(document.activeElement);
    assert.equal(calls,0);
    assert.equal(document.querySelector('dialog').open,true);
    assert.equal(document.activeElement.textContent,'取消');
    await click([...document.querySelectorAll('dialog button')].find(b=>b.textContent==='删除任务'));
    assert.equal(calls,1);
    assert.match(document.querySelector('[role="alert"]').textContent,/正在运行/);
    assert.equal(document.querySelector('dialog').open,true);
    await click([...document.querySelectorAll('dialog button')].find(b=>b.textContent==='取消'));
    await render({onDelete:async () => {calls++;}});
    await click(document.querySelector('[aria-haspopup="menu"]'));
    await click(document.querySelectorAll('[role="menuitem"]')[1]);
    await click([...document.querySelectorAll('dialog button')].find(b=>b.textContent==='删除任务'));
    assert.equal(calls,2);
    assert.equal(document.querySelector('dialog').open,false);
    await render({disabled:true,onDelete:async()=>{calls++;}});
    await click(document.querySelector('[aria-haspopup="menu"]'));
    assert.equal(document.querySelectorAll('[role="menuitem"]')[1].disabled,true);
    await act(async () => document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true})));
    assert.equal(document.querySelector('[role="menu"]'),null);
    assert.equal(calls,2);
  } finally {await act(async()=>root.unmount()); dom.window.close();}
});

test('stale report cache is preserved as backup, never uploaded after server deletion', async () => {
  const vm = require('node:vm');
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost'});
  global.window = dom.window; global.document = dom.window.document; global.navigator = dom.window.navigator;
  global.localStorage = dom.window.localStorage;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const legacy = [{id:'deleted-task',question:'old',answer:'old answer',timestamp:1}];
  localStorage.setItem('researchHistory',JSON.stringify(legacy));
  const requests = [];
  const box = {exports:{},console,window,localStorage,require: name => {
    if (name === '@/helpers/auth') return {authFetch:async (url, options) => {requests.push([url,options]); return {ok:true,json:async()=>({reports:[]})};}};
    return require(name);
  }};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('hooks/useResearchHistory.ts','utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true},
  }).outputText,box);
  let state;
  function Consumer() {state=box.exports.useResearchHistory(); return null;}
  const root=createRoot(document.getElementById('root'));
  try {
    await act(async()=>root.render(React.createElement(Consumer)));
    assert.equal(state.history.length,0);
    assert.equal(requests.length,1);
    assert.equal(requests[0][1],undefined);
    assert.deepEqual(JSON.parse(localStorage.getItem('researchHistory')),[]);
    assert.deepEqual(JSON.parse(localStorage.getItem('researchHistory.legacyBackup')),legacy);
  } finally {await act(async()=>root.unmount()); dom.window.close();}
});

test('full browser storage cannot hide server history or undo a saved report', async () => {
  const vm = require('node:vm');
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost'});
  global.window = dom.window; global.document = dom.window.document; global.navigator = dom.window.navigator;
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const legacy = [{id:'local-draft',question:'draft',answer:'unsaved',timestamp:1}];
  const server = [{id:'saved',question:'server',answer:'persisted',timestamp:2}];
  const storage = {
    getItem: key => key === 'researchHistory' ? JSON.stringify(legacy) : null,
    setItem: () => {throw new dom.window.DOMException('full','QuotaExceededError');},
  };
  const requests=[];
  const box={exports:{},console,window,Event:dom.window.Event,localStorage:storage,require:name=>{
    if(name==='react-hot-toast') return {toast:{error:()=>{},success:()=>{}}};
    if(name==='@/helpers/auth') return {authFetch:async(url,options)=>{
      requests.push([url,options]);
      return {ok:true,json:async()=>({reports:server})};
    }};
    return require(name);
  }};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('hooks/useResearchHistory.ts','utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true},
  }).outputText,box);
  let state;
  function Consumer(){state=box.exports.useResearchHistory(); return null;}
  const root=createRoot(document.getElementById('root'));
  try {
    await act(async()=>root.render(React.createElement(Consumer)));
    assert.equal(state.history[0].id,'saved');
    assert.equal(state.loading,false);
    assert.deepEqual(JSON.parse(storage.getItem('researchHistory')),legacy);
    await act(async()=>state.saveResearch('updated','new answer',[],'saved'));
    assert.equal(state.history[0].answer,'new answer');
    assert.ok(requests.some(([url,options])=>url==='/api/reports' && options?.method==='POST'));
    assert.ok(!requests.some(([,options])=>options?.method==='DELETE'));
  } finally {await act(async()=>root.unmount()); dom.window.close();}
});
