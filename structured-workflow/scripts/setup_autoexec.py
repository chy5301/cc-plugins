#!/usr/bin/env python3
"""结构化工作流 - 自动执行设置脚本

读取工作流状态，计算默认参数，生成自动执行状态文件，注册项目级 Stop hook。

用法:
    uv run setup_autoexec.py --path <project-root> [options]

选项:
    --max <N>         覆盖最大迭代次数（最小 3）
    --all             统计所有阶段的剩余任务（默认仅当前阶段）
    --phase <RANGE>   阶段范围（如 1, 1-3, 0,2）
    --task <RANGE>    任务编号范围（如 1-5, 1,3,7），指定时忽略 --phase
"""

import argparse
import json
import math
import os
import re
import subprocess
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


def parse_range(value: str) -> list[int]:
    """解析范围字符串：'2' → [2], '1-3' → [1,2,3], '1,3,5' → [1,3,5], '1-3,7' → [1,2,3,7]"""
    result = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.extend(range(int(start), int(end) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


def get_script_dir() -> Path:
    """获取脚本所在目录"""
    return Path(__file__).resolve().parent


def check_and_clean_residual(project_root: Path) -> None:
    """检测并清理残留的自动执行状态

    残留判定逻辑：
    - 同一会话 → 直接覆盖（不清理 hook，后面会重新注册）
    - 不同会话且 >24h → 自动清理（确认是残留）
    - 不同会话且 <24h → 警告可能有其他窗口在运行，仍然覆盖
    """
    state_file = project_root / ".claude" / "structured-workflow-loop.local.md"
    if not state_file.exists():
        return

    # 解析状态文件的 frontmatter
    content = state_file.read_text(encoding="utf-8")
    session_id = ""
    started_at = ""
    for line in content.split("\n"):
        if line.startswith("session_id:"):
            session_id = line.split(":", 1)[1].strip()
        elif line.startswith("started_at:"):
            started_at = line.split(":", 1)[1].strip().strip('"')

    current_session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")

    if session_id == current_session:
        print("⚠ 检测到当前会话的状态文件，将覆盖")
        return

    # 不同会话：检查时间
    is_stale = False
    if started_at:
        try:
            start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            elapsed = datetime.now(timezone.utc) - start_time
            is_stale = elapsed.total_seconds() > 86400  # 24 hours
        except (ValueError, TypeError):
            is_stale = True  # 无法解析时间，视为残留

    if is_stale:
        print("⚠ 检测到超过 24 小时的残留状态，正在清理...")
        _run_deregister(project_root)
    else:
        print("⚠ 检测到其他会话的状态文件（<24h），可能有其他窗口在运行")
        print("  将覆盖状态文件并重新注册 hook")
        _run_deregister(project_root)


def _run_deregister(project_root: Path) -> None:
    """调用 manage_hooks.py deregister 清理 hook"""
    manage_script = get_script_dir() / "manage_hooks.py"
    subprocess.run(
        [sys.executable, str(manage_script), "--path", str(project_root), "--action", "deregister"],
        check=False,
    )


def register_hook(project_root: Path) -> None:
    """调用 manage_hooks.py register 注册项目级 Stop hook"""
    manage_script = get_script_dir() / "manage_hooks.py"
    hook_source = get_script_dir() / "stop-hook.sh"
    subprocess.run(
        [
            sys.executable, str(manage_script),
            "--path", str(project_root),
            "--action", "register",
            "--hook-source", str(hook_source),
        ],
        check=True,
    )


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
    tasks: list[dict],
    phase_list: list[int] | None,
    task_nums: list[int] | None,
    task_prefix: str,
    count_all: bool,
) -> int:
    """计算剩余可执行任务数"""
    remaining = [t for t in tasks if t["status"] in ("pending", "in_progress")]

    if task_nums is not None:
        target_ids = {f"{task_prefix}-{n:02d}" for n in task_nums}
        remaining = [t for t in remaining if t["id"] in target_ids]
    elif not count_all and phase_list is not None:
        remaining = [t for t in remaining if t["phase"] in phase_list]

    return len(remaining)


def build_phase_info(phases: list[dict]) -> str:
    """构建阶段信息文本"""
    lines = []
    for i, phase in enumerate(phases):
        name = phase.get("name", f"Phase {i}")
        criteria = phase.get("exitCriteria", "未定义")
        lines.append(f"- {name}: {criteria}")
    return "\n".join(lines)


def build_scope_constraint(
    task_nums: list[int] | None,
    phase_list: list[int] | None,
    prefix: str,
    count_all: bool,
) -> str:
    """根据参数构建执行范围约束文本"""
    if task_nums is not None:
        ids = ", ".join(f"{prefix}-{n:02d}" for n in task_nums)
        return f"\n\n**执行范围限制**：仅执行以下任务：{ids}。跳过不在此列表中的任务。\n"
    if not count_all and phase_list is not None:
        phases_str = "、".join(f"Phase {p}" for p in phase_list)
        return f"\n\n**执行范围限制**：仅执行 {phases_str} 的任务。跳过其他阶段的任务。\n"
    return ""


def build_prompt(workflow: dict, scope_constraint: str = "") -> str:
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
{scope_constraint}
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
- **有** → 本次迭代结束（Stop hook 会自动触发下一次迭代）
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
    """创建 .claude/structured-workflow-loop.local.md 状态文件"""
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    state_path = claude_dir / "structured-workflow-loop.local.md"

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
        "--phase", type=str, default=None, help="阶段范围（如 1, 1-3, 0,2）"
    )
    parser.add_argument(
        "--task", type=str, default=None, help="任务编号范围（如 1-5, 1,3,7）"
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

    # 3. 解析范围参数
    prefix = workflow.get("taskPrefix", "T")
    phase_list = parse_range(args.phase) if args.phase else None
    task_nums = parse_range(args.task) if args.task else None

    # 确定阶段列表（仅在无 --task 时使用）
    if task_nums is not None:
        current_phases = None
    elif phase_list is not None:
        current_phases = phase_list
    else:
        current_phases = [find_current_phase(tasks, phases)]

    # 4. 计算任务统计
    remaining = count_remaining_tasks(
        tasks, current_phases, task_nums, prefix, args.count_all
    )
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

    # 6. 检测并清理残留状态
    check_and_clean_residual(project_root)

    # 7. 生成 prompt 并创建状态文件
    scope_constraint = build_scope_constraint(
        task_nums, current_phases, prefix, args.count_all
    )
    prompt = build_prompt(workflow, scope_constraint)
    state_path = create_state_file(project_root, max_iter, prompt)

    # 8. 注册项目级 Stop hook
    try:
        register_hook(project_root)
    except subprocess.CalledProcessError:
        # 回滚状态文件，避免孤立
        state_path.unlink(missing_ok=True)
        print("错误: Stop hook 注册失败，已回滚状态文件", file=sys.stderr)
        print("请检查 .claude/ 目录权限后重试", file=sys.stderr)
        sys.exit(1)

    # 9. 输出摘要
    if task_nums:
        scope_label = f"任务 {args.task}"
    elif args.count_all:
        scope_label = "所有阶段"
    elif current_phases and len(current_phases) > 1:
        scope_label = f"Phase {current_phases[0]}-{current_phases[-1]}"
    else:
        scope_label = f"Phase {current_phases[0]}" if current_phases else "自动检测"

    print("✓ 自动执行设置完成")
    print()
    print(f"  范围: {scope_label}")
    if not args.count_all and not task_nums and current_phases and len(current_phases) == 1:
        phase_idx = current_phases[0]
        phase_name = (
            phases[phase_idx]["name"]
            if phase_idx < len(phases)
            else f"Phase {phase_idx}"
        )
        print(f"  当前阶段: {phase_name}")
    print(f"  任务统计: 总计 {total} | 完成 {completed} | 待执行 {remaining} | 阻塞 {blocked}")
    print(f"  最大迭代: {max_iter}")
    print(f"  状态文件: {state_path}")
    print()

    print("  ✓ Stop hook: 已注册（项目级）")
    print("    自动循环将在每个任务完成后触发")


if __name__ == "__main__":
    main()
