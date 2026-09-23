---
name: task-organize
description: |
  整理 Microsoft To Do 任务：在清单间移动任务、增删分类标签。当用户点名
  "Microsoft To Do""MS To Do""微软待办""微软 To Do"，或本次对话已在操作
  Microsoft To Do，并要求把任务移到另一个清单、批量归类、打标签或改分类时使用。
  新建或删除单个任务请用 task-crud。若用户还装有其他待办工具、本轮未指明平台且
  上下文无法确定，先向用户确认再执行。
version: 0.1.0
---

# task-organize：在清单间移动任务、增删分类标签

**这是全插件风险最高的 skill。** 移动任务在 Graph 里没有原子操作，本 skill 要求你（Agent）在删除原任务之前完成一系列检查与确认——跳过任何一步都可能造成不可逆的数据丢失。

## 前置条件

遇到退出码 `2`（`CONFIG_ERROR`，本机从未登录）或退出码 `4`（`AUTH_EXPIRED`，凭据已失效），转入 `setup-guide` 完成（重新）登录后再继续，不要在本 skill 里自行处理认证。注意：退出码 `4` 但错误码**不是** `AUTH_EXPIRED`（例如 Graph 返回 `403` 的 `ErrorAccessDenied`，常见于对别人共享给你的清单没有写权限）时，重新登录解决不了问题，不要转 `setup-guide`，应把 `error.message` 转述给用户。

第一次使用本插件任何子命令前，建议先读 `${CLAUDE_PLUGIN_ROOT}/references/cli-conventions.md`，了解响应信封、全局选项与退出码的通用约定。

## CLI 工具路径

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py <子命令> [参数]
```

## 为什么没有 `move-tasks` 子命令

**Graph 没有"移动任务"这个端点。** 要把一个任务从清单 A 挪到清单 B，唯一的办法是在 B 里 `create-task` 建一个新任务，再在 A 里 `delete-task` 删掉旧任务——这是"删了重建"，不是原子操作，中途失败会有损。本插件的 CLI **刻意不提供** `move-tasks` 这样的语义化快捷命令，因为那会把一个不可原子、失败有损的写事务藏在一个看起来像原子操作的命令名后面，掩盖了真实风险。

移动的编排交给你（Agent）来做，理由是：**你能在中途停下来问用户**，CLI 脚本做不到这一点——遇到黑名单命中、或第 2 步创建失败，你可以中止并汇报，而不是像脚本那样要么全做完要么裸抛异常。

## 第 0 步：先查黑名单（在任何写操作之前）

移动任务前，先用 `get-task` 取回源任务，检查是否命中以下任意一项：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-task --list <源清单id> --task <taskId>
```

| 命中项 | 后果 | 处置 |
| --- | --- | --- |
| `hasAttachments: true` | 附件**无法迁移**，删除原任务后附件不可恢复 | **停下**，告知用户，由用户决定是否继续 |
| 源清单 `wellknownListName == "flaggedEmails"` | 该清单里的任务**全部**带邮件回链，移动会永久丢失这个回链 | **停下**，强烈建议不要移动 |
| `linkedResources` 非空 | 同上，任务与外部资源（如邮件、文件）的回链会丢失 | **停下**，告知用户具体会丢什么 |

`hasAttachments` 是 `get-task` 直接返回的字段，可以在上面这条命令的结果里直接看到。源清单的 `wellknownListName` 需要另外查（见下方 `list-management` 边界一节，或直接 `list-lists --fields id,displayName,wellknownListName` 核对源清单）。

`linkedResources` 本插件 schema 未收录，`get-task` 的字段掩码里没有它，检查它要用逃生舱 `raw`：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py raw --method GET \
  --path "/me/todo/lists/<源清单id>/tasks/<taskId>/linkedResources"
```

**这一步不能跳过、也不能因为"看起来像个普通任务"就省略**——附件和回链在 `get-task` 默认视图里不一定显眼，唯一可靠的判断依据就是这张表列出的三个信号。命中任意一项都必须先停下来跟用户确认，而不是自行判断"应该没关系"就继续。

## 第 1–3 步：先建后删，确认新 id 之后才删旧任务

通过黑名单检查（或用户明确同意继续）之后，按顺序执行：

**第 1 步**：取回源任务的全量字段与子任务。

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-task --list <源清单id> --task <taskId>
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py list-checklist-items --list <源清单id> --task <taskId>
```

