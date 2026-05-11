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
import re
import sys

import httpx

BASE_DOMAIN = os.environ.get("DIDA365_API_DOMAIN", "api.dida365.com")
_API_PREFIX = "/open/v1"
BASE_URL = f"https://{BASE_DOMAIN}{_API_PREFIX}"
TOKEN = os.environ.get("DIDA365_API_TOKEN", "")

# 语义化退出码（Agent-Native 设计规范）
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION = 4
EXIT_DRYRUN = 10

# HTTP 状态码到语义退出码的映射
_STATUS_TO_EXIT = {401: EXIT_PERMISSION, 403: EXIT_PERMISSION, 404: EXIT_NOT_FOUND}


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


def _pick(obj: object, fields: set[str]) -> object:
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k in fields}
    return obj


def apply_fields_mask(data: object, fields_str: str) -> object:
    """按逗号分隔的字段名保留顶层 key（list 元素逐项处理）。"""
    fields = {f.strip() for f in fields_str.split(",") if f.strip()}
    if not fields:
        return data
    if isinstance(data, list):
        return [_pick(item, fields) for item in data]
    return _pick(data, fields)


def _split_csv(s: str, *, cast=str) -> list:
    """逗号分隔字符串 → 列表，去空白、丢空项；可选 cast 转换元素类型。"""
    return [cast(x.strip()) for x in s.split(",") if x.strip()]


def output(
    data: object,
    *,
    command: str,
    took_ms: int | None = None,
    fields: str | None = None,
    extra_metadata: dict | None = None,
) -> None:
    """输出统一 JSON 成功信封。"""
    if fields:
        data = apply_fields_mask(data, fields)
    metadata: dict = {"command": f"dida365_cli {command}"}
    if took_ms is not None:
        metadata["took_ms"] = took_ms
    if isinstance(data, list):
        metadata["result_count"] = len(data)
    if extra_metadata:
        metadata.update(extra_metadata)
    envelope = {"success": True, "data": data, "metadata": metadata}
    print(json.dumps(envelope, ensure_ascii=False, indent=2))


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date(s: str | None) -> str | None:
    """将 YYYY-MM-DD 自动补齐为 ISO 8601（默认 +0800 时区，零时整点）。

    完整格式（含 T 与时区）原样返回，None 也原样返回。
    """
    if s and _DATE_ONLY_RE.match(s):
        return f"{s}T00:00:00+0800"
    return s


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


def execute(
    method: str,
    path: str,
    args: argparse.Namespace,
    command: str,
    *,
    json_body: object | None = None,
) -> None:
    """统一执行器：处理 --dry-run、HTTP 调用、计时、信封输出。"""
    if getattr(args, "dry_run", False):
        preview: dict = {"would_call": f"{method.upper()} {_API_PREFIX}{path}"}
        if json_body is not None:
            preview["body"] = json_body
        output(preview, command=command, extra_metadata={"dry_run": True})
        sys.exit(EXIT_DRYRUN)
    with get_client() as c:
        resp = c.request(method, path, json=json_body)
        took_ms = int(resp.elapsed.total_seconds() * 1000)
        data = handle_response(resp)
    output(data, command=command, took_ms=took_ms, fields=getattr(args, "fields", None))


# ── 项目操作 ──────────────────────────────────────────────────────────────────


def cmd_list_projects(args: argparse.Namespace) -> None:
    execute("GET", "/project", args, "list-projects")


def cmd_get_project(args: argparse.Namespace) -> None:
    execute("GET", f"/project/{args.project_id}", args, "get-project")


def cmd_get_project_data(args: argparse.Namespace) -> None:
    execute("GET", f"/project/{args.project_id}/data", args, "get-project-data")


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
    execute("POST", "/project", args, "create-project", json_body=body)


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
    execute("POST", f"/project/{args.project_id}", args, "update-project", json_body=body)


