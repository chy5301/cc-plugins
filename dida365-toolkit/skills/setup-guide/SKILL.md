---
name: setup-guide
description: |
  配置滴答清单接入并验证连接：默认引导创建个人 API Token 并写入凭据文件，用户明确选择时提供 OAuth 备选，并给出连接验证与故障排查步骤。当用户首次使用滴答清单工具，或点名 "滴答清单""滴答""TickTick"，或本次对话已在操作滴答清单，并提到"配置""设置 Token""连接""认证""dida365 setup""ticktick setup"时使用。也在其他滴答清单 skill 因缺少凭据或 401/403 报错、区域配置不受支持而转入。若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，先向用户确认再执行。
version: 0.2.0
---

# 配置滴答清单接入

把滴答清单接入配置一次：默认使用个人 API Token（写入凭据文件），用户明确要求时改走 OAuth 备选，随后验证 MCP 连接与只读调用可用。

通道选择、能力发现协议、批量部分失败、安全边界与失败分类统一见 `${CLAUDE_PLUGIN_ROOT}/references/tool-conventions.md`；使用任何滴答清单能力之前先读该文件，本文只补充配置与验证流程。

## 前置条件

- 已安装 `uv`（脚本一律通过 `uv run` 执行）
- 拥有国内版滴答清单账户
- 客户端支持 `/mcp` 查看 MCP 服务器状态

## 引导顺序

先识别现状，再按用户意愿选择路径，任何失败都不擅自改配置：

1. **识别已有可用接入**：已有 Token（环境变量或凭据文件）就先验证并复用；已有正常工作的 OAuth 接入就尊重现状，不强制改回 Token。
2. **无可用接入时默认介绍 Token**：引导创建个人 API Token 并配置一次（下文「Token 路径」）。用户明确要求 OAuth 时可直接转入备选，不要求先拒绝 Token。
3. **用户不愿或无法获取 Token 时转 OAuth**：转入下文「OAuth 备选流程」，不反复要求创建 Token。
4. **Token 无效或区域检查失败时先说明原因**：讲清是凭据问题还是配置问题，不自动切换认证方式；只有用户明确选择后才改变配置。
5. **不删除、覆盖或撤销用户已有凭据**：不改动用户未要求修改的凭据与服务器定义。

## Token 路径（凭据文件为主）

### Step 1: 创建个人 API Token（国内版）

1. 打开**网页版**滴答清单（https://dida365.com）
2. 点击右上角**头像** → **设置** → **账户与安全** → **API 口令**
3. 创建新的 API 口令并复制生成的 Token

该 Token 同时用于 MCP 接入与 Open API 补缺，只需配置一次。

### Step 2: 写入凭据文件

MCP 连接的凭据来自默认凭据文件 `~/.dida365/token`。环境变量 `DIDA365_TOKEN_FILE` **只影响本地/API 执行**（它的名称含 `TOKEN`，在插件级 helper 环境同样会被移除），MCP 通道固定读取默认路径；需要把文件放到别处时，用符号链接/联接点让默认路径指向目标，不要指望用覆盖变量改动 MCP 的读取位置。文件内容为一行纯 Token，不要加引号或多余空白。

若环境变量 `DIDA365_API_TOKEN` 已经配置好，可用一条命令生成凭据文件：

```bash
mkdir -p ~/.dida365

printf '%s' "$DIDA365_API_TOKEN" > ~/.dida365/token
```

POSIX 系统建议收紧权限：

```bash
chmod 600 ~/.dida365/token
```

**位置要求**：该文件及其链接目标必须留在仓库之外，也必须留在 `/sync-config` 同步范围（`~/.claude/`）之外 —— 默认的 `~/.dida365/token` 同时满足这两点，不要把 Token 放进项目目录或 `~/.claude/`；用符号链接/联接点改放到别处时同样遵守。Windows 下依赖用户目录权限，不要放进共享目录。

