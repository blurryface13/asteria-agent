/** Isolated component QA, no login bypass or access to real application data. */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
require.extensions['.tsx'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,esModuleInterop:true},
}).outputText,filename);
require.extensions['.css'] = module => {module.exports=new Proxy({},{get:(_,k)=>k==='__esModule'?false:String(k)});};
const Progress = require('../components/harness/CollaborationProgress.tsx').default;
const {scenarios} = require('./fixtures/collaboration.cjs');
const css = fs.readFileSync(path.join(__dirname,'../components/harness/activity.module.css'),'utf8');
const names={waiting:'并行执行中',partial:'先回传一路／求助中',complete:'全部回传',cancelled:'取消后保留结果'};
const server=http.createServer((req,res)=>{
  const selected=new URL(req.url,'http://127.0.0.1').searchParams.get('state')||'partial';
  const state=Object.hasOwn(scenarios,selected)?selected:'partial';
  const content=renderToStaticMarkup(React.createElement(Progress,{events:scenarios[state],active:['waiting','partial'].includes(state)}));
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
  res.end(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Asteria 协作组件验收</title><style>
  ${css}
  *{box-sizing:border-box}body{margin:0;background:#202124;color:#c5c7cb;font:14px/1.65 system-ui,sans-serif}main{max-width:820px;margin:40px auto;padding:0 24px}nav{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}a{color:#b7cbe7}h1{font-size:22px;font-weight:550}p{margin:6px 0}a:focus-visible{outline:2px solid #b7cbe7;outline-offset:4px}
  </style><main><h1>协作进展 · 组件验收</h1><p class="note">合成展示样例，不连接真实账户或模型；示例时间不是实测数据。</p><nav aria-label="选择展示状态">${Object.entries(names).map(([key,label])=>`<a href="?state=${key}" ${state===key?'aria-current="page"':''}>${label}</a>`).join('')}</nav>${content}</main></html>`);
});
server.listen(3025,'127.0.0.1',()=>console.log('Isolated component preview http://127.0.0.1:3025/'));
