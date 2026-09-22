# 协作验收与学习指引

日期：2026-09-22。本轮落地的是科研自主协作关键路径，不是整个 EchoMind 替换。

后续更新：本机模型服务已可用，完成了单例冻结材料上的真实 Coding 直接阅读/科研求助对照，见 [Coding 调研路径实验](coding-research-comparison.md)。下文HTTP402是此前验收的历史结果；新的局部对照不代表完整分工质量、在线调研或执行调试已经验收。

工具闭环进一步对齐 EchoMind 的结果/Trace 边界，生产 Coding 已加入实际片段完成检查与重复请求保护，参见 [工具契约](coding-tool-contract.md)；不强制通过科研子 Agent 取得证据。

## 1. 如何理解 Agentic 与 Workflow

固定的是工具授权、预算、目标契约、审查接口。动态的是 Lead 是否委派、分配什么角度、子 Agent 如何选择下一动作，以及代码 Agent 是否需要请求研究。无需固定经过每个角色，也不要求所有任务都并行。

Lead 先给出有区分度的 assignment；运行时检查所有当前目标都有归属（子 Agent 或 Lead 保留）。独立语义审查检查目标声明是否属实、任务是否为换名重复。不合格时直接返回具体错误，由 Lead 下一轮重新决定。通过只代表计划合理，不代表研究已经完成。

代码角色先读实际文件；已知论文/公式可直接 read_paper → read_paper_passage，和科研角色共享本次PaperLibrary与证据预算。需要更深入的科学原理/实验协议分析时才 request_research。Supervisor在现有预算内启动短研究子循环，回复作为观察返回原代码角色，不启动完整报告工作流，也不允许研究子角色递归派工。语法检查只解析不执行，diff预览不写文件；所有待修改内容仍须通过现有文件提案批准。

## 2. EchoMind 阅读对照

| EchoMind 位置 | Asteria 适配位置 | 本轮差异 |
| --- | --- | --- |
| agents/agent_orchestrator.py · AgentProfile | agentic/collaboration.py · AgentProfile | 科研/代码角色，明确目标和交付要求 |
| BaseAgent._call_llm | agentic/coding.py · run_coding | 保留角色/工具/观察循环，用现有通用模型接口，不绑定Anthropic；适合研究任务的轮次预算 |
| AgentOrchestrator.run_parallel | agentic/collaboration.py · run_parallel | as_completed逐项回传，每个角色接不同assignment；最终返回仍保留分工顺序，失败/取消不抹掉早期结果 |
| ResponseComposer | AutonomousReview 汇总与 write_report | 先独立审查证据/代码交付，再写作，不把拼接回答当作验收 |
| core/intent_recognizer.py | agentic/intent_fusion.py、intent.py | 三路融合；实际bge-m3向量；严格LRU＋TTL；完整上下文/用户隔离；冲突先澄清 |

这是参考源码后的模块级适配，不是整包原样复制。学 EchoMind 的角色/循环/并行章节可以对应理解；新增分工审查、c-ID验收和研究求助需看本地代码。

## 3. 用户视角指令

### A：分工覆盖与区分度

> 围绕扩散模型图像水印写一份调研报告。请并行调查：方法如何嵌入和提取水印、面对图像编辑攻击的鲁棒性如何评估。两路不要重复讲方法大全，计算和数据需求可以由负责人保留后续调查。

看 delegations.json / delegation_quality 事件：目标是否遗漏；focus、expected_output是否不同；被拒绝的分工是否真的改了研究问题；不能只改角色名字。读取同一来源并不是失败，重复回答同一个子问题才是问题。

### B：代码读文件→定向求助→继续原任务

> 请检查 attention_demo.py 的注意力计算，和 Attention Is All You Need（https://arxiv.org/abs/1706.03762）的定义是否一致。代码里好像缺了一个缩放因子，我不确定理由，请先读文件；遇到论文原理疑问时请调研角色查原文解释，再回到代码给出修改建议。不要修改文件，也不要运行代码。

夹具在 tests/fixtures/attention_demo.py；命令验收直接只读该文件，不修改个人工作区。在网页试用前，需在自己的工作区创建同名文本文件，不能假设项目源码自动对Agent可见。

看 research-requests.json、coding-results.json 和事件：先真实读文件；求助含 question/observed_problem/expected_answer；request_id能关联回复；回到相同代码任务；来源不足应说明未完成，不能把实验方案、脚本或待批准提案当作执行结果。

### C：同一Loop直接读论文、静态诊断与diff

> 检查工作区 attention_demo.py，对照 https://arxiv.org/abs/1706.03762 第4页的注意力公式。你可以自己读原文，不必另外委派调研；说明实现差异，检查 Python 语法，给出修改 diff。不要应用修改，也不要运行代码。若原文未取到，明确指出。

查看工具记录应有实际文件读取、论文页段、check_python_syntax 和 preview_code_diff；diagnostic 的 observation_id必须来自本轮读取。语法正确不代表算法正确，最终execution_performed仍为false。自动化测试用预置论文页段验证上述动作，不是在线论文结果评测。

## 4. 交互与时差验收

