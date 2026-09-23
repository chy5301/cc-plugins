# mstodo-toolkit CLI 通用约定

本文档汇总 `mstodo_cli.py` 跨所有子命令的统一约定。**任何 Skill 在使用 CLI 前都可参考本文档**，避免在每个 Skill 文档里重复同样的基础信息。Agent 在以下情况主动读取本文档：

- 第一次使用 mstodo-toolkit 的任何子命令
- 需要了解 `--fields` / `--dry-run` / `--max-pages` 等全局选项的用法
- 需要解析响应信封或处理错误时
- 遇到退出码 `5`（部分失败）或 `6`（授权未完成）
- 需要自省参数 schema 时
- 需要构造 `--body` JSON，尤其涉及日期字段或 `body` 描述字段时

---

## 前置条件

四个环境变量，均可不设置（均有默认值）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MSTODO_CLIENT_ID` | `14d82eec-204b-4c2f-b7e8-296a70dab67e` | Azure 应用 client ID。默认值是微软第一方公共 client（Graph Command Line Tools），免 Azure 注册即可用 |
| `MSTODO_TENANT` | `common` | `common` / `consumers` / `organizations`，决定登录时接受哪类账号 |
| `MSTODO_TOKEN_CACHE` | 未设置时用 XDG state 目录 | token 缓存**目录**（实际文件为 `<该目录>/token.json`）。未设置本变量时，若设置了 `XDG_STATE_HOME` 则用 `$XDG_STATE_HOME/mstodo-toolkit/`，否则用 `~/.local/state/mstodo-toolkit/` |
| `MSTODO_TIMEZONE` | `Asia/Shanghai` | `--body` JSON 中日期简写（无 `timeZone` 字段时）展开使用的默认时区 |

设置方式由用户选择：`~/.claude/settings.json` 的 `env` 字段、shell 的 `export`、或其他 secrets 管理工具。首次配置请触发 `setup-guide` Skill。

**未登录时**（本机从未成功执行过 `auth-complete`），除 `schema` 外的所有子命令都会以**退出码 `2` + `CONFIG_ERROR`** 失败，`suggestion` 指向先 `auth-start` 再 `auth-complete`。`schema` 是纯本地自省，不需要登录即可使用。

---

## 调用方式

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

所有子命令均通过 `uv run` 触发，无需预装 Python 依赖（脚本头部 PEP 723 内联声明 `httpx`）。

共 21 个子命令：4 个认证（`auth-start` / `auth-complete` / `auth-status` / `auth-logout`）、2 个自省与逃生舱（`schema` / `raw`）、15 个资源命令（清单/任务/子任务各 5 个 CRUD 动作，其中 `list-tasks` 额外支持 `--list all` 跨清单聚合）。

---

## 全局选项

以下选项可附加在**任何子命令**之后：

### `--fields KEY[,KEY...]`

顶层字段掩码，逗号分隔。`data` 是 list 时逐项裁剪，是 dict 时保留指定 key；未知字段静默丢弃，空字段串等同于不裁剪。**返回大对象时优先使用**以保护 Agent 上下文窗口。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-lists --fields id,displayName
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all --fields id,title,listId,listDisplayName
```

### `--dry-run`

只输出将要发起的 API 调用，不真正执行，**退出码 `10`**。响应 `data` 形如：

```json
{"would_call": "POST /me/todo/lists/L1/tasks", "body": {"title": "写周报"}}
```

`metadata.dry_run` 为 `true`（这也是唯一带 `dry_run` 键的场景）。`list-tasks --list all --dry-run` 的 `would_call` 是一条描述性路径而非真实端点（聚合内部会拆成多次真实调用）。**破坏性操作（`delete-list` / `delete-task` / `delete-checklist-item`）没有撤销接口，务必先 `--dry-run` 确认路径与请求体**。

### `--max-pages N`

集合端点（`list-lists` / `list-tasks` / `list-checklist-items`，含跨清单聚合的两个分页维度）最多跟随几页。`0`（默认）表示不限，即**默认跟完所有页**。负数会被拒绝（`INVALID_PARAMETER`，退出码 `2`），不存在"-1 表示不限"这种写法。触发上限时结果不完整，见下方「分页」与「跨清单聚合」两节。

---

## 响应信封

### 成功

