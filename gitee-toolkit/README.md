# gitee-toolkit

Gitee 一站式工具箱 —— 集成 Gitee MCP Server 与 DevOps Skills 的 Claude Code 插件。

## 功能概览

通过远程 MCP 连接 Gitee API，提供 14 个开箱即用的 Skills：

| Skill | 说明 |
|-------|------|
| `create-pr` | 创建 Pull Request |
| `review-pr` | 审查 Pull Request |
| `merge-pr-check` | 合并 PR 前检查 |
| `create-issue` | 创建 Issue |
| `implement-issue` | 根据 Issue 实现代码 |
| `close-issue-flow` | 关闭 Issue 流程 |
| `triage-issues` | Issue 分类与优先级排序 |
| `create-release` | 创建 Release |
| `daily-digest` | 每日仓库活动摘要 |
| `repo-explorer` | 仓库浏览与探索 |
| `search-and-fork` | 搜索并 Fork 仓库 |
| `search-repos` | 搜索 Gitee 仓库 |
| `stale-pr-reminder` | 过期 PR 提醒 |
| `quick-fix-suggestion` | 基于 Issue 的快速修复建议 |

## 前置要求

### 1. 获取 Gitee Access Token

前往 [Gitee 私人令牌](https://gitee.com/profile/personal_access_tokens) 创建令牌，勾选以下权限：

- `user_info` — 用户信息与通知
- `projects` — 仓库操作
- `pull_requests` — PR 操作
- `issues` — Issue 操作

### 2. 设置环境变量

将 token 设置为系统环境变量 `GITEE_ACCESS_TOKEN`：

**Windows（PowerShell）：**

```powershell
[System.Environment]::SetEnvironmentVariable('GITEE_ACCESS_TOKEN', '你的token', 'User')
```

**macOS / Linux：**

```bash
echo 'export GITEE_ACCESS_TOKEN="你的token"' >> ~/.bashrc
source ~/.bashrc
```

设置后需重启 Claude Code 使环境变量生效。

## 安装

参见 [仓库 README](../README.md#安装)。

## 使用

安装后，所有 Skills 以 `/gitee-toolkit:<skill-name>` 格式调用，例如：

```
/gitee-toolkit:create-pr
/gitee-toolkit:repo-explorer
/gitee-toolkit:daily-digest
```

## 更新与维护

本插件的 Skills 基于 [oschina/gitee-agent-skills](https://github.com/oschina/gitee-agent-skills) v1.0.0 拷贝并独立维护，不自动同步上游更新。

检查官方 Skills 是否有更新：

```bash
# 查看上游仓库最新提交
gh api repos/oschina/gitee-agent-skills/commits?per_page=5 --jq '.[].commit.message'

# 对比某个 skill 的差异
gh api repos/oschina/gitee-agent-skills/contents/skills/create-pr/SKILL.md --jq '.content' | base64 -d | diff - gitee-toolkit/skills/create-pr/SKILL.md
```

## 致谢

Skills 基于 [oschina/gitee-agent-skills](https://github.com/oschina/gitee-agent-skills)，MCP Server 由 [oschina/mcp-gitee](https://github.com/oschina/mcp-gitee) 提供。
