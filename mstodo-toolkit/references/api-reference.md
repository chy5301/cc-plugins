# Microsoft Graph To Do 数据模型参考

本文档描述 **Microsoft Graph To Do API 本身的数据模型**：有哪些资源、每个资源有哪些字段、字段的合法取值范围，以及 Graph 在实测中暴露出的几个坑。

**这不是 CLI 使用手册。** `mstodo_cli.py` 自己的契约——响应信封、退出码、`--fields`/`--dry-run`/`--max-pages`、分页机制、跨清单聚合、`PARTIAL_FAILURE`、认证流程——一律见 `references/cli-conventions.md`，本文档涉及这些内容时只做引用，不重复。

字段名与路径模板以仓库代码为准：字段来自 `scripts/mstodo_lib/schemas.py` 的 `OPERATION_SCHEMAS`，路径模板来自 `scripts/mstodo_cli.py` 的 `RESOURCE_COMMANDS`；Graph 官方文档 (learn.microsoft.com) 补充 CLI schema 未收录的只读字段。**凡是探针（Task 0）实测过的行为，以实测结果为准，官方文档的描述让位。**

---

## 1. `todoTaskList`（清单）字段表

| 字段 | 类型 | 读写 | 说明 |
| --- | --- | --- | --- |
| `id` | String | 只读 | 清单在用户邮箱内唯一的标识符 |
| `displayName` | String | 可写 | 清单名称。`create-list` 必填，`update-list` 可选 |
| `isOwner` | Boolean | 只读 | 当前用户是否为该清单的所有者 |
| `isShared` | Boolean | 只读 | 该清单是否与其他用户共享 |
| `wellknownListName` | 枚举，见下节 | 只读 | 标识该清单是否是内置清单 |

对应 CLI：`list-lists` / `get-list` / `create-list` / `update-list` / `delete-list`，请求体 schema 见 `schema create-list` / `schema update-list`。

---

## 2. `wellknownListName` 专节

`wellknownListName` 只有三个有实际含义的取值（第四个是 Graph 可演进枚举的哨兵值，不代表真实清单）：

| 取值 | 含义 |
| --- | --- |
| `none` | 用户自建清单 |
| `defaultList` | 内置的「Tasks」清单（对应 To Do 客户端里默认显示为「我的一天」旁边的「任务」清单） |
| `flaggedEmails` | 内置的「Flagged emails」清单，来自 Outlook 邮件加星标后自动生成的任务 |

（`unknownFutureValue` 是 Graph 可演进枚举的哨兵值，遇到即代表未来新增的未知取值，不要按业务逻辑处理。）

**`defaultList` 与 `flaggedEmails` 不可改名、不可删除**：对这两个清单调用 `update-list` 或 `delete-list` 必然失败（Graph 返回错误，CLI 透传为对应的 `HTTP_4xx` 错误码）。Agent 在批量操作清单前，应先用 `get-list` 或 `list-lists --fields id,displayName,wellknownListName` 确认目标清单的 `wellknownListName` 不是这两者之一，再决定是否调用 `update-list`/`delete-list`。

Task 0 探针实测：账号首个清单（个人账号默认拥有的「Tasks」清单）的 `wellknownListName` 确为 `defaultList`，印证了上述取值在真实账号上的行为。

---

## 3. `todoTask`（任务）字段表

