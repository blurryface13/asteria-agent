---
name: Asteria Research Workspace
description: 深色、低干扰的科研工作台。研究、报告与评测共用同一套视觉语言。
colors:
  primary: "#e7e7e5"
  onPrimary: "#171717"
  background: "#171717"
  surface: "#232323"
  surfaceVariant: "#2c2c2c"
  onSurface: "#e7e7e5"
  onSurfaceVariant: "#989896"
  outline: "#363636"
  error: "#df8984"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: inherit
    fontSize: 23px
    fontWeight: 500
    lineHeight: 1.4
  label:
    fontFamily: inherit
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace'
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.7
rounded:
  small: 8px
  medium: 18px
  large: 27px
spacing:
  small: 8px
  medium: 16px
  large: 32px
components:
  workspace:
    backgroundColor: background
    textColor: onSurface
    rounded: large
  button:
    backgroundColor: primary
    textColor: onPrimary
    typography: label
    rounded: medium
  field:
    backgroundColor: surface
    textColor: onSurface
    typography: body
    rounded: small
---

## Overview

**Creative North Star: "让研究过程和证据成为界面中心。"**

沿用当前科研工作台，以 ClawsGO 与 Codex 的任务式界面为交互参照：左侧组织项目和对话，中间完成任务，右侧检查证据、文件和报告。评测是工作台的延伸，不另起一套管理后台。产品范围见 PRODUCT.md；本文件只约束呈现和交互。

**Key Characteristics:**

- 深灰分层、克制的状态色，正文始终优先于装饰。
- 项目与任务层级清楚，侧栏可收起且始终能展开。
- 先显示结论与摘要，再按需展开工具、子 Agent 和原始记录。
- 原有研究首页及响应式入口保留，不用视觉统一改写后端路由。

**The Continuity Rule.** 新页面复用现有工作台外壳、字体与图标。不得为了新增功能重做首页、改变研究编排或替换技术栈。

## Colors

主操作使用浅灰文字色反转，不引入高饱和品牌按钮。背景、侧栏、输入区通过前述中性色层次区分；hover 在其上提高一阶明度。选中导航用石墨灰（#383838），不使用彩色发光边框。

**The Semantic Color Rule.** 红色仅表示真实失败；低饱和绿色（#a1b9ab）表示已完成/已采纳，暖灰黄色（#d0b683）表示进行中/待审核。状态必须同时有文字，不能只靠颜色表达。

**The Honest State Rule.** 运行成功不等于评测通过。缺失分数显示 N/A；计划功能保持不可用并说明具体缺口，禁止用模拟成绩填满界面。

## Typography

正文沿用系统无衬线字体，中文使用系统可用的苹方/微软雅黑回退。不引入在线字体下载，不因新页面改变既有字号。页面标题保持中等字重，辅助文字比正文低一级。代码、ID、结构化记录使用等宽字体，耗时使用等宽数字。

研究入口问候语保持既有展示尺度（32px），评测页面标题采用较小层级；两者职责不同，不机械统一。主体报告按阅读排版处理，LaTeX 产物的字体由模板负责，不受 Web UI 字体覆盖。

**The Quiet Copy Rule.** 不放“Research workspace”“你想研究什么？”等重复标题、产品说明段或空泛口号。操作文案说动作，辅助文案只解释真实限制。

## Elevation

主工作区是一整块圆角画布，由细边界与侧栏分离；列表使用分隔线，不把每一行做成浮起卡片。详情检查器通过侧边界区分，不加大面积阴影。

**The One Canvas Rule.** 默认平面层级；只有覆盖式菜单、弹窗和窄屏检查器使用阴影。禁止玻璃滤镜、渐变光晕或白色卡片覆盖当前深色语言。

## Components

