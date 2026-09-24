---
name: task-query
description: |
  筛选和查询 Microsoft To Do 任务。当用户点名 "Microsoft To Do""MS To Do"
  "微软待办""微软 To Do"，或本次对话已在操作 Microsoft To Do，并要求跨清单
  查找任务、按状态筛选、查看已完成任务、按优先级或分类筛选、统计任务数量、
  查看分配给自己的任务时使用。
  "今天要做什么""有什么逾期的"这类固定的每日视角请用 daily-review。
  若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# task-query：筛选和查询 Microsoft To Do 任务

本 skill 只读，负责按任意条件在一个或全部清单里查找、筛选、统计任务。**"今天/逾期"这个固定的每日视角属于 `daily-review`，不属于本 skill**——两者共用同一条 `list-tasks --list all` 聚合能力，区别只在于筛选条件是任意的（本 skill）还是固定的（`daily-review`）。

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。注意：退出码 `4` 但错误码**不是** `AUTH_EXPIRED`（例如 Graph 返回 `403` 的 `ErrorAccessDenied`，常见于对别人共享给你的清单没有写权限）时，重新登录解决不了问题，不要转 `setup-guide`，应把 `error.message` 转述给用户（下文「退出码 `4`：全部清单权限不足」一节是例外，那种情况仍转 `setup-guide`）。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 跨清单聚合：`list-tasks --list all`

按条件查找任务，多数时候要看全部清单而不是单个清单，用 `--list all`：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all \
  --fields id,title,status,importance,dueDateTime,listDisplayName
```

`--list <单清单id>` 也可用，用于已知只关心一个清单的场景。

**`--list all` 是二维分页，不是一次简单调用**：

1. **第一维——清单枚举**：先拿到全部清单列表，这一维本身也会分页，也受 `--max-pages` 约束
2. **第二维——每个清单内的任务**：对枚举到的每个清单分别跟完自己的分页

两维都跟完（或都命中 `--max-pages` 上限）之后，聚合结果才算数。这意味着"结果条数少"不一定是真的少，也可能是某一维被截断——判断依据见下方「截断信号」一节，不要只看返回条数就下结论。

`listId` / `listDisplayName` 两个字段是 CLI 在聚合时注入到每个任务对象上的（Graph 原生任务对象没有这两个字段），单清单模式下也会注入，可以放心用 `--fields` 掩码保留它们。

## `--fields` 是必须项，不是可选项

Graph 的 task 对象字段比滴答清单丰富得多，不加掩码会把大量用不上的字段塞进上下文，挤占窗口。**查询类调用起手式**：

```bash
--fields id,title,status,importance,dueDateTime,listDisplayName
```

需要更多字段（如 `categories`、`body`）时按需追加，但不要省略 `--fields` 直接裸调用 `list-tasks --list all`。

## `--status` 过滤发生在分页跟完之后，结果可信

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-tasks --list all \
  --status notStarted,inProgress \
  --fields id,title,status,importance,dueDateTime,listDisplayName
```

`--status` 是逗号分隔的 `taskStatus` 枚举过滤（合法值：`notStarted` / `inProgress` / `completed` / `waitingOnOthers` / `deferred`），CLI **先把每个清单的分页完整跟完，再对全量结果应用 `--status`**，不是"只看首页就过滤"。所以只要命令没有触发 `PARTIAL_FAILURE`（退出码 `5`），过滤后的结果就是可信的全量，不会因为某个清单首页恰好全是已完成任务而把未完成任务漏掉。

## 不加 `--status` 会连已完成任务一起返回——这是有意为之

Graph 的 tasks 集合本身就包含 `completed` 状态的任务，**不是 CLI 的 bug**。想看"未完成任务"必须显式传 `--status`，例如 `--status notStarted,inProgress,waitingOnOthers,deferred`；想统计已完成任务数量，反过来只传 `--status completed`。裸调用 `list-tasks --list all` 且不传 `--status` 是查看"全部任务（含已完成）"的正确方式，不需要额外解释成异常结果。

## "分配给我的任务"：接口无法区分负责人

Graph 不返回任务的负责人（见 `${CLAUDE_PLUGIN_ROOT}/references/api-reference.md`「Graph 没有的能力」节）。To Do 应用里在共享清单中"分配给某人"的信息、以及"已分配给我"智能列表，接口都拿不到。用户问"分配给我的任务有哪些"时：

1. **不要把共享清单里的全部任务当成"分配给我的"**。共享清单是整个团队的任务池，其中大部分可能分给了别人。也不要根据标题或备注的口吻（如"这个你要……"）去猜负责人——这类线索只说明是写给某个执行人的，看不出是谁。
2. **先如实说明限制**，再给出能确定的部分：用 `list-lists --fields id,displayName,isShared,isOwner` 区分清单归属。`isShared` 为 `false` 的清单只有用户自己能看到，其中的任务可以确定是用户自己的；共享清单（`isShared: true`）里的任务只能列为"共享清单中的任务，无法区分负责人"。
3. **请用户提供区分规则**，常见做法有：
   - 用户在应用的"已分配给我"列表里看一眼，把标题或关键词告诉你，再按标题查找
   - 团队约定一个接口看得到的标记：分类（`categories`）里带执行人名字，或标题加 `【姓名】` 前缀——之后按下一节的客户端筛选做法过滤
   - 按执行人拆分清单（如「项目-姓名」），之后按 `listDisplayName` 筛选
