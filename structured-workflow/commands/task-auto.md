---
description: 自动批量执行任务（基于 ralph-loop 自动循环）
argument-hint: "[--max N] [--all] [--phase N] [--yes]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /task-auto — 自动批量执行

> **⚠️ 不要在 plan mode 下使用此命令。** 此命令需要运行脚本、创建文件和执行任务，plan mode 的只读限制会阻断这些操作。

你是一个工作流自动化管理员。你的职责是配置自动循环执行机制，然后开始执行第一个任务。

## 前置条件

- 本命令依赖 **ralph-loop 插件** 实现自动循环。如果未安装，仍可执行第一个任务，但不会自动循环到后续任务。

## 输入

- `$ARGUMENTS`：可选参数
  - `--max N`：覆盖最大迭代次数（最小 3，默认自动计算）
  - `--all`：统计所有阶段的剩余任务（默认仅当前阶段）
  - `--phase N`：指定目标阶段编号
  - `--yes`：跳过确认，直接开始

## 执行流程

### 步骤 1：前置检查

1. 确认 `docs/workflow/workflow.json` 存在（否则提示运行 `/task-init`）
2. 确认 `docs/workflow/TASK_STATUS.md` 存在且有待执行任务

### 步骤 2：运行设置脚本

```!
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/setup_autoexec.py" --path <PROJECT_ROOT> $ARGUMENTS
```

将 `$ARGUMENTS` 中的参数直接透传给脚本（`--yes` 由脚本接受但忽略）。

`<PROJECT_ROOT>` 替换为当前项目的根目录绝对路径。

### 步骤 3：确认启动

如果用户**未**指定 `--yes`：
- 展示设置脚本的输出摘要
- 如果 Ralph Loop 未检测到，额外说明：
  - 将执行第一个任务，但不会自动循环
  - 建议安装 ralph-loop 插件以启用自动循环
- 等待用户确认后继续

如果用户指定了 `--yes`，跳过确认直接继续。

### 步骤 4：执行第一个任务

读取 `.claude/ralph-loop.local.md` 文件中 `---` 分隔的 prompt 部分（第二个 `---` 之后的全部内容），按照其中的**自动执行协议**开始执行第一个任务。

**从此步骤开始，严格遵循 prompt 中定义的执行流程。**

注意：
- 第一个任务执行完成后，如果 ralph-loop 插件已安装，其 Stop Hook 会自动拦截退出并触发下一次迭代
- 每次迭代只执行一个任务
- 必须完成状态更新、门控校验和 git commit 后才能结束迭代

---

## 中途取消

如需取消自动执行循环，使用 `/cancel-ralph` 命令。
