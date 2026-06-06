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
from typing import Any, NoReturn

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
        "require_content": True,
    },
    "create-project": {
        "method": "POST", "path": "/project",
        "locators": {}, "required": ["name"], "fields": _PROJECT_FIELDS,
    },
    "update-project": {
        "method": "POST", "path": "/project/{project_id}",
        "locators": {"project_id": _URL_ONLY}, "required": [], "fields": _PROJECT_FIELDS,
        "require_content": True,
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


_PYTYPE = {"str": str, "int": int, "bool": bool, "array": list}


def load_body(raw: str | None) -> Any:
    """解析 --body JSON 字符串；None/空 → {}。返回类型取决于 JSON 顶层
    （对象 → dict，数组 → list，如 move-tasks）。解析失败抛 ValueError。"""
    if not raw:
        return {}
    return json.loads(raw)


def validate_body(operation: str, body: dict) -> list[str]:
    """按 OPERATION_SCHEMAS 校验 body，返回错误信息列表（空列表表示通过）。
    规则：拒绝未知字段（防 typo，提示改用 raw）、类型不符、enum 越界、缺必填。
    move-tasks（body_is_array）由调用方单独处理，不走本函数。
    """
    schema = OPERATION_SCHEMAS[operation]
    fields = schema["fields"]
    errors: list[str] = []
    for key, val in body.items():
        if key not in fields:
            errors.append(f"未知字段 '{key}'（不在 {operation} 的 schema 中；如确需发送该字段请用 raw 子命令）")
            continue
        spec = fields[key]
        expected = _PYTYPE[spec["type"]]
        # bool 是 int 的子类，需先判 bool 再判 int
        if spec["type"] == "int" and isinstance(val, bool):
            errors.append(f"字段 '{key}' 类型应为 int，收到 bool")
            continue
        if not isinstance(val, expected):
            errors.append(f"字段 '{key}' 类型应为 {spec['type']}，收到 {type(val).__name__}")
            continue
        if "enum" in spec and val not in spec["enum"]:
            errors.append(f"字段 '{key}' 取值应在 {spec['enum']} 内，收到 {val!r}")
    for req in schema.get("required", []):
        if req not in body:
            errors.append(f"缺少必填字段 '{req}'")
    return errors


def assemble_body(operation: str, locator_values: dict, body: dict) -> dict:
    """把定位参数按 locators 映射注入 body（_URL_ONLY/None 映射表示仅用于 path，不注入）。
    用户在 --body 显式给出的同名字段优先保留。"""
    merged = dict(body)
    for cli_arg, body_field in OPERATION_SCHEMAS[operation].get("locators", {}).items():
        if body_field is None:
            continue
        if body_field not in merged and locator_values.get(cli_arg) is not None:
            merged[body_field] = locator_values[cli_arg]
    return merged


def resolve_path(operation: str, locator_values: dict) -> str:
    """用定位参数填充 path 模板，如 /task/{task_id} -> /task/T1。"""
    return OPERATION_SCHEMAS[operation]["path"].format(**locator_values)


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


def _fail(code: str, message: str, *, suggestion: str = "", exit_code: int = EXIT_ERROR) -> NoReturn:
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
    run_body_command("create-project", args, {})


def cmd_update_project(args: argparse.Namespace) -> None:
    run_body_command("update-project", args, {"project_id": args.project_id})


def cmd_delete_project(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.delete(f"/project/{args.project_id}")))


# ── 任务操作 ──────────────────────────────────────────────────────────────────


def cmd_get_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.get(f"/project/{args.project_id}/task/{args.task_id}")))


def run_body_command(operation: str, args: argparse.Namespace, locator_values: dict) -> None:
    """有请求体命令的统一流程：解析 --body → 注入定位 → 校验 → 发送。"""
    try:
        raw_body = load_body(getattr(args, "body", None))
    except (ValueError, json.JSONDecodeError) as exc:
        example = '{"title":"任务标题"}'
        _fail("INVALID_JSON", f"--body 不是合法 JSON：{exc}",
              suggestion=f"示例：--body '{example}'；字段定义见 `schema {operation}`",
              exit_code=EXIT_USAGE)
    if not isinstance(raw_body, dict):
        _fail("INVALID_BODY", "--body 顶层应为 JSON 对象",
              suggestion=f"字段定义见 `schema {operation}`", exit_code=EXIT_USAGE)
    body = assemble_body(operation, locator_values, raw_body)
    errors = validate_body(operation, body)
    if errors:
        _fail("BODY_VALIDATION_FAILED", "请求体校验未通过：" + "；".join(errors),
              suggestion=f"用 `schema {operation}` 查看合法字段；schema 外字段请用 raw 子命令",
              exit_code=EXIT_USAGE)
    schema = OPERATION_SCHEMAS[operation]
    if schema.get("require_content"):
        injected = {f for f in schema.get("locators", {}).values() if f is not None}
        if not (set(body) - injected):
            _fail("INVALID_PARAMETER", "至少需要一个要更新的字段",
                  suggestion=f"在 --body 中提供要修改的字段；字段定义见 `schema {operation}`",
                  exit_code=EXIT_USAGE)
    path = resolve_path(operation, locator_values)
    with get_client() as c:
        output(handle_response(c.request(OPERATION_SCHEMAS[operation]["method"], path, json=body)))