```json
{
  "success": true,
  "data": [{"id": "L1", "displayName": "工作"}, {"id": "L2", "displayName": "个人"}],
  "metadata": {
    "command": "mstodo_cli list-lists",
    "took_ms": 312,
    "result_count": 2,
    "pages_fetched": 1,
    "truncated": false
  }
}
```

`metadata` 各键的出现条件（并非每条命令都会出现全部键）：

| 字段 | 出现条件 | 说明 |
|---|---|---|
| `command` | 总是 | 形如 `mstodo_cli <子命令名>`，标识发起的子命令，便于回执溯源 |
| `took_ms` | 命令真的发起了计时的 HTTP 往返时（`raw`、`auth-complete`、15 个资源命令的非 dry-run 路径、`list-tasks`） | 耗时（毫秒）。`schema` / `auth-start` / `auth-status` / `auth-logout` / dry-run 不带此键 |
| `result_count` | `data` 是 list 时 | 列表长度。分页被截断时是「已取到部分」的条数，不是服务端总条数 |
| `dry_run` | `--dry-run` 命中时 | 恒为 `true` |
| `pages_fetched` | 集合端点（`list-lists` / `list-checklist-items` / `list-tasks` 两种模式） | 实际发出的分页请求数 |
| `truncated` | 同上 | 是否因 `--max-pages` 提前中止（见「分页」节） |
| `aggregated_from` | 仅 `list-tasks`（两种模式都有，单清单模式恒为 `1`） | 本次聚合覆盖的清单数 |
| `partial_failures` | 仅 `list-tasks` | 逐条不完整原因的数组，见「跨清单聚合」节 |
| `retry_after_seconds` | 仅 `list-tasks` | 所有失败清单里 `Retry-After` 的**最大值**；均无则为 `null` |
| `all_auth_failed` | 仅 `list-tasks` | 是否所有清单都因 401/403 失败（此时不是 `PARTIAL_FAILURE`，见下） |
| `list_enumeration_truncated` | 仅 `list-tasks` | 清单枚举本身是否被 `--max-pages` 截断，见「跨清单聚合」节 |

`list-tasks` 无论 `--list all` 还是 `--list <单清单id>`，`metadata` 都固定携带 `aggregated_from` / `pages_fetched` / `partial_failures` / `retry_after_seconds` / `all_auth_failed` / `truncated` / `list_enumeration_truncated` 这 7 个聚合相关键（外加通用的 `command` / `took_ms` / `result_count`，共 10 个键），单清单模式下大多为空值（`aggregated_from: 1`、`partial_failures: []`、`all_auth_failed: false`、`list_enumeration_truncated: false`）而非缺失。

### 错误

```json
{
  "success": false,
  "error": {
    "code": "CONFIG_ERROR",
    "message": "本机尚未登录 Microsoft To Do",
    "suggestion": "运行 auth-start 开始登录，再用 auth-complete 完成"
  }
}
```

`suggestion` 是可选字段。**除 `PARTIAL_FAILURE` 外，所有错误信封都不带 `data` 或 `metadata` 键**——不要假设失败响应里一定能读到 `metadata.command` 之类的字段。

常见错误码：

- `CONFIG_ERROR`：本机从未登录（退出码 `2`）
- `AUTH_EXPIRED`：登录过但凭据已失效（退出码 `4`）。只有认证服务明确返回 `invalid_grant` 这类错误时才会报它
- `AUTH_REFRESH_FAILED`：刷新凭据时认证服务暂时不可用（5xx、限流、返回非 JSON 等），**登录态并未失效**（退出码 `1`）。稍后重试即可，不要引导用户重新登录
- `NETWORK_ERROR`：连接失败、DNS 解析失败、代理错误或超时（退出码 `1`）。任何子命令都可能遇到
- `INVALID_RESPONSE`：Graph 返回了 2xx 但响应体不是 JSON（常见于代理拦截返回的 HTML 页，退出码 `1`）
- `INVALID_PARAMETER`：参数/JSON/日期格式/必填字段不合法（退出码 `2`）
- `UNKNOWN_COMMAND`：`schema` 查询了不存在的操作名（退出码 `2`）
- `AUTH_PENDING`：设备码轮询超时（退出码 `6`）
- `AUTH_DECLINED` / `AUTH_CODE_EXPIRED` / `AUTH_START_FAILED` / `AUTH_CACHE_CORRUPT`：认证流程的其他终态错误（退出码 `1`）
- `RAW_RESPONSE_NOT_JSON`：`raw` 命中了返回非 JSON 内容的 2xx 端点（退出码 `1`）
- `PARTIAL_FAILURE`：见专节（退出码 `5`）
- Graph 原生错误码（如 `ItemNotFound`、`ErrorAccessDenied`、`TooManyRequests`）或兜底的 `HTTP_<status>`：Graph 返回非 2xx 时透传其错误码，退出码按下表映射

