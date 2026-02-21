---
description: 终止工作流 + 清理环境
argument-hint: "[--reset] [终止原因]"
allowed-tools: Bash, Read, Write, Grep
---

# /task-abort — 工作流终止

你是一个工作流终止管理员。你的职责是安全地终止当前工作流、清理环境，并生成终止报告。**默认不触碰代码**，仅清理状态文件。

**不要在 plan mode 下使用此命令。**

## 输入

- `$ARGUMENTS`：可选参数
  - `--reset`：执行 `git reset --hard` 回滚到工作流初始 commit（需二次确认）
  - 其余部分作为终止原因记录

## 执行流程

### 步骤 1：读取工作流状态

1. 读取 `.claude/workflow.json`
2. 读取 TASK_STATUS.md
3. 统计任务完成情况：
   - ✅ 已完成数
   - 🔄 进行中数
   - ⬜ 待开始数
   - ❌ 已取消数
   - ⏸️ 暂停数
4. 解析 `$ARGUMENTS`：
   - 检查是否包含 `--reset` 标志
   - 提取终止原因（去掉 `--reset` 后的剩余文本）

### 步骤 2：生成工作流报告

1. 从 `workflow.json` 中读取 `initCommit` 字段
2. 如果 `initCommit` 存在且非空，验证其有效性：`git cat-file -t <initCommit>`
3. **向用户展示工作流概况**：

```
## 工作流终止确认

### 进度快照
- 任务类型: [primaryType]
- 已完成: N 个任务
- 未完成: N 个任务（进行中 N + 待开始 N + 暂停 N）
- 已取消: N 个任务

### 工作流期间的 commit（initCommit 有效时展示）
[git log --oneline <initCommit>..HEAD 的输出]

### 建议的 git 命令（供参考）
- 回滚全部更改: `git reset --hard <initCommit>`
- 查看变更详情: `git diff <initCommit>..HEAD`
- 逐个撤销 commit: `git revert <commit-hash>`
```

如果 `initCommit` 不存在或无效，跳过 commit 列表和 git 命令部分，说明"工作流初始化时未记录 initCommit，无法展示 commit 范围"。

### 步骤 3：代码回滚（仅当 `--reset` 时）

- 如果用户**未指定 `--reset`**：跳到步骤 4
- 如果 `initCommit` 无效或不存在：告知用户"initCommit 无效，无法执行代码回滚"，跳到步骤 4

执行回滚流程：

1. **检查未提交更改**：运行 `git status --porcelain`
   - 如果有未提交更改，向用户提供选项：
     - **stash**：执行 `git stash push -m "task-abort: stash before reset"`
     - **丢弃**：继续执行（reset 会一并清除）
     - **取消回滚**：跳过代码回滚，继续步骤 4

2. **二次确认**：向用户展示完整警告：
   ```
   ⚠ 代码回滚警告

   即将执行: git reset --hard <initCommit>
   将回滚 N 个 commit:
   [commit 列表]

   ⚠ 注意：这些 commit 中可能包含不属于当前工作流的提交（如紧急修复、配置调整等）。
   回滚后这些提交也会被撤销。

   确认要继续吗？
   ```
   - 用户明确确认后才执行
   - 用户拒绝则跳过回滚，继续步骤 4

3. **执行回滚**：`git reset --hard <initCommit>`
4. **验证**：确认 `git rev-parse HEAD` 等于 `initCommit`

### 步骤 4：处理状态文件

询问用户选择处理方式：

- **归档**（推荐）：保留记录，方便将来追溯
- **删除**：彻底清除，不保留任何记录

#### 归档模式

1. 生成终止报告 `docs/ABORT_REPORT.md`：

```markdown
# 工作流终止报告

## 基本信息
- **任务类型**: [primaryType]
- **终止时间**: [当前日期时间]
- **终止原因**: [用户提供的原因，未提供则写"用户主动终止"]

## 进度快照
- 已完成: N 个任务
- 进行中: N 个任务
- 待开始: N 个任务
- 暂停: N 个任务
- 已取消: N 个任务

### 已完成的任务
| 编号 | 标题 |
|------|------|
[从 TASK_STATUS.md 中提取]

### 未完成的任务
| 编号 | 标题 | 状态 |
|------|------|------|
[从 TASK_STATUS.md 中提取]

## 工作流期间的 commit
[git log --oneline <initCommit>..HEAD 或 "initCommit 不可用"]

## 代码回滚状态
[已回滚到 <initCommit> / 未执行代码回滚]
```

2. 运行归档脚本：`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/abort_workflow.py" --path <PROJECT_ROOT> --mode archive [--label <标签>]`

#### 删除模式

运行清理脚本：`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/abort_workflow.py" --path <PROJECT_ROOT> --mode delete`

### 步骤 5：验证清理

确认以下条件：
- [ ] `.claude/workflow.json` 已移除
- [ ] 状态文件已归档或删除
- [ ] 如果执行了 `--reset`：HEAD 指向 initCommit

### 步骤 6：完成报告

向用户报告：
- 工作流已终止
- 状态文件处理结果：
  - 归档模式：归档目录位置
  - 删除模式：已删除
- 代码回滚状态：
  - 已回滚：回滚到 `<initCommit>`
  - 未回滚：附上参考 git 命令（如果 initCommit 有效）
- 如果执行了 stash：提示 `git stash pop` 恢复暂存更改
- 提示可使用 `/task-init` 开始新工作流

---

## 关键约束

- **默认不触碰代码**：仅 `--reset` 时才执行 git reset
- **git reset 必须二次确认**：明确警告可能包含非工作流 commit
- **ABORT_REPORT.md 在移动文件前生成**：归档脚本运行前先写入报告
- **归档目录名含 `aborted` 标记**：与正常归档区分
- **向后兼容**：旧版 workflow.json 缺少 `initCommit` 时，跳过 commit 范围展示，不影响状态文件清理
- **不要在 plan mode 下使用**
