---
name: task-complete
description: |
  标记滴答清单任务为已完成。当用户提到"完成任务""标记完成""做完了""打勾""勾掉""mark complete""check off task""finish task""这个任务搞定了"时使用。
version: 0.1.0
tools: Bash
---

# 完成滴答清单任务

将一个或多个任务标记为已完成。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

## 步骤

### Step 1: 确认要完成的任务

如果用户已提供任务 ID 和项目 ID，直接进入 Step 3。

如果用户只描述了任务（如"把买菜那个任务完成"），需要先查找：

**查找方式 A：在特定项目中查找**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data <项目ID>
```

**查找方式 B：在收集箱中查找**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data inbox
```

**查找方式 C：不确定在哪个项目，先列出所有项目**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

然后逐个检查相关项目的任务。

### Step 2: 向用户确认

展示找到的任务信息（标题、项目、优先级等），向用户确认是否要完成该任务。

### Step 3: 执行完成操作

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py complete-task <项目ID> <任务ID>
```

**批量完成**：如果用户要完成多个任务，逐个执行 `complete-task` 命令。

### Step 4: 确认结果

操作成功后返回 `{"status": "ok"}`。向用户确认任务已完成。

## 注意事项

- 完成操作不可逆（无法通过 API 将已完成任务恢复为未完成）
- 任务完成后，可通过 `query-completed` 命令查询已完成任务