def cmd_delete_project(args: argparse.Namespace) -> None:
    execute("DELETE", f"/project/{args.project_id}", args, "delete-project")


# ── 任务操作 ──────────────────────────────────────────────────────────────────


def cmd_get_task(args: argparse.Namespace) -> None:
    execute("GET", f"/project/{args.project_id}/task/{args.task_id}", args, "get-task")


def cmd_create_task(args: argparse.Namespace) -> None:
    body: dict = {"title": args.title, "projectId": args.project}
    if args.content:
        body["content"] = args.content
    if args.desc:
        body["desc"] = args.desc
    if args.priority is not None:
        body["priority"] = args.priority
    if args.due_date:
        body["dueDate"] = normalize_date(args.due_date)
    if args.start_date:
        body["startDate"] = normalize_date(args.start_date)
    if args.time_zone:
        body["timeZone"] = args.time_zone
    if args.all_day:
        body["isAllDay"] = True
    if args.tags:
        body["tags"] = _split_csv(args.tags)
    if args.repeat_flag:
        body["repeatFlag"] = args.repeat_flag
    execute("POST", "/task", args, "create-task", json_body=body)


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
        body["dueDate"] = normalize_date(args.due_date)
    if args.start_date:
        body["startDate"] = normalize_date(args.start_date)
    if args.time_zone:
        body["timeZone"] = args.time_zone
    if args.all_day is not None:
        body["isAllDay"] = args.all_day
    if args.tags:
        body["tags"] = _split_csv(args.tags)
    if args.repeat_flag:
        body["repeatFlag"] = args.repeat_flag
    if args.status is not None:
        body["status"] = args.status
    execute("POST", f"/task/{args.task_id}", args, "update-task", json_body=body)


def cmd_complete_task(args: argparse.Namespace) -> None:
    execute(
        "POST",
        f"/project/{args.project_id}/task/{args.task_id}/complete",
        args,
        "complete-task",
    )


def cmd_delete_task(args: argparse.Namespace) -> None:
    execute(
        "DELETE",
        f"/project/{args.project_id}/task/{args.task_id}",
        args,
        "delete-task",
    )


def cmd_move_tasks(args: argparse.Namespace) -> None:
    task_ids = _split_csv(args.tasks)
    payload = [
        {"fromProjectId": args.from_project, "toProjectId": args.to_project, "taskId": tid}
        for tid in task_ids
    ]
    execute("POST", "/task/move", args, "move-tasks", json_body=payload)


# ── 查询操作 ──────────────────────────────────────────────────────────────────


def cmd_filter_tasks(args: argparse.Namespace) -> None:
    body: dict = {}
    if args.projects:
        body["projectIds"] = _split_csv(args.projects)
    if args.start_date:
        body["startDate"] = normalize_date(args.start_date)
    if args.end_date:
        body["endDate"] = normalize_date(args.end_date)
    if args.priority:
        body["priority"] = _split_csv(args.priority, cast=int)
    if args.tags:
        body["tag"] = _split_csv(args.tags)
    if args.status:
        body["status"] = _split_csv(args.status, cast=int)
    execute("POST", "/task/filter", args, "filter-tasks", json_body=body)


def cmd_query_completed(args: argparse.Namespace) -> None:
    body: dict = {}
    if args.projects:
        body["projectIds"] = _split_csv(args.projects)
    if args.start_date:
        body["startDate"] = normalize_date(args.start_date)
    if args.end_date:
        body["endDate"] = normalize_date(args.end_date)
    execute("POST", "/task/completed", args, "query-completed", json_body=body)


# ── Schema 自省 ───────────────────────────────────────────────────────────────


def _action_type_name(action: argparse.Action) -> str:
    if isinstance(action, argparse.BooleanOptionalAction):
        return "tristate-flag"
    if isinstance(action, argparse._StoreTrueAction):
        return "flag"
    if action.type is not None:
        return getattr(action.type, "__name__", str(action.type))
    return "string"


