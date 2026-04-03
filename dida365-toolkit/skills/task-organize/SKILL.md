---
name: task-organize
description: |
  在滴答清单项目间移动和整理任务。当用户提到"移动任务""把任务从...移到...""整理任务""归类""move task""reorganize tasks""任务搬到另一个清单"时使用。
version: 0.1.0
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
  --from <源项目ID> \
  --to <目标项目ID> \
  --tasks <任务ID1,任务ID2,...>
```

支持一次移动多个任务，任务 ID 用逗号分隔。

### Step 4: 确认结果

成功后返回包含任务 ID 和新 etag 的数组。向用户确认移动完成。

## 注意事项

- 移动任务不会改变任务的其他属性（标题、优先级、日期等）
- 一次 `move-tasks` 调用中，所有任务必须来自同一个源项目
- 如果需要从多个源项目移动，分多次调用