---

## 退出码

CLI 的退出码分两个波段：

| 波段 | 码 | 常量 | 语义 |
|---|---|---|---|
| 结果类（命令真的调了 API） | `0` | `EXIT_OK` | 成功 |
| | `1` | `EXIT_ERROR` | 一般错误；也是 Graph 4xx/5xx 里未特殊映射状态码（如 `429`、`500`）的兜底退出码 |
| | `2` | `EXIT_USAGE` | 参数/用法错误，或未登录（`CONFIG_ERROR`）——发出任何真实请求之前就失败 |
| | `3` | `EXIT_NOT_FOUND` | Graph 返回 `404` |
| | `4` | `EXIT_PERMISSION` | Graph 返回 `401`/`403`，或登录凭据已失效（`AUTH_EXPIRED`） |
| | `5` | `EXIT_PARTIAL` | 部分失败（`PARTIAL_FAILURE`，见专节） |
| | `6` | `EXIT_AUTH_PENDING` | 设备码轮询超时，用户仍未完成授权 |
| | `7`–`9` | — | 预留 |
| 模式类（命令没有真的调 API） | `10` | `EXIT_DRY_RUN` | `--dry-run` 预演成功 |
| | `11`+ | — | 预留 |

**为什么 `PARTIAL_FAILURE` 是 `5` 而不是 `11`**：波段划分的标准是「这次调用有没有真的发起请求」，不是「结果好不好」。`0`–`9` 的定义是「命令真的调用了 API，这是调用的结局」；触发 `PARTIAL_FAILURE` 的场景（`$batch` 子请求失败、分页或清单枚举被 `--max-pages` 截断）里 CLI 都**确实发出了真实的 HTTP 请求**，只是没能把结果拿全——这仍然是一次真实调用的（不完美）结局，因此归入 `0`–`9` 波段；`10`+ 专门留给像 `--dry-run` 这种**从头到尾没有发出任何请求**的模式，两者不能混淆。

---

## `PARTIAL_FAILURE`：全仓唯一携带 `data` 的失败信封

> **`PARTIAL_FAILURE` 是全仓唯一一种 `success: false` 仍然携带 `data` 的信封。** 其他所有错误信封都没有 `data` 键。Agent 处理错误时如果习惯性地跳过 `data` 字段，会在这一种情况下白白丢掉已经取到的数据。

触发条件（二选一，或两者叠加）：

1. 集合端点分页被 `--max-pages` 截断（`list-lists` / `list-checklist-items` / `list-tasks` 单清单模式）
2. `list-tasks --list all` 聚合时，`$batch` 里有清单子请求失败，或某清单自身分页 / 清单枚举本身被 `--max-pages` 截断

示例（`list-lists --max-pages 1`，第一页就有 `nextLink`）：

```json
{
  "success": false,
  "error": {
    "code": "PARTIAL_FAILURE",
    "message": "已取 1 页后触发 --max-pages 上限，结果不完整",
    "suggestion": "提高 --max-pages 或改用更窄的查询条件"
  },
  "data": [{"id": "L1"}],
  "metadata": {
    "command": "mstodo_cli list-lists",
    "took_ms": 45,
    "result_count": 1,
    "pages_fetched": 1,
    "truncated": true
  }
}
```

`list-tasks --list all` 场景下 `PARTIAL_FAILURE` 的 `message`/`suggestion` 会拼出更详细的情况说明（见「跨清单聚合」节）。

**`retry_after_seconds` 必须被尊重，不得立即重试**：批内被限流（`429`）的子请求不会由 CLI 自动重试，`retry_after_seconds`（若非 `null`）是已知失败清单里 `Retry-After` 头的最大值；在这个秒数之前重试大概率会再次被限流，而且被限流的请求本身仍计入 Graph 的用量限额，立即重试只会加剧限流。收到 `PARTIAL_FAILURE` 时应先处理/落盘 `data` 里已经到手的数据，再决定是否等待重试。