def _argparse_to_schema(name: str, sp: argparse.ArgumentParser, description: str) -> dict:
    """从 argparse subparser 反射出参数 schema。

    依赖 argparse 内部 API（_actions、_choices_actions、_SubParsersAction、
    _StoreTrueAction、BooleanOptionalAction）——Python 版本升级时需复测。
    """
    params = []
    for action in sp._actions:
        if action.dest == "help":
            continue
        param: dict = {
            "name": action.option_strings[0] if action.option_strings else action.dest,
            "dest": action.dest,
            "required": bool(action.required),
            "type": _action_type_name(action),
            "help": action.help or "",
        }
        if not action.option_strings:
            param["positional"] = True
        if action.choices:
            param["choices"] = list(action.choices)
        if action.default not in (None, argparse.SUPPRESS, False):
            param["default"] = action.default
        params.append(param)
    return {"command": name, "description": description, "parameters": params}


def cmd_schema(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    sub_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    help_by_name = {a.dest: (a.help or "") for a in sub_action._choices_actions}
    available = sorted(n for n in sub_action.choices if n != "schema")

    if args.command_name:
        if args.command_name not in sub_action.choices or args.command_name == "schema":
            _fail(
                "UNKNOWN_COMMAND",
                f"未知子命令 '{args.command_name}'",
                suggestion=f"可用命令: {', '.join(available)}",
                exit_code=EXIT_USAGE,
            )
        schema = _argparse_to_schema(
            args.command_name,
            sub_action.choices[args.command_name],
            help_by_name.get(args.command_name, ""),
        )
        output(schema, command=f"schema {args.command_name}")
        return

    all_schemas = {
        name: _argparse_to_schema(name, sub_action.choices[name], help_by_name.get(name, ""))
        for name in available
    }
    output({"commands": all_schemas}, command="schema")


# ── CLI 入口 ──────────────────────────────────────────────────────────────────


EPILOG = """\
示例:
  dida365_cli list-projects --fields id,name
  dida365_cli create-task --project <项目ID> --title "买菜" --due-date 2026-05-20
  dida365_cli update-task <任务ID> --project <项目ID> --status 1            # 放弃任务
  dida365_cli delete-task <项目ID> <任务ID> --dry-run                        # 预演删除（退出码 10）
  dida365_cli filter-tasks --priority 3,5 --status 0 --fields id,title,dueDate
  dida365_cli schema                                                         # 列出所有子命令的参数 schema
  dida365_cli schema create-task                                             # 查看单个命令的 schema

全局选项（所有子命令均可用）:
  --fields KEY[,KEY...]    顶层字段掩码，列表自动逐项裁剪
  --dry-run                只输出 would_call 而不真正调用 API，退出码 10

退出码:
  0=成功  1=一般错误  2=参数/用法错误  3=资源不存在  4=权限不足  10=dry-run 预览
"""


def build_parser() -> argparse.ArgumentParser:
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument("--fields", help="顶层字段掩码（逗号分隔），保护上下文窗口")
    global_parser.add_argument("--dry-run", action="store_true",
                               help="只输出将要发起的 API 调用（不执行），退出码 10")

    parser = argparse.ArgumentParser(
        prog="dida365_cli",
        description="滴答清单 Open API CLI 工具",
        parents=[global_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── 项目 ──
    sub.add_parser("list-projects", help="获取所有项目", parents=[global_parser])

    p = sub.add_parser("get-project", help="获取单个项目", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")

    p = sub.add_parser("get-project-data", help="获取项目及其任务和列", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID（可用 'inbox' 获取收集箱）")

    p = sub.add_parser("create-project", help="创建项目", parents=[global_parser])
    p.add_argument("--name", required=True, help="项目名称")
    p.add_argument("--color", help="项目颜色，如 #F18181")
    p.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    p.add_argument("--kind", choices=["TASK", "NOTE"], help="项目类型")
    p.add_argument("--sort-order", type=int, help="排序值")

    p = sub.add_parser("update-project", help="更新项目", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("--name", help="项目名称")
    p.add_argument("--color", help="项目颜色")
    p.add_argument("--view-mode", choices=["list", "kanban", "timeline"], help="视图模式")
    p.add_argument("--kind", choices=["TASK", "NOTE"], help="项目类型")
    p.add_argument("--sort-order", type=int, help="排序值")

    p = sub.add_parser("delete-project", help="删除项目", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")

    # ── 任务 ──
    p = sub.add_parser("get-task", help="获取单个任务", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("create-task", help="创建任务", parents=[global_parser])
    p.add_argument("--project", required=True, help="项目 ID")
    p.add_argument("--title", required=True, help="任务标题")
    p.add_argument("--content", help="任务内容")
    p.add_argument("--desc", help="清单描述")
    p.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级: 0=无 1=低 3=中 5=高")
    p.add_argument("--due-date", help="截止时间 (支持 YYYY-MM-DD 或完整 ISO 8601, 如 2026-04-05T00:00:00+0800)")
    p.add_argument("--start-date", help="开始时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--time-zone", help="时区，如 Asia/Shanghai")
    p.add_argument("--all-day", action="store_true", help="全天任务")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--repeat-flag", help="循环规则 (RRULE 格式)")

    p = sub.add_parser("update-task", help="更新任务", parents=[global_parser])
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--project", required=True, help="项目 ID")
    p.add_argument("--title", help="任务标题")
    p.add_argument("--content", help="任务内容")
    p.add_argument("--desc", help="清单描述")
    p.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="优先级")
    p.add_argument("--due-date", help="截止时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--start-date", help="开始时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--time-zone", help="时区")
    p.add_argument("--all-day", action=argparse.BooleanOptionalAction, default=None,
                   help="全天任务 (--all-day / --no-all-day)")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--repeat-flag", help="循环规则 (RRULE 格式)")
    p.add_argument("--status", type=int, choices=[0, 1, 2], help="状态: 0=未完成 1=放弃 2=已完成")

    p = sub.add_parser("complete-task", help="完成任务", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("delete-task", help="删除任务", parents=[global_parser])
    p.add_argument("project_id", help="项目 ID")
    p.add_argument("task_id", help="任务 ID")

    p = sub.add_parser("move-tasks", help="移动任务到其他项目", parents=[global_parser])
    p.add_argument("--from", dest="from_project", required=True, help="源项目 ID")
    p.add_argument("--to", dest="to_project", required=True, help="目标项目 ID")
    p.add_argument("--tasks", required=True, help="任务 ID，逗号分隔")

    # ── 查询 ──
    p = sub.add_parser("filter-tasks", help="按条件筛选任务", parents=[global_parser])
    p.add_argument("--projects", help="项目 ID，逗号分隔")
    p.add_argument("--start-date", help="起始时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--end-date", help="结束时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--priority", help="优先级，逗号分隔 (0,1,3,5)")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--status", help="状态，逗号分隔 (0=未完成,2=已完成)")

    p = sub.add_parser("query-completed", help="查询已完成任务", parents=[global_parser])
    p.add_argument("--projects", help="项目 ID，逗号分隔")
    p.add_argument("--start-date", help="起始时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")
    p.add_argument("--end-date", help="结束时间 (支持 YYYY-MM-DD 或完整 ISO 8601)")

    # ── Schema 自省 ──
    p = sub.add_parser("schema", help="输出子命令的参数 JSON Schema（用于 Agent 自省）",
                       parents=[global_parser])
    p.add_argument("command_name", nargs="?",
                   help="子命令名（留空则输出全部）")

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
    if args.command == "schema":
        cmd_schema(args, parser)
        return
    COMMAND_MAP[args.command](args)


if __name__ == "__main__":
    main()
