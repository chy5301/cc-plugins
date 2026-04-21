---
name: task-auto-subagent
description: "Subagent 驱动的自动批量执行任务 — 与 /task-auto 并列的独立路径，不依赖 ralph-loop 插件，
  coordinator 派遣 implementer + 两段 review subagent 串行执行，每个 phase 边界自动派 phase-reviewer。
  当用户提到 subagent 自动跑、批量但不要 ralph-loop、一次跑多个带 review 保障，
  且项目中已存在 docs/workflow/ 工作流文件时使用。"
argument-hint: "[--phase RANGE] [--task RANGE] [--all] [--skip-phase-review]"
tools: Agent, TaskCreate, TaskUpdate, TaskList, AskUserQuestion, Bash, Read, Write, Edit, Glob, Grep
---

# /task-auto-subagent — Subagent 驱动自动批量执行

> **⚠️ 不要在 plan mode 下使用此命令**。需要运行脚本、派遣 subagent、修改文件，plan mode 的只读限制会阻断这些操作。

你是 structured-workflow 批量执行流程的 **coordinator**（主代理）。你的职责是：读工作流状态 → 生成 execution plan → 串行派遣 subagent → 处理结果 → 维护 Claude Code task list 和进度总览。

## 核心架构

```
Coordinator（你）
  │
  │  启动时读 workflow.json + TASK_PLAN.md + TASK_STATUS.md + CLI 参数
  │  生成静态 execution plan → 写入 Claude Code task list
  │  做 gating 校验（跨 phase 时前 phase 必须完整）
  │  做分支处理（见"启动时分支策略"章节）
  │
  ├─ 每个 task 步骤（串行，前台同步）：
  │    1. 派 implementer         → 改代码 + 跑 build/test + 追加交接记录 + commit
  │    2. 派 spec-reviewer       → 读 diff + 交接记录，对照 TASK_PLAN 任务定义审核
  │    3. 派 code-quality-reviewer → 读 diff 审代码质量
  │    4. review 过 → 更新进度总览 ✅ + closeout commit
  │
  └─ 每个 PHASE-REVIEW 步骤（串行）：
       1. 派 phase-reviewer         → 完整版 /phase-review 步骤 1-2+4-6
       2. 有 🔴/🟡 → 派单个修正型 implementer 一次修完
       3. 修正型 implementer 走 spec-review + code-quality-review 全套
```

## 前置条件

- 项目中存在 `docs/workflow/workflow.json`（否则提示运行 `/workflow-init` 后**终止**）
- `docs/workflow/TASK_STATUS.md` 存在且有待执行任务（否则**终止**）
- 当前工作目录是 git 仓库（`git rev-parse --git-dir` 能返回）

## CLI 参数

| 参数 | 说明 |
|---|---|
| `--phase RANGE` | 阶段范围，整数索引（0-based），如 `1`、`1-3`、`0,2` |
| `--task RANGE` | 任务编号范围，如 `1-5`、`1,3,7`（指定时忽略 `--phase`） |
| `--all` | 所有阶段的待执行 task |
| `--skip-phase-review` | Planning 阶段不插入 PHASE-REVIEW 步骤（仅为逃生开关，不推荐） |

## 执行流程

### 步骤 0：前置检查

1. Glob 检查 `docs/workflow/workflow.json`，不存在 → 提示用户运行 `/workflow-init`，**终止**
2. Read `docs/workflow/TASK_STATUS.md`，如果所有任务都是 ✅/❌/⏸️（无 ⬜/🔄）→ 告知"无待执行任务"，**终止**
3. Bash `git rev-parse --git-dir`，失败 → 告知"当前目录不是 git 仓库"，**终止**

### 步骤 1：启动时分支策略

读 `workflow.json.workflowBranch` 字段（可能不存在），按以下决策：

