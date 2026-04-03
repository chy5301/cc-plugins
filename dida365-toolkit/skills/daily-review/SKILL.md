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

使用当天日期范围筛选任务（根据实际日期替换）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --start-date "今天T00:00:00+0800" \
  --end-date "今天T23:59:59+0800" \
  --status 0
```

> 将"今天"替换为实际日期，如 `2026-04-04T00:00:00+0800`。

### Step 4: 筛选逾期任务

查找截止日期早于今天且未完成的任务：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py filter-tasks \
  --end-date "昨天T23:59:59+0800" \
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
- 如果收集箱有未分类任务，建议归类到对应项目
