# dida365-toolkit

滴答清单一站式工具箱。提供 7 个 Skills 覆盖任务和项目的完整生命周期管理，包括增删改查、完成、移动、高级筛选和每日回顾。

## 架构

采用**纯 Skill + Python CLI 脚本**架构，不依赖 MCP 协议，安装即用：

```
Skill (Markdown 指令) → Bash: uv run dida365_cli.py <command> → 滴答清单 Open API
```

兼容 Claude Code（plugin 形式）和其他 AI Agent（skill 形式）。

## 安装

参见 [仓库 README](../README.md#安装)。

本地开发测试：

```bash
claude --plugin-dir ./dida365-toolkit
```

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `DIDA365_API_TOKEN` | 是 | 滴答清单 API Token（设置→账户→API Token） |
| `DIDA365_API_DOMAIN` | 否 | API 域名，默认 `api.dida365.com`，国际版用 `api.ticktick.com` |

## Skills

| Skill | 说明 |
|-------|------|
| `setup-guide` | 配置 API Token 和验证连接 |
| `task-crud` | 创建、查看、更新、删除任务（含子任务） |
| `task-complete` | 标记任务为已完成 |
| `task-organize` | 在项目间移动和整理任务 |
| `task-query` | 按优先级/标签/日期/状态筛选任务，查询已完成任务 |
| `project-management` | 项目（清单）的完整增删改查 |
| `daily-review` | 每日任务回顾：今日待办、逾期任务、高优先级概览 |

## CLI 脚本

`scripts/dida365_cli.py` 提供 14 个子命令，覆盖滴答清单 Open API 全部 13 个端点：

```bash
# 项目操作
uv run scripts/dida365_cli.py list-projects
uv run scripts/dida365_cli.py get-project <projectId>
uv run scripts/dida365_cli.py get-project-data <projectId>
uv run scripts/dida365_cli.py create-project --name "名称"
uv run scripts/dida365_cli.py update-project <projectId> --name "新名称"
uv run scripts/dida365_cli.py delete-project <projectId>

# 任务操作
uv run scripts/dida365_cli.py get-task <projectId> <taskId>
uv run scripts/dida365_cli.py create-task --project <projectId> --title "标题"
uv run scripts/dida365_cli.py update-task <taskId> --project <projectId> --title "新标题"
uv run scripts/dida365_cli.py complete-task <projectId> <taskId>
uv run scripts/dida365_cli.py delete-task <projectId> <taskId>
uv run scripts/dida365_cli.py move-tasks --from <fromId> --to <toId> --tasks <taskId1,taskId2>

# 查询操作
uv run scripts/dida365_cli.py filter-tasks --priority 3,5 --status 0
uv run scripts/dida365_cli.py query-completed --start-date "2026-04-01T00:00:00+0800"
```

## 依赖

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)（自动管理 Python 依赖）
- httpx（通过 PEP 723 内联声明，`uv run` 自动安装）