4. 用户给出规则后，按规则在客户端过滤；规则本身无法 100% 覆盖（例如有人分配时忘了加前缀）时，要在结果里注明。

## 按 `categories` / `importance` 筛选目前是客户端行为

CLI 没有提供 `--categories` / `--importance` 这类专用筛选参数。要按分类或优先级筛选，做法是：先用 `--list all --fields ...`（掩码里带上 `categories` 或 `importance`）取回候选集合，再在 Agent 侧自行按字段值过滤，不要假设服务端已经按这些字段筛过。

**`$select` 与 `$filter` 在 Graph 端的实测结论（Task 0 探针 P2，务必按此表述，不要写成可用能力）**：

- `$select=id,title` 实测返回 `400 invalidRequest`——服务端字段选择**不可用**，这也是为什么 `--fields` 只能在 CLI 客户端裁剪，而不是下推到 Graph。
- `$filter=status eq 'notStarted'` 实测返回 `200`，但**这只证明请求被 Graph 接受，不证明返回集真的被过滤过**——探针没有验证返回条目是否确实符合过滤条件，部分 Graph 端点会接受并静默忽略不支持的查询参数。因此本插件的 `--status` 维持客户端过滤（分页跟完之后再过滤，见上文），**不要把 `$filter` 的 `200` 响应当成"服务端过滤已验证可用"**，也不要建议用户改用 `raw` 子命令把过滤下推到 `$filter`——这个能力没有被证实，赌错的后果是"筛出的结果实际上没被过滤，却被当成已过滤的结果使用"。

## 截断信号：三个键必须一起看

`list-tasks --list all`（以及单清单模式）的 `metadata` 固定带 10 个键，其中三个直接关系到"这份查询结果完不完整"：

| 键 | 含义 |
|---|---|
| `truncated` | 布尔。**只要结果集已知不完整**（不论是哪一维分页被截断）就是 `true`；单纯某个清单硬失败（`reason: "error"`）不会把它置真 |
| `list_enumeration_truncated` | 布尔。**清单枚举本身**（第一维分页）被 `--max-pages` 截断——意味着有些清单**压根没有被纳入本次聚合**，不是"取了但没取全"，而是"根本没尝试" |
| `partial_failures` | 数组。每一项都有 `reason` 字段，三种取值互不相同：`"error"`（该清单 `$batch` 子请求硬失败，`data` 里没有它的数据）、`"truncated"`（该清单自身任务分页命中上限，`data` 里有已取到的部分）、`"list_enumeration_truncated"`（**伪条目**，标记清单枚举被截断这件事本身，不对应任何具体清单） |

**遍历 `partial_failures` 时先看 `reason` 再决定动作，尤其是想对失败清单重试的场景**：`reason == "list_enumeration_truncated"` 的那一条 `listId` 固定是 `null`——这不是数据缺失，而是这条本来就不指代任何清单。拿它当清单 id 去发请求（例如重新 `list-tasks --list <listId>`）会失败或发出错误请求。只处理 `reason == "error"` 或 `"truncated"` 且 `listId` 非空的条目才有重试意义。

## 退出码 `5`（`PARTIAL_FAILURE`）：残缺数据仍要用，但不能当全量

退出码 `5` 表示**部分失败**：`success` 是 `false`，但 `data` 里**仍有已取到的数据**。不要把它当纯错误丢弃，也不要把残缺数据当全量用——先按上一节的三个截断信号判断残缺程度，再决定是直接把已取到的部分呈现给用户（并说明不完整），还是提高 `--max-pages` 后重新查询。`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。

## 不要盲目重试

本 skill 调用的 `list-tasks` 里，明确"可重试"的只有三种情况：退出码 `6`（`AUTH_PENDING`，属于 `setup-guide` 的登录流程，本 skill 不会遇到）、退出码 `5` 且 `metadata.retry_after_seconds` 给出了等待时长、退出码 `1` 且错误码为 `AUTH_REFRESH_FAILED` 或 `NETWORK_ERROR`（暂时性故障，稍等片刻重试一次即可）。**其余非 0 退出码都是终态失败**（如退出码 `2` 的 `INVALID_PARAMETER`、退出码 `3` 的"未找到"），遇到时先停下来读 `error.suggestion`，而不是换个参数再试一次。

## 退出码 `4`：全部清单权限不足

`list-tasks --list all` 如果**全部**清单的子请求都返回 `401`/`403`，CLI 不会走 `PARTIAL_FAILURE`（因为没有任何数据可用），而是直接以 `HTTP_403` + 退出码 `4` 失败——语义等同于凭据/授权出了问题。遇到退出码 `4`（不论是这种全部清单权限不足，还是常规的 `AUTH_EXPIRED`）一律转 `setup-guide` 完成（重新）登录。只要至少有一个清单成功，即便其余清单全部 `401`/`403`，仍归入 `PARTIAL_FAILURE`（退出码 `5`），按上文处理，不转 `setup-guide`。

## 边界

- **固定的"今天/逾期"每日视角** → 转 `daily-review`，不要在本 skill 里现场拼装这套流程
- 查到任务后需要**改**标题/描述/截止日期，或增删子任务 → 转 `task-crud`
- 需要**改**任务状态或优先级 → 转 `task-status`
- 需要按 `categories` 对已有任务做归类整理，或跨清单移动任务 → 转 `task-organize`
- 遇到退出码 `2` + `CONFIG_ERROR`，或退出码 `4`（`AUTH_EXPIRED`，或本文「退出码 4」一节所述的全部清单权限不足）→ 转 `setup-guide`
