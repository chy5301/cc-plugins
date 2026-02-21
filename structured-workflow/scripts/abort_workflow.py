#!/usr/bin/env python3
"""结构化工作流 - 终止清理脚本

将工作流状态文件归档（标记为 aborted）或直接删除，使项目恢复"干净"状态。
仅处理状态文件，不执行任何 git 操作。

用法:
    uv run abort_workflow.py --path <project-root> --mode <archive|delete> [--label <标签>]

选项:
    --mode archive    归档状态文件到 docs/archive/（目录名含 aborted 标记）
    --mode delete     直接删除所有状态文件和 workflow.json
    --label <标签>    自定义归档标签（默认使用 workflow.json 中的 primaryType）
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="结构化工作流 - 终止清理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", required=True, help="目标项目根目录路径"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["archive", "delete"],
        help="清理模式：archive（归档）或 delete（删除）",
    )
    parser.add_argument(
        "--label", default=None, help="自定义归档标签"
    )
    return parser.parse_args()


def get_state_files(project_root: Path, config: dict) -> dict[str, Path]:
    """获取所有状态文件路径"""
    state_files = config.get("stateFiles", {})
    default_files = {
        "analysis": "docs/TASK_ANALYSIS.md",
        "plan": "docs/TASK_PLAN.md",
        "status": "docs/TASK_STATUS.md",
        "dependencyMap": "docs/DEPENDENCY_MAP.md",
    }
    return {
        key: project_root / state_files.get(key, default_path)
        for key, default_path in default_files.items()
    }


def archive_mode(project_root: Path, config: dict, label: str) -> None:
    """归档模式：移动状态文件到归档目录"""
    date_str = datetime.now().strftime("%Y%m%d")
    archive_name = f"workflow-{label}-aborted-{date_str}"

    archive_dir = project_root / "docs" / "archive" / archive_name
    if archive_dir.exists():
        counter = 2
        while archive_dir.exists():
            archive_dir = (
                project_root / "docs" / "archive" / f"{archive_name}-{counter}"
            )
            counter += 1

    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"归档目录: {archive_dir}")

    state_files = get_state_files(project_root, config)
    moved_count = 0
    skipped_count = 0

    for key, src in state_files.items():
        if src.exists():
            dst = archive_dir / src.name
            shutil.move(str(src), str(dst))
            print(f"  ✓ 移动: {src.relative_to(project_root)} → {dst.relative_to(project_root)}")
            moved_count += 1
        else:
            print(f"  - 跳过（不存在）: {src.relative_to(project_root)}")
            skipped_count += 1

    # 移动 ABORT_REPORT.md（如果存在）
    abort_report = project_root / "docs" / "ABORT_REPORT.md"
    if abort_report.exists():
        dst = archive_dir / "ABORT_REPORT.md"
        shutil.move(str(abort_report), str(dst))
        print(f"  ✓ 移动: docs/ABORT_REPORT.md → {dst.relative_to(project_root)}")
        moved_count += 1

    # 归档并删除 workflow.json
    workflow_path = project_root / ".claude" / "workflow.json"
    if workflow_path.exists():
        workflow_dst = archive_dir / "workflow.json"
        shutil.copy2(str(workflow_path), str(workflow_dst))
        workflow_path.unlink()
        print(f"  ✓ 归档并移除: .claude/workflow.json")

    print()
    print(f"归档完成！")
    print(f"  归档目录: {archive_dir.relative_to(project_root)}")
    print(f"  移动文件: {moved_count} 个")
    print(f"  跳过文件: {skipped_count} 个")
    print(f"  workflow.json: 已归档并移除")


def delete_mode(project_root: Path, config: dict) -> None:
    """删除模式：直接删除所有状态文件"""
    state_files = get_state_files(project_root, config)
    deleted_count = 0
    skipped_count = 0

    for key, src in state_files.items():
        if src.exists():
            src.unlink()
            print(f"  ✓ 删除: {src.relative_to(project_root)}")
            deleted_count += 1
        else:
            print(f"  - 跳过（不存在）: {src.relative_to(project_root)}")
            skipped_count += 1

    # 删除 ABORT_REPORT.md（如果存在）
    abort_report = project_root / "docs" / "ABORT_REPORT.md"
    if abort_report.exists():
        abort_report.unlink()
        print(f"  ✓ 删除: docs/ABORT_REPORT.md")
        deleted_count += 1

    # 删除 workflow.json
    workflow_path = project_root / ".claude" / "workflow.json"
    if workflow_path.exists():
        workflow_path.unlink()
        print(f"  ✓ 删除: .claude/workflow.json")

    print()
    print(f"删除完成！")
    print(f"  删除文件: {deleted_count} 个")
    print(f"  跳过文件: {skipped_count} 个")
    print(f"  workflow.json: 已删除")


def main() -> None:
    args = parse_args()
    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 读取 workflow.json
    workflow_path = project_root / ".claude" / "workflow.json"
    if not workflow_path.exists():
        print(f"错误: workflow.json 不存在: {workflow_path}", file=sys.stderr)
        print("提示: 可能项目尚未初始化，或已经归档/终止过了")
        sys.exit(1)

    with open(workflow_path, encoding="utf-8") as f:
        config = json.load(f)

    label = args.label or config.get("primaryType", "generic")

    if args.mode == "archive":
        archive_mode(project_root, config, label)
    else:
        delete_mode(project_root, config)

    print()
    print("项目已恢复干净状态，可使用 /task-init 开始新工作流。")


if __name__ == "__main__":
    main()
