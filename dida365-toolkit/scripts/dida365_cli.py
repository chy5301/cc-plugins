# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///
"""滴答清单 Open API CLI 工具。

通过子命令调用滴答清单 Open API，支持任务和项目的完整生命周期管理。

环境变量:
    DIDA365_API_TOKEN: API Token（必需，在滴答清单 设置→账户→API Token 中获取）
    DIDA365_API_DOMAIN: API 域名（可选，默认 api.dida365.com，国际版用 api.ticktick.com）
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

BASE_DOMAIN = os.environ.get("DIDA365_API_DOMAIN", "api.dida365.com")
BASE_URL = f"https://{BASE_DOMAIN}/open/v1"
TOKEN = os.environ.get("DIDA365_API_TOKEN", "")

# 语义化退出码（Agent-Native 设计规范）
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION = 4

# HTTP 状态码到语义退出码的映射
_STATUS_TO_EXIT = {401: EXIT_PERMISSION, 403: EXIT_PERMISSION, 404: EXIT_NOT_FOUND}

# locators 把 CLI 参数映射到请求体字段名；值为 _URL_ONLY 表示该参数仅用于 URL path，
# 不注入 body。注意：path/定位参数由 argparse（位置参数）强制必填，故不列入各操作的
# `required`（`required` 仅用于校验 body 字段）。
_URL_ONLY = None

# update-task 与 create-task 共享大部分字段：先构造共享字段，再分别组装
_TASK_FIELDS = {
    "title":      {"type": "str",  "desc": "任务标题"},
    "content":    {"type": "str",  "desc": "任务内容（正文）"},
    "desc":       {"type": "str",  "desc": "清单描述"},
    "isAllDay":   {"type": "bool", "desc": "是否全天任务"},
    "startDate":  {"type": "str",  "desc": "开始时间 ISO8601，如 2026-04-05T00:00:00+0800"},
    "dueDate":    {"type": "str",  "desc": "截止时间 ISO8601"},
    "timeZone":   {"type": "str",  "desc": "时区，如 Asia/Shanghai"},
    "reminders":  {"type": "array", "desc": "提醒触发器字符串数组，如 [\"TRIGGER:PT0S\",\"TRIGGER:P0DT9H0M0S\"]"},
    "repeatFlag": {"type": "str",  "desc": "循环规则 RRULE，如 RRULE:FREQ=DAILY;INTERVAL=1"},
    "priority":   {"type": "int",  "enum": [0, 1, 3, 5], "desc": "优先级：0无 1低 3中 5高"},
    "sortOrder":  {"type": "int",  "desc": "排序值"},
    "tags":       {"type": "array", "desc": "标签字符串数组，如 [\"工作\",\"紧急\"]"},
    "items":      {"type": "array", "desc": "子任务列表，元素见 api-reference.md ChecklistItem"},
    "projectId":  {"type": "str",  "desc": "所属项目 ID（通常由 --project 注入）"},
}

_PROJECT_FIELDS = {
    "name":      {"type": "str", "desc": "项目名称"},
    "color":     {"type": "str", "desc": "项目颜色，如 #F18181"},
    "viewMode":  {"type": "str", "enum": ["list", "kanban", "timeline"], "desc": "视图模式"},
    "kind":      {"type": "str", "enum": ["TASK", "NOTE"], "desc": "项目类型"},
    "sortOrder": {"type": "int", "desc": "排序值"},
}

OPERATION_SCHEMAS = {
    "create-task": {
        "method": "POST", "path": "/task",
        "locators": {"project": "projectId"},
        "required": ["title", "projectId"],
        "fields": _TASK_FIELDS,
    },
    "update-task": {
        "method": "POST", "path": "/task/{task_id}",
        "locators": {"task_id": "id", "project": "projectId"},
        "required": ["id", "projectId"],
        "fields": {**_TASK_FIELDS, "id": {"type": "str", "desc": "任务 ID"}},
    },
    "create-project": {
        "method": "POST", "path": "/project",
        "locators": {}, "required": ["name"], "fields": _PROJECT_FIELDS,
    },
    "update-project": {
        "method": "POST", "path": "/project/{project_id}",
        "locators": {"project_id": _URL_ONLY}, "required": [], "fields": _PROJECT_FIELDS,
    },
    "filter-tasks": {
        "method": "POST", "path": "/task/filter",
        "locators": {}, "required": [],
        "fields": {
            "projectIds": {"type": "array", "desc": "项目 ID 数组"},
            "startDate":  {"type": "str",  "desc": "任务 startDate >= 此值，ISO8601"},
            "endDate":    {"type": "str",  "desc": "任务 startDate <= 此值，ISO8601"},
            "priority":   {"type": "array", "desc": "优先级数组，如 [3,5]"},
            "tag":        {"type": "array", "desc": "标签数组（AND 关系）"},
            "status":     {"type": "array", "desc": "状态数组：0未完成 2已完成"},
        },
    },
    "query-completed": {
        "method": "POST", "path": "/task/completed",
        "locators": {}, "required": [],
        "fields": {
            "projectIds": {"type": "array", "desc": "项目 ID 数组"},
            "startDate":  {"type": "str",  "desc": "completedTime >= 此值，ISO8601"},
            "endDate":    {"type": "str",  "desc": "completedTime <= 此值，ISO8601"},
        },
    },
    "move-tasks": {
        "method": "POST", "path": "/task/move",
        "locators": {}, "required": [], "body_is_array": True,
        "fields": {
            "fromProjectId": {"type": "str", "desc": "源项目 ID"},
            "toProjectId":   {"type": "str", "desc": "目标项目 ID"},
            "taskId":        {"type": "str", "desc": "任务 ID"},
        },
    },
}


def get_schema(operation: str) -> dict:
    """返回操作的 schema 定义；未知操作抛 KeyError。"""
    return OPERATION_SCHEMAS[operation]


def get_client() -> httpx.Client:
    if not TOKEN:
        _fail("CONFIG_ERROR", "未设置环境变量 DIDA365_API_TOKEN",
              suggestion="在滴答清单网页版 头像→设置→账户与安全→API 口令 中创建，然后设置环境变量",
              exit_code=EXIT_USAGE)
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        timeout=30.0,
    )


def _fail(code: str, message: str, *, suggestion: str = "", exit_code: int = EXIT_ERROR) -> None:
    """输出统一 JSON 错误信封并退出。"""
    envelope: dict = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    if suggestion:
        envelope["error"]["suggestion"] = suggestion
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def output(data: object) -> None:
    """输出统一 JSON 成功信封。"""
    envelope = {"success": True, "data": data}
    print(json.dumps(envelope, ensure_ascii=False, indent=2))


def handle_response(resp: httpx.Response) -> object:
    if resp.status_code >= 400:
        exit_code = _STATUS_TO_EXIT.get(resp.status_code, EXIT_ERROR)
        detail = ""
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            detail = resp.text
        _fail(
            code=f"HTTP_{resp.status_code}",
            message=f"API 返回 {resp.status_code}: {detail}",
            suggestion="检查参数是否正确；401 表示 Token 无效或过期",
            exit_code=exit_code,
        )
    if resp.status_code == 204 or not resp.content:
        return {"status": "ok"}
    return resp.json()


# ── 项目操作 ──────────────────────────────────────────────────────────────────


def cmd_list_projects(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.get("/project")))


def cmd_get_project(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.get(f"/project/{args.project_id}")))


def cmd_get_project_data(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.get(f"/project/{args.project_id}/data")))


def cmd_create_project(args: argparse.Namespace) -> None:
    body: dict = {"name": args.name}
    if args.color:
        body["color"] = args.color
    if args.view_mode:
        body["viewMode"] = args.view_mode
    if args.kind:
        body["kind"] = args.kind
    if args.sort_order is not None:
        body["sortOrder"] = args.sort_order
    with get_client() as c:
        output(handle_response(c.post("/project", json=body)))


def cmd_update_project(args: argparse.Namespace) -> None:
    body: dict = {}
    if args.name:
        body["name"] = args.name
    if args.color:
        body["color"] = args.color
    if args.view_mode:
        body["viewMode"] = args.view_mode
    if args.kind:
        body["kind"] = args.kind
    if args.sort_order is not None:
        body["sortOrder"] = args.sort_order
    if not body:
        _fail("INVALID_PARAMETER", "至少需要一个要更新的字段",
              suggestion="使用 --name, --color, --view-mode, --kind 或 --sort-order 指定要更新的字段",
              exit_code=EXIT_USAGE)
    with get_client() as c:
        output(handle_response(c.post(f"/project/{args.project_id}", json=body)))


def cmd_delete_project(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.delete(f"/project/{args.project_id}")))


# ── 任务操作 ──────────────────────────────────────────────────────────────────


def cmd_get_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.get(f"/project/{args.project_id}/task/{args.task_id}")))


def cmd_create_task(args: argparse.Namespace) -> None:
    body: dict = {"title": args.title, "projectId": args.project}
    if args.content:
        body["content"] = args.content
    if args.desc:
        body["desc"] = args.desc
    if args.priority is not None:
        body["priority"] = args.priority
    if args.due_date:
        body["dueDate"] = args.due_date
    if args.start_date:
        body["startDate"] = args.start_date
    if args.time_zone:
        body["timeZone"] = args.time_zone
    if args.all_day:
        body["isAllDay"] = True
    if args.tags:
        body["tags"] = args.tags.split(",")
    if args.repeat_flag:
        body["repeatFlag"] = args.repeat_flag
    with get_client() as c:
        output(handle_response(c.post("/task", json=body)))


def cmd_update_task(args: argparse.Namespace) -> None:
    body: dict = {"id": args.task_id, "projectId": args.project}
    if args.title:
        body["title"] = args.title
    if args.content:
        body["content"] = args.content
    if args.desc:
        body["desc"] = args.desc
    if args.priority is not None:
        body["priority"] = args.priority
    if args.due_date:
        body["dueDate"] = args.due_date
    if args.start_date:
        body["startDate"] = args.start_date
    if args.time_zone:
        body["timeZone"] = args.time_zone
    if args.all_day is not None:
        body["isAllDay"] = args.all_day
    if args.tags:
        body["tags"] = args.tags.split(",")
    if args.repeat_flag:
        body["repeatFlag"] = args.repeat_flag
    with get_client() as c:
        output(handle_response(c.post(f"/task/{args.task_id}", json=body)))


def cmd_complete_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.post(f"/project/{args.project_id}/task/{args.task_id}/complete")))


def cmd_delete_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.delete(f"/project/{args.project_id}/task/{args.task_id}")))


def cmd_move_tasks(args: argparse.Namespace) -> None:
    task_ids = args.tasks.split(",")
    payload = [
        {"fromProjectId": args.from_project, "toProjectId": args.to_project, "taskId": tid}
        for tid in task_ids
    ]
    with get_client() as c:
        output(handle_response(c.post("/task/move", json=payload)))


# ── 查询操作 ──────────────────────────────────────────────────────────────────


def cmd_filter_tasks(args: argparse.Namespace) -> None:
    body: dict = {}
    if args.projects:
        body["projectIds"] = args.projects.split(",")
    if args.start_date:
        body["startDate"] = args.start_date
    if args.end_date:
        body["endDate"] = args.end_date
    if args.priority:
        body["priority"] = [int(p) for p in args.priority.split(",")]
    if args.tags:
        body["tag"] = args.tags.split(",")
    if args.status:
        body["status"] = [int(s) for s in args.status.split(",")]
    with get_client() as c:
        output(handle_response(c.post("/task/filter", json=body)))


def cmd_query_completed(args: argparse.Namespace) -> None:
    body: dict = {}
    if args.projects:
        body["projectIds"] = args.projects.split(",")
    if args.start_date:
        body["startDate"] = args.start_date
    if args.end_date:
        body["endDate"] = args.end_date
    with get_client() as c:
        output(handle_response(c.post("/task/completed", json=body)))


# ── CLI 入口 ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dida365_cli",
        description="滴答清单 Open API CLI 工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── 项目 ──
    sub.add_parser("list-projects", help="获取所有项目")

    p = sub.add_parser("get-project", help="获取单个项目")
    p.add_argument("project_id", help="项目 ID")

    p = sub.add_parser("get-project-data", help="获取项目及其任务和列")
    p.add_argument("project_id", help="项目 ID（可用 'inbox' 获取收集箱）")

    p = sub.add_parser("create-project", help="创建项目")
    p.add_argument("--name", required=True, help="项目名称")
    p.add_argument("--color", help="项目颜色，如 #F18181")
    p.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    p.add_argument("--kind", choices=["TASK", "NOTE"], help="项目类型")
    p.add_argument("--sort-order", type=int, help="排序值")

    p = sub.add_parser("update-project", help="更新项目")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("--name", help="项目名称")
    p.add_argument("--color", help="项目颜色")
    p.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    p.add_argument("--kind", choices=["TASK", "NOTE"], help="项目类型")
    p.add_argument("--sort-order", type=int, help="排序值")

    p = sub.add_parser("delete-project", help="删除项目")
    p.add_argument("project_id", help="项目 ID")

    # ── 任务 ──
    p = sub.add_parser("get-task", help="获取单个任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("create-task", help="创建任务")
    p.add_argument("--project", required=True, help="项目 ID")
    p.add_argument("--title", required=True, help="任务标题")
    p.add_argument("--content", help="任务内容")
    p.add_argument("--desc", help="清单描述")
    p.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级: 0=无 1=低 3=中 5=高")
    p.add_argument("--due-date", help="截止时间 (ISO 8601, 如 2026-04-05T00:00:00+0800)")
    p.add_argument("--start-date", help="开始时间 (ISO 8601)")
    p.add_argument("--time-zone", help="时区，如 Asia/Shanghai")
    p.add_argument("--all-day", action="store_true", help="全天任务")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--repeat-flag", help="循环规则 (RRULE 格式)")

    p = sub.add_parser("update-task", help="更新任务")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--project", required=True, help="项目 ID")
    p.add_argument("--title", help="任务标题")
    p.add_argument("--content", help="任务内容")
    p.add_argument("--desc", help="清单描述")
    p.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级")
    p.add_argument("--due-date", help="截止时间 (ISO 8601)")
    p.add_argument("--start-date", help="开始时间 (ISO 8601)")
    p.add_argument("--time-zone", help="时区")
    p.add_argument("--all-day", type=bool, help="全天任务")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--repeat-flag", help="循环规则 (RRULE 格式)")

    p = sub.add_parser("complete-task", help="完成任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("delete-task", help="删除任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("move-tasks", help="移动任务到其他项目")
    p.add_argument("--from", dest="from_project", required=True, help="源项目 ID")
    p.add_argument("--to", dest="to_project", required=True, help="目标项目 ID")
    p.add_argument("--tasks", required=True, help="任务 ID，逗号分隔")

    # ── 查询 ──
    p = sub.add_parser("filter-tasks", help="按条件筛选任务")
    p.add_argument("--projects", help="项目 ID，逗号分隔")
    p.add_argument("--start-date", help="起始时间 (ISO 8601)")
    p.add_argument("--end-date", help="结束时间 (ISO 8601)")
    p.add_argument("--priority", help="优先级，逗号分隔 (0,1,3,5)")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--status", help="状态，逗号分隔 (0=未完成,2=已完成)")

    p = sub.add_parser("query-completed", help="查询已完成任务")
    p.add_argument("--projects", help="项目 ID，逗号分隔")
    p.add_argument("--start-date", help="起始时间 (ISO 8601)")
    p.add_argument("--end-date", help="结束时间 (ISO 8601)")

    return parser


COMMAND_MAP = {
    "list-projects": cmd_list_projects,
    "get-project": cmd_get_project,
    "get-project-data": cmd_get_project_data,
    "create-project": cmd_create_project,
    "update-project": cmd_update_project,
    "delete-project": cmd_delete_project,
    "get-task": cmd_get_task,
    "create-task": cmd_create_task,
    "update-task": cmd_update_task,
    "complete-task": cmd_complete_task,
    "delete-task": cmd_delete_task,
    "move-tasks": cmd_move_tasks,
    "filter-tasks": cmd_filter_tasks,
    "query-completed": cmd_query_completed,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    COMMAND_MAP[args.command](args)


if __name__ == "__main__":
    main()
