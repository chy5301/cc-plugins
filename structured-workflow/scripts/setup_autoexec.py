#!/usr/bin/env python3
"""结构化工作流 - 自动执行设置脚本

读取工作流状态，计算默认参数，检测 Ralph Loop 插件，生成自动执行状态文件。

用法:
    uv run setup_autoexec.py --path <project-root> [options]

选项:
    --max <N>       覆盖最大迭代次数（最小 3）
    --all           统计所有阶段的剩余任务（默认仅当前阶段）
    --phase <N>     指定目标阶段编号（对应 Phase 0, Phase 1, ...）
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 任务状态 emoji 到语义的映射
STATUS_EMOJIS = {
    "⬜": "pending",
    "🔄": "in_progress",
    "✅": "completed",
    "⏸️": "blocked",
    "⏸": "blocked",  # 无变体选择符的版本
    "❌": "cancelled",
    "🔀": "split",
}


def detect_ralph_loop() -> bool:
    """检测 ralph-loop 插件是否已安装"""
    claude_dir = Path.home() / ".claude" / "plugins" / "marketplaces"
    if not claude_dir.exists():
        return False
    # 搜索所有 marketplace 下的 ralph-loop 插件
    for hooks_file in claude_dir.glob("*/plugins/ralph-loop/hooks/hooks.json"):
        if hooks_file.is_file():
            return True
    return False


def load_workflow(project_root: Path) -> dict:
    """加载 workflow.json，支持新旧路径"""
    new_path = project_root / "docs" / "workflow" / "workflow.json"
    old_path = project_root / ".claude" / "workflow.json"

    for path in (new_path, old_path):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)

    print("错误: 未找到 workflow.json（工作流未初始化）", file=sys.stderr)
    print("请先运行 /task-init 初始化工作流", file=sys.stderr)
    sys.exit(1)


def load_status_file(project_root: Path, workflow: dict) -> str:
    """加载 TASK_STATUS.md 内容"""
    status_rel = workflow.get("stateFiles", {}).get(
        "status", "docs/workflow/TASK_STATUS.md"
    )
    status_path = project_root / status_rel
    # 旧路径回退
    if not status_path.exists():
        old_path = project_root / "docs" / "TASK_STATUS.md"
        if old_path.exists():
            status_path = old_path

    if not status_path.exists():
        print(f"错误: 未找到状态文件: {status_path}", file=sys.stderr)
        sys.exit(1)

    with open(status_path, encoding="utf-8") as f:
        return f.read()


def parse_task_statuses(status_content: str) -> list[dict]:
    """从 TASK_STATUS.md 的任务状态表中解析任务列表

    解析格式：| 编号 | 标题 | 阶段 | 状态 | 依赖 |
    """
    tasks = []
    # 匹配任务状态表的行：| XX-NN | ... | Phase N... | ⬜/✅/... | ... |
    table_pattern = re.compile(
        r"^\|\s*(\S+)\s*\|[^|]*\|([^|]*)\|([^|]*)\|[^|]*\|",
        re.MULTILINE,
    )
    for match in table_pattern.finditer(status_content):
        task_id = match.group(1).strip()
        phase_text = match.group(2).strip()
        status_cell = match.group(3).strip()

        # 跳过表头和分隔行
        if task_id in ("编号", "---", "----", "-----"):
            continue
        if task_id.startswith("-"):
            continue

        # 识别状态 emoji
        status = "unknown"
        for emoji, semantic in STATUS_EMOJIS.items():
            if emoji in status_cell:
                status = semantic
                break

        # 提取阶段编号
        phase_num = -1
        phase_match = re.search(r"Phase\s*(\d+)", phase_text)
        if phase_match:
            phase_num = int(phase_match.group(1))

        tasks.append(
            {
                "id": task_id,
                "phase": phase_num,
                "status": status,
            }
        )

    return tasks


def find_current_phase(tasks: list[dict], phases: list[dict]) -> int:
    """找到第一个仍有待执行任务的阶段编号"""
    for i in range(len(phases)):
        phase_tasks = [t for t in tasks if t["phase"] == i]
        has_pending = any(
            t["status"] in ("pending", "in_progress") for t in phase_tasks
        )
        if has_pending:
            return i
    # 所有阶段都已完成，返回最后一个阶段
    return len(phases) - 1 if phases else 0


def count_remaining_tasks(
    tasks: list[dict], phase: int | None, count_all: bool
) -> int:
    """计算剩余可执行任务数"""
    remaining = [t for t in tasks if t["status"] in ("pending", "in_progress")]
    if not count_all and phase is not None:
        remaining = [t for t in remaining if t["phase"] == phase]
    return len(remaining)


def build_phase_info(phases: list[dict]) -> str:
    """构建阶段信息文本"""
    lines = []
    for i, phase in enumerate(phases):
        name = phase.get("name", f"Phase {i}")
        criteria = phase.get("exitCriteria", "未定义")
        lines.append(f"- {name}: {criteria}")
    return "\n".join(lines)


def build_prompt(workflow: dict) -> str:
    """构建自动执行协议 prompt"""
    ctx = workflow.get("projectContext", {})
    constraints = workflow.get("constraints", {})
    build_cmd = ctx.get("buildCommand", "") or "无"
    test_cmd = ctx.get("testCommand", "") or "无"
    prefix = workflow.get("taskPrefix", "T")
    max_files = constraints.get("maxFilesPerTask", 8)
    max_hours = constraints.get("maxHoursPerTask", 3)
    phase_info = build_phase_info(workflow.get("phases", []))

    return f"""# 自动执行协议