```
workflow.json.workflowBranch 字段
│
├── 有值且 git 中该分支存在
│     ├── 当前 HEAD == workflowBranch
│     │     → 直接进入步骤 2
│     └── 当前 HEAD != workflowBranch
│           → AskUserQuestion：是否切换到 workflowBranch？（推荐：是）
│           → 选"是" → git checkout <workflowBranch> → 进入步骤 2
│           → 选"否" → 告知用户后终止（不允许在非工作分支上跑）
│
├── 有值但 git 中不存在（被删除）
│     → 告知用户将重建此分支
│     → git checkout -b <workflowBranch>（从当前 HEAD 创建）
│     → 进入步骤 2
│
└── 无值（legacy workflow 或首次跑）
      │
      ├── 当前 HEAD 是 main / master
      │     → 推断 workflowType（见"类型前缀推断规则"）
      │     → 生成分支名 <type>/<workflow.json.taskName>
      │     → git checkout -b <branch-name>
      │     → 向用户宣告创建结果（不阻塞）
      │     → 写回 workflow.json 的 workflowBranch + workflowType
      │     → 进入步骤 2
      │
      └── 当前 HEAD 是其他分支
            → AskUserQuestion：
               - A. 继续在当前分支 <current-branch>（把当前分支记为 workflowBranch）
               - B. 创建 <type>/<taskName> 子分支（coordinator 自行推断 type）
               - C. 取消
            → 按选择执行：
               - A: 写 workflowBranch = current-branch（不写 workflowType）到 workflow.json
               - B: 推断 type + 分出新分支 + 写回两字段
               - C: 终止
            → 进入步骤 2
```

#### 类型前缀推断规则

按优先级读以下来源，推断 `feature` / `fix` / `refactor` / `chore` / `docs` 之一：

1. **`workflow.json.projectContext.description`**：
   - "新增 / 添加 / 实现 / 引入 / 构建 ... 功能" → `feature`
   - "修复 / 修正 / 解决 ... bug / 问题 / 缺陷" → `fix`
   - "重构 / 架构调整 / 重写 / 迁移" → `refactor`
   - "配置 / 依赖升级 / 工具链" → `chore`
   - "文档 / README / 说明" → `docs`
2. **`TASK_ANALYSIS.md`**（description 模糊或为空时）：读"项目概述" + "风险清单"
3. **`TASK_PLAN.md`**（再退一步）：读总体策略
4. **兜底**：实在无法判断用 `feature`

#### 写回 workflow.json

用 Read + Edit（或 Write 重写）在 `workflow.json` 中添加/更新：

```json
{
  "workflowBranch": "<branch-name>",
  "workflowType": "<type>"  // 仅"创建新分支"路径写入；选 A 继续当前分支时不写
}
```

（Edit 时注意保持 JSON 格式有效，可选的做法：Read 整个 JSON，在 Python / Node 层解析不适用，直接 Edit 插入字段即可）

**本步骤完成后的状态**：当前 HEAD 已在 workflowBranch 上；workflow.json 已记录。

### 步骤 2：生成 execution plan

1. 解析 CLI 参数：`--phase` / `--task` / `--all` / `--skip-phase-review`
2. Read `workflow.json` 获取 phases + projectContext
3. Read `TASK_STATUS.md` 解析任务状态表，筛选 ⬜/🔄 任务
4. 按参数过滤目标 task 集合（`--task` 优先于 `--phase`，`--all` 忽略其他 phase 范围）
5. 按 task 编号排序
6. **Gating 校验**：本 batch 涉及的 phase 集合 = S；对 S 中最小 phase 索引 P，检查 phase < P 的所有 phase 是否已无 ⬜/🔄 task；若有任何前置 phase 未完成 → 告知用户"先完成 phase N"**并终止**
7. **插入 PHASE-REVIEW 步骤**（除非 `--skip-phase-review`）：
   - 对 execution plan 中每一个 "当前 phase 的最后一个本 batch 要执行的 task" 后面插入 `PHASE-REVIEW-{phase_index}`
   - 注意：只在该 phase 的 **所有** task 都会在本 batch 跑完时才插入（即该 phase 没有 ⬜/🔄 剩余）
8. 生成 execution plan，形如 `[{step: 1, type: "task", task_id: "01-01"}, {step: 2, ...}, {step: 3, type: "phase-review", phase: 0}, ...]`
9. **用 TaskCreate 创建 Claude Code task list**，每个 step 一条：
   - Task step: `subject = "[task-N] <任务标题>"`, `description = "执行 task N：<简述>"`
   - Phase-review step: `subject = "[phase-review-N] Phase <N>: <phase 名>"`
10. 向用户**宣告 execution plan 概览**（总 task 数 + phase-review 数 + 预计 subagent 派遣量估算）

**预计 subagent 派遣量估算**：`N_task × 3 + N_phase_review × 1 + 额外修复派遣（若有）`。宣告时按最小值估算。

### 步骤 3：按 execution plan 串行执行

按 plan 顺序处理每个 step：

- 调用 TaskUpdate 把当前 step 置 `in_progress`
- 按 step 类型执行（见步骤 4 / 步骤 5）
- 成功后调用 TaskUpdate 置 `completed`
- 进入下一 step

