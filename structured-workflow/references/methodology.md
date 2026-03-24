# 结构化工作流方法论

本文档是所有工作流 skill 的共享参考，定义核心原则和行为约束。各 skill 在执行时按需加载本文档。

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
每个阶段（Phase）有明确的退出标准。阶段内所有任务完成后，必须通过 `/phase-review` 验证退出标准才能进入下一阶段。

### 7. 中央状态跟踪
所有进度、决策、问题、变更都记录在中央状态文件（TASK_STATUS.md）中。状态文件是唯一的事实来源，用于跨会话信息传递。

---

## 工作流生命周期

```
Init (分析+规划) → Execute (循环) → Review (阶段性) → Archive
                        ↓
                 任意阶段 →（放弃）→ Abort
```

| 阶段 | skill | 说明 |
|------|-------|------|
| Phase 0 | `/workflow-init` | 初始化 + 分析 + 规划 |
| Phase 1+ | `/task-exec` | 逐任务执行（主力命令） |
| 计划变更 | `/plan-adjust` | 增量调整计划 |
| 批量执行 | `/task-auto` | 自动连续执行（需 ralph-loop） |
| 阶段回顾 | `/phase-review` | 退出标准验证 |
| 异常终止 | `/workflow-abort` | 中止并清理 |
| 完成归档 | `/workflow-archive` | 生成摘要并归档 |

---

## workflow.json 配置说明

`workflow.json` 位于项目的 `docs/workflow/` 目录下，由 `/workflow-init` 自动生成。

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
| `TASK_ANALYSIS.md` | 分析报告 | `/workflow-init` |
| `TASK_PLAN.md` | 任务清单 | `/workflow-init`，`/plan-adjust` 增量更新 |
| `TASK_STATUS.md` | 进度跟踪 + 交接记录 | `/workflow-init`，每次 `/task-exec` 更新 |
| `DEPENDENCY_MAP.md` | 依赖关系图（可选） | `/workflow-init` |

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

---

## 参考文档索引

- `${CLAUDE_PLUGIN_ROOT}/references/task-format.md` — 任务定义格式规范
- `${CLAUDE_PLUGIN_ROOT}/references/exception-handling.md` — 异常处理与计划变更程序
- `${CLAUDE_PLUGIN_ROOT}/references/handover-template.md` — 交接记录模板
- `${CLAUDE_PLUGIN_ROOT}/references/analyzer-prompts.md` — 分类型分析 prompt
- `${CLAUDE_PLUGIN_ROOT}/references/planner-prompts.md` — 分类型规划 prompt