你正在自动执行结构化工作流。每次迭代执行一个任务，然后 commit。

## 项目配置
- 构建命令: {build_cmd}
- 测试命令: {test_cmd}
- 任务前缀: {prefix}
- 粒度约束: ≤{max_files} 文件, ≤{max_hours} 小时

## 阶段与退出标准
{phase_info}

## 执行流程

### 1. 加载状态
读取 docs/workflow/workflow.json、TASK_PLAN.md、TASK_STATUS.md。
查看最近的交接记录，了解上一任务的关注点和遗留问题。

### 2. 选择下一任务
优先级：
1. 🔄 进行中的任务（续接）
2. ⬜ 待开始且所有依赖已完成（✅）的任务（按编号顺序）

如果没有可执行任务 → 跳到「完成检查」。

### 3. 执行任务（自动模式）

**理解**：读取任务定义和最近交接记录，记录理解要点，直接继续（不等待用户确认）。

**最小变更路径**：列出具体修改步骤（修改什么文件的什么位置，做什么修改，为什么）。

**实施**：按步骤实施，仅限任务范围内变更。使用 Edit 工具进行文件修改。

**验证**：
- 运行构建命令: {build_cmd}
- 运行测试命令: {test_cmd}
- 逐项检查验收标准

**自动模式异常处理**：
- 任务过大 → 拆分为子任务（编号 {prefix}-XX-a/b/c），执行第一个，其余留给后续迭代
- 计划有误 → 标记当前任务为 ⏸️ 阻塞，在已知问题中记录原因，跳到下一任务
- 依赖未满足 → 标记当前任务为 ⏸️ 阻塞，记录原因，跳到下一任务
- 范围蔓延 → 完成范围内工作，在遗留问题中记录范围外需求
- 验证失败 → 尝试修复一次，仍失败则标记 ⏸️ 阻塞

### 4. 更新状态（不可跳过）
- 更新 TASK_STATUS.md：将任务标记为 ✅ 已完成，更新进度总览表，记录决策和问题
- 追加交接记录，包含以下内容：
  - 完成时间
  - 完成内容（结果导向）
  - 修改的文件（每个文件附变更说明）
  - 验证结果（编译/测试/功能）
  - 关键决策（方案选择和原因）
  - 计划变更（如有）
  - 下一任务及关注点
  - 遗留问题
- 如需调整后续任务，同步更新 TASK_PLAN.md

### 5. 门控校验（不可跳过）
重新读取 TASK_STATUS.md，确认：
□ 当前任务已标记 ✅（或 ⏸️ 如果是跳过的）
□ 交接记录已追加（包含完成内容和修改文件）
□ 进度总览表数字已更新
→ 任何一项缺失：立即补全后再继续

### 6. 自动提交
- 运行 `git status` 和 `git diff HEAD` 了解当前所有变更
- 运行 `git log --oneline -5` 了解最近的 commit 风格
- 暂存本任务相关的变更文件（使用 `git add` 添加具体文件）
- git commit，遵循 Angular Commit Convention，Subject 和 Body 使用中文
- 不包含 Co-Authored-By 声明和工具生成标记

### 7. 阶段检查点
检查当前阶段是否所有任务已完成（✅ 或 ⏸️）。如果是：
- 逐项验证该阶段的退出标准
- 运行构建命令和测试命令
- 评估下游阶段任务是否需要调整（前提条件是否变化、文件是否有变化、步骤是否需要修改）
- 如需调整，更新 TASK_PLAN.md 并在决策日志记录原因
- 在 TASK_STATUS.md 决策日志中记录阶段回顾结论
- 提交阶段回顾的更新