def cmd_create_task(args: argparse.Namespace) -> None:
    run_body_command("create-task", args, {"project": args.project})


def cmd_update_task(args: argparse.Namespace) -> None:
    run_body_command("update-task", args, {"task_id": args.task_id, "project": args.project})


def cmd_complete_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.post(f"/project/{args.project_id}/task/{args.task_id}/complete")))


def cmd_delete_task(args: argparse.Namespace) -> None:
    with get_client() as c:
        output(handle_response(c.delete(f"/project/{args.project_id}/task/{args.task_id}")))


def cmd_move_tasks(args: argparse.Namespace) -> None:
    try:
        payload = load_body(args.body)
    except (ValueError, json.JSONDecodeError) as exc:
        _fail("INVALID_JSON", f"--body 不是合法 JSON：{exc}",
              suggestion='示例：--body \'[{"fromProjectId":"A","toProjectId":"B","taskId":"T1"}]\'',
              exit_code=EXIT_USAGE)
    if not isinstance(payload, list) or not payload:
        _fail("INVALID_BODY", "move-tasks 的 --body 应为非空 JSON 数组",
              suggestion="每个元素需含 fromProjectId/toProjectId/taskId", exit_code=EXIT_USAGE)
    allowed = set(OPERATION_SCHEMAS["move-tasks"]["fields"])
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            _fail("INVALID_BODY", f"第 {i} 个元素应为对象", exit_code=EXIT_USAGE)
        bad = set(item) - allowed
        if bad:
            _fail("INVALID_BODY", f"第 {i} 个元素含未知字段 {sorted(bad)}",
                  suggestion=f"允许字段：{sorted(allowed)}", exit_code=EXIT_USAGE)
        missing = allowed - set(item)
        if missing:
            _fail("INVALID_BODY", f"第 {i} 个元素缺少必填字段 {sorted(missing)}",
                  suggestion="每个元素需含 fromProjectId/toProjectId/taskId", exit_code=EXIT_USAGE)
    with get_client() as c:
        output(handle_response(c.request("POST", "/task/move", json=payload)))


# ── 查询操作 ──────────────────────────────────────────────────────────────────


def cmd_filter_tasks(args: argparse.Namespace) -> None:
    run_body_command("filter-tasks", args, {})


def cmd_query_completed(args: argparse.Namespace) -> None:
    run_body_command("query-completed", args, {})


# ── 通用透传 ─────────────────────────────────────────────────────────────────


def cmd_raw(args: argparse.Namespace) -> None:
    """通用透传：对任意端点发任意请求体。绕过 schema 校验，用于 schema 未收录的字段/端点。
    仍享受认证注入、统一信封与退出码。"""
    method = args.method.upper()
    try:
        body = load_body(args.body) if args.body else None
    except (ValueError, json.JSONDecodeError) as exc:
        _fail("INVALID_JSON", f"--body 不是合法 JSON：{exc}", exit_code=EXIT_USAGE)
    path = args.path if args.path.startswith("/") else "/" + args.path
    with get_client() as c:
        output(handle_response(c.request(method, path, json=body)))


# ── Schema 自省 ──────────────────────────────────────────────────────────────


def cmd_schema(args: argparse.Namespace) -> None:
    """输出操作的字段 schema（单一事实来源），供 agent 构造 --body。"""
    if args.all:
        output({op: s for op, s in OPERATION_SCHEMAS.items()})
        return
    if not args.operation:
        _fail("INVALID_PARAMETER", "需指定操作名或使用 --all",
              suggestion=f"可选操作：{', '.join(OPERATION_SCHEMAS)}", exit_code=EXIT_USAGE)
    if args.operation not in OPERATION_SCHEMAS:
        _fail("UNKNOWN_OPERATION", f"未知操作 '{args.operation}'",
              suggestion=f"可选操作：{', '.join(OPERATION_SCHEMAS)}", exit_code=EXIT_USAGE)
    output(OPERATION_SCHEMAS[args.operation])


