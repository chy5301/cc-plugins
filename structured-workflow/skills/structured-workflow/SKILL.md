---
name: structured-workflow
description: "大型工程任务的结构化管理方法论。提供分阶段里程碑规划、
  粒度约束任务分解、执行协议和会话交接管理。当项目中存在
  docs/workflow/workflow.json 或 docs/workflow/TASK_STATUS.md
  （或旧路径 .claude/workflow.json、docs/TASK_STATUS.md）时自动激活。
  配合 /task-init, /task-adjust, /task-exec, /task-pause,
  /task-review, /task-abort, /task-archive 使用。"
---

# 结构化工作流系统

## 系统概述

结构化工作流是一套针对**大型工程任务**的全生命周期管理方法论。它将复杂的跨多会话任务分解为可控的执行单元，通过标准化的状态文件实现会话间信息传递，确保每个独立上下文都能自主执行分配的任务。

**适用场景**：重构、迁移、大型功能开发、系统集成、性能优化、大规模缺陷修复、基础设施改造等需要跨多个会话完成的工程任务。

**不适用场景**：单次会话可完成的小型任务、纯探索性研究、一次性脚本编写。

---

## 七项核心原则

### 1. 任务粒度约束
每个任务必须满足 `workflow.json` 中配置的约束上限（默认 ≤8 文件、≤3 小时）。超出约束的任务必须拆分。这确保每个任务在单次会话的上下文窗口内可完成。

### 2. 自包含描述
每个任务的描述必须包含足够的上下文信息，使得一个全新的会话（无任何先验知识）能够理解并执行该任务。禁止使用"如前所述""参见上文"等依赖外部上下文的引用。

### 3. 六步执行协议
每个任务严格按照 6 步执行：复述确认 → 最小变更路径 → 实施 → 验证 → 状态更新（不可跳过）→ 完成汇报。步骤 5 必须在向用户汇报之前完成。

### 4. 交接记录
每个任务完成后必须追加标准化的交接记录块到状态文件。交接记录包含完成内容、修改文件、验证结果、下一任务关注点和遗留问题。

### 5. 异常处理
4 种标准异常处理程序：任务过大→拆分、计划有误→停止等待确认、前置未完成→告知依赖、范围蔓延→完成范围内工作并记录范围外需求。

### 6. 阶段退出标准
每个阶段（Phase）有明确的退出标准。阶段内所有任务完成后，必须通过 `/task-review` 验证退出标准才能进入下一阶段。

### 7. 中央状态跟踪
所有进度、决策、问题、变更都记录在中央状态文件（TASK_STATUS.md）中。状态文件是唯一的事实来源，用于跨会话信息传递。

---

## 与 Claude Code Plan Mode 的关系

`/task-init` **不要在 plan mode 下使用**。`/task-init` 需要运行初始化脚本、创建 workflow.json、写入分析报告和任务计划等多个文件，plan mode 的只读限制会阻断这些操作，导致工作流无法正常初始化。`/task-init` 自身已内置类型确认、配置确认、策略确认等用户审批点，不需要 plan mode 额外辅助。

其他命令（`/task-exec`、`/task-adjust`、`/task-review` 等）可根据需要配合 plan mode 使用。

---

## 工作流生命周期

```
Init (分析+规划) → Execute (循环) → Review (阶段性) → Archive
                        ↓
                 任意阶段 →（放弃）→ Abort
```

### Phase 0: 初始化 + 分析 + 规划 (`/task-init`)
- 创建项目配置（workflow.json）
- 自动分诊任务类型
- 执行针对性分析，输出 TASK_ANALYSIS.md
- 制定总体策略和分阶段里程碑
- 分解任务（遵循粒度约束）
- 输出 TASK_PLAN.md + TASK_STATUS.md

### Phase 1: 执行 (`/task-exec` 循环)
- 逐任务执行，每次一个
- 遇到问题时 `/task-pause` 分析
- 需要调整计划时 `/task-adjust [变更描述]`

### Phase 2: 回顾 (`/task-review`)
- 每个阶段完成后执行
- 验证退出标准
- 评估下游影响

### 异常终止 (`/task-abort`)
- 在任意阶段放弃整个工作流
- 默认仅清理状态文件，不触碰代码
- 可选 `--reset` 回滚到工作流初始 commit（需二次确认）
- 生成终止报告，记录进度快照和 commit 列表

