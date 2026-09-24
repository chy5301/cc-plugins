---
name: daily-review
description: |
  Microsoft To Do 每日回顾与规划。当用户点名 "Microsoft To Do""MS To Do"
  "微软待办""微软 To Do"，或本次对话已在操作 Microsoft To Do，并问"今天要做什么"
  "有什么逾期的""任务概览""帮我规划今天"时使用。按任意自定义条件查找或统计任务
  请用 task-query。若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，
  先向用户确认再执行。
version: 0.1.1
---

# daily-review：Microsoft To Do 每日回顾与规划

本 skill 是**固定视角**："今天要做什么" / "有什么逾期的" / "帮我规划今天"——只读、只呈现，不做任意条件的筛选。**任意自定义筛选条件（按分类、按优先级、按任意状态组合、统计数量等）属于 `task-query`，不属于本 skill**；两者共用同一条 `list-tasks --list all` 聚合能力，区别只在于本 skill 的查询条件是写死的每日回顾条件。

## 只读边界

本 skill **只查询、只呈现，不修改任何任务**。回顾中发现任务该完成、该延期、该改优先级，都只是在报告里提示用户，交由用户自己决定；不要顺手调用 `update-task` 帮用户改状态——那是 `task-status` 的职责，且未经用户明确要求就修改数据违背"回顾"这个动作本身的预期。

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效，或全部清单权限不足触发的 `HTTP_403`），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。注意：退出码 `4` 但错误码**不是** `AUTH_EXPIRED`（例如 Graph 返回 `403` 的 `ErrorAccessDenied`，常见于对别人共享给你的清单没有写权限）时，重新登录解决不了问题，不要转 `setup-guide`，应把 `error.message` 转述给用户（`list-tasks --list all` 全部清单都返回 `401`/`403` 时报的 `HTTP_403` 除外，那是授权问题，仍转 `setup-guide`）。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 固定流程：两条命令取全量候选集与清单归属

每日回顾的命令和条件是写死的：

```bash
# 1. 全量候选集
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all \
  --status notStarted,inProgress,waitingOnOthers \
  --fields id,title,status,importance,dueDateTime,listId,listDisplayName

# 2. 清单归属：哪些清单是别人共享给用户的
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-lists --fields id,displayName,isShared
```

- `--list all` 触发跨清单聚合，这是**二维分页**：第一维是清单枚举本身，第二维是每个清单内的任务分页，两维都跟完（或都命中 `--max-pages` 截断）聚合结果才算数
- `--status notStarted,inProgress,waitingOnOthers` 把已完成（`completed`）和已挂起（`deferred`）的任务排除在候选集之外——回顾关心的是"还要处理的事"
- 第 1 条的 `--fields` 覆盖了分档、展示、识别"卡在别人身上"所需的字段；`listId` 用来和第 2 条的结果关联
- 第 2 条是必须的："是否共享"是清单的属性（`isShared`），任务上没有，只看 `listDisplayName` 无法判断，见下文「共享清单里的任务不等于"你的任务"」

拿到结果后，**分档、呈现、标记 `waitingOnOthers` 全部在 Agent 侧完成**，CLI 不提供这些语义化能力。

## 按 `dueDateTime` 分三档：已逾期 / 今天到期 / 未来

拿到候选集后，按每个任务的 `dueDateTime` 分三档展示：已逾期、今天到期、未来（`dueDateTime` 为空的任务单独列一类"未设截止日期"，不要漏掉或硬塞进某一档）。

**分档前必须先把 `dueDateTime` 换算回本地时区，再取日期部分比较——直接用 Graph 回显的 UTC 日期会在跨日边界上错一天**。原因（Task 0 探针 P6 实测结论）：

- `dueDateTime` 提交时可以带 `+08:00` 等时区，但 Graph **回显时一律归一化为 `UTC`，且日期粒度保留、具体时刻被丢弃**（当作提交日期的当地零点处理，再转 UTC）。例如提交 `{"dateTime": "2026-12-31T09:00:00", "timeZone": "Asia/Shanghai"}`，回显是 `{"dateTime": "2026-12-30T16:00:00", "timeZone": "UTC"}`。
- 如果直接拿回显的 `2026-12-30` 当"到期日"用，会比用户实际设置的 `12-31` 早一天——**必须先按 `MSTODO_TIMEZONE`（默认 `Asia/Shanghai`）把回显的 UTC 时刻换算回本地时区，再取换算后的日期部分**做"今天 / 逾期 / 未来"的比较，不能对 UTC 字符串直接做日期截取或字符串比较。
- 换算回本地时区后得到的时刻不是原始提交的具体时刻（时刻已被丢弃、统一为当地零点），但**日期是准的**，分档只需要日期，这一步足够。

