// Render the actual TSX with real React; no synthetic browser state injection.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const Module = require('node:module');
const root = path.resolve(__dirname, '../frontend/nextjs');
const req = Module.createRequire(path.join(root, 'package.json'));
const ts = req('typescript'), React = req('react');
const render = req('react-dom/server').renderToStaticMarkup;
const filename = path.join(root, 'components/harness/ResearchActivity.tsx');
const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
}}).outputText;
const mod = new Module(filename);
mod.filename = filename; mod.paths = Module._nodeModulePaths(root);
mod.require = name => name.endsWith('.css') ? {} : req(name);
mod._compile(source, filename);
const logs = [
  {header:'agent_action',text:{agent:'lead',tool:'search',status:'started',purpose:'检索论文',call_id:'1',arguments:{query:'test'}}},
  {header:'agent_action',text:{agent:'lead',tool:'search',status:'completed',purpose:'检索论文',call_id:'1',result:['paper']}},
  {header:'citation_graph',text:{nodes:[{id:'https://arxiv.org/abs/1',url:'https://arxiv.org/abs/1',title:'Paper A',status:'read'},
    {id:'https://arxiv.org/abs/2',url:'https://arxiv.org/abs/2',title:'Paper B',status:'discovered'}],
    edges:[{source:'https://arxiv.org/abs/1',target:'https://arxiv.org/abs/2',evidence:'bibliography'}]}}
];
const html = render(React.createElement(mod.exports.default, {logs,done:false,active:true}));
assert(!html.includes('<details open'));
assert(html.includes('一跳引用关系') && html.includes('bibliography'));
assert(html.includes('test') && html.includes('已完成'));
assert(html.includes('仅发现') && html.includes('Paper B'));
const issues = [
  {header:'agent_action',text:{agent:'researcher-a:test',tool:'read_passage',status:'failed',purpose:'读取参数错误',call_id:'bad',error:'exactly one paper',severity:'attempt'}},
  {header:'agent_action',text:{agent:'researcher-a:test',tool:'finish',status:'incomplete',purpose:'回传缺口'}},
  {header:'agent_action',text:{agent:'researcher-a:test',tool:'agent',status:'incomplete',purpose:'回传缺口'}},
  {header:'agent_action',text:{agent:'assessor',tool:'sufficiency',status:'completed',purpose:'核心证据充分'}},
];
const recovered = render(React.createElement(mod.exports.default, {logs:[...logs,...issues],done:true,active:false}));
assert(recovered.includes('1 次失败或部分失败的尝试') && recovered.includes('1 项研究曾带缺口回传'));
assert(recovered.includes('1 个研究子任务') && recovered.includes('研究与交付已完成'));
assert(!recovered.includes('异常记录') && !recovered.includes('研究任务失败'));
const failed = render(React.createElement(mod.exports.default, {logs:[...issues,{header:'error',text:'行动预算耗尽'}],done:false,active:false}));
assert(failed.includes('研究任务失败') && failed.includes('role="alert"') && failed.includes('行动预算耗尽'));
console.log('PASS: activity grouping, retained arguments, collapsed detail, citation graph and provenance');