**所有 Agent 调用使用前台同步模式**（默认，**不使用** `run_in_background`）：coordinator 每步决策都依赖前一步的返回，无可并行的独立工作。

### 步骤 4：处理 task 类型 step

#### 4a. 捕获 BASE_SHA 并派 implementer（normal 模式）

1. Bash `git rev-parse HEAD` → 记为 `BASE_SHA`
2. Read TASK_PLAN.md 定位该 task 的完整定义
3. Read TASK_STATUS.md 的"交接记录"章节 → 取该 task 在 TASK_PLAN.md 之前的那一 task 的交接记录（如果存在）→ 提取"下一任务需关注"作为 context
4. 用 Agent tool 派遣：
   - `subagent_type`: `general-purpose`
   - `description`: `"Task N: <简短标题>"`
   - `prompt`: 用 `implementer-prompt.md` 模板（见 `${CLAUDE_PLUGIN_ROOT}/references/subagent-templates/task-auto-subagent/implementer-prompt.md`）填入：
     - `{{MODE}}` = `normal`
     - `{{TASK_FULL_TEXT}}` = 该 task 在 TASK_PLAN.md 中的完整定义
     - `{{BUILD_COMMAND}}` / `{{TEST_COMMAND}}` = workflow.json.projectContext 对应字段
     - `{{BASE_SHA}}` = 上面捕获的 SHA
     - `{{CONTEXT}}` = 上面提取的 context
     - （`{{AUDIT_FINDINGS}}` 留空或删除占位符）
5. 接收 implementer 回传

#### 4b. 根据 implementer 状态分支

参考 `${CLAUDE_PLUGIN_ROOT}/references/exception-handling.md`：

| Status | 处理 |
|---|---|
| `DONE` | 继续 4c 派 spec-reviewer |
| `DONE_WITH_CONCERNS` | 读 Concerns：correctness 问题 → 重派 implementer 修正（用 fix 模式 + concern 作为审计清单，**计入 4e 合并计数；达上限则按 plan 错 ⏸️ 跳下一**），observation → 记录到决策日志，继续 4c |
| `BLOCKED`（task 太大）| 异常 1：停止本 task，更新 TASK_PLAN.md 拆分为 XX-a/b/c（用 Edit），TASK_STATUS.md 决策日志记录；仅执行 XX-a（即回到步骤 4 派遣 XX-a 作为本 step）|
| `BLOCKED`（plan 错）| 异常 2：标记当前 task 状态为 ⏸️；追加问题到 TASK_STATUS.md "已知问题"；跳到 execution plan 的下一 step |
| `BLOCKED`（dependency missing）| 异常 3：同上处理成 ⏸️，原因写依赖关系 |
| `BLOCKED`（technical failure）| 同异常 2，记录错误摘要后 ⏸️ 跳过 |
| `NEEDS_CONTEXT` | coordinator 从 TASK_PLAN.md / 更早交接记录补充 context，**重派 1 次**；仍 `BLOCKED` → 按 plan 错处理（⏸️ 跳下一） |

每次 ⏸️ 跳下一 step 前，先调用 TaskUpdate 把当前 step 置 `completed`（带注释说明 ⏸️）。

#### 4c. 派 spec-reviewer

1. Bash `git rev-parse HEAD` → `HEAD_SHA`（implementer commit 后的 SHA）
2. 派遣：
   - `subagent_type`: `general-purpose`
   - `description`: `"Spec review: Task N"`
   - `prompt`: 用 `spec-reviewer-prompt.md` 模板填入 task 定义、implementer 报告、BASE_SHA/HEAD_SHA

3. 根据回传：
   - `SPEC_COMPLIANT` → 继续 4d
   - `SPEC_ISSUES` → 派**修正型 implementer**（`MODE=fix`，`AUDIT_FINDINGS` 填入 SPEC_ISSUES 清单）→ commit → 记录循环计数 → 再派 spec-reviewer

#### 4d. 派 code-quality-reviewer

结构同 4c：
1. `HEAD_SHA` 更新为当前
2. 用 `code-quality-reviewer-prompt.md` 模板派遣
3. 根据回传：
   - `CODE_QUALITY_APPROVED` → 继续 4e
   - `CODE_QUALITY_ISSUES` → **按严重级别区别处理**：
     - 含 Critical 或 Important 条目 → 同 4c 的修复循环（计入 4e 合并计数）
     - **仅** Minor 条目 → **不**触发修复循环；把 Minor 清单追加到交接记录的"遗留问题"，视为已通过，继续 4e