- **工作台外壳**：桌面侧栏常规宽度 248px，现有宽屏/紧凑断点继续生效；主画布距外边缘 5px，顶部工具栏高 53px。左上角仅一枚猫标识，左下角显示用户名称。
- **导航与项目树**：图标为现有线性 SVG（常规 18–20px），不混入另一套彩色图标。项目可展开子任务；新增任务使用行内动作，不为简单操作多开弹窗。悬停动作需同时支持键盘聚焦和触屏。
- **项目与任务操作**：行尾省略号打开紧凑菜单，鼠标悬停、键盘聚焦和触屏均可访问。菜单通过 Portal 避免被侧栏滚动区域裁切；删除独立确认，默认聚焦取消，显示对象名称和删除范围，执行中禁止重复提交。删除项目仅解除分组，删除任务清理对话/报告/执行记录，不删除工作目录或报告文件。
- **Agent 头像**：输入区检索选择器与研究开始后的身份行使用用户提供的 `public/img/agent-avatar.png`，分别为24×21px和30×26px，保持透明背景、等比完整显示。此处是彩色身份图案的明确例外，导航仍用线性图标，左上角猫标识不替换。
- **侧栏开关**：关闭后顶部开关仍存在。窄于 900px 使用覆盖式侧栏和可关闭遮罩；评测页默认收起。切换评测栏目不触发研究任务。
- **输入区**：沿用研究页面的上下两层输入结构、模型/工具区与圆形发送键。不要因评测输入 JSONL 而修改研究 composer；JSONL 在独立详情面板填写。
- **列表与筛选**：标题、来源切换、搜索、状态过滤为一个紧凑工具区。列表优先名称、状态与时间；ID 为次级信息。加载、空数据、无搜索结果、接口错误分别呈现。
- **详情检查器**：评测页右侧最大 440px、常规占宽不超过 44%；窄屏覆盖内容区并保留明确关闭按钮。Escape 可关闭；打开聚焦关闭按钮，关闭返回列表。研究报告继续使用原有可伸缩文件检查器。
- **进度与轨迹**：按主 Agent / 子 Agent / Tool 父子关系展开；首层摘要可见，输入输出及原始 JSON 默认折叠。导入数据出现孤立或循环父节点时不得丢弃整条记录或无限递归。
- **按钮与状态**：主按钮浅灰填充，次按钮细描边，图标按钮圆形（32px）。焦点轮廓沿用现有 2px 可见边框；disabled 不仅靠 tooltip，关键不可用原因在相邻位置说明。
- **动效与响应式**：仅保留约 150–160ms 的 hover/显隐反馈，遵守 reduced-motion。评测列表在 1100px 以下隐藏独立时间列，760px 以下详情覆盖显示。原有研究首页的 899px 路由分支不在此轮更改。

**The Progressive Evidence Rule.** 先看任务结果、关键指标和失败原因，需要定位时再展开具体调用。不得默认把所有节点平铺成日志墙。

实现源：`frontend/nextjs/components/harness/harness.module.css`、`Icon.tsx`、`ResearchHarness.tsx`；评测扩展为 `components/evaluation/evaluation.module.css`。修改本文件中的规范时同步代码，既有研究外壳是视觉回归基准。

## Do's and Don'ts

项目/任务重命名在行尾菜单内切换为紧凑表单；任务移动使用同一菜单内目标选择，包含“独立任务”选项。保存前不改变列表，失败保留输入；名称、侧栏和搜索同步。运行中任务不能移动，分组变化不改报告内容或文件位置。

Do:

- 保留现有深色研究工作台，以真实任务、证据和产物组织空间。
- 使用相同外壳、图标、字体、圆角和渐进展开方式扩展评测。
- 对错误、缺失数据与未接入功能明确标识，操作完成后再反馈成功。
- 用真实页面截图展示功能，公开前检查用户名、文件与内容是否适合发布。

Don't:

- 不使用 SaaS landing-page clichés 或 generic AI tool marketing 式布局。
- 不加入大标题口号、三张装饰性 KPI 卡、彩色发光和无意义说明文字。
- 不破坏原有首页的响应式入口，不更改 Agent 后端行为来适应排版。
- 不把生产审查当独立评测，不把占位按钮或历史规则分数宣传为新功能完成。
