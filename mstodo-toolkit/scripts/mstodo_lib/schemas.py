"""请求体字段 schema、日期与 body 展开、参数校验。

Agent 在构造 --body 前用 `schema <操作>` 自省字段定义。
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any


class InvalidDatetimeFormat(ValueError):
    """日期时间字符串格式不合法。"""

# 默认时区。Graph 同时接受 Windows 名与 IANA 名（官方 dateTimeTimeZone 的
# "Additional time zones" 列表显式含 Asia/Shanghai），此处取 IANA 名——
# 它是 Linux 用户的自然写法，且与系统 TZ 一致。
DEFAULT_TIMEZONE = "Asia/Shanghai"

# 这些字段在 Graph 里是 dateTimeTimeZone 嵌套对象
# completedDateTime 是 Graph 的只读字段（不出现在请求体中），故不在此集合里
DATETIME_FIELDS = frozenset({
    "dueDateTime", "reminderDateTime", "startDateTime",
})

_STATUS_ENUM = ["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]
_IMPORTANCE_ENUM = ["low", "normal", "high"]

_BODY_DESC = (
    "任务描述。传字符串会自动展开为 {content, contentType:'text'}。"
    "注意：Graph 的该字段名与 CLI 的 --body 选项同名但不是一回事——"
    "--body 是整个请求体，这里的 body 是请求体里的描述字段。"
)

_DATETIME_DESC = (
    "支持 'YYYY-MM-DD'（补 T00:00:00）、'YYYY-MM-DDTHH:MM:SS'（补默认时区），"
    "或完整的 {dateTime, timeZone} 对象。timeZone 同时接受 Windows 名"
    "（China Standard Time）与 IANA 名（Asia/Shanghai）。默认时区由 "
    "MSTODO_TIMEZONE 控制。"
)

OPERATION_SCHEMAS: dict[str, dict] = {
    "create-list": {
        "method": "POST",
        "path": "/me/todo/lists",
        "fields": {
            "displayName": {"type": "str", "required": True, "desc": "清单名称"},
        },
    },
    "update-list": {
        "method": "PATCH",
        "path": "/me/todo/lists/{listId}",
        "at_least_one": True,
        "fields": {
            "displayName": {"type": "str", "desc": "清单名称。内置清单不可改名"},
        },
    },
    "create-task": {
        "method": "POST",
        "path": "/me/todo/lists/{listId}/tasks",
        "fields": {
            "title": {"type": "str", "required": True, "desc": "任务标题"},
            "body": {"type": ["str", "object"], "desc": _BODY_DESC},
            "importance": {"type": "str", "enum": _IMPORTANCE_ENUM, "desc": "优先级"},
            "status": {"type": "str", "enum": _STATUS_ENUM, "desc": "任务状态"},
            "dueDateTime": {"type": ["str", "object"], "desc": f"截止时间。{_DATETIME_DESC}"},
            "reminderDateTime": {"type": ["str", "object"],
                                 "desc": f"提醒时间。{_DATETIME_DESC}"},
            "startDateTime": {"type": ["str", "object"],
                              "desc": f"开始时间。{_DATETIME_DESC}"},
            "isReminderOn": {"type": "bool", "desc": "是否开启提醒"},
            "categories": {"type": "array", "items": "str",
                           "desc": "Outlook 分类名数组，相当于标签"},
            "checklistItems": {"type": "array", "items": "object",
                               "desc": "子任务数组，元素形如 {displayName}。"
                                       "能否内联创建见 references/api-reference.md"},
        },
    },
    "update-task": {
        "method": "PATCH",
        "path": "/me/todo/lists/{listId}/tasks/{taskId}",
        "at_least_one": True,
        "fields": {
            "title": {"type": "str", "desc": "任务标题"},
            "body": {"type": ["str", "object"], "desc": _BODY_DESC},
            "importance": {"type": "str", "enum": _IMPORTANCE_ENUM, "desc": "优先级"},
            "status": {"type": "str", "enum": _STATUS_ENUM,
                       "desc": "任务状态。标记完成传 'completed'"},
            "dueDateTime": {"type": ["str", "object"], "desc": f"截止时间。{_DATETIME_DESC}"},
            "reminderDateTime": {"type": ["str", "object"],
                                 "desc": f"提醒时间。{_DATETIME_DESC}"},
            "startDateTime": {"type": ["str", "object"],
                              "desc": f"开始时间。{_DATETIME_DESC}"},
            "isReminderOn": {"type": "bool", "desc": "是否开启提醒"},
            "categories": {"type": "array", "items": "str", "desc": "Outlook 分类名数组"},
        },
    },
    "create-checklist-item": {
        "method": "POST",
        "path": "/me/todo/lists/{listId}/tasks/{taskId}/checklistItems",
        "fields": {
            "displayName": {"type": "str", "required": True, "desc": "子任务名称"},
            "isChecked": {"type": "bool", "desc": "是否已勾选"},
        },
    },
    "update-checklist-item": {
        "method": "PATCH",
        "path": "/me/todo/lists/{listId}/tasks/{taskId}/checklistItems/{itemId}",
        "at_least_one": True,
        "fields": {
            "displayName": {"type": "str", "desc": "子任务名称"},
            "isChecked": {"type": "bool", "desc": "是否已勾选"},
        },
    },
}

_PYTYPE = {"str": str, "int": int, "bool": bool, "array": list, "object": dict}


def default_timezone() -> str:
    return os.environ.get("MSTODO_TIMEZONE") or DEFAULT_TIMEZONE


def expand_datetime(value: Any) -> Any:
    """把日期简写展开为 Graph 的 dateTimeTimeZone 嵌套对象。

    接受的字符串格式：
    - YYYY-MM-DD（展开为 YYYY-MM-DDTHH:MM:SS）
    - YYYY-MM-DDTHH:MM:SS（可包含小数秒）

    非字符串、非 dict 的值原样透传（类型校验由 validate_body 负责）。
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return value

    # 验证日期形状：YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS（含小数秒）
    # 使用 \Z 而非 $ 严格匹配字符串结尾（$ 允许尾随换行）
    date_pattern = r'^\d{4}-\d{2}-\d{2}\Z'
    datetime_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\Z'

    if re.match(date_pattern, value):
        stamp = f"{value}T00:00:00"
    elif re.match(datetime_pattern, value):
        stamp = value
    else:
        raise InvalidDatetimeFormat(
            f"日期时间格式应为 'YYYY-MM-DD' 或 'YYYY-MM-DDTHH:MM:SS'，"
            f"实际为: {value!r}"
        )

    return {"dateTime": stamp, "timeZone": default_timezone()}


