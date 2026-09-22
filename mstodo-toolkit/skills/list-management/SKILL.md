---
name: list-management
description: |
  管理 Microsoft To Do 清单。当用户点名 "Microsoft To Do""MS To Do""微软待办"
  "微软 To Do"，或本次对话已在操作 Microsoft To Do，并要求查看所有清单、新建清单、
  重命名清单、删除清单时使用。操作清单里的任务请用 task-crud。
  若用户还装有其他待办工具、本轮未指明平台且上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# list-management：管理 Microsoft To Do 清单

本 skill 只负责清单（list）本身的增删改查——清单里的任务属于 `task-crud`。

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 查看所有清单 `list-lists`

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-lists \
  --fields id,displayName,wellknownListName,isOwner,isShared
```

`wellknownListName`、`isOwner`、`isShared` 三个字段应当**始终**进入 `list-lists` 的 `--fields`，不要只取 `id,displayName`——它们分别决定了本 skill 下面两节要做的前置检查，省掉它们会让检查无从下手，只能再补一次请求。

## `update-list` / `delete-list` 之前必须先读 `wellknownListName`（内置清单保护，不可跳过）

这是本 skill 唯一一条**不可跳过的前置检查**，不是提醒，是执行顺序的一部分：**任何 `update-list` 或 `delete-list` 调用之前，先跑一次上面的 `list-lists --fields id,displayName,wellknownListName,isOwner,isShared`，确认目标清单的 `wellknownListName`。**

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-lists \
  --fields id,displayName,wellknownListName,isOwner,isShared
```

拿到结果后按 `wellknownListName` 的取值分流：

| `wellknownListName` | 含义 | 能否 `update-list` / `delete-list` |
| --- | --- | --- |
| `none` | 用户自建清单 | 可以 |
| `defaultList` | 内置「任务」清单 | **不可以**——官方明确内置清单不可改名、不可删除，调用必然失败 |
| `flaggedEmails` | 内置「已标记的邮件」清单 | **不可以**，同上 |

如果目标清单命中 `defaultList` 或 `flaggedEmails`，**直接停下、告诉用户这个限制**，不要发请求让用户吃一个原始的 Graph 报错——用户体验上"我们已经知道这个限制、不必浪费一次往返去验证它"，比"发出去再翻译错误信息"更清楚。

Task 0 探针实测佐证：探针实际读到的账号首个清单为 `displayName='任务'`、`wellknownListName='defaultList'`，确认该字段在真实账号上可读、且与这条限制一致。

## `isOwner: false`：这是别人共享给你的清单

`list-lists` 结果里 `isOwner: false` 的清单，是别人共享给当前用户的，不是用户自己创建的。对这类清单执行删除，行为与自有清单不同——**删除共享清单通常只是把它从当前用户视图里移除，不代表把原清单从对方账号里抹掉**（具体行为以 Graph 实际返回为准，不要替用户假设）。操作这类清单前，先把 `isOwner: false` 这件事告诉用户，让用户明确知道自己动的不是自己独有的东西，再决定是否继续。

## Graph v1.0 没有共享管理 API

用户如果要求"把某个清单分享给谁"，**这个能力本插件做不到，Graph v1.0 本身也没有提供**——`todoTaskList.isOwner` / `isShared` 只是只读字段，反映当前共享状态，没有对应的邀请协作者、移除协作者、修改权限的写接口。遇到这类请求直接告知用户：分享/取消分享清单只能在 Microsoft To Do 客户端（网页版或 App）里完成，CLI 和本 skill 都无法代劳。

## 新建清单 `create-list`

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py schema create-list

uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-list \
  --body '{"displayName":"读书清单"}'
```

`displayName` 是唯一必填字段。构造 `--body` 前建议先跑一次 `schema create-list` 确认字段。

`create-list` 响应里返回的 `id` 就是新清单的 `listId`——如果建这个清单是为了接收 `task-organize` 移动过来的任务（比如用户要求"归档到一个新建的清单"），把这个 `id` 原样带给 `task-organize` 当目标清单 `--list` 用，不需要再另外查一次。

## 重命名清单 `update-list`（前置检查见上文）

确认目标清单不是内置清单之后：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-list --list <listId> \
  --body '{"displayName":"读书清单（2026）"}'
```

## 删除清单 `delete-list`（不可逆，会连带删除所有任务，必须先 `--dry-run`）

`delete-list` 删除的不只是清单本身，**清单里的所有任务会被一并删除**，且在 API 层面没有撤销接口——这是本 skill 风险最高的操作。确认目标清单不是内置清单（见上文前置检查）之后，**先 `--dry-run` 预演，确认目标路径无误再真正执行**：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-list --list <listId> --dry-run
```

`--dry-run` 只输出将要发起的调用、不真正执行，退出码固定为 `10`（`EXIT_DRY_RUN`），表示"预演成功"而不是错误。确认无误后去掉 `--dry-run` 再真正执行：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-list --list <listId>
```

删除前，如果清单里还有任务，建议先用 `task-query` 或 `list-checklist-items` 确认这些任务是否需要先迁移——迁移到其他清单属于 `task-organize` 的职责，本 skill 不做。

## 通用注意事项（所有子命令都适用）

### 退出码 `5`（`PARTIAL_FAILURE`）

退出码 `5` 表示**部分失败**：`success` 是 `false`，但 `data` 里**仍有已取到的数据**。不要把它当纯错误丢弃，也不要把残缺数据当全量用。`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。本 skill 里 `list-lists` 是集合端点，理论上可能触发这个错误码；`get-list`/`create-list`/`update-list`/`delete-list` 不是集合端点，一般不会触发，但仍需了解这条约定，因为它是全仓通用契约的一部分。

### 不要盲目重试

本 skill 调用的子命令里，明确"可重试"的只有两种情况：退出码 `6`（`AUTH_PENDING`，属于 `setup-guide` 的登录流程）、退出码 `5` 且 `metadata.retry_after_seconds` 给出了等待时长。**其余非 0 退出码（如 `2` 的 `INVALID_PARAMETER`、`3` 的"未找到"、`4` 的 `AUTH_EXPIRED`，以及内置清单触发的 `update-list`/`delete-list` 失败）都是终态失败**，遇到时先停下来读 `error.suggestion`，而不是换个参数再试一次。

## 边界

- 操作清单里的任务（创建、查看、修改、删除、勾选子任务）→ 转 `task-crud`
- 把任务从一个清单移到另一个清单、批量归类、打标签 → 转 `task-organize`
- 需要按条件查找、统计清单内任务 → 转 `task-query`
- 遇到退出码 `2` + `CONFIG_ERROR` 或退出码 `4` + `AUTH_EXPIRED` → 转 `setup-guide` 完成（重新）登录