| 字段 | 类型 | 读写 | 说明 |
| --- | --- | --- | --- |
| `id` | String | 只读 | 任务标识符。**默认情况下，任务从一个清单移动到另一个清单后该值会变化**（Graph 官方原文）——这是「无移动端点」的根源，见下方「Graph 没有的能力」节 |
| `title` | String | 可写 | 任务标题。`create-task` 必填 |
| `body` | `itemBody`（`{content, contentType}`） | 可写 | 任务描述。传字符串会被 CLI 自动展开为 `{"content": "...", "contentType": "text"}`；传对象原样透传。**与 `--body` 命令行选项同名不同物**，见「`body` 同名陷阱」节 |
| `importance` | 枚举 `low` / `normal` / `high` | 可写 | 优先级。**不得与滴答清单的 `priority`（`0`/`1`/`3`/`5`）做任何数值映射**，两者是完全不同的取值域 |
| `status` | 枚举 `notStarted` / `inProgress` / `completed` / `waitingOnOthers` / `deferred` | 可写 | 任务状态。标记完成传 `"completed"`；CLI 没有独立的 `complete-task` 子命令，统一走 `update-task --body '{"status":"completed"}'` |
| `dueDateTime` | `dateTimeTimeZone` | 可写 | 截止时间，见「日期与时区」节 |
| `reminderDateTime` | `dateTimeTimeZone` | 可写 | 提醒时间，同上 |
| `startDateTime` | `dateTimeTimeZone` | 可写 | 开始时间，同上 |
| `isReminderOn` | Boolean | 可写 | 是否开启提醒 |
| `categories` | String 数组 | 可写 | Outlook 分类名数组，相当于标签；元素须是用户已在 Outlook 中定义过的 `outlookCategory.displayName` |
| `checklistItems` | `checklistItem` 数组 | 仅 `create-task` 可写 | 子任务数组，元素形如 `{"displayName": "..."}`。**支持内联创建（deep insert）**，见下方说明；`update-task` 不支持通过此字段改子任务，改子任务走 `update-checklist-item` |
| `completedDateTime` | `dateTimeTimeZone` | 只读 | 任务完成的时间，由服务端在 `status` 变为 `completed` 时维护。本插件 schema 未收录为可写字段（不出现在请求体里） |
| `createdDateTime` | DateTimeOffset | 只读 | 创建时间，UTC |
| `lastModifiedDateTime` | DateTimeOffset | 只读 | 最后修改时间，UTC |
| `bodyLastModifiedDateTime` | DateTimeOffset | 只读 | `body` 字段最后修改时间，UTC |
| `hasAttachments` | Boolean | 只读 | 是否有附件 |
| `recurrence` | `patternedRecurrence` | Graph 原生可写，**本插件 schema 未收录** | 重复规则；本插件的 `create-task`/`update-task` 不支持直接设置，需要时走 `raw` |

对应 CLI：`list-tasks` / `get-task` / `create-task` / `update-task` / `delete-task`，请求体 schema 见 `schema create-task` / `schema update-task`。`list-tasks` 额外注入的 `listId`/`listDisplayName` 是 CLI 层字段而非 Graph 原生字段，见 cli-conventions.md「跨清单聚合」节。

**deep insert 实测**：Task 0 探针在 `create-task` 请求体里内联 `checklistItems: [{"displayName": "子项A"}, {"displayName": "子项B"}]`，返回 `201`，随后查询该任务的 `checklistItems` 集合，**实际落地 2 个子项**（不是被静默忽略）。因此建一个带子任务的任务，一次 `create-task` 请求即可，不需要先 `create-task` 再逐个 `create-checklist-item`（`1 + N` 次请求）。

---

## 4. `checklistItem`（子任务）字段表

| 字段 | 类型 | 读写 | 说明 |
| --- | --- | --- | --- |
| `id` | String | 只读 | 服务端生成 |
| `displayName` | String | 可写 | 子任务名称。`create-checklist-item` 必填，`update-checklist-item` 可选 |
| `isChecked` | Boolean | 可写 | 是否已勾选。`create-checklist-item`/`update-checklist-item` 均可选 |
| `createdDateTime` | DateTimeOffset | 只读 | 创建时间 |
| `checkedDateTime` | DateTimeOffset | 只读 | 勾选完成的时间，由服务端维护。本插件 schema 未收录为可写字段 |

对应 CLI：`list-checklist-items` / `get-checklist-item` / `create-checklist-item` / `update-checklist-item` / `delete-checklist-item`，请求体 schema 见 `schema create-checklist-item` / `schema update-checklist-item`。

---

## 5. 日期与时区