# ── CLI 入口 ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dida365_cli",
        description="滴答清单 Open API CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "字段透传说明：\n"
            "  有请求体的命令（create-task/update-task/create-project/update-project/\n"
            "  filter-tasks/query-completed/move-tasks）字段统一经 --body JSON 传入。\n"
            "  构造 --body 前，用 `schema <操作>` 查询该操作的完整字段定义。\n"
            "\n"
            "完备性：\n"
            "  schema 未收录的字段或端点，用 `raw --method --path --body` 直接透传。\n"
            "  任何 Open API 能做的操作 CLI 都不限制。\n"
            "\n"
            "示例：\n"
            "  dida365_cli.py schema create-task\n"
            "  dida365_cli.py create-task --project inbox --body '{\"title\":\"买菜\"}'\n"
            "  dida365_cli.py raw --method POST --path /task/<id> --body '{...}'"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── 项目 ──
    sub.add_parser("list-projects", help="获取所有项目")

    p = sub.add_parser("get-project", help="获取单个项目")
    p.add_argument("project_id", help="项目 ID")

    p = sub.add_parser("get-project-data", help="获取项目及其任务和列")
    p.add_argument("project_id", help="项目 ID（可用 'inbox' 获取收集箱）")

    p = sub.add_parser("create-project", help="创建项目（字段经 --body，见 `schema create-project`）")
    p.add_argument("--body", help="请求体 JSON，如 '{\"name\":\"工作\"}'，见 `schema create-project`")

    p = sub.add_parser("update-project", help="更新项目（字段经 --body，见 `schema update-project`）")
    p.add_argument("project_id", help="项目 ID（path）")
    p.add_argument("--body", help="请求体 JSON，只传要改的字段")

    p = sub.add_parser("delete-project", help="删除项目")
    p.add_argument("project_id", help="项目 ID")

    # ── 任务 ──
    p = sub.add_parser("get-task", help="获取单个任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("create-task", help="创建任务（字段经 --body JSON 传入，见 `schema create-task`）")
    p.add_argument("--project", required=True, help="项目 ID（注入 body.projectId）")
    p.add_argument("--body", help="请求体 JSON，字段见 `schema create-task`，如 '{\"title\":\"买菜\"}'")

    p = sub.add_parser("update-task", help="更新任务（字段经 --body JSON 传入，见 `schema update-task`）")
    p.add_argument("task_id", help="任务 ID（注入 path 与 body.id）")
    p.add_argument("--project", required=True, help="项目 ID（注入 body.projectId）")
    p.add_argument("--body", help="请求体 JSON，只传要改的字段，见 `schema update-task`")

    p = sub.add_parser("complete-task", help="完成任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("delete-task", help="删除任务")
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("move-tasks", help="移动任务到其他项目（--body 为 JSON 数组，见 `schema move-tasks`）")
    p.add_argument("--body", required=True,
                   help='JSON 数组，如 \'[{"fromProjectId":"A","toProjectId":"B","taskId":"T1"}]\'')

    # ── 查询 ──
    p = sub.add_parser("filter-tasks", help="按条件筛选任务（条件经 --body，见 `schema filter-tasks`）")
    p.add_argument("--body", help="筛选条件 JSON，如 '{\"priority\":[3,5],\"status\":[0]}'")

    p = sub.add_parser("query-completed", help="查询已完成任务（条件经 --body，见 `schema query-completed`）")
    p.add_argument("--body", help="查询条件 JSON，如 '{\"projectIds\":[\"<id>\"]}'")


    # ── Schema 自省 ──
    p = sub.add_parser("schema", help="输出某操作的请求体字段 schema（构造 --body 前查询）")
    p.add_argument("operation", nargs="?", help="操作名，如 create-task；省略时配合 --all")
    p.add_argument("--all", action="store_true", help="输出全部操作的 schema")

    # ── 通用透传 ──
    p = sub.add_parser("raw", help="通用透传：对任意 Open API 端点发任意请求体（schema 兜底逃生舱）")
    p.add_argument("--method", required=True, type=str.upper,
                   choices=["GET", "POST", "DELETE", "PUT"], help="HTTP 方法（大小写不限）")
    p.add_argument("--path", required=True, help="API 路径（/open/v1 之后部分），如 /task/<id>")
    p.add_argument("--body", help="请求体 JSON（GET/DELETE 可省略）")

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
    "schema": cmd_schema,
    "raw": cmd_raw,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    COMMAND_MAP[args.command](args)


if __name__ == "__main__":
    main()
