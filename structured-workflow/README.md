# structured-workflow

大型工程任务的结构化管理工作流 Plugin。

提供**探索 → 分析 → 规划 → 执行 → 回顾 → 归档**全生命周期管理，适用于重构、迁移、大型功能开发、系统集成、性能优化等跨多会话的工程任务。

## 适用场景

- 代码重构（跨多模块的架构调整）
- 技术迁移（框架升级、平台切换）
- 大型功能开发（需要拆分为多个子任务）
- 系统集成（接入外部系统或服务）
- 性能优化（系统性瓶颈定位和优化）
- 大规模缺陷修复
- 基础设施改造（CI/CD、部署架构）

**不适用**：单次会话可完成的小型任务。

## 安装

参见 [仓库 README](../README.md#安装)。

## 快速开始

### 0. 需求不清时先探索

```
/workflow-brainstorm
```

通过逐问澄清帮你理清需求、对比方案、记录决策。产出结构化决策文档，可直接移交给后续 skill。

### 1. 初始化工作流

```
/workflow-init
```

Claude 会通过子代理并行探索代码库，执行系统性分析，设计多个架构方案供你选择，制定完整的阶段和任务计划。一次性生成 TASK_ANALYSIS.md、TASK_PLAN.md 和 TASK_STATUS.md。

如果之前做了 brainstorm，init 会自动读取决策文档作为输入。

### 2. 逐任务执行

```
/task-exec 01
```

按 6 步协议执行单个任务：复述确认 → 最小变更路径 → 实施 → 验证 → 状态更新 → 完成汇报。

### 3. 自动批量执行

```
/task-auto
```

基于 ralph-loop 插件自动循环执行多个任务。支持指定阶段、任务范围和最大迭代次数。

### 4. 阶段回顾

```
/phase-review Phase 0
```

汇总检查、变更审计（置信度过滤）、退出标准验证、构建验证、下游影响评估。

### 5. 执行过程中调整计划

```
/plan-adjust 在05后面加一个缓存层任务
/plan-adjust 删除08
/plan-adjust 调整06和07的执行顺序
```

### 6. 需要放弃时终止

```
/workflow-abort 方案不可行，需要换技术路线
```

终止当前工作流，清理状态文件。默认不触碰代码，仅生成终止报告并列出建议的 git 命令。

如果确信需要回滚全部代码：

```
/workflow-abort --reset 方案不可行
```

### 7. 全部完成后归档

```
/workflow-archive
```

生成完成摘要，归档状态文件，清理环境。

## 命令速查

| 命令 | 用途 | 使用时机 |
|------|------|----------|
| `/workflow-brainstorm` | 需求探索与方案决策 | 需求不清时 |
| `/workflow-init` | 初始化 + 分析 + 规划 | 大型任务开始时 |
| `/plan-adjust [变更]` | 增量计划变更 | 需调整计划时 |
| `/task-exec [XX]` | 执行单个任务 | 日常执行 |
| `/task-auto [--max N] [--all]` | 自动批量执行 | 连续自动执行多个任务时（需 ralph-loop 插件） |
| `/phase-review [Phase]` | 阶段回顾 | 阶段完成后 |
| `/workflow-abort [--reset] [原因]` | 终止 + 清理 | 需要放弃时 |
| `/workflow-archive` | 归档清理 | 全部完成后 |

## 设计原则

### 核心原则

1. **任务粒度**：上下文自包含、单会话可完成、可独立验证、可独立回滚
2. **自包含描述**：每个任务独立可理解，不依赖外部上下文
3. **六步执行协议**：复述 → 路径 → 实施 → 验证 → 状态更新 → 汇报
4. **交接记录**：每个任务完成后追加标准化交接记录
5. **异常处理**：5 种标准程序（过大/有误/前置未完成/范围蔓延/技术故障）
6. **阶段退出标准**：每阶段有明确的质量关卡
7. **中央状态跟踪**：TASK_STATUS.md 是唯一的事实来源

### 工作流生命周期

```
Brainstorm (可选) → Init (分析+规划) → Execute (循环) → Review (阶段性) → Archive
                                              ↓
                                       任意阶段 →（放弃）→ Abort
```

### workflow.json 配置

初始化后生成 `docs/workflow/workflow.json`：

```json
{
  "version": "2.0",
  "taskName": "extract-auth-module",
  "stateFiles": {
    "analysis": "docs/workflow/TASK_ANALYSIS.md",
    "plan": "docs/workflow/TASK_PLAN.md",
    "status": "docs/workflow/TASK_STATUS.md",
    "dependencyMap": "docs/workflow/DEPENDENCY_MAP.md"
  },
  "phases": [...],
  "projectContext": {
    "description": "",
    "buildCommand": "cmake --build build",
    "testCommand": ""
  }
}
```

### 状态文件体系

所有状态文件位于 `docs/workflow/` 目录：

| 文件 | 用途 | 生成时机 |
|------|------|----------|
| `workflow.json` | 工作流配置 | `/workflow-init` |
| `TASK_ANALYSIS.md` | 分析报告 | `/workflow-init` |
| `TASK_PLAN.md` | 任务清单 | `/workflow-init`，`/plan-adjust` 增量更新 |
| `TASK_STATUS.md` | 进度跟踪 + 交接记录 | `/workflow-init`，每次 `/task-exec` 更新 |
| `DEPENDENCY_MAP.md` | 依赖关系图（可选） | `/workflow-init` |
| `brainstorm/` | 需求探索决策文档 | `/workflow-brainstorm` |

## 文件结构

```
structured-workflow/
├── .claude-plugin/
│   └── plugin.json              # Plugin 元数据
├── README.md                    # 本文件
├── skills/
│   ├── workflow-brainstorm/SKILL.md  # 需求探索与方案决策
│   ├── workflow-init/SKILL.md   # 初始化 + 分析 + 规划
│   ├── task-exec/SKILL.md       # 执行单个任务
│   ├── plan-adjust/SKILL.md     # 增量计划变更
│   ├── phase-review/SKILL.md    # 阶段回顾
│   ├── task-auto/SKILL.md       # 自动批量执行
│   ├── workflow-abort/SKILL.md  # 终止工作流（仅手动调用）
│   └── workflow-archive/SKILL.md # 归档清理（仅手动调用）
├── scripts/
│   ├── init_project.py          # 项目初始化
│   ├── setup_autoexec.py        # 自动执行设置
│   ├── abort_workflow.py        # 工作流终止清理
│   └── archive_workflow.py      # 工作流归档
└── references/
    ├── task-format.md           # 任务格式规范 + 粒度原则
    ├── exception-handling.md    # 异常处理程序
    ├── verification-gate.md     # 验证门函数协议
    ├── debugging-protocol.md    # 四阶段调试协议
    └── subagent-templates/      # 子代理 prompt 模板
        ├── explorer-prompt.md
        └── architect-prompt.md
```

## 工作流全景

```
/workflow-brainstorm  →  需求探索 + 方案决策 (docs/workflow/brainstorm/*.md)
                           ↓ 可选，需求清晰可跳过
/workflow-init        →  子代理探索 + 分析 + 多方案设计 + 规划
                           ↓ 用户审阅
/task-exec            →  逐任务执行 (循环)
  /task-auto          →    自动批量执行（需 ralph-loop 插件）
  /plan-adjust        →    需要时调整计划
  /workflow-abort     →    需要放弃时终止
                           ↓ 阶段完成
/phase-review         →  阶段回顾（置信度过滤审计 + 退出标准验证）
                           ↓ 所有阶段完成
/workflow-archive     →  归档清理
```
