---
name: task-query
description: |
  按条件筛选和查询滴答清单任务。当用户提到"查找任务""筛选任务""按优先级查""查看已完成""本周完成了什么""高优先级任务""filter tasks""search tasks""completed tasks""有哪些逾期任务""带某标签的任务"时使用。
version: 0.1.0
tools: Bash
---

# 筛选和查询滴答清单任务

使用高级条件筛选未完成或已完成的任务。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

## 筛选未完成/全部任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  [--projects <项目ID1,项目ID2>] \
  [--start-date "2026-04-01T00:00:00+0800"] \
  [--end-date "2026-04-07T23:59:59+0800"] \
  [--priority 0,1,3,5] \
  [--tags "标签1,标签2"] \
  [--status 0,2]
```

### 筛选参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--projects` | 按项目筛选，逗号分隔 | `--projects id1,id2` |
| `--start-date` | 任务 startDate >= 此值 | `--start-date "2026-04-01T00:00:00+0800"` |
| `--end-date` | 任务 startDate <= 此值 | `--end-date "2026-04-07T23:59:59+0800"` |
| `--priority` | 优先级列表。0=无, 1=低, 3=中, 5=高 | `--priority 3,5`（中和高） |
| `--tags` | 标签（AND 关系，需全部匹配） | `--tags "工作,紧急"` |
| `--status` | 状态。0=未完成, 2=已完成 | `--status 0` |

所有参数都是可选的，可自由组合。

### 常见查询场景

**查看所有高优先级任务：**
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks --priority 5
```

**查看本周某项目的任务：**
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --projects <项目ID> \
  --start-date "2026-03-31T00:00:00+0800" \
  --end-date "2026-04-06T23:59:59+0800"
```

**查看带特定标签的未完成任务：**
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks --tags "紧急" --status 0
```

### 查找逾期任务

> **重要**：`filter-tasks` 的日期参数基于任务的 `startDate` 字段，而非 `dueDate`。若需按截止日期查找逾期任务，应使用 `get-project-data` 获取项目任务列表，在结果中筛选 `dueDate` 早于当前日期且 `status` 为 0 的任务。

步骤：
1. 用 `list-projects` 获取所有项目 ID
2. 逐个调用 `get-project-data <项目ID>` 获取未完成任务
3. 在返回的 JSON 中，筛选 `dueDate` 早于今天且 `status == 0` 的任务

如果用户只需要粗略的逾期检测（任务开始日期已过），可以用：
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --end-date "昨天T23:59:59+0800" \
  --status 0
```

> 更全面的每日回顾请使用 daily-review skill。

## 查询已完成任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py query-completed \
  [--projects <项目ID1,项目ID2>] \
  [--start-date "2026-04-01T00:00:00+0800"] \
  [--end-date "2026-04-04T23:59:59+0800"]
```

筛选条件基于任务的 `completedTime`（完成时间）。

### 常见查询场景

**查看本周完成了什么：**
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py query-completed \
  --start-date "2026-03-31T00:00:00+0800" \
  --end-date "2026-04-06T23:59:59+0800"
```

**查看某项目的已完成任务：**
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py query-completed --projects <项目ID>
```

## 结果展示建议

查询结果为 JSON 数组，建议以表格形式向用户展示关键信息：
- 任务标题
- 所属项目
- 优先级（用 🔴🟡🔵⚪ 等标识）
- 截止日期
- 状态