### 8. 完成检查
检查是否还有可执行任务（⬜ 且依赖已满足，或 🔄 进行中）：
- **有** → 本次迭代结束（ralph-loop 会自动触发下一次迭代）
- **无，且所有任务已完成** → 输出完成摘要，然后输出 <promise>ALL COMPLETE</promise>
- **无，但存在阻塞任务** → 输出阻塞报告（列出每个阻塞任务及原因），然后输出 <promise>ALL COMPLETE</promise>

## 约束
- 每次迭代只执行一个任务
- 不做范围外变更（无关重构、格式化、顺手修 bug）
- 门控校验不可跳过
- 在状态更新和 commit 完成之前不要结束迭代
- **禁止在步骤 8 的最终完成检查之外输出 `<promise>` 标签**（stop hook 会检测该标签来判断是否终止循环，提前输出会导致循环意外终止）
"""


def create_state_file(project_root: Path, max_iterations: int, prompt: str) -> Path:
    """创建 .claude/ralph-loop.local.md 状态文件"""
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    state_path = claude_dir / "ralph-loop.local.md"

    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    content = f"""---
active: true
iteration: 1
session_id: {session_id}
max_iterations: {max_iterations}
completion_promise: "ALL COMPLETE"
started_at: "{now}"
---

{prompt}"""

    with open(state_path, "w", encoding="utf-8") as f:
        f.write(content)

    return state_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="结构化工作流 - 自动执行设置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", required=True, help="目标项目根目录路径")
    parser.add_argument(
        "--max", type=int, default=0, dest="max_iterations", help="最大迭代次数（0=自动计算）"
    )
    parser.add_argument(
        "--all", action="store_true", dest="count_all", help="统计所有阶段的剩余任务"
    )
    parser.add_argument(
        "--phase", type=int, default=None, help="指定目标阶段编号（0-based）"
    )
    parser.add_argument(
        "--yes", action="store_true", help="（由命令层处理，脚本中忽略）"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 1. 加载工作流配置
    workflow = load_workflow(project_root)
    phases = workflow.get("phases", [])

    # 2. 加载并解析任务状态
    status_content = load_status_file(project_root, workflow)
    tasks = parse_task_statuses(status_content)

    if not tasks:
        print("错误: TASK_STATUS.md 中未找到任务", file=sys.stderr)
        print("请确认工作流已完成初始化和任务规划", file=sys.stderr)
        sys.exit(1)

    # 3. 确定当前阶段
    current_phase = (
        args.phase if args.phase is not None else find_current_phase(tasks, phases)
    )

    # 4. 计算任务统计
    remaining = count_remaining_tasks(tasks, current_phase, args.count_all)
    completed = sum(1 for t in tasks if t["status"] == "completed")
    blocked = sum(1 for t in tasks if t["status"] == "blocked")
    total = len(tasks)

    if remaining == 0:
        print("所有任务已完成或阻塞，无需启动自动执行")
        print(f"  总计: {total} | 完成: {completed} | 阻塞: {blocked}")
        sys.exit(0)

    # 5. 计算 max-iterations
    if args.max_iterations > 0:
        max_iter = max(args.max_iterations, 3)
    else:
        max_iter = max(math.ceil(remaining * 1.5), 3)

    # 6. 检测 Ralph Loop
    ralph_detected = detect_ralph_loop()

    # 7. 检查是否已有活跃的 ralph-loop
    existing_state = project_root / ".claude" / "ralph-loop.local.md"
    if existing_state.exists():
        print("⚠ 检测到已有活跃的 ralph-loop 状态文件，将覆盖")

    # 8. 生成 prompt 并创建状态文件
    prompt = build_prompt(workflow)
    state_path = create_state_file(project_root, max_iter, prompt)

    # 9. 输出摘要
    scope_label = "所有阶段" if args.count_all else f"Phase {current_phase}"
    phase_name = (
        phases[current_phase]["name"]
        if current_phase < len(phases)
        else f"Phase {current_phase}"
    )

    print("✓ 自动执行设置完成")
    print()
    print(f"  范围: {scope_label}")
    if not args.count_all:
        print(f"  当前阶段: {phase_name}")
    print(f"  任务统计: 总计 {total} | 完成 {completed} | 待执行 {remaining} | 阻塞 {blocked}")
    print(f"  最大迭代: {max_iter}")
    print(f"  状态文件: {state_path}")
    print()

    if ralph_detected:
        print("  ✓ Ralph Loop 插件: 已检测到")
        print("    自动循环将在每个任务完成后触发")
    else:
        print("  ⚠ Ralph Loop 插件: 未检测到")
        print("    将执行第一个任务，但不会自动循环")
        print("    安装方式: /install-plugin chy5301/cc-plugins 或手动安装 ralph-loop 插件")


if __name__ == "__main__":
    main()