**目标清单必须已存在**：第 2 步的 `--list <目标清单id>` 要求这个 `listId` 已经真实存在。如果用户要求"移到一个新建的清单"（比如"归档到一个新的『归档』清单"），**先转 `list-management` 用 `create-list` 建好目标清单、拿到返回的新 `id`**，再回来用这个 `id` 继续第 2 步——不要在 `task-organize` 里自行推断或跳过建清单这一步，这两个 skill 的定位就是不用互相猜。

**第 2 步**：在目标清单 `create-task`，把标题、描述、日期、优先级、分类等字段与子任务一并带过去。Task 0 探针实测：`create-task` 的请求体里内联 `checklistItems` 数组会被 Graph 真实落地（不是被静默忽略），所以子任务和主任务**一次 `create-task` 请求就能一起带过去**，不需要先建任务再逐个补子任务：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list <目标清单id> \
  --body '{"title":"...","importance":"...","status":"...","dueDateTime":{...},"checklistItems":[{"displayName":"..."}]}'
```

**确认这条命令的响应里确实返回了新任务的 `id` 之后**，才能进行第 3 步——这是整个编排里最关键的停止点。如果 `create-task` 失败、或响应里没有拿到新 id，**立刻停下，不要执行任何删除**，把失败情况报告给用户，原任务原样保留在源清单里。

**第 3 步**：仅在拿到新任务 id 之后，删除源清单里的旧任务，且同样先 `--dry-run` 预演：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-task --list <源清单id> --task <taskId> --dry-run
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py delete-task --list <源清单id> --task <taskId>
```

### 第 3 步失败或超时：这时候是"可能多一份"，不是"可能丢了"

第 2 步失败的处置很明确（见上文：立刻停下，原任务原样保留）。但**第 3 步 `delete-task` 失败或超时是编排里第二个真正危险的分支**，处置方式完全不同——因为此时新任务**已经建好、已经拿到新 id 了**，数据不存在丢失的可能，唯一的不确定性是"旧任务到底删没删掉"。遇到这种情况：

1. **不要慌，也不要盲目重试删除**，更不要因为"移动看起来失败了"就重新跑一遍第 1–2 步——那样只会在目标清单里再建出第三份。
2. **用旧的 `listId`/`taskId` 跑一次 `get-task` 确认真实状态**：

   ```bash
   uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-task --list <源清单id> --task <taskId>
   ```

3. 如果旧任务**仍在**（`get-task` 能查到）：说明删除确实没成功，**只重试第 3 步这一次删除**，不要碰第 1、2 步。
4. 如果旧任务**已不在**（`get-task` 返回"未找到"）：说明移动其实已经成功，`delete-task` 报的错很可能只是响应丢失或超时，不是删除本身失败——不需要再做任何事。
5. 无论落在哪种情况，都要把"当前是多一份还是已经完成"明确报告给用户，不要让用户以为移动失败了但实际上任务已经在新清单里。

第 1 步（`get-task` / `list-checklist-items` 读取）失败则简单得多：这两条都是只读操作，不涉及任何写入，原任务不受影响，直接重试或中止都是安全的。

### 顺序不可颠倒

**先建后删，是因为两种失败方向的后果完全不对称**：

- 如果第 2 步（建）失败，原任务还在源清单里，什么都没丢——大不了重试一次第 2 步。
- 如果顺序反过来，先删后建，一旦"建"这一步失败，任务就**真的消失了**，没有任何办法恢复（`delete-task` 在 API 层面没有撤销接口）。

所以本 skill 的编排固定是"先建、确认成功、再删"，任何情况下都不允许为了省一步检查而颠倒这个顺序，也不允许在没拿到新 id 前就删旧任务。

### 任务 `id` 移动后会变

新建出来的任务 `id` 和原任务的 `id` 是两个不同的值（Graph 官方原文：任务从一个清单移动到另一个清单后 `id` 会变化）。移动完成后，**后续所有对这个任务的操作都要用新清单里的新 id，不要拿旧 id 继续操作**——旧 id 对应的任务已经被删除，拿它去 `get-task`/`update-task` 只会得到"未找到"。

## 批量移动：逐个走完整三步，不省检查

一次移动多个任务时，**每一个任务都要独立走完第 0–3 步的完整流程**，不要因为前几个任务顺利就对后面的任务跳过黑名单检查——每个任务的 `hasAttachments`/`linkedResources` 状态互不相同，不能用前一个任务的检查结果替代当前任务的检查。

