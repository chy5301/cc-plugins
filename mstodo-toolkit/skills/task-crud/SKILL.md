---
name: task-crud
description: |
  创建、查看、更新、删除 Microsoft To Do 任务及其子任务。当用户点名
  "Microsoft To Do""MS To Do""微软待办""微软 To Do"，或本次对话已在操作
  Microsoft To Do，并要求新建任务、查看任务详情、修改标题/描述/截止日期/提醒、
  删除任务，或增删改勾选子任务时使用。改任务状态或优先级请用 task-status；
  在清单间移动任务请用 task-organize。若用户还装有其他待办工具、本轮未指明
  平台且上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# task-crud：创建、查看、更新、删除 Microsoft To Do 任务及子任务

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 构造 `--body` 前先查 schema

构造 `create-task` / `update-task` / `create-checklist-item` / `update-checklist-item` 的 `--body` 之前，先跑对应的 `schema` 查询，了解字段类型、必填项、枚举合法值，避免凭记忆瞎猜字段名：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py schema create-task
```

## 任务 CRUD 四条命令

### 创建任务 `create-task`

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"写季度报告","dueDateTime":"2026-04-05"}'
```

### 查看任务详情 `get-task`

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-task --list <listId> --task <taskId>
```

### 更新任务 `update-task`

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"title":"写季度报告（修订版）"}'
```

改 `status`（完成/进行中/挂起等）或 `importance`（优先级）不在本 skill 范围，见下方「边界」一节转 `task-status`。

### 删除任务 `delete-task`（不可逆，先 `--dry-run`）

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-task --list <listId> --task <taskId> --dry-run
```

`delete-task` 在 API 层面没有撤销接口，执行前务必先 `--dry-run` 确认目标路径无误。`--dry-run` 只输出将要发起的调用、不真正执行，退出码固定为 `10`（`EXIT_DRY_RUN`），表示「预演成功」而不是错误。确认无误后去掉 `--dry-run` 再真正执行：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-task --list <listId> --task <taskId>
```

## 子任务（checklist item）五个子命令

```bash
# 列出子任务
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-checklist-items --list <listId> --task <taskId>

# 查看单个子任务
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-checklist-item --list <listId> --task <taskId> --item <itemId>

# 创建子任务
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-checklist-item --list <listId> --task <taskId> \
  --body '{"displayName":"确认收件人名单"}'

# 更新子任务（含勾选）
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-checklist-item --list <listId> --task <taskId> --item <itemId> \
  --body '{"isChecked":true}'

# 删除子任务（不可逆，同样建议先 --dry-run）
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-checklist-item --list <listId> --task <taskId> --item <itemId> --dry-run
```

## 一次请求建带子任务的任务（Task 0 探针 P5 实测结论）

Task 0 探针实测：`create-task` 的请求体里内联 `checklistItems` 数组，Graph 返回 `201`，且实际落地了 2 个子项——不是被静默忽略。所以建一个带子任务的任务，**一次 `create-task` 请求就够**，不必先建任务再逐个 `create-checklist-item`（`1 + N` 次请求）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"筹备发布会","checklistItems":[{"displayName":"确认场地"},{"displayName":"发邀请函"}]}'
```

注意：`checklistItems` 这个内联字段只有 `create-task` 支持；`update-task` 不支持通过它改子任务，改已有子任务要走 `update-checklist-item`。

## 日期三种写法

`dueDateTime` / `reminderDateTime` / `startDateTime` 支持三种写法：

1. `"YYYY-MM-DD"`（自动补 `T00:00:00`）
2. `"YYYY-MM-DDTHH:MM:SS"`（自动补 `MSTODO_TIMEZONE` 指定的时区）
3. 完整对象 `{"dateTime": "...", "timeZone": "..."}`

`timeZone` 同时接受 Windows 时区名（如 `China Standard Time`）与 IANA/Olson 时区名（如 `Asia/Shanghai`）——两种写法 Task 0 探针实测均返回 `201`，都可以放心使用，不必纠结用哪一种命名。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"提醒开会","dueDateTime":"2026-04-05"}'

uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"提醒开会","dueDateTime":"2026-04-05T09:00:00"}'

uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"提醒开会","dueDateTime":{"dateTime":"2026-04-05T09:00:00","timeZone":"Asia/Shanghai"}}'
```

