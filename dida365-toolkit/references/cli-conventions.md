# dida365-toolkit CLI 通用约定

本文档汇总 `dida365_cli.py` 跨所有子命令的统一约定。**任何 Skill 在使用 CLI 前都可参考本文档**，避免在每个 Skill 文档里重复同样的基础信息。Agent 在以下情况主动读取本文档：

- 第一次使用 dida365-toolkit 的任何子命令
- 需要了解 `--fields` / `--dry-run` 等通用选项的用法
- 需要解析响应信封或处理错误时
- 需要 Agent 自省参数 schema 时

---

## 前置条件

- **`DIDA365_API_TOKEN`**（必需）：在滴答清单网页版 头像→设置→账户与安全→API 口令 创建。未设置时所有子命令会以退出码 2 失败并提示。
- **`DIDA365_API_DOMAIN`**（可选）：国内版默认 `api.dida365.com`，国际版（TickTick）设为 `api.ticktick.com`。

设置方式由用户选择：`~/.claude/settings.json` 的 `env` 字段、shell 的 `export`、或其他 secrets 管理工具。首次配置请触发 `setup-guide` Skill。

---

## 调用方式

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py <子命令> [参数]
```

所有子命令均通过 `uv run` 触发，无需预装 Python 依赖（脚本头部 PEP 723 内联声明 `httpx`）。

---

## 通用全局选项

以下选项可附加在**任何子命令**之后：

### `--fields KEY[,KEY...]`

顶层字段掩码，逗号分隔。返回结果是 list 时逐项裁剪；是 dict 时保留指定 key。**返回大对象时优先使用**以保护 Agent 上下文窗口。

```bash
# 只取项目 id 和 name
uv run ... list-projects --fields id,name

# 任务筛选只取关键字段
uv run ... filter-tasks --priority 5 --fields id,title,dueDate,priority
```

未知字段会被静默丢弃；空字段串等同于不裁剪。

### `--dry-run`

只输出将要发起的 API 调用（不真正执行），退出码 `10`。响应 `data` 形如：

```json
{
  "would_call": "POST /open/v1/task/<taskId>",
  "body": { ... }
}
```

`metadata` 中会带 `"dry_run": true` 标识。**破坏性操作（`delete-*` / `update-*` / `move-tasks`）建议先 dry-run 预演**，确认请求路径与请求体无误后再正式调用。

---

## 响应信封

### 成功

```json
{
  "success": true,
  "data": <实际数据，结构由子命令决定>,
  "metadata": {
    "command": "dida365_cli <子命令名>",
    "took_ms": 234,
    "result_count": 12,
    "dry_run": true
  }
}
```

`metadata` 字段：

| 字段 | 出现条件 | 说明 |
|---|---|---|
| `command` | 总是 | 标识发起的子命令，便于回执溯源 |
| `took_ms` | 真实 API 调用时 | HTTP 往返耗时（毫秒） |
| `result_count` | data 是 list 时 | 列表长度，便于不解析 data 即可判断结果规模 |
| `dry_run` | 预演时 | 标识本次为 dry-run，未真正调用 API |

### 错误

```json
{
  "success": false,
  "error": {
    "code": "HTTP_401" | "CONFIG_ERROR" | "INVALID_PARAMETER" | "UNKNOWN_COMMAND" | ...,
    "message": "人类可读的错误描述",
    "suggestion": "可选——恢复建议"
  }
}
```

错误码语义：

- `CONFIG_ERROR`：环境变量未设置或配置无效
- `INVALID_PARAMETER`：参数不符合预期（如 update 时没传任何字段）
- `UNKNOWN_COMMAND`：schema 子命令查询不存在的子命令名
- `HTTP_<status>`：API 返回非 2xx 状态码（如 `HTTP_401` Token 无效）

---

## 退出码

| 码 | 语义 |
|---|---|
| `0` | 成功 |
| `1` | 一般错误（Agent 应报告给用户） |
| `2` | 参数/用法错误（Agent 应修正参数后重试） |
| `3` | 资源不存在（Agent 应跳过或创建） |
| `4` | 权限不足（401/403——Agent 应提示用户检查 Token） |
| `10` | dry-run 预演成功（Agent 据此决定是否正式执行） |

---

## Schema 自省

```bash
# 列出所有子命令的参数 schema
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py schema

# 查看单个子命令的 schema
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dida365_cli.py schema create-task
```

输出每个参数的 `name` / `dest` / `required` / `type` / `choices` / `default` / `help`。Agent 在不解析文本 `--help` 的情况下也可获取参数定义。

`type` 字段取值：`string` / `int` / `flag`（`--all-day` 等）/ `tristate-flag`（`--all-day / --no-all-day / 默认未指定`，仅 `update-task` 用）。

---

## 跨子命令的行为约定

- **逗号分隔参数**（如 `--tags`、`--projects`、`--tasks`、`--priority`、`--status`）：自动 `trim` 元素空白并丢弃空项。形如 `"3, 5,"` 与 `"3,5"` 等价。
- **日期参数**（`--due-date`、`--start-date`、`--end-date`）：同时支持简短 `YYYY-MM-DD`（CLI 自动补 `T00:00:00+0800`）和完整 ISO 8601（如 `2026-04-05T14:30:00+0800`）。需要小时/分钟粒度时使用后者。
- **无交互**：CLI 始终无交互式提示、pager 或确认对话框，Agent 可安全在非交互环境下调用。
- **删除/移动不可逆**：API 层面没有"撤销"接口，破坏性操作前先用 `--dry-run` 预演。
