# dida365-toolkit

滴答清单一站式工具箱。提供 7 个 Skills 覆盖任务和项目的完整生命周期管理，包括增删改查、完成、放弃、移动、高级筛选和每日回顾。

**本版本仅支持国内滴答服务**：API 出口固定 `https://api.dida365.com`、MCP 出口固定 `https://mcp.dida365.com`。国际 TickTick 不再支持。

## 架构

采用 **Skills + 官方远程 MCP + 通用 API 补缺脚本** 架构：

```
Skill (Markdown 指令)
  ├─ 默认：官方滴答 MCP（.mcp.json 注册的 dida365 服务，远程 HTTP，凭据由 headersHelper 注入）
  └─ 补缺：uv run scripts/dida365_api.py --method ... --path /open/v1/...  → 滴答官方 Open API
```

- **默认走 MCP**：任务、清单、状态、查询与移动等操作优先用官方 MCP 工具完成；工具名以运行时实际发现到的 schema 为准。
- **仅在确认缺口时补缺**：只有 MCP 明确缺少所需工具或必需参数（例如删除单个清单）时，才按 `references/tool-conventions.md` 的能力发现协议调用通用 API 执行器。
- **运行失败不是切换理由**：MCP 返回 401/403/429、超时或参数错误时按失败分类处置，不因此改用 API 重发同一操作，也不因此更换认证方式。
- 兼容 Claude Code（plugin 形式）和其他 AI Agent（skill 形式）。

### 能力边界

- 能力上限是官方 MCP 与官方 Open API，二者都是滴答 app 的子集：标签的独立增删改、习惯打卡、番茄钟、智能清单、子任务的精细排序等 app 功能未暴露，Agent 无法做到。
- 通用执行器不需要为具体端点新增子命令；新发现的接口也不会因为一次调用就自动成为长期支持能力。

## 认证

默认 Bearer MCP 接入与 API 补缺共用**同一枚凭据**：国内版个人 API Token（网页版 头像 → 设置 → 账户与安全 → API 口令），只需配置一次。已有正常工作的手动 OAuth MCP 接入不需要个人 Token 或默认凭据文件；只有需要正式调用 API 补缺时，才另行配置个人 Token，不改动现有 OAuth MCP。

| 来源 | 适用范围 | 说明 |
|------|----------|------|
| 凭据文件（**主来源**） | 默认 Bearer MCP 与 API | 默认 `~/.dida365/token`，内容为一行纯 Token；插件 `headersHelper` 模式固定读取该路径 |
| 环境变量 `DIDA365_API_TOKEN` | 仅本地/API 直调 | **可选且优先**：设置了就以它为准，未设置才回退凭据文件；无法替代默认 Bearer MCP 的凭据文件 |
| OAuth | 仅 MCP 接入 | 备选，只在用户明确选择时启用；不需要个人 Token 文件，API 补缺仍需要个人 Token |

**为什么默认 Bearer MCP 需要凭据文件**：插件级 `headersHelper` 运行时，Claude Code 会移除名称含 `TOKEN`/`SECRET`/`PASSWORD`/`KEY`/`AUTH` 的环境变量，并要求 helper 改为从文件或凭据存储读取凭据。因此 `DIDA365_API_TOKEN` 在该模式的 MCP 连接时通常不可见，实际凭据来源是默认凭据文件 `~/.dida365/token`；`DIDA365_TOKEN_FILE` 的名称同样含 `TOKEN`、同样会被移除，它的覆盖**只对本地/API 执行有效**，不能改变默认 Bearer MCP 的读取位置——需要异地存放时用符号链接/联接点把默认路径指过去。此要求不适用于手动 OAuth MCP。

凭据文件支持 UTF-8（含 BOM）；去掉首尾空白后必须是无内部空白、无控制字符的单行 ASCII Token。格式无效时会在输出认证头或发送请求前报 `TOKEN_INVALID`，不会回显 Token。

写入凭据文件：

```bash
mkdir -p ~/.dida365

printf '%s' '<你的 Token>' > ~/.dida365/token

chmod 600 ~/.dida365/token   # POSIX 系统建议收紧权限
```

