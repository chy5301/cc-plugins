---
name: task-status
description: |
  推进 Microsoft To Do 任务状态与优先级。当用户点名 "Microsoft To Do"
  "MS To Do""微软待办""微软 To Do"，或本次对话已在操作 Microsoft To Do，
  并要求标记完成、改为进行中、标为等待他人、标为已挂起、重新打开任务，
  或调整任务优先级时使用。改标题、描述、截止日期请用 task-crud。
  若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# task-status：推进 Microsoft To Do 任务状态与优先级

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 没有 `complete-task` 子命令

**本插件没有独立的 `complete-task` 子命令。** 标记任务完成，就是对 `update-task` 传 `status: completed`：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"status":"completed"}'
```

不要照搬滴答清单的习惯去找一个专门的"完成"子命令——这里没有，CLI 刻意没有提供这类语义化快捷命令，所有状态流转统一走 `update-task`。

## 五个状态的中文对照与适用场景

| `status` | 含义 | 什么时候用 |
| --- | --- | --- |
| `notStarted` | 未开始 | 新建默认；重新打开一个已完成任务 |
| `inProgress` | 进行中 | 已着手但未完成 |
| `completed` | 已完成 | 做完了 |
| `waitingOnOthers` | 等待他人 | 卡在别人身上，自己没法推进 |
| `deferred` | 已挂起 | 主动搁置，暂不处理 |

## 状态流转命令示例

```bash
# 标记进行中
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"status":"inProgress"}'

# 标记等待他人
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"status":"waitingOnOthers"}'

# 标记已挂起
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"status":"deferred"}'

# 重新打开一个已完成任务
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"status":"notStarted"}'
```

## 优先级 `importance`

三档字符串枚举：`low` / `normal` / `high`。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"importance":"high"}'
```

`importance` 与滴答清单的 `priority`（整数 `0`/`1`/`3`/`5`）不是同一个取值域，**不要做任何数值映射**（比如不要把 `high` 映射成 `5`、`normal` 映射成 `3` 之类）——两边字段的语义与取值个数都不对应，强行映射只会制造虚假的对应关系，误导用户。

## 批量改状态：逐个 `update-task`，没有批量端点

Graph 没有批量修改任务状态的端点。要批量推进一批任务的状态，只能对每个任务各发一次 `update-task`，没有捷径：

```bash
for taskId in T1 T2 T3; do
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task "$taskId" \
    --body '{"status":"completed"}'
done
```

上面只是示意逐个调用的形状——实际执行时请按各任务真实的 `listId`/`taskId` 分别调用，且要逐条检查每次调用的退出码，一批里某一个失败不代表其余的也失败或成功。

构造 `--body` 前建议先看 schema 确认字段：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py schema update-task
```

## 通用注意事项（所有子命令都适用）

### 退出码 `5`（`PARTIAL_FAILURE`）

退出码 `5` 表示**部分失败**：`success` 是 `false`，但 `data` 里**仍有已取到的数据**。不要把它当纯错误丢弃，也不要把残缺数据当全量用。`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。本 skill 全部通过 `update-task` 推进状态/优先级，`update-task` 不是集合端点，通常不会触发这个错误码，但它是全仓通用契约的一部分，仍需了解。

### 不要盲目重试

本 skill 调用的子命令里，明确「可重试」的只有两种情况：退出码 `6`（`AUTH_PENDING`，属于 `setup-guide` 的登录流程）、退出码 `5` 且 `metadata.retry_after_seconds` 给出了等待时长。**其余非 0 退出码（如 `2` 的 `INVALID_PARAMETER`、`3` 的「未找到」、`4` 的 `AUTH_EXPIRED`）都是终态失败**，遇到时先停下来读 `error.suggestion`，而不是换个参数再试一次。

## 边界

- 改标题、描述、截止日期、提醒，或增删改勾选子任务 → 转 `task-crud`
- 遇到退出码 `2` + `CONFIG_ERROR` 或退出码 `4` + `AUTH_EXPIRED` → 转 `setup-guide` 完成（重新）登录