#### 4e. Review 循环上限 = 3

4c 和 4d 合并计数。**任意一种 review 的 fix 循环总计 ≥ 3 轮**仍未过 → 标记当前 task ⏸️ 阻塞，把 3 轮 review 历史**全部追加到交接记录**（作为"Review 失败记录"块），跳到下一 step。

#### 4f. Closeout：更新 TASK_STATUS.md 两张表 + commit

`TASK_STATUS.md` 里有**两张不同的表**，coordinator 在 closeout 时需要**同时更新**：

- **"任务状态"表**（`## 任务状态` 章节下，每个 task 一行，列含 `编号 / 标题 / 阶段 / 状态 / 依赖`）：把当前 task 的**状态**单元格从 ⬜/🔄 改为 ✅
- **"进度总览"表**（`## 进度总览` 章节下，聚合计数，列含 `阶段 / 总数 / 完成 / 进行中 / 待开始`）：把对应 phase 那一行的 `完成` +1、`待开始` -1（若从 🔄 切换还需 `进行中` -1），同步更新 `**合计**` 行

步骤：

1. Read `TASK_STATUS.md`
2. 用 Edit 修改**任务状态表**对应 task 行的状态格
3. 用 Edit 修改**进度总览表**对应 phase 行与合计行的计数
4. Bash commit：

```bash
git add docs/workflow/TASK_STATUS.md
git commit -m "docs(structured-workflow): task XX-YY 进度总览 ✅"
```

5. 在 Claude Code task list 中 TaskUpdate 当前 step 为 `completed`

### 步骤 5：处理 phase-review 类型 step

#### 5a. 派 phase-reviewer

1. Bash 定位 `PHASE_BASE_SHA`：
   - 读 TASK_STATUS.md 找到该 phase 第一个 task 的交接记录，取其"完成时间"
   - `git log --until="<完成时间前 1 分钟>" -1 --format=%H`
   - 若失败则 fallback 用 `workflow.json.initCommit`（同时告知 phase-reviewer 用了 fallback）
2. `PHASE_HEAD_SHA` = `git rev-parse HEAD`
3. 派遣：
   - `subagent_type`: `general-purpose`
   - `description`: `"Phase N review"`
   - `prompt`: 用 `phase-reviewer-prompt.md` 模板填入 PHASE_INDEX / PHASE_NAME / PHASE_EXIT_CRITERIA / BUILD/TEST 命令 / SHA / 该 phase 的 task 清单
4. 接收回传

#### 5b. 处理 phase-reviewer 结果

**注意**：phase-reviewer 自己会 commit TASK_PLAN.md（若有下游调整）+ TASK_STATUS.md 决策日志。coordinator 在此不重复写这些文件。

- `PHASE_PASSED`（Findings 里 🔴/🟡 都为空）→ 5d
- `PHASE_BLOCKED` 或 Findings 有 🔴/🟡 →
  1. 整理 🔴/🟡 清单（抛弃 🔵——phase-reviewer 已记录到决策日志）
  2. 派**修正型 implementer**（`MODE=fix`, `AUDIT_FINDINGS` = 🔴/🟡 清单）
  3. 派修正 implementer 后，**走完整 review 链**（spec-reviewer + code-quality-reviewer，循环规则同 4c/4d/4e）
  4. 复核通过后进入 5c

#### 5c. 修正完后重跑 phase-reviewer？

**不重跑**。修正型 implementer 已经走过 spec-review + code-quality-review 两段，审计清单本身就是 spec。再跑一次 phase-reviewer 会对"修正"本身做审计，大概率无新发现，代价不值。直接进入 5d。

#### 5d. 如果 TASK_PLAN.md 被改过：重新生成后续 execution plan

`phase-reviewer` 如果应用了"必须 / 建议"级下游调整，TASK_PLAN.md 现在可能有新增/删除/修改/重排序的 task：

1. Read 新的 TASK_PLAN.md + TASK_STATUS.md
2. 按步骤 2 的算法**重新生成** execution plan 中剩余（未 completed）部分
3. 用 TaskUpdate 调整 Claude Code task list（删除不再需要的、添加新的）
4. 保持当前 step 前的已完成步骤不动

#### 5e. Claude Code task list 置 completed

TaskUpdate 当前 PHASE-REVIEW step → `completed`。

### 步骤 6：batch 结束汇总

所有 execution plan 的 step 处理完后（无论是走完还是因 ⏸️ 累计跳出），向用户输出：

