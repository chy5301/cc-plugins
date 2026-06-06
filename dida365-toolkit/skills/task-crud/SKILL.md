---
name: task-crud
description: |
  创建、查看、更新、删除、放弃滴答清单任务。当用户提到"新建任务""添加待办""修改任务""删除任务""编辑任务标题""放弃任务""不做了""取消任务""create task""update task""delete task""abandon task""add todo""在滴答清单里加一个..."时使用。
version: 0.2.0
tools: Bash
---

# 滴答清单任务管理

对滴答清单中的任务进行增删改查操作。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置（未设置时引导用户先完成配置，触发 setup-guide skill）

## CLI 工具路径

所有命令通过以下方式调用：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

> 全局通用约定（`--fields`、`--dry-run`、响应信封、退出码、`schema` 自省等）见 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`。字段经 `--body` JSON 传入，完整字段用 `schema <操作>` 查询。

## 操作说明

### 创建任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py create-task \
  --project <项目ID> \
  --body '{"title":"任务标题","content":"任务内容","priority":3,"dueDate":"2026-04-05T00:00:00+0800","isAllDay":true,"reminders":["TRIGGER:PT0S"]}'
```

**必需**：`--project`（定位，注入 body.projectId）与 body 中的 `title`。
**字段定义**：`uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py schema create-task`。
**优先级**：0=无 1=低 3=中 5=高。
**提醒 reminders**：ISO8601 触发器数组，`TRIGGER:PT0S`=准时、`TRIGGER:P0DT9H0M0S`=提前 9 小时、`TRIGGER:P1D`=提前 1 天。

> 如果用户未提供项目 ID，先执行 `list-projects` 获取项目列表，让用户选择目标项目。

### 查看任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-task <项目ID> <任务ID>
```

> 如果用户只知道项目但不知道任务 ID，先用 `get-project-data` 列出项目下所有任务。

### 更新任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py update-task <任务ID> \
  --project <项目ID> \
  --body '{"title":"新标题","priority":5}'
```

**必需**：位置参数 `task_id`、`--project`。只在 `--body` 中传要修改的字段。
**字段定义**：`schema update-task`。

**状态说明**：`status` 取值 0=未完成、1=放弃、2=已完成。

**放弃任务**：
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py update-task <任务ID> \
  --project <项目ID> \
  --body '{"status":1}'
```

**标记完成**：推荐使用 task-complete skill 的 `complete-task` 子命令（专用 API 端点，非 status 更新）。

**日期格式**：`--body` 中的日期字段同时支持简短 `YYYY-MM-DD`（CLI 自动补 `T00:00:00+0800`）和完整 ISO 8601（如 `2026-04-05T14:30:00+0800`）。

### 删除任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py delete-task <项目ID> <任务ID>
```

> **注意**：删除操作不可逆，执行前应向用户确认。建议先附加 `--dry-run` 验证将要删除的资源路径（退出码 10），确认无误后再正式执行。

## 辅助操作

### 查找项目 ID

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

### 查找任务 ID

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data <项目ID>
```

可传 `inbox` 作为项目 ID 获取收集箱中的任务。

## 工作流建议

1. 如果用户提供了明确的任务信息（标题、项目），直接创建
2. 如果信息不完整，询问用户补充（至少需要标题和目标项目）
3. 创建/更新成功后，向用户展示返回的任务详情作为确认
4. 对于删除操作，先展示任务信息再确认