---

## 分页

- Graph 所有集合端点都是服务端强制分页（即使不传 `$top` 也会分页），CLI **默认跟完所有页**再返回，避免「只读首页导致数据静默残缺但信封仍是 `success:true`」。
- `--max-pages N`（`N>0`）触发上限时：`metadata.truncated` 为 `true`，退出码为 `5`（`PARTIAL_FAILURE`），`data` 中仍保留已取到的部分条目。
- `metadata.result_count` 永远是「本次实际跟到的条目总数」——分页完整时等于服务端总数，被截断时只是已取到部分的条数。
- `list-tasks` 的 `--status` 过滤**发生在分页完整跟完之后**：如果只过滤了首页就应用 `--status`，会在「首页全是已完成任务」的清单上把未完成任务漏掉且没有任何错误提示。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-lists --max-pages 1
```

---

## 跨清单聚合（`list-tasks --list all`）

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all --status notStarted,inProgress
```

`--list all` 是**二维分页**：

1. **第一维——清单枚举**：`GET /me/todo/lists`，本身受 `--max-pages` 约束，也会分页
2. **第二维——每个清单的任务**：先用一次 `$batch`（单批最多 20 个子请求，超过则分批）并发拿到每个清单的任务首页，再对带 `@odata.nextLink` 的清单串行跟续页（`$batch` 只能压缩首页请求，续页 URL 是运行时才知道的）；这一维同样受 `--max-pages` 约束

`listId` / `listDisplayName` 两个字段在**单清单模式和 `--list all` 聚合模式下都会被注入**到每个任务对象上（Graph 原生 `todoTask` 没有这两个字段）——如果只在聚合模式下注入，`--fields id,listId` 在单清单模式下会静默拿到裁剪后缺字段的结果。

`metadata.partial_failures` 里每一项都带 `reason`，三种取值互不相同、含义不能混淆：

| `reason` | 含义 | `data` 中是否有该清单已取到的数据 | `listId` |
|---|---|---|---|
| `"error"` | 该清单的 `$batch` 子请求硬失败（4xx/5xx 或响应缺失），或跟续页时失败（4xx/5xx 或网络错误，`status` 为 `0` 表示网络错误）。续页失败时该清单已取到的前几页也会丢弃 | 否 | 该清单的真实 id |
| `"truncated"` | 该清单自身的任务分页命中 `--max-pages` 上限 | 是（已取到的部分） | 该清单的真实 id |
| `"list_enumeration_truncated"` | 清单枚举本身（第一维分页）被 `--max-pages` 截断，本条不对应任何具体清单 | 不适用——未被枚举到的清单压根没有被尝试 | **`null`** |

> **遍历 `partial_failures` 做重试的 Agent 必须先看 `reason` 字段，再决定要不要用 `listId` 去重试**：`reason == "list_enumeration_truncated"` 的条目 `listId` 是 `null`，直接拿它当清单 id 重试会失败或产生错误请求。这条只在清单枚举被截断时出现，且只会出现一次。

`metadata.truncated` 的语义是「本次结果是否已知不完整」，只反映**分页/枚举截断**（`reason` 为 `"truncated"` 或清单枚举被截断时）；单纯的 `"error"` 硬失败不会把 `truncated` 置为 `true`（虽然仍会触发 `PARTIAL_FAILURE`）——两者是正交的两种不完整原因，判断「是否值得提高 `--max-pages` 重试」要看 `truncated`，判断「是否需要等待后重试某个清单」要看 `partial_failures` 里 `reason == "error"` 的条目。

示例（一个清单成功，一个清单被限流）：

```json
{
  "success": false,
  "error": {
    "code": "PARTIAL_FAILURE",
    "message": "已知 2 个清单中 1 个完整成功；1 个清单请求失败（data 中无对应数据）",
    "suggestion": "data 中已含目前已知的成功与部分数据；至少等待 30 秒后再重试失败清单，不要立即重试"
  },
  "data": [{"id": "T1", "listId": "L1", "listDisplayName": "工作"}],
  "metadata": {
    "command": "mstodo_cli list-tasks",
    "took_ms": 58,
    "result_count": 1,
    "aggregated_from": 2,
    "pages_fetched": 1,
    "partial_failures": [
      {"listId": "L2", "displayName": "个人", "status": 429,
       "retry_after": 30, "reason": "error"}
    ],
    "retry_after_seconds": 30,
    "all_auth_failed": false,
    "truncated": false,
    "list_enumeration_truncated": false
  }
}
```

