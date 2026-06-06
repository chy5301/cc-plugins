---
name: task-organize
description: |
  在滴答清单项目间移动和整理任务。当用户提到"移动任务""把任务从...移到...""整理任务""归类""转移""换个清单""move task""reorganize tasks""任务搬到另一个清单"时使用。
version: 0.2.0
tools: Bash
---

# 移动和整理滴答清单任务

在不同项目（清单）之间移动任务，支持批量操作。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

> 全局通用约定（`--fields`、`--dry-run`、响应信封、退出码、`schema` 自省等）见 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`。字段经 `--body` JSON 传入，完整字段用 `schema <操作>` 查询。

## 步骤

### Step 1: 了解用户意图

确认以下信息：
- 要移动哪些任务？
- 从哪个项目移出？
- 移到哪个项目？

### Step 2: 查找项目和任务 ID

**列出所有项目：**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

**查看源项目中的任务：**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data <源项目ID>
```

从返回的任务列表中找到要移动的任务 ID。

### Step 3: 执行移动

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py move-tasks \
  --body '[{"fromProjectId":"<源项目ID>","toProjectId":"<目标项目ID>","taskId":"<任务ID1>"},{"fromProjectId":"<源项目ID>","toProjectId":"<目标项目ID>","taskId":"<任务ID2>"}]'
```

每个任务对应数组中的一个对象，支持一次移动多个任务。

### Step 3.5: 预演（推荐）

移动操作不可逆，建议先用 `--dry-run` 预演确认：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py move-tasks \
  --body '[{"fromProjectId":"<源项目ID>","toProjectId":"<目标项目ID>","taskId":"<任务ID>"}]' \
  --dry-run
```

预演返回 `data.would_call`（API 路径）和 `data.body`（请求体），确认无误后再去掉 `--dry-run` 正式执行。退出码 10 表示预演成功。

### Step 5: 确认结果

成功后返回包含任务 ID 和新 etag 的数组。向用户确认移动完成。

## 注意事项

- 移动任务不会改变任务的其他属性（标题、优先级、日期等）
- 一次 `move-tasks` 调用中，所有任务必须来自同一个源项目
- 如果需要从多个源项目移动，分多次调用
