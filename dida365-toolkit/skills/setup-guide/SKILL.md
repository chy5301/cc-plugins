---
name: setup-guide
description: |
  配置滴答清单 API Token 和验证连接。当用户首次使用滴答清单工具、提到"配置滴答清单""设置 API Token""dida365 setup""ticktick setup""连接滴答清单"时使用。
version: 0.1.0
tools: Bash
---

# 配置滴答清单 API 连接

引导用户获取 API Token 并验证与滴答清单 API 的连接。

## 前置条件

- 已安装 `uv`（Python 包管理器）
- 拥有滴答清单账户

## 步骤

### Step 1: 获取 API Token（API 口令）

引导用户操作：

1. 打开**网页版**滴答清单（https://dida365.com）
2. 点击右上角 **头像** → **设置** → **账户与安全** → **API 口令**
3. 点击创建新的 API 口令，复制生成的 Token（格式类似 `dp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）

> **国际版用户**（TickTick）：访问 https://ticktick.com，路径为 Avatar → Settings → Account & Security → API Token。
>
> **说明**：该 Token 同时用于滴答清单 MCP 和 Open API，本插件通过 Open API 调用。

### Step 2: 设置环境变量

根据用户的操作系统，指导设置环境变量：

**方式 A：在 Claude Code settings.json 中配置（推荐）**

建议用户在 `~/.claude/settings.json` 的 `env` 字段中添加：

```json
{
  "env": {
    "DIDA365_API_TOKEN": "你的API Token"
  }
}
```

**方式 B：在 shell 配置中设置**

```bash
# ~/.bashrc 或 ~/.zshrc
export DIDA365_API_TOKEN="你的API Token"
```

**国际版用户**额外设置域名：

```bash
export DIDA365_API_DOMAIN="api.ticktick.com"
```

### Step 3: 验证连接

执行以下命令测试连接：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py list-projects
```

**预期结果**：返回 JSON 格式的项目列表，表示连接成功。

**如果返回错误**：
- `401 Unauthorized`：API Token 无效或过期，请重新获取
- `连接超时`：检查网络连接，国内用户确认域名为 `api.dida365.com`
- `未设置 DIDA365_API_TOKEN`：检查环境变量是否正确设置

### Step 4: 确认完成

向用户确认配置成功，并介绍可用的功能：
- 任务管理：创建、更新、完成、删除任务
- 项目管理：创建、查看、更新、删除项目
- 高级查询：按优先级、标签、日期、状态筛选任务
- 每日回顾：查看今日待办和任务概览
