#!/usr/bin/env python3
"""结构化工作流 - 项目初始化脚本

在目标项目中创建 docs/workflow/ 目录结构、workflow.json 配置文件和 TASK_STATUS.md 模板。

用法:
    uv run init_project.py --path <project-root> [options]

选项:
    --task-name <slug>      任务名称 slug（如 extract-auth-module）
    --phases <names>        自定义阶段名（逗号分隔）
    --description <desc>    项目简述
    --build-cmd <cmd>       构建命令
    --test-cmd <cmd>        测试命令
    --force                 跳过覆盖确认（非交互式环境使用）
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_current_commit(project_root: Path) -> str:
    """获取当前 HEAD 的 commit hash，失败时返回空字符串"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="结构化工作流 - 项目初始化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", required=True, help="目标项目根目录路径"
    )
    parser.add_argument(
        "--task-name",
        default=None,
        help="任务名称 slug（英文短横线分隔，如 extract-auth-module）",
    )
    parser.add_argument(
        "--phases", default=None, help="自定义阶段名，逗号分隔"
    )
    parser.add_argument(
        "--description", default="", help="项目简述"
    )
    parser.add_argument(
        "--build-cmd", default="", help="构建命令"
    )
    parser.add_argument(
        "--test-cmd", default="", help="测试命令"
    )
    parser.add_argument(
        "--force", action="store_true", help="跳过覆盖确认（用于非交互式环境）"
    )
    return parser.parse_args()


def create_workflow_json(args: argparse.Namespace) -> dict:
    """生成 workflow.json v2.0 配置"""
    if args.phases:
        phase_names = [p.strip() for p in args.phases.split(",")]
        phases = [
            {"name": f"Phase {i}: {name}", "exitCriteria": ""}
            for i, name in enumerate(phase_names)
        ]
    else:
        phases = []

    return {
        "version": "2.0",
        "initCommit": "",
        "taskName": args.task_name or "",
        "stateFiles": {
            "analysis": "docs/workflow/TASK_ANALYSIS.md",
            "plan": "docs/workflow/TASK_PLAN.md",
            "status": "docs/workflow/TASK_STATUS.md",
            "dependencyMap": "docs/workflow/DEPENDENCY_MAP.md",
        },
        "phases": phases,
        "projectContext": {
            "description": args.description,
            "buildCommand": args.build_cmd,
            "testCommand": args.test_cmd,
        },
    }


def create_status_template() -> str:
    """生成 TASK_STATUS.md 模板"""
    date = datetime.now().strftime("%Y-%m-%d")

    return f"""# 任务状态跟踪

> 创建时间: {date}

## 进度总览

| 阶段 | 总数 | 完成 | 进行中 | 待开始 |
|------|------|------|--------|--------|
| **合计** | **0** | **0** | **0** | **0** |

## 任务状态

| 编号 | 标题 | 阶段 | 状态 | 依赖 |
|------|------|------|------|------|

状态图例: ⬜ 待开始 | 🔄 进行中 | ✅ 已完成 | ⏸️ 暂停 | ❌ 已取消 | 🔀 已拆分

## 已知问题

（执行过程中发现的问题记录在此）

## 决策日志

（重要决策和变更原因记录在此）

## 交接记录

（每次 /task-exec 完成后在此追加交接记录块）
"""


def main() -> None:
    args = parse_args()
    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 创建目录
    workflow_dir = project_root / "docs" / "workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    # 检查是否已存在 workflow.json（新路径优先，旧路径回退）
    workflow_path = workflow_dir / "workflow.json"
    old_workflow_path = project_root / ".claude" / "workflow.json"
    existing_path = None
    if workflow_path.exists():
        existing_path = workflow_path
    elif old_workflow_path.exists():
        existing_path = old_workflow_path

    if existing_path:
        if args.force:
            print(f"⚠ 覆盖已有 workflow.json: {existing_path}")
        else:
            print(f"警告: workflow.json 已存在于 {existing_path}", file=sys.stderr)
            response = input("是否覆盖? (y/N): ").strip().lower()
            if response != "y":
                print("已取消")
                sys.exit(0)
        # 如果旧路径存在，清理旧文件
        if old_workflow_path.exists() and old_workflow_path != workflow_path:
            old_workflow_path.unlink()
            print(f"✓ 已清理旧路径: {old_workflow_path}")

    # 生成配置
    config = create_workflow_json(args)
    config["initCommit"] = get_current_commit(project_root)

    # 写入 workflow.json
    with open(workflow_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"✓ 已创建: {workflow_path}")

    # 生成并写入 TASK_STATUS.md（如果不存在）
    status_path = workflow_dir / "TASK_STATUS.md"
    if not status_path.exists():
        status_content = create_status_template()
        with open(status_path, "w", encoding="utf-8") as f:
            f.write(status_content)
        print(f"✓ 已创建: {status_path}")
    else:
        print(f"⚠ 已跳过（已存在）: {status_path}")

    # 输出摘要
    print()
    print("初始化完成！")
    if config["taskName"]:
        print(f"  任务: {config['taskName']}")
    print(f"  阶段: {len(config['phases'])} 个" if config["phases"] else "  阶段: 待规划")
    if config["initCommit"]:
        print(f"  initCommit: {config['initCommit'][:8]}")


if __name__ == "__main__":
    main()
