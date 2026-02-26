# structured-workflow

大型工程任务的结构化管理工作流 Plugin。

提供**分析 → 规划 → 执行 → 回顾 → 归档**全生命周期管理，适用于重构、迁移、大型功能开发、系统集成、性能优化等跨多会话的工程任务。

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

### 1. 初始化工作流

```
/task-init
```

Claude 会引导你描述任务，自动识别任务类型，执行针对性分析，制定策略、划分阶段、分解任务。一次性生成 TASK_ANALYSIS.md、TASK_PLAN.md 和 TASK_STATUS.md。

你也可以直接指定类型：

```
/task-init refactor
```

### 2. 逐任务执行

```
/task-exec R-01
```

按 6 步协议执行单个任务：复述确认 → 最小变更路径 → 实施 → 验证 → 状态更新 → 完成汇报。

### 3. 遇到问题时暂停分析

```
/task-pause 编译报错，头文件循环引用
```

仅分析问题、评估影响、提出方案，不修改代码。

### 4. 阶段回顾

```
/task-review Phase 0
```

汇总检查、退出标准验证、构建验证、下游影响评估。

### 5. 执行过程中调整计划

```
/task-adjust 在R-05后面加一个缓存层任务
/task-adjust 删除R-08
/task-adjust 调整R-06和R-07的执行顺序
```

### 6. 需要放弃时终止

```
/task-abort 方案不可行，需要换技术路线
```

终止当前工作流，清理状态文件。默认不触碰代码，仅生成终止报告并列出建议的 git 命令。

如果确信需要回滚全部代码：

```
/task-abort --reset 方案不可行
```

### 7. 全部完成后归档

```
/task-archive
```

生成完成摘要，归档状态文件，清理环境。

## 命令速查

| 命令 | 用途 | 使用时机 |
|------|------|----------|
| `/task-init [type]` | 初始化 + 分析 + 规划 | 大型任务开始时 |
| `/task-adjust [变更]` | 增量计划变更 | 需调整计划时 |
| `/task-exec [T-XX]` | 执行单个任务 | 日常执行 |
| `/task-pause [问题]` | 问题分析 | 遇到阻塞时 |
| `/task-review [Phase]` | 阶段回顾 | 阶段完成后 |
| `/task-abort [--reset] [原因]` | 终止 + 清理 | 需要放弃时 |
| `/task-archive` | 归档清理 | 全部完成后 |

## 支持的任务类型

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

## 核心原则

1. **任务粒度约束**：每个任务 ≤8 文件、≤3 小时（可配置）
2. **自包含描述**：每个任务独立可理解，不依赖外部上下文
3. **六步执行协议**：复述 → 路径 → 实施 → 验证 → 状态更新 → 汇报
4. **交接记录**：每个任务完成后追加标准化交接记录
5. **异常处理**：4 种标准程序（过大/有误/前置未完成/范围蔓延）
6. **阶段退出标准**：每阶段有明确的质量关卡
7. **中央状态跟踪**：TASK_STATUS.md 是唯一的事实来源

## 文件结构

```
structured-workflow/
├── .claude-plugin/
│   └── plugin.json              # Plugin 元数据
├── README.md                    # 本文件
├── commands/                    # 斜杠命令
│   ├── task-init.md
│   ├── task-adjust.md
│   ├── task-exec.md
│   ├── task-pause.md
│   ├── task-review.md
│   ├── task-abort.md
│   └── task-archive.md
├── skills/
│   └── structured-workflow/
│       └── SKILL.md             # 核心方法论
├── scripts/
│   ├── init_project.py          # 项目初始化
│   ├── abort_workflow.py        # 工作流终止清理
│   └── archive_workflow.py      # 工作流归档
└── references/
    ├── task-format.md           # 任务格式规范
    ├── exception-handling.md    # 异常处理程序
    ├── handover-template.md     # 交接记录模板
    ├── analyzer-prompts.md      # 分类型分析 prompt
    └── planner-prompts.md       # 分类型规划 prompt
```

## 项目级配置

初始化后，项目中会生成 `docs/workflow/workflow.json`，可自定义：

```json
{
  "version": "1.1",
  "taskName": "extract-auth-module",
  "primaryType": "refactor",
  "taskPrefix": "R",
  "constraints": {
    "maxFilesPerTask": 8,
    "maxHoursPerTask": 3
  },
  "phases": [...],
  "projectContext": {
    "buildCommand": "cmake --build build",
    "testCommand": ""
  }
}
```

## 工作流全景

```
/task-init     →  分析 + 规划 (TASK_ANALYSIS.md + TASK_PLAN.md + TASK_STATUS.md)
                      ↓ 用户审阅
/task-exec     →  逐任务执行 (循环)
  /task-pause  →    遇到问题时分析
  /task-adjust   →    需要时调整计划
  /task-abort  →    需要放弃时终止
                      ↓ 阶段完成
/task-review   →  阶段回顾
                      ↓ 所有阶段完成
/task-archive  →  归档清理
```
