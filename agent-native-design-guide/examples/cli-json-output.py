#!/usr/bin/env python3
"""Agent-Native CLI --json 输出示例

演示标准 JSON 信封结构的实现，包含：
- 成功/错误响应的统一格式
- --fields 字段掩码
- --quiet 静默模式
- 规范化退出码

规范边界:
  本示例仅对 JSON 信封形状 {success, data, metadata, error}、error 必含 {code, message, 恢复建议}、
  退出码语义 (0/1/2/3/4/10) 三项是规范性的。其余字段 (metadata 的 command/timestamp/version、
  error.code 枚举、data 字段命名) 均为实现选择, 可按业务增删 (如 took_ms、result_count)。

运行方式：
  uv run python cli-json-output.py list --json
  uv run python cli-json-output.py list --json --fields id,name
  uv run python cli-json-output.py get --id 1 --json
  uv run python cli-json-output.py create --title "New" --format docx --json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

# === 模拟数据 ===

PROJECTS = [
    {"id": 1, "name": "Project A", "status": "active", "created": "2026-01-15", "tags": ["web", "api"]},
    {"id": 2, "name": "Project B", "status": "done", "created": "2026-02-20", "tags": ["cli"]},
    {"id": 3, "name": "Project C", "status": "active", "created": "2026-03-01", "tags": ["agent", "ml"]},
]

ALLOWED_FORMATS = ["pdf", "html", "json", "csv"]

# === 退出码常量 ===
# 语义化退出码，Agent 据此判断重试策略：
#   0 = 成功
#   1 = 一般错误（Agent 应报告给用户）
#   2 = 参数/用法错误（Agent 应修正参数后重试）
#   3 = 资源不存在（Agent 应跳过或创建）
#   4 = 权限不足（Agent 应提示用户授权）
#  10 = dry-run 预览成功（Agent 可据此决定是否正式执行）

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_NOT_FOUND = 3
EXIT_PERMISSION = 4
EXIT_DRY_RUN = 10

# === 核心：JSON 信封结构 ===


def make_success(data, command):
    """构造标准成功响应"""
    return {
        "success": True,
        "data": data,
        "metadata": {
            "command": f"demo {command}",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "version": "0.1.0",
        },
    }


def make_error(code, message, **details):
    """构造标准错误响应"""
    error = {"code": code, "message": message}
    error.update(details)
    return {"success": False, "error": error}


def apply_fields_mask(data, fields_str):
    """应用字段掩码，只保留指定字段"""
    fields = [f.strip() for f in fields_str.split(",")]
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in fields} for item in data]
    return {k: v for k, v in data.items() if k in fields}


def output_json(obj):
    """输出 JSON 到 stdout"""
    print(json.dumps(obj, ensure_ascii=False))


def output_human_list(projects):
    """人类友好的列表输出"""
    print(f"{'ID':<5} {'Name':<15} {'Status':<10} {'Created':<12}")
    print("-" * 42)
    for p in projects:
        print(f"{p['id']:<5} {p['name']:<15} {p['status']:<10} {p['created']:<12}")
    print(f"\nTotal: {len(projects)} items")


# === 命令实现 ===


def cmd_list(args):
    """列出所有项目"""
    data = PROJECTS

    if args.json:
        if args.fields:
            data = apply_fields_mask(data, args.fields)
        output_json(make_success(data, "list"))
    elif not args.quiet:
        output_human_list(PROJECTS)

    return EXIT_SUCCESS


def cmd_get(args):
    """获取单个项目"""
    project = next((p for p in PROJECTS if p["id"] == args.id), None)

    if project is None:
        if args.json:
            output_json(make_error(
                "NOT_FOUND",
                f"Project with id {args.id} not found",
                parameter="id",
                provided=args.id,
            ))
        else:
            print(f"Error: Project {args.id} not found", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        data = project
        if args.fields:
            data = apply_fields_mask(data, args.fields)
        output_json(make_success(data, "get"))
    elif not args.quiet:
        for k, v in project.items():
            print(f"  {k}: {v}")

    return EXIT_SUCCESS


def cmd_create(args):
    """创建项目（演示参数校验和错误输出）"""
    # 参数校验：format 必须是允许的值
    if args.format not in ALLOWED_FORMATS:
        if args.json:
            output_json(make_error(
                "INVALID_PARAMETER",
                f"Unsupported format '{args.format}'",
                parameter="format",
                provided=args.format,
                allowed=ALLOWED_FORMATS,
            ))
        else:
            print(f"Error: Unsupported format '{args.format}'. "
                  f"Allowed: {', '.join(ALLOWED_FORMATS)}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    new_project = {
        "id": len(PROJECTS) + 1,
        "name": args.title,
        "status": "active",
        "format": args.format,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    if args.json:
        output_json(make_success(new_project, "create"))
    elif not args.quiet:
        print(f"Created project: {args.title} (format: {args.format})")

    return EXIT_SUCCESS


# === 入口 ===


def main():
    # 全局选项作为 parent parser，让每个子命令都继承
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    global_parser.add_argument("--fields", type=str, help="Comma-separated field mask")
    global_parser.add_argument("--quiet", action="store_true", help="Suppress non-critical output")

    parser = argparse.ArgumentParser(
        prog="demo",
        description="Agent-Native CLI JSON 输出示例",
        parents=[global_parser],
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list 子命令
    subparsers.add_parser("list", help="List all projects", parents=[global_parser])

    # get 子命令
    get_parser = subparsers.add_parser("get", help="Get a project by ID", parents=[global_parser])
    get_parser.add_argument("--id", type=int, required=True, help="Project ID")

    # create 子命令
    create_parser = subparsers.add_parser("create", help="Create a new project", parents=[global_parser])
    create_parser.add_argument("--title", type=str, required=True, help="Project title")
    create_parser.add_argument("--format", type=str, default="json", help="Output format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return EXIT_USAGE_ERROR

    handlers = {"list": cmd_list, "get": cmd_get, "create": cmd_create}
    exit_code = handlers[args.command](args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