## 读回时日期被归一化为 UTC，这不是写入失败（Task 0 探针 P6 实测结论）

Task 0 探针提交了同一时刻的两种时区写法：

- `{"dateTime": "2026-12-31T09:00:00", "timeZone": "Asia/Shanghai"}`
- `{"dateTime": "2026-12-31T09:00:00", "timeZone": "China Standard Time"}`

两次都返回 `201`，但读回时 Graph 把两者统一归一化为：

```json
{"dateTime": "2026-12-30T16:00:00.0000000", "timeZone": "UTC"}
```

换算本身是对的（`+08:00` 的 `12-31 09:00` 就是 UTC 的 `12-30 16:00`），但**写入时提交的时区不会被原样保留**。

- 写完任务后读回确认，看到的 `dateTime`/`timeZone` 会与提交值**字面不同**，这是正常现象，**不要据此判断写入失败**。
- **更不要去"修正"这个值再提交一次**——每次"修正"提交后，读回依然会被再次归一化为 UTC，只会陷入无意义的循环。
- 任何"读回比对"都必须先把提交值和回显值换算到同一时区（或同一时刻的绝对值）再比较，**不能直接做字符串比较**——`"2026-12-31T09:00:00"` 和 `"2026-12-30T16:00:00.0000000"` 这两个字符串永远不相等，即使它们代表同一时刻。

## `body` 同名陷阱

`--body` 是整条命令的请求体 JSON（外层容器）；Graph 任务对象内部还有一个同名的 `body` 字段，专指任务描述（`itemBody`），是 `--body` JSON 里的一个 key，两者不是一回事。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <listId> \
  --body '{"title":"写周报","body":"覆盖三个里程碑"}'
```

这里外层 `--body` 选项的取值是整个 `{"title":...,"body":...}` JSON 对象；对象里的 `"body"` key 才是任务描述字段——传字符串会被 CLI 自动展开为 `{"content": "...", "contentType": "text"}`，传对象则原样透传。读这条命令时不要把「命令行选项 `--body`」和「JSON 里的字段 `body`」混为一谈。

## 通用注意事项（所有子命令都适用）

### 退出码 `5`（`PARTIAL_FAILURE`）

退出码 `5` 表示**部分失败**：`success` 是 `false`，但 `data` 里**仍有已取到的数据**。不要把它当纯错误丢弃，也不要把残缺数据当全量用。`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。本 skill 里 `list-checklist-items` 是集合端点，分页被 `--max-pages` 截断时会触发这个错误码；建/查/改/删单个任务或子任务本身不是集合端点，一般不会触发，但仍需了解这条约定，因为它是全仓通用契约的一部分。

### 不要盲目重试

本 skill 调用的子命令里，明确「可重试」的只有两种情况：退出码 `6`（`AUTH_PENDING`，属于 `setup-guide` 的登录流程）、退出码 `5` 且 `metadata.retry_after_seconds` 给出了等待时长。**其余非 0 退出码（如 `2` 的 `INVALID_PARAMETER`、`3` 的「未找到」、`4` 的 `AUTH_EXPIRED`）都是终态失败**，遇到时先停下来读 `error.suggestion`，而不是换个参数再试一次。

## 边界

- 改任务状态（`notStarted`/`inProgress`/`completed`/`waitingOnOthers`/`deferred`）或 `importance` 优先级 → 转 `task-status`
- 在清单之间移动任务 → 转 `task-organize`
- 遇到退出码 `2` + `CONFIG_ERROR` 或退出码 `4` + `AUTH_EXPIRED` → 转 `setup-guide` 完成（重新）登录