**特例——`all_auth_failed`**：如果**全部**清单的 `$batch` 子请求都返回 `401`/`403`，这不算 `PARTIAL_FAILURE`，而是直接以 `HTTP_403` + 退出码 `4`（`EXIT_PERMISSION`）失败（提示检查登录账号与 `Tasks.ReadWrite` 授权），因为这种情况下没有任何数据可用，不是「部分」失败。只要有至少一个清单成功，即便其余全部 401/403，也仍归入 `PARTIAL_FAILURE`。

---

## Schema 自省

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py schema --all
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py schema create-task
```

`schema --all` 列出全部 6 个有请求体的操作：`create-list` / `update-list` / `create-task` / `update-task` / `create-checklist-item` / `update-checklist-item`。这 6 个之外的资源命令（`get-*` / `list-*` / `delete-*`）没有请求体，不出现在 schema 里。

单操作查询 `schema <操作>` 输出：

```json
{
  "method": "POST",
  "path": "/me/todo/lists/{listId}/tasks",
  "fields": {
    "title": {"type": "str", "required": true, "desc": "任务标题"},
    "body": {"type": ["str", "object"], "desc": "任务描述。传字符串会自动展开为 {content, contentType:'text'}。注意：Graph 的该字段名与 CLI 的 --body 选项同名但不是一回事——--body 是整个请求体，这里的 body 是请求体里的描述字段。"},
    "importance": {"type": "str", "enum": ["low", "normal", "high"], "desc": "优先级"},
    "dueDateTime": {"type": ["str", "object"], "desc": "截止时间。..."},
    "categories": {"type": "array", "items": "str", "desc": "Outlook 分类名数组，相当于标签"}
  }
}
```

- `type` 可能是**数组**（union），表示该字段接受多种类型之一，如 `body` / `dueDateTime` / `reminderDateTime` / `startDateTime` 都是 `["str", "object"]`（既能传字符串简写，也能传完整对象）
- `enum`：合法取值枚举（如 `importance` 的 `["low", "normal", "high"]`、任务 `status` 的 5 个取值）
- `items`：`type` 为 `"array"` 时数组元素类型
- `required`：仅 `create-*` 操作有必填字段；`update-*` 操作没有单字段必填，但整体上 `at_least_one: true`（至少传一个待更新字段，否则 `INVALID_PARAMETER`）
- 查询不存在的操作名（如 `move-tasks`——该操作本就未实现）会以退出码 `2` + `UNKNOWN_COMMAND` 失败，`suggestion` 里列出全部可用操作名
- `schema` 不需要登录即可使用

schema 未收录的字段（如 `linkedResources` / `attachments` / delta 查询）用 `raw` 子命令透传，见下节。

---

## 跨子命令行为约定

- **日期三种写法**（适用于 `dueDateTime` / `reminderDateTime` / `startDateTime`；`completedDateTime` 是只读字段，不出现在请求体里）：
  1. `"YYYY-MM-DD"`（自动补 `T00:00:00`）
  2. `"YYYY-MM-DDTHH:MM:SS"`（可含小数秒，自动补 `MSTODO_TIMEZONE` 指定的时区）
  3. 完整的 `{"dateTime": "...", "timeZone": "..."}` 对象（`timeZone` 同时接受 Windows 名如 `China Standard Time` 与 IANA 名如 `Asia/Shanghai`）

  日期字符串**形状不合法**（既不匹配 `YYYY-MM-DD` 也不匹配 `YYYY-MM-DDTHH:MM:SS`）时，CLI 在**发出任何请求之前**就以退出码 `2` + `INVALID_PARAMETER` 失败，不会把非法字符串透传给 Graph。

  ```bash
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list L1 \
    --body '{"title":"写周报","dueDateTime":"2026-04-05"}'
  ```

- **`body` 字段与 `--body` 选项的同名陷阱**：`--body` 是整条命令的请求体 JSON（外层）；`body` 是 Graph 任务对象内部的描述字段（`--body` JSON 里的一个 key）。传字符串会被自动展开为 `{"content": "...", "contentType": "text"}`；传对象则原样透传。

- **数组字段**：如 `categories`（字符串数组，相当于标签）、`checklistItems`（对象数组，元素形如 `{"displayName": "..."}`，仅 `create-task` 支持）在 `--body` JSON 中以数组形式传入。

- **校验顺序**：`--body` JSON 解析 → 必填字段/`at_least_one` 检查 → 逐字段类型与 `enum` 校验 → 日期与 `body` 字段展开（`normalize_body`）。以上全部**先于**登录态检查执行——也就是说，即使本机尚未登录，传一个非法的 `--body` 仍会先报 `INVALID_PARAMETER` 而不是 `CONFIG_ERROR`。

- **无交互**：CLI 始终无交互式提示、pager 或确认对话框，Agent 可安全在非交互环境下调用。

- **删除不可逆须先 `--dry-run`**：`delete-list` / `delete-task` / `delete-checklist-item` 在 API 层面没有撤销接口，执行前先用 `--dry-run` 确认目标路径无误。

- **不存在 `move-tasks` / `complete-task` 子命令**：跨清单移动任务与「标记完成」都通过 `update-task --body '{"status":"completed"}'`（或改写目标字段）完成，CLI 刻意没有提供额外的语义化快捷命令。

---

## 认证专节

登录采用 OAuth2 **设备码流**，拆成 `auth-start` / `auth-complete` 两步：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-start
# => {"data": {"user_code": "ABCD1234", "verification_uri": "https://microsoft.com/link",
#              "device_code": "...", "expires_in": 900, "interval": 5}, ...}

uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py auth-complete --device-code <上一步的 device_code>
```

