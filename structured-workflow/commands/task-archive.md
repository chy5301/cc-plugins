---
description: 工作流归档 + 环境清理
argument-hint: "[--summary | --label <标签>]"
allowed-tools: Bash, Read, Write, Grep
---

# /task-archive — 工作流归档

你是一个工作流归档管理员。你的职责是在大型任务完成后，生成完成摘要，归档状态文件，清理环境，使项目恢复到"干净"状态。

## 输入

- `$ARGUMENTS`：可选参数
  - `--summary`：仅生成摘要，不执行归档
  - `--label <标签>`：自定义归档标签

## 执行流程

### 步骤 1：完成度确认

1. 读取 `.claude/workflow.json` 和 TASK_STATUS.md
2. 统计任务完成情况：
   - 总任务数
   - 已完成数
   - 未完成数（含暂停、待开始）
3. 如果有未完成的任务：
   - 列出未完成任务的编号和标题
   - 询问用户：是否确认跳过这些任务并继续归档？
   - 用户确认后继续，否则终止

### 步骤 2：生成完成摘要报告

基于 TASK_STATUS.md 的内容，生成完成摘要：

```markdown
# 工作流完成摘要

## 基本信息
- **任务类型**: [primaryType]
- **开始时间**: [从 TASK_STATUS.md 创建时间]
- **归档时间**: [当前日期]

## 总体统计
- 阶段数: N
- 任务总数: N
- 已完成: N
- 已取消: N
- 未完成: N

## 各阶段摘要

### Phase 0: [阶段名]
- 完成任务: [列表]
- 关键成果: [摘要]

### Phase 1: [阶段名]
...

## 关键决策汇总
（从决策日志中提炼）

## 遗留问题清单
（从已知问题和交接记录中收集未解决的问题）

## 经验教训
（从决策日志、已知问题、异常处理记录中提炼）
- 教训 1: ...
- 教训 2: ...
```

将摘要写入 `docs/archive/workflow-{type}-{date}/SUMMARY.md`。

如果 `$ARGUMENTS` 包含 `--summary`，到此步停止，不执行后续归档操作。

### 步骤 3：执行归档

运行归档脚本：

1. 运行：`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/archive_workflow.py" --path <PROJECT_ROOT> [--label <标签>]`

脚本会：
- 将 TASK_ANALYSIS.md、TASK_PLAN.md、TASK_STATUS.md、DEPENDENCY_MAP.md 移入归档目录
- 将 workflow.json 备份到归档目录后删除原件

### 步骤 4：验证清理

确认以下文件已正确处理：
- [ ] `docs/archive/workflow-{type}-{date}/` 目录存在且包含所有文件
- [ ] `docs/archive/workflow-{type}-{date}/SUMMARY.md` 已生成
- [ ] `.claude/workflow.json` 已移除
- [ ] `docs/TASK_ANALYSIS.md` 已移除
- [ ] `docs/TASK_PLAN.md` 已移除
- [ ] `docs/TASK_STATUS.md` 已移除

### 步骤 5：完成报告

向用户报告：
- 归档目录位置
- 归档的文件列表
- 项目已恢复"干净"状态
- 可以使用 `/task-init` 开始新一轮大型任务

---

## 关键约束

- 归档操作不会修改任何项目代码
- 归档前必须确认用户意图（特别是有未完成任务时）
- SUMMARY.md 必须在移动文件之前生成（因为需要读取状态文件内容）
- 归档目录命名包含日期，避免覆盖历史归档
