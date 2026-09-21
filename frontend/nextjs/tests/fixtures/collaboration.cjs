// Explicit display fixture. Timings are synthetic, not performance measurements.
const assignments = [
  {name:'代码核对',role:'coding',objective:'核对注意力实现中的缩放项，并预览修改。',focus:'实现与公式的对应关系',expected_output:'文件位置、差异预览和未执行项',exclude:'不训练模型，不重复概述整篇论文'},
  {name:'方法原理',role:'researcher',objective:'查明缩放点积注意力的定义与数值稳定性依据。',focus:'原文公式和适用条件',expected_output:'页段依据与局限',exclude:'不修改代码'},
];
const start = {tool:'parallel_batch',status:'started',batch_id:'display-fixture',assignments};
const fast = {tool:'parallel_result',status:'completed',batch_id:'display-fixture',index:1,assignment:assignments[1],
  since_dispatch_ms:8200,result:{summary:'已找到缩放点积注意力的原文公式，缩放项为 √dₖ。代码对应情况仍由另一子任务核对。'}};
const help = {tool:'research_handoff',status:'waiting',request_id:'help-fixture',purpose:'核对缩放的原因',
  request:{question:'为什么使用 √dₖ 作为缩放因子？',observed_problem:'实际文件中只有 QKᵀ，未观察到缩放项。'}};
const slow = {tool:'parallel_result',status:'incomplete',batch_id:'display-fixture',index:0,assignment:assignments[0],
  since_dispatch_ms:18500,result:{summary:'已核对文件并生成缩放项 diff；Python 语法检查通过。修改尚未应用，也未执行测试或训练。'}};
exports.scenarios = {
  waiting:[start], partial:[start,fast,help],
  complete:[start,fast,help,{...help,status:'completed',wait_ms:6100,result:{summary:'原文解释指出缩放用于控制点积的方差。'}},slow,
    {...start,status:'completed',elapsed_ms:18500,first_result_ms:8200}],
  cancelled:[start,fast,help,{tool:'parallel_batch',batch_id:'display-fixture',status:'cancelled',elapsed_ms:10000,first_result_ms:8200}],
};