### Phase 3: 归档 (`/task-archive`)
- 生成完成摘要
- 归档状态文件
- 清理环境

---

## 命令速查表

| 命令 | 用途 | 使用时机 |
|------|------|----------|
| `/task-init [type]` | 初始化 + 分析 + 规划 | 大型任务开始时（一步到位） |
| `/task-adjust [变更描述]` | 增量计划变更 | 执行过程中需调整计划时 |
| `/task-exec [T-XX]` | 执行单个任务 | 日常执行（主力命令） |
| `/task-pause [问题]` | 问题分析暂停 | 执行中遇到阻塞时 |
| `/task-review [Phase X]` | 阶段回顾 | 阶段任务全部完成后 |
| `/task-abort [--reset] [原因]` | 终止 + 清理 | 需要放弃整个工作流时 |
| `/task-archive` | 归档清理 | 所有阶段完成后 |

---

## workflow.json 配置说明

`workflow.json` 位于项目的 `docs/workflow/` 目录下，由 `/task-init` 自动生成。

```json
{
  "version": "1.1",
  "taskName": "<任务名称slug>",
  "primaryType": "<任务类型>",
  "secondaryTags": [],
  "taskPrefix": "<编号前缀>",
  "constraints": {
    "maxFilesPerTask": 8,
    "maxHoursPerTask": 3
  },
  "stateFiles": {
    "analysis": "docs/workflow/TASK_ANALYSIS.md",
    "plan": "docs/workflow/TASK_PLAN.md",
    "status": "docs/workflow/TASK_STATUS.md",
    "dependencyMap": "docs/workflow/DEPENDENCY_MAP.md"
  },
  "phases": [],
  "projectContext": {
    "description": "",
    "buildCommand": "",
    "testCommand": ""
  }
}
```

### 任务类型与默认前缀

| 类型 | 前缀 | 说明 |
|------|------|------|
| `feature` | F | 新功能开发 |
| `refactor` | R | 代码重构 |
| `migration` | M | 技术迁移 |
| `integration` | I | 系统集成 |
| `optimization` | O | 性能优化 |
| `bugfix` | B | 大规模缺陷修复 |
| `infrastructure` | T | 基础设施改造 |
| `generic` | G | 通用任务 |

### 约束配置

- `maxFilesPerTask`：单任务涉及的最大文件数（默认 8）
- `maxHoursPerTask`：单任务预估最大工时（默认 3 小时）

---

## 状态文件体系

所有状态文件位于 `docs/workflow/` 目录下：

| 文件 | 用途 | 生成时机 |
|------|------|----------|
| `docs/workflow/TASK_ANALYSIS.md` | 分析报告 | `/task-init` |
| `docs/workflow/TASK_PLAN.md` | 任务清单 | `/task-init`，`/task-adjust` 增量更新 |
| `docs/workflow/TASK_STATUS.md` | 进度跟踪 + 交接记录 | `/task-init`，每次 `/task-exec` 更新 |
| `docs/workflow/DEPENDENCY_MAP.md` | 依赖关系图（可选） | `/task-init` |

---

## 资源索引

本工作流系统包含以下参考文档，供各命令在执行时加载：

- `${CLAUDE_PLUGIN_ROOT}/references/task-format.md` — 任务定义格式规范
- `${CLAUDE_PLUGIN_ROOT}/references/exception-handling.md` — 异常处理与计划变更程序
- `${CLAUDE_PLUGIN_ROOT}/references/handover-template.md` — 交接记录模板
- `${CLAUDE_PLUGIN_ROOT}/references/analyzer-prompts.md` — 分类型分析 prompt
- `${CLAUDE_PLUGIN_ROOT}/references/planner-prompts.md` — 分类型规划 prompt

---

## 关键行为约束

### 执行阶段禁止事项
- 一次执行多个任务
- 范围外变更（无关重构、格式化、顺手修 bug）
- 使用"如前所述"等模糊引用
- 跳过验证步骤
- 在状态更新前向用户汇报完成

### 规划阶段约束
- 所有任务必须遵循 `${CLAUDE_PLUGIN_ROOT}/references/task-format.md` 格式
- 所有任务必须满足粒度约束
- 依赖关系必须显式声明