`dueDateTime` / `reminderDateTime` / `startDateTime` 在 Graph 里都是嵌套对象 `dateTimeTimeZone`，只有两个字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dateTime` | String | 形如 `2026-12-31T09:00:00.0000000`，不带时区偏移 |
| `timeZone` | String | 时区名称 |

`completedDateTime` 虽然也是 `dateTimeTimeZone` 结构，但它是只读字段，不出现在请求体里（见上方 `todoTask` 字段表）。

**`timeZone` 同时接受 Windows 时区名（如 `China Standard Time`）与 IANA/Olson 时区名（如 `Asia/Shanghai`）**——Graph 官方 `dateTimeTimeZone` 文档的 "Additional time zones" 列表显式包含 `Asia/Shanghai`，且 Task 0 探针对两种写法各建一次任务实测均返回 `201`（见下方实测详情）。

CLI 对这三个字段支持三种简写（`"YYYY-MM-DD"` / `"YYYY-MM-DDTHH:MM:SS"` / 完整 `{dateTime, timeZone}` 对象）及默认时区展开逻辑（`MSTODO_TIMEZONE`），属于 CLI 自己的契约，见 cli-conventions.md「跨子命令行为约定」节，不在此重复。

### 实测发现：`dueDateTime` 读回后日期不变，但时刻被丢弃（2026-09-22 订正）

Task 0 探针对 **`dueDateTime`** 用同一个时刻、两种时区写法各建了一个任务：

- 提交 `{"dateTime": "2026-12-31T09:00:00", "timeZone": "Asia/Shanghai"}` → `201`
- 提交 `{"dateTime": "2026-12-31T09:00:00", "timeZone": "China Standard Time"}` → `201`

**两者回显完全相同**：

```json
{"dateTime": "2026-12-30T16:00:00.0000000", "timeZone": "UTC"}
```

**这不是单纯的时区换算。** 对照：

| | |
| --- | --- |
| 提交 | `2026-12-31T09:00:00`，`+08:00` |
| 若只做时区换算，应得 | `2026-12-31T01:00:00Z` |
| **Graph 实际回显** | `2026-12-30T16:00:00Z` |
| 回显换算回 `+08:00` | `2026-12-31T`**`00:00`**`:00` |

回显换算回提交时区后，**日期（`12-31`）保留了，但时刻从 `09:00` 变成了 `00:00`**——Graph 把提交的时刻部分丢弃、当作当天零点处理，再转成 UTC，不是保留 `09:00` 原样换算。这与 To Do 的产品语义一致：**`dueDateTime` 是日期粒度的截止日期字段，不是精确到时刻的字段**；需要具体时刻的语义由 `reminderDateTime`（提醒）承载。

后果：

- Agent 写完任务再读回确认时，会看到一个**字面上与提交值不同**的 `dateTime`/`timeZone`。这**不是写入失败**，不要据此认为提交没有生效，更不要去"修正"这个值——每次"修正"提交后，读回依然会被同样处理，只会陷入无意义的循环。
- 需要"当天某个具体时刻"语义（例如"明天下午 3 点前完成"）时，`dueDateTime` 承载不了这个时刻信息。
- **任何"读回比对"都不能做字符串比较，也不能假设两者代表同一时刻**——换算到同一时区后两者只是**同一日期**，具体时刻已经丢失，直接比较 `"2026-12-31T09:00:00"` 和 `"2026-12-30T16:00:00.0000000"` 这两个字符串既不相等，也不代表同一时刻。
- **`reminderDateTime` 保留具体时刻（2026-09-23 验收实测）**：同一任务同时提交 `dueDateTime` 与 `reminderDateTime`，都是 `2026-12-31T09:00:00` + `Asia/Shanghai`。读回时 `dueDateTime` 仍为 `2026-12-30T16:00:00Z`（时刻丢弃，与上述结论一致），`reminderDateTime` 为 `2026-12-31T01:00:00Z`，即 `+08:00` 的 `09:00`，**时刻完整保留，只做了时区换算**。需要"某个具体时刻"的语义时，应写进 `reminderDateTime`（同时设 `isReminderOn: true`）。
- **`startDateTime` 仍未实测**：不要假设它与 `dueDateTime` 或 `reminderDateTime` 中的哪一个行为相同，有疑问以实测或官方文档为准。

---

## 6. `$select` 不被支持（服务端字段选择不可用）

Task 0 探针对 To Do 的任务端点实测了四个常见 OData 查询参数：

| 查询参数 | 结果 |
| --- | --- |
| `$top=2` | `200` |
| `$filter=status eq 'notStarted'` | `200` |
| `$orderby=createdDateTime desc` | `200` |
| `$count=true` | `200` |
| `$select=id,title` | **`400 invalidRequest`（`RequestBroker--ParseUri`）** |

`$select` 不可用，意味着**服务端字段选择不可用**——`--fields` 只能在 CLI 客户端裁剪响应，这不是设计取舍而是被 Graph 逼出来的（没有别的选择）。

**保留意见**：`$filter` 返回 `200` **只证明它被 Graph 接受，不证明它被真正执行**。探针没有验证返回集是否真的按 `$filter` 被过滤过，部分 Graph 端点会接受并静默忽略不支持的查询参数。因此本插件的 `list-tasks --status` 维持客户端过滤（在分页跟完之后再过滤，见 cli-conventions.md「分页」节），**不要把 `$filter` 可用当成既成事实去改造成服务端过滤**——赌错的后果是"筛出的结果实际上没被过滤，Agent 却以为已经过滤"。

---

## 7. `body` 同名陷阱专节

CLI 的 `--body` 选项与 Graph 任务对象内部的 `body` 字段**同名但不是一回事**：

- `--body` 是整条命令的**请求体 JSON（外层）**——包含 `title`、`importance`、`body` 等所有字段的容器。
- Graph 任务对象里的 `body` 是请求体**内部**的一个 key，专指任务描述（`itemBody`），传字符串会被 CLI 自动展开为 `{"content": "...", "contentType": "text"}`。

完整命令行示例（`--body` 是外层 JSON，其中的 `"body"` key 是描述字段）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py create-task --list L1 \
  --body '{"title":"写季度报告","body":"包含 Q3 营收对比与下季度目标"}'
```