无秘密自检（只输出配置状态，不回显 Token）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mcp_headers.py --check
```

重点看两个字段：`token_source`（本次有效 Token 来自环境变量还是文件）与 `mcp_file_present`（默认凭据文件里是否有格式有效的 Token）。`mcp_file_present` 为 `false` 时默认 Bearer MCP 连接拿不到有效凭据，即使 `token_source` 显示 `file` 也一样——那只是本地/API 侧的假绿灯。该自检不用于判断手动 OAuth MCP 是否可用；OAuth 通过客户端连接状态与只读调用验证。

凭据文件及其链接目标必须留在仓库与 `/sync-config` 同步范围（`~/.claude/`）之外；Token 不得出现在命令行参数、请求体、日志或任何输出中。

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `DIDA365_API_TOKEN` | 否 | 可选且优先的凭据来源，**仅本地/API 直调生效**（MCP 连接看不到它） |
| `DIDA365_TOKEN_FILE` | 否 | 凭据文件路径覆盖，仅本地/API 执行生效 |
| `DIDA365_API_DOMAIN` | 否 | 仅接受 `api.dida365.com`（或留空）；其他值（如 `api.ticktick.com`）会被拒绝 |

## 安装

参见 [仓库 README](../README.md#安装)。

本地开发测试：

```bash
claude --plugin-dir ./dida365-toolkit
```

## Skills

| Skill | 说明 |
|-------|------|
| `setup-guide` | 配置凭据文件与 MCP 接入、无秘密自检、连接验证与故障排查（OAuth 备选） |
| `task-crud` | 创建、查看、更新、删除、放弃/恢复任务（含子任务） |
| `task-complete` | 标记任务为已完成 |
| `task-organize` | 在项目（清单）间移动和整理任务 |
| `task-query` | 按优先级/标签/日期/状态筛选任务，查询已完成任务 |
| `project-management` | 项目（清单）的完整增删改查（删除清单走 API 补缺，先 dry-run） |
| `daily-review` | 每日任务回顾：今日待办、逾期任务、高优先级概览 |

七个 Skill 统一引用 `references/tool-conventions.md`（通道选择、能力发现协议、批量部分失败、安全边界与失败分类）；官方端点来源与已验证限制见 `references/api-reference.md`。

## API 补缺执行器

`scripts/dida365_api.py` 是**通用执行器，不是端点专用 CLI**：单次请求、固定出口、不跟随重定向、不自动重试、不为具体端点新增子命令。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method <METHOD> --path <PATH> [--query '<JSON>'] [--body '<JSON>'] [--fields a,b] [--dry-run]
```

```bash
# 预演：输出方法、路径与请求体，不发请求、不需要 Token（退出码 10）
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method POST --path /open/v1/task --body '{"title":"示例"}' --dry-run

# 只读查询：列出清单并裁剪输出顶层字段
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method GET --path /open/v1/project --fields id,name

# 删除清单补缺：先用 --dry-run 展示目标与连带影响，确认后去掉 --dry-run 执行
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method DELETE --path /open/v1/project/<id> --dry-run
```

- `--path` 必须以 `/open/v1/` 开头；`--query`/`--body` 传 JSON；`--fields` 只在输出侧裁剪顶层字段，不减少网络下载量。
- `--dry-run` 是本地构造的预演，不等于服务端验证；写操作先预演、执行后读回核验。
- 退出码：`0` 成功 / `1` 一般错误 / `2` 参数错误 / `3` 不存在 / `4` 凭据或权限不足 / `10` dry-run。

## 0.6.1 修复说明

- **错误正文先脱敏再截断**：避免 Token 跨越截断边界时泄漏凭据前缀，覆盖 JSON 与纯文本错误响应。
- **兼容 UTF-8 BOM 凭据文件**：在输出认证头或发送请求前校验 Token 格式；非法 Token 返回 `TOKEN_INVALID`，无秘密自检不再误报可用。
- **修正 OAuth-only 接入前提**：已有可用的手动 OAuth MCP 不要求个人 Token 文件或 Token helper 自检；正式 API 补缺仍需要个人 Token，不改变现有 OAuth MCP。

## 0.6.0 迁移说明（破坏性）

- **改用官方远程 MCP**：任务、清单、状态、查询与移动默认经 `.mcp.json` 注册的官方滴答 MCP 完成；仅默认 Bearer MCP 的凭据固定来自 `~/.dida365/token`，已有可用的手动 OAuth MCP 不要求此文件。
- **旧命令式 CLI 已移除**：其子命令与 `--body` 等参数形式（含 schema 自省与 raw 透传）不再提供；MCP 缺口统一走通用 API 执行器（`--method` + `--path` + `--fields` + `--dry-run`）。
- **国际 TickTick 不再支持**：只支持国内滴答服务，API 出口固定 `https://api.dida365.com`、MCP 出口固定 `https://mcp.dida365.com`；`DIDA365_API_DOMAIN` 指向 `api.ticktick.com` 等国际/其他域名时会被拒绝，且失败发生在发送任何凭据之前，不做静默降级。
- **认证方式不自动切换**：401/403/429/超时等失败都不自动换通道或换认证方式；OAuth 只在用户明确选择时用于 MCP 接入，不覆盖 API 补缺。
- 各 SKILL.md 的 `version` 是该 skill 自身的迭代标识，与 plugin 发布版本解耦。

## 依赖

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)（自动管理 Python 依赖）
- httpx（仅 API 执行器需要，通过 PEP 723 内联声明，`uv run` 自动安装）

## 测试

在仓库根目录执行：

```bash
uv run --with pytest --with httpx pytest dida365-toolkit/tests -q
```
