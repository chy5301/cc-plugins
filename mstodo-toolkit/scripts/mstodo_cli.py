# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///
"""Microsoft To Do CLI（基于 Microsoft Graph v1.0 的 To Do API）。

认证走 OAuth2 设备码流，token 缓存在本机 ~/ 下的独立目录。

环境变量:
    MSTODO_CLIENT_ID:    Azure 应用 client ID（默认用微软第一方公共 client）
    MSTODO_TENANT:       common / consumers / organizations（默认 common）
    MSTODO_TOKEN_CACHE:  token 缓存目录（默认 XDG state 目录）
    MSTODO_TIMEZONE:     日期字段默认时区（默认 Asia/Shanghai）
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable

from mstodo_lib import aggregate, auth, client, schemas
from mstodo_lib import envelope as env

AUTH_COMPLETE_DEFAULT_TIMEOUT = 90


class JsonArgumentParser(argparse.ArgumentParser):
    """用法错误也输出 JSON 信封，而不是裸文本。

    Agent 统一按信封解析输出，裸文本会让它的解析直接崩溃。
    """

    def error(self, message: str):  # type: ignore[override]
        env.fail("INVALID_PARAMETER", message,
                 suggestion="用 --help 查看该子命令的用法",
                 exit_code=env.EXIT_USAGE)


def add_global_options(parser: argparse.ArgumentParser) -> None:
    """挂 --fields / --dry-run / --max-pages 全局选项。"""
    parser.add_argument("--fields", default=None,
                        help="顶层字段掩码，逗号分隔。返回大对象时优先使用")
    parser.add_argument("--dry-run", action="store_true",
                        help="只输出将要发起的 API 调用，不真正执行（退出码 10）")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="集合端点最多跟随几页，0 表示不限。触发上限会标 truncated")


def resolve_token() -> str:
    """取 access_token，把认证异常映射为对应的信封与退出码。

    未登录 → 退出码 2 + CONFIG_ERROR（走完整引导）
    refresh 失败 → 退出码 4 + AUTH_EXPIRED（只需重登）
    """
    try:
        return auth.get_access_token()
    except auth.NotLoggedInError:
        env.fail("CONFIG_ERROR", "本机尚未登录 Microsoft To Do",
                 suggestion="运行 auth-start 开始登录，再用 auth-complete 完成",
                 exit_code=env.EXIT_USAGE)
    except auth.AuthExpiredError as exc:
        env.fail("AUTH_EXPIRED", f"登录凭据已失效：{exc.detail}",
                 suggestion="重新运行 auth-start 登录（凭据过期不是配置问题）",
                 exit_code=env.EXIT_PERMISSION)


# --------------------------------------------------------------------------
# 自省与逃生舱
# --------------------------------------------------------------------------

def cmd_schema(args: argparse.Namespace) -> None:
    """输出请求体字段 schema。自省不需要登录。"""
    if args.all:
        env.output(schemas.all_schemas(), command="schema", fields=args.fields)
    try:
        env.output(schemas.get_schema(args.operation), command="schema", fields=args.fields)
    except KeyError:
        env.fail("UNKNOWN_COMMAND", f"没有名为 {args.operation!r} 的有请求体操作",
                 suggestion=f"用 `schema --all` 查看全部；"
                            f"可用操作: {', '.join(sorted(schemas.all_schemas()))}",
                 exit_code=env.EXIT_USAGE)


def cmd_raw(args: argparse.Namespace) -> None:
    """通用透传：对任意 Graph 端点发任意请求体。

    这是 schema 的兜底逃生舱，linkedResources / attachments / delta 都靠它。
    不剥 OData 噪音、不做 schema 校验，原样返回。
    """
    try:
        body = json.loads(args.body) if args.body else None
    except json.JSONDecodeError as exc:
        env.fail("INVALID_PARAMETER", f"--body 不是合法 JSON：{exc}",
                 exit_code=env.EXIT_USAGE)

    if args.dry_run:
        env.output({"would_call": f"{args.method} {args.path}", "body": body},
                   command="raw", dry_run=True, fields=args.fields,
                   exit_code=env.EXIT_DRY_RUN)

    token = resolve_token()
    started = time.time()
    http = client.make_client()
    try:
        resp = client.request(args.method, args.path, http=http, token=token, body=body)
        if resp.status_code >= 400:
            client.handle_response(resp)   # 抛 GraphError
        try:
            payload = resp.json() if resp.content else None
        except (json.JSONDecodeError, ValueError) as exc:
            # 对任意端点（含二进制、非 JSON 文本响应）的兜底
            preview = resp.text[:200] if resp.text else "(空响应体)"
            env.fail("RAW_RESPONSE_NOT_JSON",
                     f"Graph 返回了非 JSON 的 2xx 响应：{exc}",
                     suggestion=f"检查 --path 是否指向返回二进制或文本的端点；"
                               f"响应体开头：{preview!r}",
                     exit_code=env.EXIT_ERROR)
        env.output(payload, command="raw",
                   took_ms=int((time.time() - started) * 1000), fields=args.fields)
    except client.GraphError as exc:
        env.fail(exc.code, exc.message, exit_code=client.status_to_exit(exc.status))
    finally:
        http.close()


# --------------------------------------------------------------------------
# 认证子命令
# --------------------------------------------------------------------------

def cmd_auth_start(args: argparse.Namespace) -> None:
    """发起设备码登录，立即返回用户码。"""
    try:
        payload = auth.device_code_start()
    except auth.DeviceCodeError as exc:
        env.fail("AUTH_START_FAILED", f"发起设备码流失败：{exc.detail}",
                 suggestion="检查网络与代理，或确认 MSTODO_TENANT 取值合法")
    env.output({
        "user_code": payload["user_code"],
        "verification_uri": payload.get("verification_uri", "https://microsoft.com/link"),
        "device_code": payload["device_code"],
        "expires_in": payload.get("expires_in", 900),
        "interval": payload.get("interval", 5),
    }, command="auth-start", fields=args.fields)


def cmd_auth_complete(args: argparse.Namespace) -> None:
    """轮询等待授权完成并落盘 token。"""
    started = time.time()
    try:
        token = auth.device_code_poll(
            args.device_code,
            interval=args.interval,
            timeout_s=args.timeout,
        )
    except auth.DeviceCodeError as exc:
        if exc.kind == "declined":
            env.fail("AUTH_DECLINED", f"用户拒绝了授权：{exc.detail}",
                     suggestion="重新运行 auth-start 并在浏览器中同意授权")
        if exc.kind == "expired":
            env.fail("AUTH_CODE_EXPIRED", f"设备码已过期：{exc.detail}",
                     suggestion="重新运行 auth-start 获取新的设备码")
        env.fail("AUTH_FAILED", exc.detail, suggestion="重新运行 auth-start")

    if token is None:
        env.fail("AUTH_PENDING",
                 f"等待 {args.timeout} 秒后用户仍未完成授权",
                 suggestion=f"用同一个 device_code 再跑一次："
                            f"auth-complete --device-code {args.device_code}",
                 exit_code=env.EXIT_AUTH_PENDING)

    auth.write_cache(token)
    cached = auth.read_cache()
    if cached is None:
        env.fail("AUTH_CACHE_CORRUPT",
                 "写入缓存后立即读回失败（client_id 或 tenant 可能中途变更）",
                 suggestion="检查环境变量 MSTODO_CLIENT_ID 与 MSTODO_TENANT 未改变，然后重试",
                 exit_code=env.EXIT_ERROR)
    env.output({
        "logged_in": True,
        "tenant": auth.tenant(),
        "scope": cached.get("scope", ""),
        "expires_in_seconds": int(cached.get("expires_at", 0) - time.time()),
    }, command="auth-complete", took_ms=int((time.time() - started) * 1000),
        fields=args.fields)


def cmd_auth_status(args: argparse.Namespace) -> None:
    """查看本机登录状态。"""
    cached = auth.read_cache()
    if cached is None:
        env.fail("CONFIG_ERROR", "本机尚未登录 Microsoft To Do",
                 suggestion="运行 auth-start 开始登录，再用 auth-complete 完成",
                 exit_code=env.EXIT_USAGE)
    env.output({
        "logged_in": True,
        "tenant": auth.tenant(),
        "scope": cached.get("scope", ""),
        "expires_in_seconds": int(cached.get("expires_at", 0) - time.time()),
        "cache_path": str(auth.cache_path()),
    }, command="auth-status", fields=args.fields)


def cmd_auth_logout(args: argparse.Namespace) -> None:
    """删除本机 token 缓存。"""
    env.output({"removed": auth.clear_cache(), "cache_path": str(auth.cache_path())},
               command="auth-logout", fields=args.fields)


# --------------------------------------------------------------------------
# 资源子命令（表驱动）
# --------------------------------------------------------------------------

# CLI 参数名 -> 路径模板占位符
LOCATORS = {"list": "listId", "task": "taskId", "item": "itemId"}

_LISTS = "/me/todo/lists"
_TASKS = "/me/todo/lists/{listId}/tasks"
_ITEMS = "/me/todo/lists/{listId}/tasks/{taskId}/checklistItems"

RESOURCE_COMMANDS: dict[str, dict] = {
    # 清单
    "list-lists":   {"method": "GET",    "path": _LISTS,           "locators": [],
                     "collection": True},
    "get-list":     {"method": "GET",    "path": _LISTS + "/{listId}", "locators": ["list"]},
    "create-list":  {"method": "POST",   "path": _LISTS,           "locators": [],
                     "operation": "create-list"},
    "update-list":  {"method": "PATCH",  "path": _LISTS + "/{listId}", "locators": ["list"],
                     "operation": "update-list"},
    "delete-list":  {"method": "DELETE", "path": _LISTS + "/{listId}", "locators": ["list"]},
    # 任务
    "list-tasks":   {"method": "GET",    "path": _TASKS,           "locators": ["list"],
                     "collection": True},
    "get-task":     {"method": "GET",    "path": _TASKS + "/{taskId}",
                     "locators": ["list", "task"]},
    "create-task":  {"method": "POST",   "path": _TASKS,           "locators": ["list"],
                     "operation": "create-task"},
    "update-task":  {"method": "PATCH",  "path": _TASKS + "/{taskId}",
                     "locators": ["list", "task"], "operation": "update-task"},
    "delete-task":  {"method": "DELETE", "path": _TASKS + "/{taskId}",
                     "locators": ["list", "task"]},
    # 子任务
    "list-checklist-items":  {"method": "GET", "path": _ITEMS,
                              "locators": ["list", "task"], "collection": True},
    "get-checklist-item":    {"method": "GET", "path": _ITEMS + "/{itemId}",
                              "locators": ["list", "task", "item"]},
    "create-checklist-item": {"method": "POST", "path": _ITEMS,
                              "locators": ["list", "task"],
                              "operation": "create-checklist-item"},
    "update-checklist-item": {"method": "PATCH", "path": _ITEMS + "/{itemId}",
                              "locators": ["list", "task", "item"],
                              "operation": "update-checklist-item"},
    "delete-checklist-item": {"method": "DELETE", "path": _ITEMS + "/{itemId}",
                              "locators": ["list", "task", "item"]},
}

_RESOURCE_HELP = {
    "list-lists": "获取所有清单",
    "get-list": "获取单个清单",
    "create-list": "创建清单（字段见 `schema create-list`）",
    "update-list": "更新清单（内置清单不可改名）",
    "delete-list": "删除清单（内置清单不可删除，不可逆，建议先 --dry-run）",
    "list-tasks": "获取清单内的任务（含已完成，用 --status 筛选）",
    "get-task": "获取单个任务",
    "create-task": "创建任务（字段见 `schema create-task`）",
    "update-task": "更新任务，含标记完成（字段见 `schema update-task`）",
    "delete-task": "删除任务（不可逆，建议先 --dry-run）",
    "list-checklist-items": "获取任务的子任务列表",
    "get-checklist-item": "获取单个子任务",
    "create-checklist-item": "创建子任务",
    "update-checklist-item": "更新子任务，含勾选",
    "delete-checklist-item": "删除子任务（不可逆）",
}


def resolve_path(spec: dict, args: argparse.Namespace) -> str:
    values = {LOCATORS[name]: getattr(args, name) for name in spec["locators"]}
    return spec["path"].format(**values)


def load_body(raw: str | None, operation: str | None) -> dict | None:
    """解析 --body JSON，校验并展开。校验不过时在发请求之前就失败。"""
    if operation is None:
        return None
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        env.fail("INVALID_PARAMETER", f"--body 不是合法 JSON：{exc}",
                 suggestion="检查引号与括号；用 `schema <操作>` 查询字段定义",
                 exit_code=env.EXIT_USAGE)
    if not isinstance(parsed, dict):
        env.fail("INVALID_PARAMETER", "--body 必须是一个 JSON 对象",
                 exit_code=env.EXIT_USAGE)
    errors = schemas.validate_body(operation, parsed)
    if errors:
        env.fail("INVALID_PARAMETER", "；".join(errors),
                 suggestion=f"用 `schema {operation}` 查询完整字段定义",
                 exit_code=env.EXIT_USAGE)
    try:
        return schemas.normalize_body(operation, parsed)
    except schemas.InvalidDatetimeFormat as exc:
        # Task 7 的修复轮次引入：日期形状不合法时不再静默透传，
        # 在此转成退出码 2，而不是让裸异常穿透到 Agent 面前。
        env.fail("INVALID_PARAMETER", str(exc),
                 suggestion="日期支持 'YYYY-MM-DD' 或 'YYYY-MM-DDTHH:MM:SS'，"
                            "也可传完整的 {dateTime, timeZone} 对象",
                 exit_code=env.EXIT_USAGE)


def run_resource(name: str, args: argparse.Namespace) -> None:
    spec = RESOURCE_COMMANDS[name]
    path = resolve_path(spec, args)
    body = load_body(getattr(args, "body", None), spec.get("operation"))

    if args.dry_run:
        env.output({"would_call": f"{spec['method']} {path}", "body": body},
                   command=name, dry_run=True, fields=args.fields,
                   exit_code=env.EXIT_DRY_RUN)

    token = resolve_token()
    started = time.time()
    http = client.make_client()
    try:
        if spec.get("collection"):
            items, paging = client.get_collection(
                path, http=http, token=token, max_pages=args.max_pages)
            took = int((time.time() - started) * 1000)
            if paging["truncated"]:
                env.fail("PARTIAL_FAILURE",
                         f"已取 {paging['pages_fetched']} 页后触发 --max-pages 上限，结果不完整",
                         suggestion="提高 --max-pages 或改用更窄的查询条件",
                         exit_code=env.EXIT_PARTIAL,
                         data=env.apply_fields(items, args.fields),
                         extra={"command": f"mstodo_cli {name}",
                                "took_ms": took,
                                "result_count": len(items), **paging})
            env.output(items, command=name, took_ms=took,
                       extra=paging, fields=args.fields)

        resp = client.request(spec["method"], path, http=http, token=token, body=body)
        data = client.handle_response(resp)
        if data is None:
            data = {"deleted": True} if spec["method"] == "DELETE" else {}
        env.output(data, command=name,
                   took_ms=int((time.time() - started) * 1000), fields=args.fields)
    except client.GraphError as exc:
        env.fail(exc.code, exc.message,
                 suggestion="用 `schema <操作>` 核对字段，或用 raw 子命令排查",
                 exit_code=client.status_to_exit(exc.status))
    finally:
        http.close()


def cmd_list_tasks(args: argparse.Namespace) -> None:
    """列出任务。--list all 走跨清单聚合。"""
    if args.dry_run:
        target = "全部清单" if args.list == "all" else args.list
        env.output({"would_call": f"GET /me/todo/lists/{target}/tasks"},
                   command="list-tasks", dry_run=True, fields=args.fields,
                   exit_code=env.EXIT_DRY_RUN)

    token = resolve_token()
    started = time.time()
    http = client.make_client()
    try:
        if args.list == "all":
            lists, _ = client.get_collection("/me/todo/lists", http=http, token=token,
                                             max_pages=args.max_pages)
            items, meta = aggregate.aggregate_tasks(
                lists, http=http, token=token, max_pages=args.max_pages)
        else:
            entry = client.handle_response(client.request(
                "GET", f"/me/todo/lists/{args.list}", http=http, token=token))
            raw, paging = client.get_collection(
                f"/me/todo/lists/{args.list}/tasks", http=http, token=token,
                max_pages=args.max_pages)
            items = aggregate.inject_list_identity(
                raw, list_id=args.list, display_name=entry.get("displayName", ""))
            meta = {"aggregated_from": 1, "partial_failures": [],
                    "retry_after_seconds": None, "all_auth_failed": False,
                    **paging}
            if paging["truncated"]:
                meta["partial_failures"] = [{"listId": args.list,
                                             "displayName": entry.get("displayName", ""),
                                             "status": 0, "retry_after": None,
                                             "reason": "truncated"}]

        # 状态过滤必须在分页完整跟完之后
        items = aggregate.filter_by_status(items, args.status)
        took = int((time.time() - started) * 1000)

        if meta["all_auth_failed"]:
            env.fail("HTTP_403", "所有清单都返回了权限不足",
                     suggestion="检查登录账号与 Tasks.ReadWrite 授权，必要时重新登录",
                     exit_code=env.EXIT_PERMISSION)

        if meta["partial_failures"]:
            wait = meta.get("retry_after_seconds")
            hint = (f"至少等待 {wait} 秒后再重试失败项，不要立即重试"
                    if wait else "失败清单见 metadata.partial_failures")
            env.fail("PARTIAL_FAILURE",
                     f"{meta['aggregated_from']} 个清单中 "
                     f"{meta['aggregated_from'] - len(meta['partial_failures'])} 个成功，"
                     f"{len(meta['partial_failures'])} 个失败",
                     suggestion=f"data 中已含成功部分；{hint}",
                     exit_code=env.EXIT_PARTIAL,
                     data=env.apply_fields(items, args.fields),
                     extra={"command": "mstodo_cli list-tasks", "took_ms": took,
                            "result_count": len(items), **meta})

        env.output(items, command="list-tasks", took_ms=took,
                   extra=meta, fields=args.fields)
    except client.GraphError as exc:
        env.fail(exc.code, exc.message, exit_code=client.status_to_exit(exc.status))
    finally:
        http.close()


# 认证四条 + schema + raw 的字面量 dict；随后 .update() 两次：
# 第一次合入资源表（RESOURCE_COMMANDS）生成的 15 条通用执行器，
# 第二次用 cmd_list_tasks 覆盖 "list-tasks"（聚合 --list all 与 --status）。
# 覆盖必须晚于第一次 .update()，否则会被资源表的通用 run_resource 盖回去。
# 故这里必须保持 .update() 可追加的形状，不能写死成字面量或改成不可变结构。
COMMAND_MAP: dict[str, Callable[[argparse.Namespace], None]] = {
    "auth-start": cmd_auth_start,
    "auth-complete": cmd_auth_complete,
    "auth-status": cmd_auth_status,
    "auth-logout": cmd_auth_logout,
    "schema": cmd_schema,
    "raw": cmd_raw,
}
COMMAND_MAP.update({
    # 用默认参数在定义时绑定 name，避免闭包晚绑定（所有 lambda 共享同一个循环变量）
    name: (lambda args, _name=name: run_resource(_name, args))
    for name in RESOURCE_COMMANDS
})
COMMAND_MAP["list-tasks"] = cmd_list_tasks


def build_parser() -> JsonArgumentParser:
    """组装 argparse 树。"""
    parser = JsonArgumentParser(prog="mstodo_cli",
                                description="Microsoft To Do CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth-start", help="发起设备码登录，立即返回用户码")
    add_global_options(p)

    p = sub.add_parser("auth-complete", help="轮询等待授权完成并落盘 token")
    p.add_argument("--device-code", required=True, help="auth-start 返回的 device_code")
    p.add_argument("--timeout", type=int, default=AUTH_COMPLETE_DEFAULT_TIMEOUT,
                   help="最多等待多少秒（默认 90，刻意小于调用方的 120 秒超时）")
    p.add_argument("--interval", type=int, default=5, help="轮询间隔秒数")
    add_global_options(p)

    p = sub.add_parser("auth-status", help="查看本机登录状态")
    add_global_options(p)

    p = sub.add_parser("auth-logout", help="删除本机 token 缓存")
    add_global_options(p)

    p = sub.add_parser("schema", help="输出某操作的请求体字段 schema（构造 --body 前查询）")
    p.add_argument("operation", nargs="?", help="操作名，如 create-task")
    p.add_argument("--all", action="store_true", help="输出全部操作的 schema")
    add_global_options(p)

    p = sub.add_parser("raw", help="通用透传：对任意 Graph 端点发任意请求体（逃生舱）")
    p.add_argument("--method", required=True,
                   choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    p.add_argument("--path", required=True, help="相对 /v1.0 的路径，如 /me/todo/lists")
    p.add_argument("--body", default=None, help="请求体 JSON")
    add_global_options(p)

    _LOCATOR_HELP = {"list": "清单 id", "task": "任务 id", "item": "子任务 id"}
    for name, spec in RESOURCE_COMMANDS.items():
        p = sub.add_parser(name, help=_RESOURCE_HELP[name])
        for locator in spec["locators"]:
            help_text = _LOCATOR_HELP[locator]
            if name == "list-tasks" and locator == "list":
                help_text = "清单 id，或 all 表示跨全部清单聚合"
            p.add_argument(f"--{locator}", required=True, help=help_text)
        if spec.get("operation"):
            p.add_argument("--body", default=None,
                           help=f"请求体 JSON（字段见 `schema {spec['operation']}`）")
        if name == "list-tasks":
            p.add_argument("--status", default=None,
                           help="按 taskStatus 过滤，逗号分隔。"
                                "过滤在分页完整跟完之后执行")
        add_global_options(p)

    return parser


def main(argv: list[str] | None = None) -> None:
    """主入口。"""
    args = build_parser().parse_args(argv)
    COMMAND_MAP[args.command](args)


if __name__ == "__main__":
    main()
