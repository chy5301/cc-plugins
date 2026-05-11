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

> 全局通用约定（`--fields` 字段掩码、`--dry-run` 预演、响应信封、退出码、`schema` 自省、日期格式归一化等）见 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`。本文档仅讲解任务子命令本身。

## 操作说明

### 创建任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py create-task \
  --project <项目ID> \
  --title "任务标题" \
  [--content "任务内容"] \
  [--desc "清单描述"] \
  [--priority 0|1|3|5] \
  [--due-date "2026-04-05"] \
  [--start-date "2026-04-04"] \
  [--time-zone "Asia/Shanghai"] \
  [--all-day] \
  [--tags "标签1,标签2"] \
  [--repeat-flag "RRULE:FREQ=DAILY;INTERVAL=1"]
```

**必需参数**：`--project`（项目 ID）和 `--title`（标题）。

**优先级说明**：0=无, 1=低, 3=中, 5=高。

**日期格式**：`--due-date` / `--start-date` 同时支持简短日期 `YYYY-MM-DD`（CLI 会自动补齐为 `T00:00:00+0800`）和完整 ISO 8601（如 `2026-04-05T14:30:00+0800`）。需要精确到时分时用后者。

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
  [--title "新标题"] \
  [--content "新内容"] \
  [--desc "清单描述"] \
  [--priority 0|1|3|5] \
  [--due-date "2026-04-05"] \
  [--start-date "2026-04-04"] \
  [--tags "标签1,标签2"] \
  [--status 0|1|2]
```

**必需参数**：`task_id`（位置参数）和 `--project`。只需传入要修改的字段。

**状态说明**：`--status` 取值 0=未完成、1=放弃、2=已完成。放弃任务用 `--status 1`；完成任务推荐用专门的 `complete-task` 子命令。

**日期格式**：同 create-task，支持 `YYYY-MM-DD` 或完整 ISO 8601。

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
