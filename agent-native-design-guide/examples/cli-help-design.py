#!/usr/bin/env python3
"""Agent-Native CLI --help 与 Schema 自省示例

演示 Agent 友好的可发现性设计，包含：
- 结构化 --help 输出（分组、示例）
- --help --json 机器可读帮助
- schema 子命令（JSON Schema 自省）
- 双模帮助（人类文本 + Agent JSON）

运行方式：
  uv run python cli-help-design.py --help
  uv run python cli-help-design.py --help --json
  uv run python cli-help-design.py schema transform
  uv run python cli-help-design.py schema --all
  uv run python cli-help-design.py transform --width 800 --json
"""

import argparse
import json
import sys

# === 命令 Schema 注册表 ===

COMMAND_SCHEMAS = {
    "transform": {
        "command": "datatool transform",
        "description": "Apply data transformations",
        "parameters": [
            {"name": "input", "type": "string", "required": True, "description": "Input file path"},
            {"name": "width", "type": "integer", "required": False, "default": None, "description": "Target width"},
            {"name": "height", "type": "integer", "required": False, "default": None, "description": "Target height"},
            {"name": "format", "type": "string", "required": False, "enum": ["png", "jpg", "webp"], "default": "png",
             "description": "Output format"},
        ],
        "examples": [
            "datatool transform --input data.csv --width 800 --json",
            "datatool transform --input img.png --format webp --json",
        ],
    },
    "export": {
        "command": "datatool export",
        "description": "Export data to various formats",
        "parameters": [
            {"name": "input", "type": "string", "required": True, "description": "Input file path"},
            {"name": "output", "type": "string", "required": True, "description": "Output file path"},
            {"name": "format", "type": "string", "required": True, "enum": ["pdf", "html", "csv", "json"],
             "description": "Export format"},
            {"name": "template", "type": "string", "required": False, "default": "default",
             "description": "Report template name"},
        ],
        "examples": [
            "datatool export --input data.csv --output report.pdf --format pdf --json",
        ],
    },
    "info": {
        "command": "datatool info",
        "description": "Show file/project information",
        "parameters": [
            {"name": "input", "type": "string", "required": True, "description": "File to inspect"},
        ],
        "examples": [
            "datatool info --input data.csv --json",
        ],
    },
}

TOOL_INFO = {
    "name": "datatool",
    "version": "0.1.0",
    "description": "Agent-native data processing tool",
    "global_options": [
        {"name": "--json", "description": "Output in JSON format"},
        {"name": "--quiet", "description": "Suppress non-critical output"},
        {"name": "--dry-run", "description": "Validate without executing"},
        {"name": "--fields", "description": "Comma-separated field mask"},
    ],
    "command_groups": {
        "Core": ["transform", "info"],
        "IO": ["export"],
    },
}


# === --help 双模输出 ===


def print_help_human():
    """人类友好的 --help 输出"""
    info = TOOL_INFO
    lines = [
        f"{info['name']} - {info['description']}",
        "",
        "USAGE:",
        f"  {info['name']} <command> [options]",
        "",
        "COMMANDS:",
    ]

    for group, cmds in info["command_groups"].items():
        for cmd in cmds:
            schema = COMMAND_SCHEMAS[cmd]
            lines.append(f"  {cmd:<15} {schema['description']}")

    lines.extend([
        "",
        "GLOBAL OPTIONS:",
    ])
    for opt in info["global_options"]:
        lines.append(f"  {opt['name']:<15} {opt['description']}")

    lines.extend([
        "",
        "EXAMPLES:",
        f"  {info['name']} transform --input data.csv --width 800 --json",
        f"  {info['name']} export --input data.csv --output report.pdf --format pdf --json",
        f"  {info['name']} info --input data.csv --json",
        "",
        "SCHEMA INTROSPECTION:",
        f"  {info['name']} schema <command>   Show command parameters as JSON Schema",
        f"  {info['name']} schema --all       Show all commands",
    ])

    print("\n".join(lines))


