#!/usr/bin/env python3
"""结构化工作流 - Hook 管理工具

管理项目级 Stop hook 的注册和注销。

用法:
    uv run manage_hooks.py --path <project-root> --action register --hook-source <path>
    uv run manage_hooks.py --path <project-root> --action deregister
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

HOOK_FILENAME = "structured-workflow-stop.sh"
HOOK_COMMAND = f"bash .claude/hooks/{HOOK_FILENAME}"
HOOK_MARKER = "structured-workflow-stop"
STATE_FILENAME = "structured-workflow-loop.local.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="结构化工作流 - Hook 管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", required=True, help="目标项目根目录路径")
    parser.add_argument(
        "--action",
        required=True,
        choices=["register", "deregister"],
        help="操作: register（注册）或 deregister（注销）",
    )
    parser.add_argument(
        "--hook-source", default=None, help="hook 源文件路径（register 时必需）"
    )
    return parser.parse_args()


def load_settings(settings_path: Path) -> dict:
    """加载 settings.local.json，不存在则返回空 dict"""
    if settings_path.exists():
        with open(settings_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(settings_path: Path, settings: dict) -> None:
    """保存 settings.local.json"""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def has_our_hook(settings: dict) -> bool:
    """检查 settings 中是否已有我们的 hook"""
    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    for entry in stop_hooks:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if HOOK_MARKER in cmd:
                return True
    return False


def register(project_root: Path, hook_source: Path) -> None:
    """注册 Stop hook：复制脚本 + 写入 settings.local.json"""
    # 1. 复制 hook 脚本到项目 .claude/hooks/
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    dest = hooks_dir / HOOK_FILENAME
    shutil.copy2(str(hook_source), str(dest))

    # 2. 注册到 settings.local.json（幂等）
    settings_path = project_root / ".claude" / "settings.local.json"
    settings = load_settings(settings_path)

    if has_our_hook(settings):
        print(f"  ✓ Stop hook 已注册（跳过）")
        print(f"  ✓ Hook 脚本: .claude/hooks/{HOOK_FILENAME}")
        return

    # 添加 hook 条目
    hooks = settings.setdefault("hooks", {})
    stop_list = hooks.setdefault("Stop", [])
    stop_list.append({"hooks": [{"type": "command", "command": HOOK_COMMAND}]})

    save_settings(settings_path, settings)
    print(f"  ✓ Stop hook 已注册到 .claude/settings.local.json")
    print(f"  ✓ Hook 脚本: .claude/hooks/{HOOK_FILENAME}")


def deregister(project_root: Path) -> None:
    """注销 Stop hook：从 settings.local.json 移除 + 删除脚本 + 删除状态文件"""
    settings_path = project_root / ".claude" / "settings.local.json"
    settings = load_settings(settings_path)

    # 1. 从 settings 中移除包含我们标记的 hook 条目
    if "hooks" in settings and "Stop" in settings["hooks"]:
        stop_list = settings["hooks"]["Stop"]
        new_stop_list = []
        for entry in stop_list:
            new_hooks = [
                h for h in entry.get("hooks", [])
                if HOOK_MARKER not in h.get("command", "")
            ]
            if new_hooks:
                entry["hooks"] = new_hooks
                new_stop_list.append(entry)
        if new_stop_list:
            settings["hooks"]["Stop"] = new_stop_list
        else:
            del settings["hooks"]["Stop"]
        if not settings["hooks"]:
            del settings["hooks"]

        save_settings(settings_path, settings)
        print(f"  ✓ 已从 settings.local.json 移除 Stop hook")
    else:
        print(f"  - settings.local.json 中无 Stop hook（跳过）")

    # 2. 删除 hook 脚本
    hook_script = project_root / ".claude" / "hooks" / HOOK_FILENAME
    if hook_script.exists():
        hook_script.unlink()
        print(f"  ✓ 已删除 hook 脚本: .claude/hooks/{HOOK_FILENAME}")
    else:
        print(f"  - hook 脚本不存在（跳过）")

    # 3. 清理空的 hooks 目录
    hooks_dir = project_root / ".claude" / "hooks"
    if hooks_dir.exists() and not any(hooks_dir.iterdir()):
        hooks_dir.rmdir()

    # 4. 删除状态文件
    state_file = project_root / ".claude" / STATE_FILENAME
    if state_file.exists():
        state_file.unlink()
        print(f"  ✓ 已删除状态文件: .claude/{STATE_FILENAME}")
    else:
        print(f"  - 状态文件不存在（跳过）")


def main() -> None:
    args = parse_args()
    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    if args.action == "register":
        if not args.hook_source:
            print("错误: register 操作需要 --hook-source 参数", file=sys.stderr)
            sys.exit(1)
        hook_source = Path(args.hook_source).resolve()
        if not hook_source.is_file():
            print(f"错误: hook 源文件不存在: {hook_source}", file=sys.stderr)
            sys.exit(1)
        register(project_root, hook_source)
    else:
        deregister(project_root)


if __name__ == "__main__":
    main()