**为什么需要文件而不是环境变量**：插件级 `headersHelper` 运行时，Claude Code 会移除名称含 `TOKEN`/`SECRET`/`PASSWORD`/`KEY`/`AUTH` 的环境变量，并要求这类脚本改为从文件或凭据存储读取凭据（官方文档《Which variables a helper can read》）。因此 `DIDA365_API_TOKEN` 在 MCP 连接时通常不可见，实际凭据来源是默认凭据文件；`DIDA365_TOKEN_FILE` 的名称同样含 `TOKEN`，同样会被移除，所以覆盖只服务于本地/API 执行，不能用来改变 MCP 的读取位置。

环境变量 `DIDA365_API_TOKEN` 只是**可选且优先**的来源：本地直接调用 API 执行器时，设置了就以它为准，未设置才回退凭据文件。它不能替代默认凭据文件。Token 不得出现在命令行参数、请求体、日志或任何输出中。

### Step 3: 无秘密自检

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mcp_headers.py --check
```

输出是不含秘密的 JSON 状态，重点看两个字段：

- `token_source`：`env` 表示本次由环境变量提供（注意 MCP 连接看不到它，仍要写好默认凭据文件）、`file` 表示来自当前生效的凭据文件、`null`（`token_present: false`）表示两处都没有，回到 Step 1/2。
- `mcp_file_present`：**MCP 相关的信号** —— 默认凭据文件 `~/.dida365/token` 里是否有凭据。它为 `false` 时 MCP 连接拿不到凭据：即使 `token_source` 显示 `file` 也一样，那种情况下凭据来自 `DIDA365_TOKEN_FILE` 覆盖，而该变量在插件级 helper 环境会被移除，属于本地/API 侧的假绿灯。

`ok: false` 时状态里带 `error.code` 与 `error.message`，按「故障排查」处置。不要运行不带 `--check` 的辅助入口，也不要把它的认证头输出展示给用户。

### Step 4: 区域边界

**本版本仅支持国内**滴答服务，API 出口固定 `https://api.dida365.com`、MCP 出口固定 `https://mcp.dida365.com`：

- 国际版 Token 会认证失败，本版本不提供国际版支持。
- `DIDA365_API_DOMAIN` 指向国际域名（如 `api.ticktick.com`）时会被拒绝，且失败发生在发送任何凭据之前；请移除该变量或改为 `api.dida365.com`。
- 不能从 Token 字符串判断地区，也不做静默降级。

## 连接验证

1. **查看客户端状态**：在客户端运行 `/mcp`，找到插件服务器 `plugin:dida365-toolkit:dida365`，确认已连接且工具列表非空。
2. **准备运行环境**：首次连接前先手动执行一次 Step 3 的自检，让 `uv` 完成环境准备，避免首次环境下载挤占客户端连接超时。
3. **只读验证调用**：通过 MCP 做一次只读操作（如列出清单、查询任务）。工具名以当前实际发现为准：插件模式下形如 `mcp__plugin_dida365-toolkit_dida365__<tool>`，不要凭记忆拼工具名。
4. **可选：API 通道验证**：先用 `--dry-run` 看请求概要（不发请求、不需要 Token，退出码 `10`），再发一条只读 GET 确认 Token 在 API 通道可用：

```bash
# 预演：只输出请求概要
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method GET --path /open/v1/project --dry-run

# 只读 GET：确认 API 通道的 Token 可用
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_api.py --method GET --path /open/v1/project --fields id,name
```

返回可解析信封且成功即为通过；401 见「故障排查」。API 通道只在确认 MCP 缺口时使用，用法与协议见 `tool-conventions.md`。

5. **确认完成**：向用户说明接入已可用，其他 skill 会自动接管任务增删改查、完成与放弃、项目与整理、高级查询与每日回顾。

## OAuth 备选流程（仅用户明确选择时）

OAuth 交给客户端原生支持，不新建插件自己的 OAuth 客户端、缓存或刷新器。仅当用户明确要求，或不愿/无法获取 Token 时进入本节。