读这条命令时不要把 `--body` 的取值（那个 JSON 整体）和它里面的 `"body"` key 混为一谈——前者是命令行参数，后者是该 JSON 对象里的一个字段。

---

## 8. 与滴答清单的差异对照表

| 维度 | Microsoft To Do（Graph） | 滴答清单 |
| --- | --- | --- |
| 容器命名 | `todoTaskList`（「清单」），路径 `/me/todo/lists/{listId}` | `Project`（「项目」），路径 `/open/v1/project/{projectId}` |
| 优先级 | `importance`：三档字符串枚举 `low` / `normal` / `high` | `priority`：整数 `0`/`1`/`3`/`5`（无/低/中/高）。**两者取值域完全不同，不做数值映射** |
| 状态 | `status`：五档字符串枚举 `notStarted`/`inProgress`/`completed`/`waitingOnOthers`/`deferred` | `status`：整数，任务完成值为 `2`，子任务（ChecklistItem）完成值为 `1`，两个层级的完成值还不一样 |
| 标签 | `categories`：字符串数组，元素须是用户已在 Outlook 中预先定义的 `outlookCategory.displayName`，不能随手传任意新字符串 | `tags`：自由文本字符串数组，无需预先定义 |
| 子任务 | `checklistItems`：仅 `displayName`/`isChecked` 可写，无日期字段、无全天标记；`create-task` 支持内联创建（deep insert，Task 0 实测确认真实落地） | `items`：字段更丰富（`startDate`/`isAllDay`/`completedTime` 等），随创建任务的请求体一并提交 |
| 共享 | `todoTaskList.isOwner`/`isShared` 只读反映当前共享状态，**Graph 无邀请/移除协作者的共享管理端点** | `Project.permission`（`read`/`write`/`comment`）只读反映当前权限，Open API 同样**无共享管理端点** |
| 分页 | 集合端点服务端强制分页（`@odata.nextLink`），详见 cli-conventions.md「分页」节 | Open API 未见分页机制，`task/filter`/`task/completed` 等端点一次性返回全量结果 |

---

## 9. Graph 没有的能力

