#!/usr/bin/env python3
"""结构化工作流 - 项目初始化脚本

在目标项目中创建 workflow.json 配置文件和 TASK_STATUS.md 模板。

用法:
    uv run init_project.py --path <project-root> [options]

选项:
    --type <type>           显式指定任务类型（跳过自动分诊）
    --task-name <slug>      任务名称 slug（如 extract-auth-module）
    --tags <tag1,tag2>      附加标签
    --max-files <N>         单任务最大文件数（默认 8）
    --max-hours <N>         单任务最大工时（默认 3）
    --prefix <X>            任务编号前缀（默认按类型自动选择）
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

VALID_TYPES = [
    "feature",
    "refactor",
    "migration",
    "integration",
    "optimization",
    "bugfix",
    "infrastructure",
    "generic",
]

DEFAULT_PREFIX = {
    "feature": "F",
    "refactor": "R",
    "migration": "M",
    "integration": "I",
    "optimization": "O",
    "bugfix": "B",
    "infrastructure": "T",
    "generic": "G",
}

DEFAULT_PHASES = {
    "feature": [
        {"name": "Phase 0: 基础设施", "exitCriteria": "项目骨架和依赖就绪，空壳可编译"},
        {"name": "Phase 1: 核心逻辑", "exitCriteria": "核心功能逻辑实现并通过单元测试"},
        {"name": "Phase 2: 集成", "exitCriteria": "与现有系统集成完成，端到端流程可运行"},
        {"name": "Phase 3: 打磨", "exitCriteria": "UI/UX 完善、边缘用例处理、错误处理"},
        {"name": "Phase 4: 发布准备", "exitCriteria": "文档、测试覆盖、性能验证全部完成"},
    ],
    "refactor": [
        {"name": "Phase 0: 脚手架", "exitCriteria": "新结构就位，新旧代码可共同编译"},
        {"name": "Phase 1: 最小端到端", "exitCriteria": "一个核心功能通过新架构完整运行"},
        {"name": "Phase 2: 逐模块迁移", "exitCriteria": "所有模块按新架构运行"},
        {"name": "Phase 3: 清理", "exitCriteria": "旧代码移除，无废弃引用"},
        {"name": "Phase 4: 验证", "exitCriteria": "全量回归测试通过，性能达标"},
    ],
    "migration": [
        {"name": "Phase 0: 准备", "exitCriteria": "目标环境就绪，迁移工具可用"},
        {"name": "Phase 1: 双写", "exitCriteria": "数据同时写入新旧系统"},
        {"name": "Phase 2: 迁移", "exitCriteria": "历史数据迁移完成，数据一致性验证通过"},
        {"name": "Phase 3: 切换", "exitCriteria": "读流量切换到新系统，旧系统降级为备份"},
        {"name": "Phase 4: 清理", "exitCriteria": "旧系统下线，迁移工具移除"},
    ],
    "integration": [
        {"name": "Phase 0: 契约确认", "exitCriteria": "接口契约文档化，Mock 服务可用"},
        {"name": "Phase 1: 适配层", "exitCriteria": "适配器/网关实现完成，单元测试通过"},
        {"name": "Phase 2: 联调", "exitCriteria": "与真实外部系统连通，基本流程通过"},
        {"name": "Phase 3: 端到端", "exitCriteria": "所有业务场景通过端到端测试"},
        {"name": "Phase 4: 稳定化", "exitCriteria": "异常处理、重试、监控就绪"},
    ],
    "optimization": [
        {"name": "Phase 0: 基准建立", "exitCriteria": "基准测试就绪，当前指标已记录"},
        {"name": "Phase 1: 关键路径", "exitCriteria": "最大瓶颈优化完成，指标提升可测量"},
        {"name": "Phase 2: 次要路径", "exitCriteria": "次要瓶颈优化完成"},
        {"name": "Phase 3: 验证", "exitCriteria": "全量性能测试通过，无功能回归"},
        {"name": "Phase 4: 监控", "exitCriteria": "性能监控和告警就绪"},
    ],
    "bugfix": [
        {"name": "Phase 0: 复现", "exitCriteria": "所有缺陷可稳定复现，测试用例就绪"},
        {"name": "Phase 1: 定位", "exitCriteria": "所有缺陷根因定位完成"},
        {"name": "Phase 2: 修复", "exitCriteria": "修复实施完成，单元测试通过"},
        {"name": "Phase 3: 回归", "exitCriteria": "全量回归测试通过，无新缺陷"},
        {"name": "Phase 4: 加固", "exitCriteria": "防御性代码和监控就绪"},
    ],
    "infrastructure": [
        {"name": "Phase 0: 规划", "exitCriteria": "架构方案确认，工具链就绪"},
        {"name": "Phase 1: 搭建", "exitCriteria": "核心组件部署完成"},
        {"name": "Phase 2: 迁移", "exitCriteria": "现有项目/流程迁移完成"},
        {"name": "Phase 3: 验证", "exitCriteria": "端到端流程验证通过"},
        {"name": "Phase 4: 文档化", "exitCriteria": "操作手册和维护文档完成"},
    ],
    "generic": [
        {"name": "Phase 0: 准备", "exitCriteria": "准备工作完成"},
        {"name": "Phase 1: 核心实施", "exitCriteria": "核心工作完成"},
        {"name": "Phase 2: 完善", "exitCriteria": "补充工作完成"},
        {"name": "Phase 3: 验证", "exitCriteria": "全部验证通过"},
    ],
}


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
        "--type",
        choices=VALID_TYPES,
        default=None,
        help="任务类型（不指定则由 Claude 自动分诊）",
    )
    parser.add_argument(
        "--task-name",
        default=None,
        help="任务名称 slug（英文短横线分隔，如 extract-auth-module）",
    )
    parser.add_argument(
        "--tags", default="", help="附加标签，逗号分隔"
    )
    parser.add_argument(
        "--max-files", type=int, default=8, help="单任务最大文件数（默认 8）"
    )
    parser.add_argument(
        "--max-hours", type=int, default=3, help="单任务最大工时（默认 3）"
    )
    parser.add_argument(
        "--prefix", default=None, help="任务编号前缀（默认按类型自动选择）"
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
    """生成 workflow.json 配置"""
    primary_type = args.type or "generic"
    prefix = args.prefix or DEFAULT_PREFIX.get(primary_type, "G")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if args.phases:
        phase_names = [p.strip() for p in args.phases.split(",")]
        phases = [
            {"name": f"Phase {i}: {name}", "exitCriteria": ""}
            for i, name in enumerate(phase_names)
        ]
    else:
        phases = DEFAULT_PHASES.get(primary_type, DEFAULT_PHASES["generic"])

    return {
        "version": "1.1",
        "initCommit": "",
        "taskName": args.task_name or "",
        "primaryType": primary_type,
        "secondaryTags": tags,
        "taskPrefix": prefix,
        "constraints": {
            "maxFilesPerTask": args.max_files,
            "maxHoursPerTask": args.max_hours,
        },
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


def create_status_template(config: dict) -> str:
    """生成 TASK_STATUS.md 模板"""
    date = datetime.now().strftime("%Y-%m-%d")
    primary_type = config["primaryType"]
    phases = config["phases"]

    phase_rows = ""
    for phase in phases:
        phase_rows += f"| {phase['name']} | 0 | 0 | 0 | 0 |\n"

    return f"""# 任务状态跟踪

> 创建时间: {date}
> 任务类型: {primary_type}
> 任务前缀: {config['taskPrefix']}

## 进度总览

| 阶段 | 总数 | 完成 | 进行中 | 待开始 |
|------|------|------|--------|--------|
{phase_rows}| **合计** | **0** | **0** | **0** | **0** |

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
        status_content = create_status_template(config)
        with open(status_path, "w", encoding="utf-8") as f:
            f.write(status_content)
        print(f"✓ 已创建: {status_path}")
    else:
        print(f"⚠ 已跳过（已存在）: {status_path}")

    # 输出摘要
    print()
    print("初始化完成！")
    print(f"  类型: {config['primaryType']}")
    print(f"  前缀: {config['taskPrefix']}")
    print(f"  约束: ≤{config['constraints']['maxFilesPerTask']} 文件/任务, ≤{config['constraints']['maxHoursPerTask']} 小时/任务")
    print(f"  阶段: {len(config['phases'])} 个")
    if config["initCommit"]:
        print(f"  initCommit: {config['initCommit'][:8]}")
    if not args.type:
        print()
        print("提示: 未指定类型，请使用 /task-init 让 Claude 自动分诊")


if __name__ == "__main__":
    main()