## 单独列出 `waitingOnOthers`

候选集里 `status == "waitingOnOthers"` 的任务要**从三档展示里摘出来单独成组**，并提示用户"这些卡在别人身上"——这是 Microsoft To Do 相对滴答清单的独有语义（滴答没有对应状态），回顾场景下应当被突出，而不是混进"未来"或按截止日期随便归档。一个任务如果同时落在某个日期档位又是 `waitingOnOthers`，仍按 `waitingOnOthers` 单独展示优先，因为"卡在别人身上"比"哪天到期"对用户更有行动指导意义。

## 截断信号：三个键必须一起看，回顾场景下尤其危险

`list-tasks --list all` 的 `metadata` 固定带 10 个键，其中三个直接关系到"这份回顾完不完整"：

| 键 | 含义 |
|---|---|
| `truncated` | 布尔。结果集已知不完整（不论哪一维分页被截断）就是 `true` |
| `list_enumeration_truncated` | 布尔。清单枚举本身被 `--max-pages` 截断——**有些清单压根没被纳入这次回顾**，不是取了没取全，而是根本没尝试 |
| `partial_failures` | 数组，每项有 `reason`：`"error"`（该清单硬失败，无数据）/ `"truncated"`（该清单分页被截断，有部分数据）/ `"list_enumeration_truncated"`（伪条目，**`listId` 为 `null`**，标记清单枚举本身被截断这件事） |

**如果要基于 `partial_failures` 做任何后续动作（比如提示用户"再查一次某个清单"），先看 `reason`**：`reason == "list_enumeration_truncated"` 的条目 `listId` 是 `null`，不对应具体清单，不能拿去重试或点名某个清单。

**退出码 `5`（`PARTIAL_FAILURE`）复述**：`success` 是 `false`，但 `data` 里仍有已取到的数据，不要当纯错误丢弃，也不要把残缺数据当全量用；`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。**其余非 0 退出码都是终态失败**（明确可重试的只有退出码 `6` 的 `AUTH_PENDING`、退出码 `5` 且给出 `retry_after_seconds` 的情况，以及退出码 `1` 的 `AUTH_REFRESH_FAILED` / `NETWORK_ERROR`（暂时性故障，稍等片刻重试一次即可）），遇到时先停下读 `error.suggestion`，不要换参数硬试。

**为什么这对 `daily-review` 比对 `task-query` 更危险**：`daily-review` 的产出是直接给用户看的"今天要做什么"。如果数据残缺却不声明，用户会把这份不全的列表当成全部——漏看的任务可能就是今天最要紧的那件。所以只要 `truncated` 为 `true`，或 `partial_failures` 非空，**回顾报告的开头就必须明确写出"有 N 个清单没有取到完整数据"**（N 可以数 `partial_failures` 里 `reason` 为 `"error"` / `"truncated"` 的条目，加上 `list_enumeration_truncated` 为真时未被枚举到的清单），不能默默呈现一份看起来完整、实际不全的清单。这条比一般 skill 里"提一下退出码 5"的要求更严格：**这里是必须做、且要放在报告最前面的动作，不是可选的免责声明**。

## 共享清单里的任务不等于"你的任务"

候选集包含**所有**清单，其中也包括别人共享给用户的清单。Graph 不返回任务负责人，共享清单里的任务可能大部分分给了别人。呈现时：

- 不要把候选集笼统称为"你今天要做的事"。如果结果里有共享清单的任务，用任务的 `listId` 对上第 2 条命令结果里 `isShared` 为 `true` 的清单，按 `listDisplayName` 注明来源，并提醒用户共享清单的任务无法区分负责人
- 用户追问"哪些是分配给我的"→ 转 `task-query`，按其中"分配给我的任务"一节处理，不要在本 skill 里猜

## 边界

- 用户要按分类、优先级、自定义状态组合筛选，或要统计任务数量 → 转 `task-query`（本 skill 只做固定的"今天/逾期"视角）
- 回顾中发现要**改**任务状态或优先级（比如用户看完想标记完成） → 转 `task-status`，不要在本 skill 里自作主张改
- 回顾中发现要**改**标题/描述/截止日期，或增删子任务 → 转 `task-crud`
- 需要按 `categories` 对已有任务做归类整理，或跨清单移动任务 → 转 `task-organize`
- 遇到退出码 `2` + `CONFIG_ERROR`，或退出码 `4`（`AUTH_EXPIRED`，或全部清单权限不足触发的 `HTTP_403`）→ 转 `setup-guide`
