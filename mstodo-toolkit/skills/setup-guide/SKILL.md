---
name: setup-guide
description: >-
  配置并登录 Microsoft To Do。当用户首次使用 Microsoft To Do 工具，或点名
  "Microsoft To Do""MS To Do""微软待办""微软 To Do"并提到"登录""配置""设置"
  "连接""重新授权""退出登录"，或本次对话已在操作 Microsoft To Do 并提到"登录""配置"
  "设置""连接""重新授权""退出登录"时使用。也在其他 Microsoft To Do skill 遇到退出码
  2（CONFIG_ERROR，未登录）或退出码 4（AUTH_EXPIRED，凭据失效）时转入。
  若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# setup-guide：Microsoft To Do 登录与配置

配置并完成 Microsoft To Do 的登录 / 登出 / 状态查询，是 mstodo-toolkit 插件唯一的认证入口。

## 前置条件

本 skill 本身就是认证入口，没有更前置的 skill。

其余 Microsoft To Do skill 的触发判据是"平台是否已确定"——用户首次使用该工具，或本次对话已在操作 Microsoft To Do——而不是"用户是否点名"了工具名称。也就是说，即便用户没有显式说出"Microsoft To Do"这几个字，只要上下文已经在操作它，那些 skill 遇到退出码 2（`CONFIG_ERROR`）或退出码 4（`AUTH_EXPIRED`）时，仍会转入本 skill 完成（重新）登录，不需要用户重新点名平台。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## 常用操作

### 一次登录（核心职责）

CLI 把登录拆成了 `auth-start` / `auth-complete` 两个子命令，这是实现细节——**不要把这两步的拆分暴露给用户**，用户感知到的应该是"一次登录"。完整流程：

1. 运行：

   ```bash
   uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-start
   ```

   返回信封的 `data` 里含 `user_code`、`verification_uri`、`device_code`、`expires_in`（约 900 秒）、`interval`。

2. 向用户播报：打开 `<verification_uri>`，输入 `<user_code>`，完成后告诉我。

3. 运行：

   ```bash
   uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-complete --device-code <device_code>
   ```

   这里的 `<device_code>` 就是第 1 步返回的那个值。

4. **若退出码为 6（`AUTH_PENDING`）**：用**同一个** `device_code` 再跑一次第 3 步，最多重复到第 1 步返回的 `expires_in` 耗尽（约 900 秒）。每次重试前先问用户是否已经完成浏览器里的授权操作，不要在用户没有回应"已完成"的情况下自行连续轮询——用户点确认之间的间隔完全由用户决定，不是 Agent 能替用户加速的事。

5. 成功后向用户报告登录结果：账号（如信封中含用户标识）、`scope`、token 的有效期。

> **退出码 `6`（`AUTH_PENDING`）不是错误。** 它表示"用户还没有在浏览器里点完授权"，是这个 CLI 契约的一部分，不是异常。遇到它应该按上面第 4 步继续等待 / 重试，而不是把它当失败上报给用户或中止整个登录流程。

`auth-complete` 的 `--timeout` 默认 90 秒，刻意小于调用方（Claude Code 的 Bash 工具）的 120 秒超时——这样 CLI 能在被调用方杀掉进程之前，干净地返回 `AUTH_PENDING` 信封，而不是被粗暴杀掉、什么信息都拿不到。

### 查看登录状态

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-status
```

返回 `logged_in` / `tenant` / `scope` / `expires_in_seconds` / `cache_path`，**从不回显 `access_token` 本体**。未登录时同样以 `CONFIG_ERROR` + 退出码 2 失败——这种情况下应转入上面的"一次登录"流程。

### 退出登录

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-logout
```

删除本机 token 缓存，是幂等操作：重复调用返回 `"removed": false`，不会报错。

### `CONFIG_ERROR` 与 `AUTH_EXPIRED` 的区别

| 错误码 | 退出码 | 含义 | 应采取的动作 |
| --- | --- | --- | --- |
| `CONFIG_ERROR` | 2 | 本机**从未**成功登录过（缓存不存在，或 `client_id` / `tenant` 变更导致缓存判定为不匹配） | 完整走一遍上面"一次登录"流程：`auth-start` → `auth-complete` |
| `AUTH_EXPIRED` | 4 | 本机**登录过**，但 `refresh_token` 刷新失败（凭据被吊销、超过 90 天未用、用户改了密码等） | 同样需要重新走一遍登录流程——不能复用旧的 `device_code`，因为这不是"等待中"而是凭据已彻底失效，必须重新 `auth-start` |