def print_help_json():
    """Agent 友好的 --help --json 输出"""
    output = {
        "name": TOOL_INFO["name"],
        "version": TOOL_INFO["version"],
        "description": TOOL_INFO["description"],
        "commands": list(COMMAND_SCHEMAS.keys()),
        "global_options": TOOL_INFO["global_options"],
        "schema_endpoint": f"{TOOL_INFO['name']} schema <command>",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# === schema 子命令 ===


def cmd_schema(args):
    """输出命令的 JSON Schema"""
    if args.all:
        print(json.dumps({"commands": COMMAND_SCHEMAS}, ensure_ascii=False, indent=2))
        return 0

    if not args.command_name:
        print("Error: specify a command name or use --all", file=sys.stderr)
        return 2

    name = args.command_name
    if name not in COMMAND_SCHEMAS:
        error = {
            "success": False,
            "error": {
                "code": "UNKNOWN_COMMAND",
                "message": f"Unknown command '{name}'",
                "provided": name,
                "allowed": list(COMMAND_SCHEMAS.keys()),
            },
        }
        print(json.dumps(error, ensure_ascii=False))
        return 2

    print(json.dumps(COMMAND_SCHEMAS[name], ensure_ascii=False, indent=2))
    return 0


# === transform 子命令（演示实际命令） ===


def cmd_transform(args):
    """模拟 transform 命令"""
    result = {
        "input": args.input,
        "transformations_applied": [],
    }
    if args.width:
        result["transformations_applied"].append({"type": "resize_width", "value": args.width})
    if args.height:
        result["transformations_applied"].append({"type": "resize_height", "value": args.height})
    result["output_format"] = args.format

    if args.json:
        response = {
            "success": True,
            "data": result,
            "metadata": {"command": "datatool transform", "version": "0.1.0"},
        }
        print(json.dumps(response, ensure_ascii=False))
    else:
        print(f"Transformed {args.input}")
        for t in result["transformations_applied"]:
            print(f"  Applied: {t['type']} = {t['value']}")
        print(f"  Format: {result['output_format']}")

    return 0


# === 入口 ===


def main():
    # 检查 --help --json 组合（在 argparse 之前拦截）
    if "--help" in sys.argv and "--json" in sys.argv:
        print_help_json()
        return

    # 全局选项作为 parent parser
    global_parser = argparse.ArgumentParser(add_help=False)
    global_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    global_parser.add_argument("--quiet", action="store_true", help="Suppress non-critical output")
    global_parser.add_argument("--dry-run", action="store_true", help="Validate without executing")
    global_parser.add_argument("--fields", type=str, help="Comma-separated field mask")

    parser = argparse.ArgumentParser(
        prog="datatool",
        description="Agent-native data processing tool",
        parents=[global_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "EXAMPLES:\n"
            "  datatool transform --input data.csv --width 800 --json\n"
            "  datatool schema transform\n"
            "  datatool schema --all\n"
            "\n"
            "SCHEMA INTROSPECTION:\n"
            "  datatool schema <command>   Show command JSON Schema\n"
            "  datatool schema --all       Show all commands"
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    # schema 子命令
    schema_parser = subparsers.add_parser("schema", help="Show command JSON Schema")
    schema_parser.add_argument("command_name", nargs="?", help="Command to inspect")
    schema_parser.add_argument("--all", action="store_true", help="Show all commands")

    # transform 子命令
    transform_parser = subparsers.add_parser("transform", help="Apply data transformations",
                                             parents=[global_parser])
    transform_parser.add_argument("--input", type=str, required=True, help="Input file path")
    transform_parser.add_argument("--width", type=int, help="Target width")
    transform_parser.add_argument("--height", type=int, help="Target height")
    transform_parser.add_argument("--format", type=str, default="png", choices=["png", "jpg", "webp"],
                                  help="Output format")

    args = parser.parse_args()

    if not args.command:
        print_help_human()
        return

    handlers = {"schema": cmd_schema, "transform": cmd_transform}
    exit_code = handlers[args.command](args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