```
## /task-auto-subagent 执行汇总

- 工作分支: <workflowBranch>
- 处理 task 数: N
  - ✅ 完成: N
  - ⏸️ 阻塞（含原因清单）: N
  - ❌ 取消: 0
- 处理 phase-review 数: N
  - PASSED: N
  - BLOCKED（含修正清单）: N
- 总 commit 数: <git rev-list --count HEAD...<启动时 BASE_SHA>>

### ⏸️ 阻塞任务详情

- <task 编号>: <原因>
- ...

### 🔵 建议级下游调整（仅记录到决策日志，未应用）

- <phase N 的调整建议>
- ...

### 下一步建议

- 处理 ⏸️ 阻塞任务：运行 `/plan-adjust <任务编号>` 根据原因调整计划
- 应用 🔵 调整建议：运行 `/plan-adjust <调整描述>`
- 继续剩余 task：重跑 `/task-auto-subagent`（幂等 re-entry，自动从 ⬜/🔄 处继续）
- 工作流完成时：手动 merge / 发起 PR（本 skill 不自动做）
```

## 幂等 Re-Entry

用户中断（Ctrl+C / session crash）后**直接重跑同命令**即可继续：

- 已 ✅ 的 task 自动跳过（步骤 3 中 ⬜/🔄 过滤逻辑保证）
- ⬜/🔄 的继续
- ⏸️ 的跳过（除非用户用 `/plan-adjust` 清除了 ⏸️ 状态）
- 无 `--resume` 参数，无额外持久化文件

## 其他 skill 的互动

- 用户 Ctrl+C 后输入 `/plan-adjust` / `/workflow-abort` / `/phase-review` 等，作用于 coordinator 的主会话，**不特殊处理**
- 打断会丢失当前 subagent 的未 commit 工作（和现状一致）
- 旧 `/task-auto`（ralph-loop 驱动）：并存，本 skill 不做 mutex 检测（ralph-loop 版本将逐步弃用）

## 不做的事（强约束）

- **不** push / merge / rebase / force-reset 等影响远程或历史的 git 操作
- **不** 自动发起 PR
- **不** 用 `git worktree`（分支切换即可，worktree 对 IDE 集成不友好）
- **不** 在 Claude Code task list 之外另建持久化状态文件（`TASK_STATUS.md` 就是 SSOT）
- **不** 使用 `run_in_background` 派遣 subagent（全前台同步串行）
- **不** 修改 `TASK_PLAN.md` 除非是 phase-reviewer 返回的下游调整（且由 phase-reviewer 自己写）

## 参考文档

- `${CLAUDE_PLUGIN_ROOT}/references/subagent-templates/task-auto-subagent/implementer-prompt.md`
- `${CLAUDE_PLUGIN_ROOT}/references/subagent-templates/task-auto-subagent/spec-reviewer-prompt.md`
- `${CLAUDE_PLUGIN_ROOT}/references/subagent-templates/task-auto-subagent/code-quality-reviewer-prompt.md`
- `${CLAUDE_PLUGIN_ROOT}/references/subagent-templates/task-auto-subagent/phase-reviewer-prompt.md`
- `${CLAUDE_PLUGIN_ROOT}/references/verification-gate.md`（验证门函数五步协议）
- `${CLAUDE_PLUGIN_ROOT}/references/exception-handling.md`（异常 1-4 处理程序）
- `${CLAUDE_PLUGIN_ROOT}/references/debugging-protocol.md`（implementer 内部调试的参考协议）

## 红旗表

| 禁令 | 常见借口 | 为什么无效 |
|---|---|---|
| 不跳过启动时分支处理 | "用户肯定知道自己在哪个分支" | `main`/`master` 启动会直接污染主分支，必须程序化校验 |
| 不跳过 gating 校验 | "跨 phase 跑应该也 OK" | phase 的设计就是阶段门禁，跳过 = 废掉 phase 概念 |
| 不信任 implementer 的自我验证 | "implementer 说测试通过了" | spec-reviewer 的职责就是独立验证，不是复述 |
| 不拆分 review 失败计数 | "spec 和 quality 是两个 reviewer" | spec 失败后 fix，fix 触发 quality 失败，两者交替会无限刷次数——必须合并计数才能真正限流 |
| 不在 batch 中途做 push/PR | "反正都要提的" | PR / merge 是用户决策，本 skill 不越权 |
| 不省略类型前缀推断 | "反正就是 feature/xxx" | 自动推断 + 宣告让用户能快速发现推断错误，比"静默建分支"安全 |