负责清单 / 任务 / 子任务增删改查、状态流转、跨清单查询与组织归类等能力的其他 Microsoft To Do skill，遇到这两个退出码时都会转入本 skill 完成（重新）登录。

### 企业租户的两类报错

工作 / 学校账号（Azure AD 租户）登录时可能遇到以下两类报错；**个人微软账号（如 outlook.com / hotmail.com 邮箱）使用默认配置即可登录，不受这两条影响**：

| 症状 | 原因 | 处置 |
| --- | --- | --- |
| 错误信息含 `AADSTS50105` | 默认 client ID（`14d82eec-204b-4c2f-b7e8-296a70dab67e`）在该租户被管理员设为"需用户分配"，未被分配的用户无法用它登录 | 引导用户自建 Azure AD 应用注册，把新的 client ID 设到环境变量 `MSTODO_CLIENT_ID` |
| 授权过程中提示设备码流被策略阻止 / 被 Conditional Access 拦截 | 租户启用了阻断设备码流的 Conditional Access 策略（微软自 2025 年 2 月起因 STORM-2372 钓鱼活动，建议企业租户收紧此类策略） | 同上：自建 Azure 应用并设置 `MSTODO_CLIENT_ID`；并明确告知用户**这是租户自身的安全策略，不是插件的问题** |

实测依据：本插件的探针曾用**个人微软账号**、默认 `MSTODO_TENANT=common`、默认 client ID，直接登录成功——说明默认配置本身没有问题，上述两条报错的根源在企业租户的安全策略，不在插件或默认配置。

### 环境变量

四个环境变量均可不设置（都有默认值）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MSTODO_CLIENT_ID` | `14d82eec-204b-4c2f-b7e8-296a70dab67e` | Azure 应用 client ID。默认值是微软第一方公共 client（Graph Command Line Tools），免 Azure 注册即可用 |
| `MSTODO_TENANT` | `common` | `common` / `consumers` / `organizations`，决定登录时接受哪类账号 |
| `MSTODO_TOKEN_CACHE` | 未设置时用 XDG state 目录 | token 缓存**目录**（实际文件是 `<该目录>/token.json`）。未设置本变量时，若设置了 `XDG_STATE_HOME` 则用 `$XDG_STATE_HOME/mstodo-toolkit/`，否则用 `~/.local/state/mstodo-toolkit/` |
| `MSTODO_TIMEZONE` | `Asia/Shanghai` | `--body` JSON 中日期简写（无 `timeZone` 字段时）展开使用的默认时区 |

设置方式由用户自行选择，几种常见做法：

- `~/.claude/settings.json` 的 `env` 字段
- shell 的 `export`（写进 `~/.bashrc` / `~/.zshrc` 等）
- 其他 secrets 管理工具

### token 缓存位置与安全性

token 缓存文件的完整路径是：

```
${MSTODO_TOKEN_CACHE:-${XDG_STATE_HOME:-~/.local/state}/mstodo-toolkit}/token.json
```

- 所在目录权限 `0700`，文件本身权限 `0600`，写入采用先写临时文件再 rename 的原子写入方式。
- **这份缓存绝不应进仓库**——不要把它加入 git 追踪，也不要把它复制、粘贴或分享给别人。
- 每台设备需要各自独立登录一次；换设备或换 profile 不会自动带过去。
- 这份缓存**不参与** `/sync-config` 之类的配置同步流程——它是纯本机凭据，不是可同步的配置项。

## 边界

本 skill 只负责：登录、登出、查看登录状态、环境变量配置指引、企业租户报错排查。

以下能力**不**由本 skill 负责，遇到时应转出给对应的 Microsoft To Do skill：

- 清单（list）的增删改查
- 任务（task）的增删改查、状态流转（完成 / 未完成 / 延后等）
- 子任务 / 清单项（checklist item）的增删改查
- 跨清单查询、聚合、按状态过滤等组织类操作

## 注意事项

- 退出码 `6`（`AUTH_PENDING`）不是错误，见上文"一次登录"一节——不要把它当失败上报或中止流程。
- `auth-start` 返回的 `device_code` 有效期约等于 `expires_in`（约 900 秒），超过后必须重新执行 `auth-start` 拿新的 `device_code`，旧的不能再用。
- `auth-complete --timeout` 默认 90 秒，小于调用方 120 秒超时是刻意设计，超时只代表要按契约重试，不代表出错。
- `CONFIG_ERROR`（退出码 2，本机从未登录）与 `AUTH_EXPIRED`（退出码 4，登录过但已失效）处置动作相同（都要重新走一遍登录流程），但语义不同，判断时不要混为一谈——具体区别见上文表格。