- 研究运行使用持久化agent_action事件，普通代码对话使用按会话鉴权的Coordinator progress；UI轮询间隔800ms，因此不承诺零延迟或逐token推送。
- 前端“分工与阶段结果”显示分工侧重/交付/排除范围，结果按实际完成顺序排列；可独立展开，不必读原始JSON。阶段结果醒目标注未最终验收。
- parallel_result记录elapsed_ms及since_dispatch_ms；parallel_batch记录first_result_ms及elapsed_ms。research_handoff记录wait_ms，区分代码等待和整批耗时。不把合成样例时长写进简历。
- 一路先完成时立即保存brief/delegations并发事件；另一路失败/取消不会抹掉已有结果。取消后的未完成求助显示停止，不继续显示“运行中”。
- Lead在本批回传后继续综合验收；本轮没有让Lead在每个阶段结果到达后立即启动新一批，也没有实现通用DAG调度器。
- 独立组件验收页不接真实账户/模型，不修改主站鉴权：在frontend/nextjs执行 `node tests/serve-collaboration-preview.cjs`，访问 http://127.0.0.1:3025/。有并行中/部分回传/全部回传/取消四种合成状态，数字仅用于展示。

## 5. 可重复命令

工作目录：/Users/dora/Developer/asteria-agent。Python：/Users/dora/miniconda3/envs/dora/bin/python。

```bash
python -m pytest tests/test_agentic_collaboration.py tests/test_collaboration_streaming.py -q
python -m pytest tests/test_intent_fusion.py -q
python -m pytest tests -q
ASTERIA_RUNS_DB_TESTS=1 python -m pytest tests/test_lab_release.py tests/test_durable_runs.py tests/test_coordinator_turns.py -q
python scripts/evaluate-collaboration.py --live --case all
python scripts/evaluate-intent-routing.py --vector-only
python scripts/evaluate-intent-routing.py --live
```

真实模型指令显式使用 --live，最多24次逻辑模型调用；底层SDK可能重试。使用当前环境配置，不自动换供应商；结果写入 outputs/collaboration-eval-*。其中planning仅验收分工与语义审查，不假冒已跑完整调研；coding是只读夹具+实际模型/论文工具，不执行代码。

路由脚本单独提供六条固定输入：代码检查、学习计划、论文综述、投稿查询、金融概念与公司公开资料核查。`--vector-only` 只调用当前 Embedding；`--live` 最多六次逻辑分类调用，遇到模型错误停止，不生成“通过”的替代结果。输出 `outputs/intent-routing-*/summary.json`；两种模式均不执行用户业务任务。七类非研究能力另在替身测试中验证：无论由旧入口现场识别还是作为已有分类传入，都不能误启动研究循环。

前端在frontend/nextjs执行：

```bash
node node_modules/typescript/bin/tsc --noEmit --incremental false
node --test tests/collaboration.test.cjs tests/management.test.cjs tests/memory.test.cjs tests/markdown.test.mjs
```

## 6. 本次结果与未完成项

- 协作专项35条通过：原25条加直接论文工具、静态检查不执行、伪造observation拒绝、快任务先返回、取消保留结果、进度投影和独立代码入口的实时回传。
- 入口专项33条通过，覆盖融合、LLM/向量并行、模板复用、10用户冷启动、上下文与身份缓存隔离、TTL/LRU、降级标注、澄清和旧入口拒绝误启动。语义决策用替身，不把这些测试称为模型准确率评测。
- 全量后端199条通过、5条环境条件跳过；另启用真实PG/Redis的指定测试集14条通过，含运行中progress持久化、跨用户读取拒绝、终态保留、澄清不启动任务（与全量有重叠，不相加宣传总数）。
- 上述是当前工作区（含之前的实验室共享版改动）。本轮待提交文件单独导出的干净副本全量195通过/4跳过，另启用真实PG的Coordinator/durable Run集9条通过；证明路由协作增量不依赖未提交的登录/公共库代码。副本测试所需数据库地址仅从本机环境加载，不复制或提交凭据。
- 前端TypeScript检查通过，8条React/Markdown/历史/记忆测试通过。历史测试补齐新增鉴权辅助函数的Mock，保持旧免登录缓存测试语义，不修改业务实现绕过失败。
- 浏览器对实际组件的隔离样例检查通过：分工展开、先回传一路、全部回传仍待验收、取消保留结果；未改主站认证，未伪造生产任务。本项是组件视觉与交互验收，不是登录后真实LLM端到端验收。
- 实际MCP子进程读了隔离测试用户文件，研究/代码决策使用脚本模型和论文替身；不能称为真实模型效果评测。
- GitHub只读工具真实读取了 psf/requests，固定commit dae7ef63b4df6eded86637f251fc4e3a06c3b479；文件 docs/_themes/flask_theme_support.py，4875字符，未执行。
- 真实模型首次请求返回HTTP402余额不足；两条真实模型验收未通过验收流程，尤其不能声称“研究分工质量已证实”。失败记录在 outputs/collaboration-eval-0ce962d515/summary.json。
- 真实Ollama bge-m3的六条向量探针均匹配预期类别，记录在 outputs/intent-routing-aa210d7c51/summary.json；不是融合路由或任务成功率，也不支持“准确率100%”的结论。
- 待继续：模型服务可用后按上述用户指令观察真实分工/求助质量；普通领域主辅路由；授权隔离的实验执行器。语法检查和diff不是完整coding验收，还需测试执行、退出码/日志、修复后重跑与结果比对。
