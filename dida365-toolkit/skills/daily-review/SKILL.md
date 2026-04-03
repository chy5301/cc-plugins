---
name: daily-review
description: |
  每日任务回顾与规划。当用户提到"今日待办""每日回顾""daily review""今天有什么任务""任务概览""task overview""what's on my plate""看看今天要做什么""有什么逾期的吗"时使用。
version: 0.1.0
tools: Bash
---

# 滴答清单每日回顾

查看今日待办、逾期任务和整体任务概览，帮助用户规划一天的工作。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

## 执行流程

### Step 1: 获取项目列表

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

记录所有项目的 ID 和名称，用于后续查询和展示。

### Step 2: 获取收集箱任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data inbox
```

收集箱中通常包含未分类的快速记录任务。

### Step 3: 筛选今日任务

使用当天日期范围筛选任务。将日期替换为实际的当前日期（如 `2026-04-04`）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --start-date "2026-04-04T00:00:00+0800" \
  --end-date "2026-04-04T23:59:59+0800" \
  --status 0
```

> **注意**：`filter-tasks` 的日期参数基于任务的 `startDate` 字段，而非 `dueDate`。

### Step 4: 查找逾期任务

`filter-tasks` 无法直接按 `dueDate` 筛选，因此需要获取各项目的任务数据，在结果中查找逾期项：

1. 对 Step 1 中获取的每个项目（以及 inbox），已在 Step 2 获取的数据中查找
2. 对其他重要项目，调用 `get-project-data <项目ID>` 获取任务列表
3. 在返回的任务 JSON 中，筛选满足以下条件的任务：
   - `dueDate` 存在且早于今天
   - `status` 为 0（未完成）

如果项目较多，可以先用 `filter-tasks` 做一个粗略筛选（基于 startDate），再补充检查：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --end-date "2026-04-03T23:59:59+0800" \
  --status 0
```

### Step 5: 筛选高优先级任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks --priority 3,5 --status 0
```

### Step 6: 汇总展示

将以上信息整理为结构化的回顾报告，建议格式：

```
## 📋 今日任务回顾

### 🔴 逾期任务（X 项）
| 任务 | 项目 | 截止日期 | 优先级 |
|------|------|---------|--------|
| ...  | ...  | ...     | ...    |

### 📌 今日待办（X 项）
| 任务 | 项目 | 优先级 |
|------|------|--------|
| ...  | ...  | ...    |

### ⭐ 高优先级（未安排日期）（X 项）
| 任务 | 项目 | 优先级 |
|------|------|--------|
| ...  | ...  | ...    |

### 📥 收集箱（X 项）
- 任务1
- 任务2
```

### Step 7: 提供建议

根据任务情况向用户提供建议：
- 如果有逾期任务，建议优先处理或调整截止日期
- 如果今日任务较多，建议关注高优先级项
- 如果收集箱有未分类任务，建议归类到对应项目（可使用 task-organize skill）
- 如果用户需要更灵活的条件筛选，引导使用 task-query skill
