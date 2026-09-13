const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const {JSDOM}=require('jsdom');
const React=require('react');
const {act}=React;

test('memory editor preserves drafts on conflict and updates file-switch baseline',async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
  global.window=dom.window;global.document=dom.window.document;global.navigator=dom.window.navigator;
  global.IS_REACT_ACT_ENVIRONMENT=true;
  // Load react-dom after installing DOM so its input event support is detected.
  const {createRoot}=require('react-dom/client');
  let files=[{name:'PROJECT.md',content:'old',version:'old-hash',exists:true,path:'/test/PROJECT.md'},
    {name:'memory/MEMORY.md',content:'index',version:'index-hash',exists:true,path:'/test/memory/MEMORY.md'}];
  let dirty=false, puts=0;
  const box={exports:{},window,require:name=>{
    if(name==='@/helpers/auth')return {authFetch:async(url,options)=>{
      if(options.method==='PUT'){puts++;return {ok:false,status:409,json:async()=>({detail:'磁盘版本已变化'})};}
      return {ok:true,json:async()=>({directory:'/test',files:files.map(f=>({...f}))})};
    }};
    if(name.endsWith('.css'))return {};
    return require(name);
  }};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('components/memory/MemoryEditor.tsx','utf8'),{
    compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true},
  }).outputText,box);
  const root=createRoot(document.getElementById('root'));
  const button=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
  const click=async b=>{assert.ok(b);await act(async()=>b.click());};
  try{
    await act(async()=>root.render(React.createElement(box.exports.default,{projectId:'p',onDirtyChange:value=>{dirty=value;}})));
    const input=document.querySelector('textarea');
    await act(async()=>{
      Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype,'value').set.call(input,'browser draft');
      input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    });
    assert.equal(dirty,true);
    assert.equal(button('PROJECT.md').disabled,true);
    files[0]={...files[0],content:'local new version',version:'new-hash'};
    await click(button('保存'));
    assert.equal(puts,1);assert.equal(input.value,'browser draft');
    assert.match(document.querySelector('[role="alert"]').textContent,/磁盘版本/);
    await click(button('读取磁盘版本'));
    assert.equal(input.value,'browser draft');
    await click(button('放弃草稿，使用磁盘内容'));
    assert.equal(input.value,'local new version');assert.equal(dirty,false);
    await click(button('memory/MEMORY.md'));
    await click(button('PROJECT.md'));
    assert.equal(input.value,'local new version');
  }finally{await act(async()=>root.unmount());dom.window.close();}
});