- **无移动端点**：Graph 没有「把任务从清单 A 移到清单 B」的专用 API。要移动任务只能在目标清单 `create-task` 一个新任务再在原清单 `delete-task` 旧任务——而且移动后任务 `id` 必然改变（见 `todoTask.id` 字段说明）。本插件刻意不提供 `move-tasks` 语义化快捷命令（与 cli-conventions.md 一致）。
- **无跨清单查询端点**：Graph 没有「一次请求返回所有清单下所有任务」的端点，只能逐清单请求。本插件的 `list-tasks --list all` 是 CLI 层用 `$batch` + 逐清单分页拼出来的聚合结果，不是 Graph 原生能力，聚合机制详见 cli-conventions.md「跨清单聚合」节。
- **无任务负责人信息**：共享清单里可以在 To Do 应用内把任务"分配给"某个成员，但 Graph 不返回这个信息——`todoTask` 没有负责人字段（2026-09-24 实测：同一个共享清单，v1.0 与 beta 端点返回的任务字段完全相同，都没有负责人字段）；应用里的"已分配给我"智能列表也不是 `todoTaskList`，`list-lists` 列不出来。因此**无法通过接口判断任务分配给了谁**，处置方式见 `task-query` skill。
- **无共享管理端点**：`todoTaskList.isOwner`/`isShared` 只是只读反映当前共享状态的字段，Graph 没有提供邀请协作者、移除协作者、修改协作者权限的 API。

---

## 10. 被砍掉的三项及 `raw` 兜底写法

以下三项 Graph 原生支持，但本插件的 `RESOURCE_COMMANDS`/`OPERATION_SCHEMAS` 未收录为专属子命令，需要时用 `raw` 逃生舱直接打 Graph 端点：

**`linkedResources`**（任务关联的外部资源，如邮件、文件链接）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py raw --method GET \
  --path "/me/todo/lists/L1/tasks/T1/linkedResources"
```

**`attachments`**（任务的文件附件）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py raw --method GET \
  --path "/me/todo/lists/L1/tasks/T1/attachments"
```

**`delta`**（增量查询，追踪某清单下任务的增删改）：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/mstodo_cli.py raw --method GET \
  --path "/me/todo/lists/L1/tasks/delta"
```

`raw` 不做 schema 校验、不剥 OData 噪音，原样透传请求与响应，用法见 cli-conventions.md「自省与逃生舱」节。

---

## 11. Task 0 实测结论汇总

以下六项数据来自 Task 0 探针在真实账号上的一次性实测，本文档与 `cli-conventions.md` 的相关结论均据此得出：

| 编号 | 待验项 | 实测结果 | 采用的路径 |
| --- | --- | --- | --- |
| P1 | `$batch` 是否支持 `/me/todo/lists/{id}/tasks` | 支持：外层请求 `200`，子请求状态均为 `[200, 200]` | 跨清单聚合按计划使用 `$batch`，无需退回串行 N 次请求 |
| P2 | `$top` / `$filter` / `$orderby` / `$count` / `$select` 支持面 | `$top`/`$filter`/`$orderby`/`$count` 均返回 `200`；`$select=id,title` 返回 `400 invalidRequest`（`RequestBroker--ParseUri`） | `--fields` 必须在 CLI 客户端做（没有服务端选择字段的余地）；`$filter` 的 `200` 只证明被接受、未证明被执行，`--status` 维持客户端过滤 |
| P3 | `lists`/`tasks` 集合的默认页大小与 `nextLink` 形态 | **未能校准**——探针账号数据量过小（2 个清单 / 16 个任务），两个端点均未触发 `nextLink`。这不是「分页不存在」的证据，只是探针数据量不够大，够不到分页边界 | 分页实现保持不变（服务端强制分页的假设不变），但没有拿到第一手的页大小数字 |
| P4 | `common` tenant 是否可用于个人账号登录 | 登录成功 | `MSTODO_TENANT` 默认值维持 `common` |
| P5 | `create-task` 能否内联 `checklistItems`（deep insert） | 支持：返回 `201`，且实际落地 2 个子项（未被静默忽略） | 建带子任务的任务一次 `create-task` 请求即可，不需要 `1 + N` 次请求 |
| P6 | `timeZone` 是否接受 IANA 名（`Asia/Shanghai`） | 两种写法（`Asia/Shanghai` 与 `China Standard Time`）均返回 `201`；但**读回时一律归一化为 `UTC`**，且不是单纯的时区换算——`dueDateTime` 日期保留、时刻被丢弃（提交 `+08:00` 的 `09:00` 回显为当日零点对应的 UTC 表示 `16:00`，即前一日 `16:00`），`reminderDateTime` 则保留时刻（2026-09-23 验收实测），详见「日期与时区」节 | 默认时区维持 `Asia/Shanghai`（IANA 名）；同时在文档中明确「读回比对必须先换算，不得做字符串比较，也不得假设两者代表同一时刻」，见「日期与时区」节 |
