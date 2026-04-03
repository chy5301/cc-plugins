---
name: project-management
description: |
  管理滴答清单项目（清单）。当用户提到"创建项目""新建清单""查看所有项目""修改项目""删除项目""list projects""create project""project management""我有哪些清单""看看我的项目"时使用。
version: 0.1.0
tools: Bash
---

# 滴答清单项目管理

对滴答清单中的项目（清单）进行增删改查操作。

## 前置条件

- 环境变量 `DIDA365_API_TOKEN` 已设置

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

## 操作说明

### 查看所有项目

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

返回所有项目的列表，包含 ID、名称、颜色、视图模式等信息。

### 查看单个项目

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project <项目ID>
```

### 查看项目及其任务

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py get-project-data <项目ID>
```

返回项目信息、未完成任务列表和看板列信息。可传 `inbox` 作为项目 ID 获取收集箱数据。

### 创建项目

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py create-project \
  --name "项目名称" \
  [--color "#F18181"] \
  [--view-mode list|kanban|timeline] \
  [--kind TASK|NOTE] \
  [--sort-order 0]
```

**必需参数**：`--name`。

**视图模式说明**：
- `list`：列表视图（默认）
- `kanban`：看板视图
- `timeline`：时间线视图

**项目类型说明**：
- `TASK`：任务类型（默认）
- `NOTE`：笔记类型

### 更新项目

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py update-project <项目ID> \
  [--name "新名称"] \
  [--color "#FFD700"] \
  [--view-mode kanban] \
  [--kind TASK|NOTE]
```

只需传入要修改的字段。

### 删除项目

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py delete-project <项目ID>
```

> **注意**：删除项目会同时删除项目下的所有任务，此操作不可逆。执行前必须向用户确认。

## 结果展示建议

展示项目列表时，建议以表格形式呈现：
- 项目名称
- 视图模式
- 类型
- 颜色（可用色块表示）
- 是否已关闭
