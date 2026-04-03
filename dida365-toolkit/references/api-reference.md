# 滴答清单 Open API 参考文档

## 概述

滴答清单 Open API 提供 RESTful 接口，用于访问和管理用户的任务、项目及相关资源。基于标准 HTTP 协议，数据格式为 JSON。

- **Base URL（国内）**：`https://api.dida365.com`
- **Base URL（国际）**：`https://api.ticktick.com`

---

## 认证：OAuth 2.0

### 第一步：重定向用户授权

```
GET https://dida365.com/oauth/authorize
```

| 参数 | 说明 |
|------|------|
| `client_id` | 应用唯一 ID |
| `scope` | 权限范围，空格分隔。可选值：`tasks:write` `tasks:read` |
| `state` | 原样传递到 redirect_uri |
| `redirect_uri` | 应用配置的回调地址 |
| `response_type` | 固定为 `code` |

示例：

```
https://dida365.com/oauth/authorize?scope=tasks:write%20tasks:read&client_id=CLIENT_ID&state=STATE&redirect_uri=REDIRECT_URI&response_type=code
```

### 第二步：获取授权码

用户授权后，滴答清单重定向回 `redirect_uri`，查询参数包含：

| 参数 | 说明 |
|------|------|
| `code` | 授权码，用于换取 access_token |
| `state` | 第一步传入的 state 参数 |

### 第三步：换取 Access Token

```
POST https://dida365.com/oauth/token
Content-Type: application/x-www-form-urlencoded
```

认证方式：**Basic Auth**（`client_id` 作为用户名，`client_secret` 作为密码，放在 Header 中）

| 参数 | 说明 |
|------|------|
| `code` | 第二步获取的授权码 |
| `grant_type` | 固定为 `authorization_code` |
| `scope` | 权限范围（同第一步） |
| `redirect_uri` | 应用配置的回调地址 |

响应：

```json
{
  "access_token": "access token value"
}
```

### 调用 API

在请求 Header 中设置：

```
Authorization: Bearer <access_token>
```

---

## API 端点

### Task（任务）

#### 获取任务

```
GET /open/v1/project/{projectId}/task/{taskId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |
| Path | taskId | 是 | 任务 ID | string |

**响应**：200 返回 [Task](#task-1) 对象

**示例请求**

```http
GET /open/v1/project/{{projectId}}/task/{{taskId}} HTTP/1.1
Host: api.dida365.com
Authorization: Bearer {{token}}
```

**示例响应**

```json
{
  "id": "63b7bebb91c0a5474805fcd4",
  "isAllDay": true,
  "projectId": "6226ff9877acee87727f6bca",
  "title": "Task Title",
  "content": "Task Content",
  "desc": "Task Description",
  "timeZone": "America/Los_Angeles",
  "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=1",
  "startDate": "2019-11-13T03:00:00+0000",
  "dueDate": "2019-11-14T03:00:00+0000",
  "reminders": ["TRIGGER:P0DT9H0M0S", "TRIGGER:PT0S"],
  "priority": 1,
  "status": 0,
  "completedTime": "2019-11-13T03:00:00+0000",
  "sortOrder": 12345,
  "items": [
    {
      "id": "6435074647fd2e6387145f20",
      "status": 0,
      "title": "Item Title",
      "sortOrder": 12345,
      "startDate": "2019-11-13T03:00:00+0000",
      "isAllDay": false,
      "timeZone": "America/Los_Angeles",
      "completedTime": "2019-11-13T03:00:00+0000"
    }
  ]
}
```

---

#### 创建任务

```
POST /open/v1/task
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Body | title | 是 | 任务标题 | string |
| Body | projectId | 是 | 项目 ID | string |
| Body | content | 否 | 任务内容 | string |
| Body | desc | 否 | 清单描述 | string |
| Body | isAllDay | 否 | 是否全天 | boolean |
| Body | startDate | 否 | 开始时间，格式 `yyyy-MM-dd'T'HH:mm:ssZ` | date |
| Body | dueDate | 否 | 截止时间，格式同上 | date |
| Body | timeZone | 否 | 时区 | string |
| Body | reminders | 否 | 提醒列表 | list |
| Body | repeatFlag | 否 | 循环规则（RRULE 格式） | string |
| Body | priority | 否 | 优先级，默认 0 | integer |
| Body | sortOrder | 否 | 排序值 | integer |
| Body | items | 否 | 子任务列表 | list |
| Body | items.title | — | 子任务标题 | string |
| Body | items.startDate | — | 子任务开始时间 | date |
| Body | items.isAllDay | — | 子任务是否全天 | boolean |
| Body | items.sortOrder | — | 子任务排序值 | integer |
| Body | items.timeZone | — | 子任务时区 | string |
| Body | items.status | — | 子任务完成状态 | integer |
| Body | items.completedTime | — | 子任务完成时间 | date |

