#!/usr/bin/env python3
"""结构化工作流 - 归档脚本

将工作流状态文件移入归档目录，清理 workflow.json，使项目恢复"干净"状态。

用法:
    uv run archive_workflow.py --path <project-root> [--label <标签>]

选项:
    --label <标签>    自定义归档标签（默认使用 workflow.json 中的 primaryType）
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def slugify(text: str) -> str:
    """将文本转为目录名安全的 slug（小写字母、数字、短横线）"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="结构化工作流 - 归档",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path", required=True, help="目标项目根目录路径"
    )
    parser.add_argument(
        "--label", default=None, help="自定义归档标签"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 读取 workflow.json（新路径优先，旧路径回退）
    workflow_path = project_root / "docs" / "workflow" / "workflow.json"
    if not workflow_path.exists():
        workflow_path = project_root / ".claude" / "workflow.json"
    if not workflow_path.exists():
        print(f"错误: workflow.json 不存在", file=sys.stderr)
        print("提示: 可能项目尚未初始化，或已经归档过了")
        sys.exit(1)

    with open(workflow_path, encoding="utf-8") as f:
        config = json.load(f)

    # 确定归档目录名
    primary_type = config.get("primaryType", "generic")
    task_name = config.get("taskName", "")
    if args.label:
        name_part = slugify(args.label)
    elif task_name:
        name_part = slugify(task_name)
    else:
        name_part = primary_type
    date_str = datetime.now().strftime("%Y%m%d")
    archive_name = f"{date_str}-{primary_type}-{name_part}"

    archive_dir = project_root / "docs" / "workflow" / "archive" / archive_name
    if archive_dir.exists():
        # 如果同一天已有归档，追加序号
        counter = 2
        while archive_dir.exists():
            archive_dir = project_root / "docs" / "workflow" / "archive" / f"{archive_name}-{counter}"
            counter += 1

    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"归档目录: {archive_dir}")

    # 要归档的状态文件
    state_files = config.get("stateFiles", {})
    default_files = {
        "analysis": "docs/workflow/TASK_ANALYSIS.md",
        "plan": "docs/workflow/TASK_PLAN.md",
        "status": "docs/workflow/TASK_STATUS.md",
        "dependencyMap": "docs/workflow/DEPENDENCY_MAP.md",
    }

    moved_count = 0
    skipped_count = 0

    for key, default_path in default_files.items():
        rel_path = state_files.get(key, default_path)
        src = project_root / rel_path
        if src.exists():
            dst = archive_dir / src.name
            shutil.move(str(src), str(dst))
            print(f"  ✓ 移动: {rel_path} → {dst.relative_to(project_root)}")
            moved_count += 1
        else:
            print(f"  - 跳过（不存在）: {rel_path}")
            skipped_count += 1

    # 将 workflow.json 也复制一份到归档目录（作为记录），然后删除原件
    workflow_dst = archive_dir / "workflow.json"
    shutil.copy2(str(workflow_path), str(workflow_dst))
    workflow_path.unlink()
    print(f"  ✓ 归档并移除: {workflow_path.relative_to(project_root)}")

    # 输出摘要
    print()
    print(f"归档完成！")
    print(f"  归档目录: {archive_dir.relative_to(project_root)}")
    print(f"  移动文件: {moved_count} 个")
    print(f"  跳过文件: {skipped_count} 个")
    print(f"  workflow.json: 已归档并移除")
    print()
    print("项目已恢复干净状态，可以开展下一轮大型任务。")


if __name__ == "__main__":
    main()