def expand_body_field(value: Any) -> Any:
    """把纯文本描述展开为 Graph 的 itemBody 对象。"""
    if isinstance(value, str):
        return {"content": value, "contentType": "text"}
    return value


def normalize_body(operation: str, body: dict) -> dict:
    """展开日期与 body 字段。

    仅展开该操作 schema 里声明的字段。未声明的字段原样透传。
    不修改调用方传入的 dict。

    可能抛出 InvalidDatetimeFormat（若日期字符串形状不合法）。
    """
    schema = OPERATION_SCHEMAS[operation]
    declared_fields = schema["fields"]
    result = copy.deepcopy(body)

    for key in list(result):
        if key not in declared_fields:
            continue  # 未声明的字段原样透传
        if key in DATETIME_FIELDS:
            result[key] = expand_datetime(result[key])
        elif key == "body":
            result[key] = expand_body_field(result[key])

    return result


def get_schema(operation: str) -> dict:
    return OPERATION_SCHEMAS[operation]


def all_schemas() -> dict:
    return OPERATION_SCHEMAS


def _type_names(declared: Any) -> list[str]:
    return list(declared) if isinstance(declared, list) else [declared]


def validate_body(operation: str, body: dict) -> list[str]:
    """校验请求体。返回错误消息列表，空列表表示通过。"""
    schema = OPERATION_SCHEMAS[operation]
    fields = schema["fields"]
    errors: list[str] = []

    for name, spec in fields.items():
        if spec.get("required") and name not in body:
            errors.append(f"{operation} 缺少必需字段: {name}")

    if schema.get("at_least_one") and not body:
        errors.append(f"{operation} 至少需要一个待更新字段")

    for name, value in body.items():
        spec = fields.get(name)
        if spec is None:
            continue  # 未收录字段交给 Graph 判断，raw 子命令是逃生舱
        allowed = [_PYTYPE[t] for t in _type_names(spec["type"]) if t in _PYTYPE]
        if allowed and not isinstance(value, tuple(allowed)):
            names = " 或 ".join(_type_names(spec["type"]))
            errors.append(f"{operation} 的 {name} 类型应为 {names}，"
                          f"实际为 {type(value).__name__}")
            continue
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{operation} 的 {name} 取值非法: {value!r}，"
                          f"允许值: {', '.join(map(str, spec['enum']))}")

    return errors
