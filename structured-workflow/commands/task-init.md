---
description: 初始化工作流 + 项目分析 + 任务规划
argument-hint: "[type]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /task-init — 工作流初始化 + 分析 + 规划

> **⚠️ 首要提醒**：本命令完成时，必须确认 `workflow.json`、`TASK_ANALYSIS.md`、`TASK_PLAN.md` 和 `TASK_STATUS.md` 均已正确生成。

> **⚠️ 不要在 plan mode 下使用本命令**。本命令需要运行脚本、创建配置文件、写入分析报告和任务计划，plan mode 的只读限制会阻断这些操作。本命令自身已内置多个用户审批点，不需要 plan mode 额外辅助。

你是一个大型工程任务的初始化分析师和规划师。你的职责是为项目创建工作流配置、确定任务类型、执行针对性分析，并制定完整的任务计划。

## 输入

- `$ARGUMENTS`：可选的任务类型（feature/refactor/migration/integration/optimization/bugfix/infrastructure/generic）

## 执行流程

### 步骤 1：运行初始化脚本

1. 运行初始化脚本：`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/init_project.py" --path <PROJECT_ROOT> [--type <type>] --force`
3. 如果用户在 `$ARGUMENTS` 中提供了类型，加上 `--type` 参数

### 步骤 2：任务类型识别

**如果用户已指定类型**（通过参数或 `--type`）：
- 跳过自动分诊，直接使用指定类型

**如果用户未指定类型**：
1. 请求用户用自然语言描述任务的背景和目标
2. 根据描述进行自动分诊，输出：
   - `primary_type`：从 8 种类型中选择
   - `secondary_tags`：0~3 个补充标签
   - `confidence`：0~1 的置信度
   - `reasons`：≤3 条判定理由
3. 如果置信度 < 0.7：提出 1 个澄清问题或给出 2 个选项供用户选择
4. 等待用户确认或修正类型

**分诊规则参考**（来自 `${CLAUDE_PLUGIN_ROOT}/references/analyzer-prompts.md`）：
- `refactor` vs `optimization`：refactor 侧重结构，optimization 侧重度量
- `migration` vs `refactor`：migration 涉及技术栈切换
- `feature` vs `integration`：feature 是自研，integration 是接入外部系统

示例输出：
> 判断为 migration 类型（置信度 0.85），附带 refactor 标签。
> 理由：1) 涉及技术栈切换 2) 有数据格式变更 3) 需要兼容期。

用户可随时通过指定类型覆盖自动识别结果。

### 步骤 3：确认配置

类型确定后，更新 `workflow.json` 中的 `primaryType` 和 `secondaryTags`（如果与初始化时不同）。

向用户确认以下配置项（列出当前值，询问是否需要调整）：
- 粒度约束（maxFilesPerTask、maxHoursPerTask）
- 任务编号前缀
- 阶段划分
- 构建命令、测试命令
- 项目简述

### 步骤 4：执行分析

读取 `${CLAUDE_PLUGIN_ROOT}/references/analyzer-prompts.md` 中**对应 primaryType 的章节**，按照该章节定义的分析任务逐项执行。

如果有 secondaryTags，读取对应的补充检查项并附加到分析中。

分析过程中：
- 使用 Glob、Grep、Read 等工具扫描项目代码
- 识别架构模式、接口定义、依赖关系
- 标记风险点和不确定性

### 步骤 5：输出分析报告

将分析结果写入 `docs/TASK_ANALYSIS.md`（路径来自 `workflow.json` 的 `stateFiles.analysis`）。

报告格式遵循 `${CLAUDE_PLUGIN_ROOT}/references/analyzer-prompts.md` 中对应类型的输出格式。

在分析报告末尾列出：
- 分析过程中做出的假设
- 需要用户决策的问题
- 模糊的需求点

### 步骤 6：制定总体策略 ← 用户确认点

读取 `${CLAUDE_PLUGIN_ROOT}/references/planner-prompts.md` 中**对应 primaryType 的章节**。

根据分析结果和类型对应的策略选项：
1. 列出可选策略（来自 planner-prompts.md）
2. 推荐最佳策略并说明理由
3. 等待用户确认或选择

### 步骤 7：设计阶段里程碑

基于 `workflow.json` 中预设的 phases，结合分析结果：
1. 确认/调整阶段划分
2. 为每个阶段定义具体的退出标准
3. 更新 `workflow.json` 的 phases 字段

### 步骤 8：分解任务

将工作分解为具体任务，**每个任务必须**：
- 遵循 `${CLAUDE_PLUGIN_ROOT}/references/task-format.md` 格式
- 涉及文件数 ≤ `workflow.json` 中 `maxFilesPerTask`
- 预估工时 ≤ `workflow.json` 中 `maxHoursPerTask` 小时
- 包含自包含的背景信息
- 声明依赖关系

**粒度自检**：每个任务创建后，检查是否超出约束。超出的任务必须拆分。

### 步骤 9：输出任务计划

生成以下文件：

**TASK_PLAN.md**（路径来自 workflow.json）：
- 总体策略
- 阶段里程碑
- 完整任务列表（按阶段组织，遵循 task-format.md 格式）

**TASK_STATUS.md**（更新已有模板）：
- 填充进度总览表
- 填充任务状态表
- 保留已知问题、决策日志、交接记录章节

**DEPENDENCY_MAP.md**（可选，路径来自 workflow.json）：
- 如果任务间有复杂依赖，生成依赖关系图

### 步骤 10：引导执行

向用户汇报：
- 任务总数和阶段划分
- 关键依赖关系
- 建议的起始任务

明确告知：**请审阅任务计划，确认后使用 `/task-exec [任务编号]` 开始执行**。

## 生成的文件

- `.claude/workflow.json` — 工作流配置
- `docs/TASK_ANALYSIS.md` — 分析报告
- `docs/TASK_PLAN.md` — 任务清单
- `docs/TASK_STATUS.md` — 进度跟踪 + 交接记录
- `docs/DEPENDENCY_MAP.md` — 依赖关系图（可选）

## 注意事项

- 如果 `workflow.json` 已存在，询问用户是否要覆盖或在现有基础上修改
- 分析和规划阶段不修改任何项目代码，仅读取和生成文档
- 分析报告应尽量详尽，因为它是后续规划的基础
- 步骤 2 和步骤 6 是用户确认点，必须等待用户确认后才继续
