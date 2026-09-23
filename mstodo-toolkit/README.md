# mstodo-toolkit

Microsoft To Do 一站式工具箱。提供 7 个 Skills 覆盖任务与清单的完整生命周期管理，包括增删改查、状态推进、子任务、跨清单聚合查询、整理与每日回顾。

## 架构

采用**纯 Skill + Python CLI**架构，不依赖 MCP 协议：

```
Skill (Markdown 指令) → Bash: uv run mstodo_cli.py <command> → Microsoft Graph To Do API
```

认证走 OAuth2 **设备码流**（device code flow），token 缓存在本机 `~/` 下的独立目录，不进仓库、不参与配置同步。

## 安装

### 方式一：通过 marketplace

```bash
/plugin marketplace add chy5301/cc-plugins
/plugin install mstodo-toolkit
```

### 方式二：本地开发调试

```bash
claude --plugin-dir ./mstodo-toolkit
```

## 首次登录

登录分两步，`setup-guide` skill 会把这两步包成一次连贯的登录引导（Agent 自动发起、等待你输码、自动完成）：

1. `auth-start` —— 发起设备码登录，立即返回一个用户码（user code）和验证地址
2. 在浏览器打开返回的 `verification_uri`，输入该用户码并完成微软账号授权
3. `auth-complete --device-code <上一步返回的 device_code>` —— 轮询等待授权完成，成功后把 token 落盘缓存

之后每次调用会自动用缓存的 refresh token 续期；`auth-status` 可随时查看登录状态，`auth-logout` 可清除本机缓存。

个人微软账号开箱可用；工作/学校账号可能需自建 Azure 应用，见 `setup-guide`。

## Skills

| Skill | 说明 |
|-------|------|
| `setup-guide` | 配置并登录 Microsoft To Do（首次登录、状态查询、退出登录），是全插件唯一的认证入口 |
| `task-crud` | 创建、查看、更新、删除任务及其子任务 |
| `task-status` | 推进任务状态（进行中/等待他人/已挂起/已完成/重新打开）与优先级 |
| `task-query` | 按任意条件（状态/优先级/分类等）跨清单筛选、统计、查询任务 |
| `list-management` | 清单（list）本身的增删改查 |
| `task-organize` | 在清单间移动任务、增删分类标签（全插件风险最高的 skill，移动无原子操作） |
| `daily-review` | 固定视角的每日回顾：今天要做什么、有什么逾期的、任务概览 |

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `MSTODO_CLIENT_ID` | 否 | 微软第一方公共 client（Graph Command Line Tools） | Azure 应用 client ID，自建应用时覆盖 |
| `MSTODO_TENANT` | 否 | `common` | 租户类型：`common` / `consumers` / `organizations` |
| `MSTODO_TOKEN_CACHE` | 否 | XDG state 目录（`$XDG_STATE_HOME` 或 `~/.local/state`）下的 `mstodo-toolkit/` | token 缓存目录 |
| `MSTODO_TIMEZONE` | 否 | `Asia/Shanghai` | 日期字段未显式指定时区时使用的默认时区 |

## CLI 脚本

`scripts/mstodo_cli.py` 提供 **21 个子命令**，覆盖 Microsoft Graph To Do API 的清单 / 任务 / 子任务资源，外加认证与自省逃生舱：

```bash
# 认证（4）
uv run mstodo-toolkit/scripts/mstodo_cli.py auth-start
uv run mstodo-toolkit/scripts/mstodo_cli.py auth-complete --device-code <device_code>
uv run mstodo-toolkit/scripts/mstodo_cli.py auth-status
uv run mstodo-toolkit/scripts/mstodo_cli.py auth-logout

# 清单（5）
uv run mstodo-toolkit/scripts/mstodo_cli.py list-lists
uv run mstodo-toolkit/scripts/mstodo_cli.py get-list --list <listId>
uv run mstodo-toolkit/scripts/mstodo_cli.py create-list --body '{"displayName":"名称"}'
uv run mstodo-toolkit/scripts/mstodo_cli.py update-list --list <listId> --body '{"displayName":"新名称"}'
uv run mstodo-toolkit/scripts/mstodo_cli.py delete-list --list <listId>

# 任务（5，list-tasks 支持 --list all 跨清单聚合）
uv run mstodo-toolkit/scripts/mstodo_cli.py list-tasks --list <listId|all> [--status <逗号分隔>]
uv run mstodo-toolkit/scripts/mstodo_cli.py get-task --list <listId> --task <taskId>
uv run mstodo-toolkit/scripts/mstodo_cli.py create-task --list <listId> --body '{"title":"标题"}'
uv run mstodo-toolkit/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> --body '{"title":"新标题"}'
uv run mstodo-toolkit/scripts/mstodo_cli.py delete-task --list <listId> --task <taskId>

# 子任务 / checklistItems（5）
uv run mstodo-toolkit/scripts/mstodo_cli.py list-checklist-items --list <listId> --task <taskId>
uv run mstodo-toolkit/scripts/mstodo_cli.py get-checklist-item --list <listId> --task <taskId> --item <itemId>
uv run mstodo-toolkit/scripts/mstodo_cli.py create-checklist-item --list <listId> --task <taskId> --body '{"displayName":"子任务"}'
uv run mstodo-toolkit/scripts/mstodo_cli.py update-checklist-item --list <listId> --task <taskId> --item <itemId> --body '{"isChecked":true}'
uv run mstodo-toolkit/scripts/mstodo_cli.py delete-checklist-item --list <listId> --task <taskId> --item <itemId>

# 自省与逃生舱（2）
uv run mstodo-toolkit/scripts/mstodo_cli.py schema <操作>       # 查询某操作的请求体字段定义，或加 --all 看全部
uv run mstodo-toolkit/scripts/mstodo_cli.py raw --method GET --path /me/todo/lists   # schema 未覆盖端点的透传逃生舱
```

所有命令支持全局选项 `--fields`（字段掩码）、`--dry-run`（只预览将发起的调用）、`--max-pages`（集合端点分页上限）。字段定义见 `references/cli-conventions.md` 与 `references/api-reference.md`。

## 测试

```bash
uv run --with pytest --with httpx pytest mstodo-toolkit/tests/ -v
```

## 依赖

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)（自动管理 Python 依赖）
- httpx（通过 PEP 723 内联声明，`uv run` 自动安装）