**响应**：200 返回 [Task](#task-1) 对象

**示例请求**

```http
POST /open/v1/task HTTP/1.1
Host: api.dida365.com
Content-Type: application/json
Authorization: Bearer {{token}}

{
  "title": "Task Title",
  "projectId": "6226ff9877acee87727f6bca"
}
```

---

#### 更新任务

```
POST /open/v1/task/{taskId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | taskId | 是 | 任务 ID | string |
| Body | id | 是 | 任务 ID | string |
| Body | projectId | 是 | 项目 ID | string |
| Body | title | 否 | 任务标题 | string |
| Body | content | 否 | 任务内容 | string |
| Body | desc | 否 | 清单描述 | string |
| Body | isAllDay | 否 | 是否全天 | boolean |
| Body | startDate | 否 | 开始时间 | date |
| Body | dueDate | 否 | 截止时间 | date |
| Body | timeZone | 否 | 时区 | string |
| Body | reminders | 否 | 提醒列表 | list |
| Body | repeatFlag | 否 | 循环规则 | string |
| Body | priority | 否 | 优先级 | integer |
| Body | sortOrder | 否 | 排序值 | integer |
| Body | items | 否 | 子任务列表（结构同创建任务） | list |

**响应**：200 返回 [Task](#task-1) 对象（含 `kind` 字段）

---

#### 完成任务

```
POST /open/v1/project/{projectId}/task/{taskId}/complete
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |
| Path | taskId | 是 | 任务 ID | string |

**响应**：200 无内容

---

#### 删除任务

```
DELETE /open/v1/project/{projectId}/task/{taskId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |
| Path | taskId | 是 | 任务 ID | string |

**响应**：200 无内容

---

#### 移动任务

```
POST /open/v1/task/move
```

将一个或多个任务从一个项目移动到另一个项目。请求体为 JSON 数组。

**参数**（数组元素）

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Body | fromProjectId | 是 | 源项目 ID | string |
| Body | toProjectId | 是 | 目标项目 ID | string |
| Body | taskId | 是 | 任务 ID | string |

**示例请求**

```http
POST /open/v1/task/move HTTP/1.1
Host: api.dida365.com
Authorization: Bearer {{token}}

[
  {
    "fromProjectId": "69a850ef1c20d2030e148fdd",
    "toProjectId": "69a850f41c20d2030e148fdf",
    "taskId": "69a850f8b9061f374d54a046"
  }
]
```

**示例响应**

```json
[
  {
    "id": "69a850f8b9061f374d54a046",
    "etag": "43p2zso1"
  }
]
```

---

#### 查询已完成任务

```
POST /open/v1/task/completed
```

按项目和时间范围查询已完成的任务。

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Body | projectIds | 否 | 项目 ID 列表 | list |
| Body | startDate | 否 | 起始时间（completedTime >= startDate） | date |
| Body | endDate | 否 | 结束时间（completedTime <= endDate） | date |

**响应**：200 返回 Task 数组

**示例请求**

```http
POST /open/v1/task/completed HTTP/1.1
Host: api.dida365.com
Authorization: Bearer {{token}}

{
  "projectIds": ["69a850f41c20d2030e148fdf"],
  "startDate": "2026-03-01T00:58:20.000+0000",
  "endDate": "2026-03-05T10:58:20.000+0000"
}
```

---

#### 筛选任务

```
POST /open/v1/task/filter
```

按多维条件高级筛选任务。

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Body | projectIds | 否 | 项目 ID 列表 | list |
| Body | startDate | 否 | 任务 startDate >= 此值 | date |
| Body | endDate | 否 | 任务 startDate <= 此值 | date |
| Body | priority | 否 | 优先级列表。值：0=无, 1=低, 3=中, 5=高 | list |
| Body | tag | 否 | 标签列表（AND 关系，需全部匹配） | list |
| Body | status | 否 | 状态列表。值：0=未完成, 2=已完成 | list |

**示例请求**

```http
POST /open/v1/task/filter HTTP/1.1
Host: api.dida365.com
Authorization: Bearer {{token}}

{
  "projectIds": ["69a850f41c20d2030e148fdf"],
  "startDate": "2026-03-01T00:58:20.000+0000",
  "endDate": "2026-03-06T10:58:20.000+0000",
  "priority": [0],
  "tag": ["urgent"],
  "status": [0]
}
```

---

### Project（项目）

#### 获取所有项目

```
GET /open/v1/project
```

**响应**：200 返回 Project 数组

**示例响应**

```json
[
  {
    "id": "6226ff9877acee87727f6bca",
    "name": "project name",
    "color": "#F18181",
    "closed": false,
    "groupId": "6436176a47fd2e05f26ef56e",
    "viewMode": "list",
    "permission": "write",
    "kind": "TASK"
  }
]
```

---

#### 获取单个项目

```
GET /open/v1/project/{projectId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |

**响应**：200 返回 [Project](#project-1) 对象

---

#### 获取项目及数据

```
GET /open/v1/project/{projectId}/data
```

返回项目信息、未完成任务列表和看板列信息。`projectId` 可传 `"inbox"` 获取收集箱数据。

**响应**：200 返回 [ProjectData](#projectdata) 对象

**示例响应**

```json
{
  "project": {
    "id": "6226ff9877acee87727f6bca",
    "name": "project name",
    "color": "#F18181",
    "closed": false,
    "groupId": "6436176a47fd2e05f26ef56e",
    "viewMode": "list",
    "kind": "TASK"
  },
  "tasks": [
    {
      "id": "6247ee29630c800f064fd145",
      "isAllDay": true,
      "projectId": "6226ff9877acee87727f6bca",
      "title": "Task Title",
      "content": "Task Content",
      "desc": "Task Description",
      "timeZone": "America/Los_Angeles",
      "repeatFlag": "RRULE:FREQ=DAILY;INTERVAL=1",
      "startDate": "2019-11-13T03:00:00+0000",
      "dueDate": "2019-11-14T03:00:00+0000",
      "reminders": ["TRIGGER:P0DT9H0M0S", "TRIGGER:PT0S"],
      "priority": 1,
      "status": 0,
      "completedTime": "2019-11-13T03:00:00+0000",
      "sortOrder": 12345,
      "items": [
        {
          "id": "6435074647fd2e6387145f20",
          "status": 0,
          "title": "Subtask Title",
          "sortOrder": 12345,
          "startDate": "2019-11-13T03:00:00+0000",
          "isAllDay": false,
          "timeZone": "America/Los_Angeles",
          "completedTime": "2019-11-13T03:00:00+0000"
        }
      ]
    }
  ],
  "columns": [
    {
      "id": "6226ff9e76e5fc39f2862d1b",
      "projectId": "6226ff9877acee87727f6bca",
      "name": "Column Name",
      "sortOrder": 0
    }
  ]
}
```

---

#### 创建项目

```
POST /open/v1/project
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Body | name | 是 | 项目名称 | string |
| Body | color | 否 | 项目颜色，如 `"#F18181"` | string |
| Body | sortOrder | 否 | 排序值 | integer (int64) |
| Body | viewMode | 否 | 视图模式：`list` / `kanban` / `timeline` | string |
| Body | kind | 否 | 项目类型：`TASK` / `NOTE` | string |

**响应**：200 返回 [Project](#project-1) 对象

---

#### 更新项目

```
POST /open/v1/project/{projectId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |
| Body | name | 否 | 项目名称 | string |
| Body | color | 否 | 项目颜色 | string |
| Body | sortOrder | 否 | 排序值，默认 0 | integer (int64) |
| Body | viewMode | 否 | 视图模式 | string |
| Body | kind | 否 | 项目类型 | string |

**响应**：200 返回 [Project](#project-1) 对象

---

#### 删除项目

```
DELETE /open/v1/project/{projectId}
```

**参数**

| 位置 | 名称 | 必填 | 说明 | 类型 |
|------|------|------|------|------|
| Path | projectId | 是 | 项目 ID | string |

**响应**：200 无内容

---

## 数据模型定义

### ChecklistItem（子任务）

| 字段 | 说明 | 类型 |
|------|------|------|
| id | 子任务 ID | string |
| title | 子任务标题 | string |
| status | 完成状态。0=未完成, 1=已完成 | integer (int32) |
| completedTime | 完成时间，格式 `yyyy-MM-dd'T'HH:mm:ssZ` | string (date-time) |
| isAllDay | 是否全天 | boolean |
| sortOrder | 排序值 | integer (int64) |
| startDate | 开始时间，格式 `yyyy-MM-dd'T'HH:mm:ssZ` | string (date-time) |
| timeZone | 时区，如 `"America/Los_Angeles"` | string |

### Task（任务）

| 字段 | 说明 | 类型 |
|------|------|------|
| id | 任务 ID | string |
| projectId | 所属项目 ID | string |
| title | 任务标题 | string |
| isAllDay | 是否全天 | boolean |
| completedTime | 完成时间 | string (date-time) |
| content | 任务内容 | string |
| desc | 清单描述 | string |
| dueDate | 截止时间 | string (date-time) |
| items | 子任务列表 | ChecklistItem[] |
| priority | 优先级。0=无, 1=低, 3=中, 5=高 | integer (int32) |
| reminders | 提醒触发器列表，如 `["TRIGGER:P0DT9H0M0S", "TRIGGER:PT0S"]` | string[] |
| repeatFlag | 循环规则（RRULE 格式），如 `"RRULE:FREQ=DAILY;INTERVAL=1"` | string |
| sortOrder | 排序值 | integer (int64) |
| startDate | 开始时间 | string (date-time) |
| status | 完成状态。0=未完成, 2=已完成 | integer (int32) |
| timeZone | 时区 | string |
| kind | 类型：`TEXT` / `NOTE` / `CHECKLIST` | string |

> **注意**：任务的 status 完成值为 **2**，子任务（ChecklistItem）的 status 完成值为 **1**。

### Project（项目）

| 字段 | 说明 | 类型 |
|------|------|------|
| id | 项目 ID | string |
| name | 项目名称 | string |
| color | 项目颜色 | string |
| sortOrder | 排序值 | integer (int64) |
| closed | 是否已关闭 | boolean |
| groupId | 所属分组 ID | string |
| viewMode | 视图模式：`list` / `kanban` / `timeline` | string |
| permission | 权限：`read` / `write` / `comment` | string |
| kind | 类型：`TASK` / `NOTE` | string |

### Column（看板列）

| 字段 | 说明 | 类型 |
|------|------|------|
| id | 列 ID | string |
| projectId | 所属项目 ID | string |
| name | 列名称 | string |
| sortOrder | 排序值 | integer (int64) |

### ProjectData（项目数据）

| 字段 | 说明 | 类型 |
|------|------|------|
| project | 项目信息 | Project |
| tasks | 未完成任务列表 | Task[] |
| columns | 看板列列表 | Column[] |

---

## 通用响应码

| HTTP Code | 说明 |
|-----------|------|
| 200 | 成功 |
| 201 | 已创建 |
| 401 | 未授权（Token 无效或过期） |
| 403 | 禁止访问 |
| 404 | 资源不存在 |