```bash
for taskId in T1 T2 T3; do
  # 对每个 taskId 分别执行：第 0 步黑名单检查 → 第 1 步取回 → 第 2 步 create-task
  # → 确认新 id → 第 3 步 --dry-run 再 delete-task
  :
done
```

上面只是示意逐个处理的形状，不是可以直接照抄执行的脚本——实际执行时每个任务都要按真实的 `listId`/`taskId` 走完整套三步编排。**每完成一个任务的迁移，就向用户报告一次进度**（成功/失败、命中了哪些黑名单项），不要等全部处理完才一次性汇总，这样用户能在中途发现问题时随时叫停。

## `categories` 打标签：整体替换，不是追加

对已有任务打分类标签，走 `update-task`：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"categories":["工作","紧急"]}'
```

**`categories` 是整体替换语义，不是追加**——提交的数组会完整覆盖任务原有的 `categories`，不是在原有基础上加几个新标签。要"新增一个分类而保留原有分类"，必须先 `get-task` 取回当前的 `categories`，在 Agent 侧把新分类合并进这个数组，再把合并后的完整数组一起提交：

```bash
# 1. 先取回现有值
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py get-task --list <listId> --task <taskId> \
  --fields id,categories

# 2. 在 Agent 侧合并（假设现有 ["工作"]，要新增 "紧急"，合并后是 ["工作","紧急"]）
# 3. 提交合并后的完整数组
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py update-task --list <listId> --task <taskId> \
  --body '{"categories":["工作","紧急"]}'
```

如果只想删掉某个分类、保留其余，同样是"先取回、在 Agent 侧移除目标项、再整体提交剩余数组"，没有单独的"追加"或"移除单项"接口。

`categories` 数组的每个元素对应 Outlook 分类（`outlookCategory.displayName`），**元素必须是用户已经在 Outlook 中预先定义过的分类名**，不能随手传一个从未定义过的新字符串——传入未定义的分类名不会自动创建新分类，也不会在 To Do 客户端里显示颜色。如果用户想要一个全新的分类，需要先在 Outlook（网页版或客户端）里定义好，再回来用本 skill 打标签。

## 通用注意事项（所有子命令都适用）

### 退出码 `5`（`PARTIAL_FAILURE`）

退出码 `5` 表示**部分失败**：`success` 是 `false`，但 `data` 里**仍有已取到的数据**。不要把它当纯错误丢弃，也不要把残缺数据当全量用。`metadata.retry_after_seconds` 给出的等待秒数必须尊重，不要立即重试。本 skill 里 `list-checklist-items` 是集合端点，分页被 `--max-pages` 截断时会触发这个错误码；`get-task`/`create-task`/`update-task`/`delete-task`/`raw` 不是集合端点，一般不会触发，但仍需了解这条约定，因为它是全仓通用契约的一部分。

### 不要盲目重试

本 skill 调用的子命令里，明确"可重试"的只有三种情况：退出码 `6`（`AUTH_PENDING`，属于 `setup-guide` 的登录流程）、退出码 `5` 且 `metadata.retry_after_seconds` 给出了等待时长、退出码 `1` 且错误码为 `AUTH_REFRESH_FAILED` 或 `NETWORK_ERROR`（暂时性故障，稍等片刻重试一次即可）。**其余非 0 退出码（如 `2` 的 `INVALID_PARAMETER`、`3` 的"未找到"、`4` 的 `AUTH_EXPIRED`）都是终态失败**，遇到时先停下来读 `error.suggestion`，而不是换个参数再试一次。尤其是第 2 步 `create-task` 失败时，**不要反复重试导致重复创建**——先确认失败原因（读 `error.suggestion`），必要时向用户确认后再决定是否重试一次。

## 边界

- **新建**一个全新任务，或删除单个任务（不涉及迁移）→ 转 `task-crud`（本 skill 第 1–3 步内部调用的 `create-task`/`delete-task` 是移动编排的一部分，不改变这条边界——单纯"建一个任务"或"删一个任务"仍是 `task-crud` 的职责）
- 改任务状态或优先级 → 转 `task-status`
- 需要按条件查找、筛选任务（比如先找出要批量归类的任务集合）→ 转 `task-query`
- 清单本身的增删改查（不是清单里的任务）→ 转 `list-management`
- 遇到退出码 `2` + `CONFIG_ERROR` 或退出码 `4` + `AUTH_EXPIRED` → 转 `setup-guide` 完成（重新）登录