**为什么拆成两步**：用户需要在浏览器里手动输入 `user_code` 并完成授权，这个动作的耗时完全由用户决定，可能是几秒也可能是几分钟。`auth-start` 立即返回（不阻塞），把 `user_code` 展示给用户；`auth-complete` 才是真正阻塞轮询等待授权结果的一步，且有明确的 `--timeout`（默认 **90 秒**，刻意小于调用方——即 Claude Code 工具调用——的 **120 秒**超时），保证 CLI 自己先于调用方超时返回一个明确的信封，而不是被调用方粗暴杀掉、什么信息都拿不到。

- 退出码 `6` + `AUTH_PENDING`：等待超时后用户仍未完成授权，这是**契约行为**而非异常——`suggestion` 会给出用**同一个 `device_code`** 再跑一次 `auth-complete` 的命令；超时不会破坏本机已有的登录态。
- 用户在浏览器里点了「拒绝」：`AUTH_DECLINED`，退出码 `1`，需要重新 `auth-start`。
- `device_code` 本身过期（通常 900 秒）：`AUTH_CODE_EXPIRED`，退出码 `1`，需要重新 `auth-start`。

`CONFIG_ERROR` 与 `AUTH_EXPIRED` 的区别：

| 错误码 | 退出码 | 含义 | 应采取的动作 |
|---|---|---|---|
| `CONFIG_ERROR` | `2` | 本机**从未**登录过（缓存不存在，或 `client_id`/`tenant` 变更导致缓存判定为不匹配） | 完整走一遍 `auth-start` → `auth-complete` |
| `AUTH_EXPIRED` | `4` | 本机**登录过**，但 `refresh_token` 刷新失败（凭据被吊销、超过 90 天未用、用户改了密码等） | 同样需要重新 `auth-start`（`auth-complete` 用不了旧的 `device_code`，因为这不是「等待中」而是凭据已彻底失效）——但因为「曾经登录过」这一事实本身是有意义的诊断信息，两者用不同错误码和退出码区分 |

其他细节：

- `auth-status` 报告当前登录状态（`logged_in` / `tenant` / `scope` / `expires_in_seconds` / `cache_path`），从不回显 `access_token` 本体；未登录时同样以 `CONFIG_ERROR` + 退出码 `2` 失败。
- `auth-logout` 删除本机 token 缓存，幂等（重复调用返回 `"removed": false` 而不是报错）。
- access token 剩余有效期低于 300 秒时，任何资源命令都会在请求前**透明自动刷新**并写回缓存，Agent 不需要手动处理续期。
- token 缓存文件权限 `0600`、所在目录权限 `0700`，原子写入（先写临时文件再 rename）。
