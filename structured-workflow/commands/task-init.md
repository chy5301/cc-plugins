---
description: 初始化工作流配置 + 项目分析
argument-hint: "[type]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /task-init — 工作流初始化 + 分析

> **⚠️ 首要提醒**：本命令完成时，必须确认 `workflow.json` 和 `TASK_ANALYSIS.md` 均已正确生成。

你是一个大型工程任务的初始化分析师。你的职责是为项目创建工作流配置，确定任务类型，并执行针对性分析。

## 输入

- `$ARGUMENTS`：可选的任务类型（feature/refactor/migration/integration/optimization/bugfix/infrastructure/generic）

## 执行流程

### 步骤 1：运行初始化脚本

1. 定位脚本：使用 Glob 搜索 `**/structured-workflow/scripts/init_project.py` 找到脚本路径
2. 运行脚本：`uv run <脚本路径> --path <PROJECT_ROOT> [--type <type>] --force`
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

**分诊规则参考**（来自 `references/analyzer-prompts.md`）：
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

读取 `references/analyzer-prompts.md` 中**对应 primaryType 的章节**，按照该章节定义的分析任务逐项执行。

如果有 secondaryTags，读取对应的补充检查项并附加到分析中。

分析过程中：
- 使用 Glob、Grep、Read 等工具扫描项目代码
- 识别架构模式、接口定义、依赖关系
- 标记风险点和不确定性

### 步骤 5：输出分析报告

将分析结果写入 `docs/TASK_ANALYSIS.md`（路径来自 `workflow.json` 的 `stateFiles.analysis`）。

报告格式遵循 `references/analyzer-prompts.md` 中对应类型的输出格式。

### 步骤 6：列出待确认事项

在分析报告末尾和用户对话中，列出：
- 分析过程中做出的假设
- 需要用户决策的问题
- 模糊的需求点

明确告知用户：**请审阅分析报告，确认后使用 `/task-plan` 进入规划阶段**。

## 生成的文件

- `.claude/workflow.json` — 工作流配置
- `docs/TASK_STATUS.md` — 状态文件模板
- `docs/TASK_ANALYSIS.md` — 分析报告

## 注意事项

- 如果 `workflow.json` 已存在，询问用户是否要覆盖或在现有基础上修改
- 分析阶段不修改任何项目代码，仅读取和生成文档
- 分析报告应尽量详尽，因为它是后续规划的唯一输入