1. **先检查更高优先级的同端点配置**：核对现有的、指向 `https://mcp.dida365.com` 的用户/项目/本地 scope 定义与组织策略。存在更高优先级或组织策略冲突时，说明冲突并停止，不静默改动。
2. **用户授权后添加手动定义**：增加一个同一端点、不带 Authorization、也不带 `headersHelper` 的手动 MCP 定义，默认使用用户 scope 便于复用。手动同端点定义会整体替换插件的服务器条目，不是字段合并。
3. **验证生效项**：
   - 生效的是不带 Bearer 的手动定义；
   - 插件辅助入口不再为该连接运行；
   - 没有重复工具（同一服务出现两套工具列表）；
   - 工具命名空间按实际发现，不要假设仍是插件前缀。
4. **必要时显式停用插件服务器**：在 `/mcp` 中停用插件服务器后再使用手动定义；不要靠反复试登录掩盖仍然生效的 Authorization。
5. **完成授权并验证**：在客户端完成 OAuth，然后做一次只读调用确认可用。
6. **API 补缺边界**：OAuth 只覆盖 MCP 接入。仅使用 OAuth 的用户遇到 API 缺口时，说明 API 通道需要个人 API Token，可改在滴答应用中完成该操作；不读取客户端 OAuth 缓存，不承诺 OAuth 单次授权覆盖 API 补缺。以后补配的 Token 只用于 API，不自动把正在使用的 OAuth MCP 改回 Bearer。

## 故障排查

| 现象 | 原因与处置 |
|---|---|
| `TOKEN_MISSING`，或 MCP 侧没有可用凭据 | 默认凭据文件 `~/.dida365/token` 缺失且环境变量为空。按 Step 1/2 创建并写入，再用 `mcp_headers.py --check` 确认 `mcp_file_present: true`。 |
| 仅 API 通道：本地/API 调用缺凭据 | 覆盖变量 `DIDA365_TOKEN_FILE` 只对本地/API 执行有效，检查它指向的覆盖文件是否存在、内容是否为一行纯 Token；MCP 侧与此无关，看 `mcp_file_present`。 |
| `REGION_UNSUPPORTED`，区域检查失败 | `DIDA365_API_DOMAIN` 指向非国内域名。移除该变量或改为 `api.dida365.com`；不自动切换通道。 |
| MCP 已连接但调用返回 401 | 凭据问题：Token 缺失、无效或过期。重新核对 Token 后更新凭据文件，再跑一次 `mcp_headers.py --check`。 |
| 调用返回 403 | 权限问题：清单或操作权限不足。说明权限原因，不要一概描述成「令牌失效」，也不要换通道重发同一操作。 |
| 仅使用 OAuth 却遇到 API 补缺 | 说明 API 通道需要个人 Token，可改在滴答应用内完成；不读取 OAuth 缓存，不新建插件 OAuth 客户端。 |
| 未安装 `uv` | 提示先安装 `uv`（所有脚本以 `uv run` 执行），安装后回到 Step 3 自检。 |
| 首次连接超时 | 先手动跑一次 Step 3 自检，让 `uv` 完成环境准备后重新连接。 |

任何一类失败都不自动切换通道或认证方式，也不自动重试；只有用户明确选择后才改变配置。完整失败分类见 `tool-conventions.md`。

## 边界

- 不删除、覆盖或撤销用户已有凭据；不改动用户未要求修改的定义。
- Token 不出现在参数、日志、`--check` 输出或错误回显中。
- 不读取客户端 OAuth 缓存，不新建插件自己的 OAuth 客户端。
- 平台消歧：与 mstodo 等其他待办工具并存、本轮未指明平台且上下文无法确定时，先向用户确认平台再执行。

> 通道选择、能力发现协议、批量部分失败、安全边界与失败分类见 `${CLAUDE_PLUGIN_ROOT}/references/tool-conventions.md`；官方端点来源与已验证限制见 `${CLAUDE_PLUGIN_ROOT}/references/api-reference.md`。
