---
name: agent-native-design-guide
description: >
  This skill should be used when the user is designing software, tools, CLIs, or
  Skills meant to be operated by AI agents rather than humans. It provides a
  decision framework and design principles for Agent-Native software architecture.
  Trigger on 'design for agents', 'agent-native', 'agent-friendly CLI',
  'make this tool agent-compatible', 'CLI for agents', 'Skill architecture',
  'agent-first design', 'how should agents use this tool',
  'convert to agent-native', 'tool design principles'.
---

# Agent-Native 设计指南

面向 Agent-Native 软件的设计原则与架构模式——当软件的主要用户从人类变成 AI Agent 时，如何设计、构建和分发软件。

当用户正在设计、构建或重构面向 Agent 使用的工具/CLI/Skill 时，使用本指南辅助设计决策。核心命题：Agent 通过文本感知世界、通过工具操作世界、通过组合原子能力产生涌现工作流。

## 何时使用本指南

**适用场景**：
- 设计一个 Agent 将调用的 CLI 工具
- 重构现有工具使其对 Agent 友好
- 在 CLI+Skill、MCP 或其他协议间做选择
- 为同时服务 Agent 和人类用户的工具做架构决策
- 为新能力编写 SKILL.md

**不适用场景**：
- 构建纯人类使用的 GUI，无 Agent 交互
- 处理 Agent 不会触及的内部业务逻辑
- 编写一次性脚本，不打算复用

## 决策框架

### 1. 这个工具需要 Agent-Native 设计吗？

```
这个工具会被 AI Agent 调用吗？
  否 --> 标准 CLI/API 设计即可
  是 --> 继续

Agent 是主要用户吗？
  是 --> 完整 Agent-Native 设计（所有原则适用）
  否 --> 双模设计（添加 --json + --help，保留人类默认值）
```

### 2. 选择协议

默认使用 CLI+Skill，仅在必要时升级：

```
从 CLI + --json 输出 + 输入验证开始                    (P0，覆盖所有平台)
  |
添加 SKILL.md + --help --json                          (P1，可发现性)
  |
添加 --dry-run + --fields                              (P2，安全性 + 效率)
  |
参数结构复杂？Shell 转义成为瓶颈？
  是 --> 在 CLI 基础上叠加 MCP Server 表面
  否 --> CLI+Skill 已足够
```

核心原则：一个实现，两个表面。CLI 和 MCP 共享同一份 schema 和业务逻辑。MCP 是 CLI 的补充，而非替代。

### 3. 选择架构

架构复杂度应匹配工具的实际需求：

| 复杂度 | 架构 | 控制层 | 数据层 |
|--------|------|--------|--------|
| 简单 | 单体 CLI | CLI + `--json` | 文件系统 |
| 中等 | CLI + 服务 | CLI + SKILL.md（+ 可选 MCP） | 文件系统 + 轻量 DB |
| 复杂 | 平台 | CLI/MCP + 后端 Agent | 后端 API + DB |

三层分离模式适用于所有层级：**控制层**（Agent 入口——结构化接口）、**展示层**（人类入口——可视化渲染）、**数据层**（共享内核——唯一事实来源）。两个入口共享同一数据层。详见 `${CLAUDE_PLUGIN_ROOT}/references/architecture-patterns.md`。

## 十大设计原则——速查表

### 核心原则（回答"为什么"）

| 编号 | 原则 | 一句话定义 |
|------|------|-----------|
| C1 | 文本即界面 | Agent 通过文本感知和操作世界，结构化文本是原生交互媒介 |
| C2 | 原子化与可组合 | 能力以最小独立单元暴露，Agent 通过组合产生涌现能力 |
| C3 | 对等性 | Agent 能做用户能做的一切——能力不打折扣 |
| C4 | 安全边界优先 | 先定义权限边界，在边界内自由操作 |

### 实践原则（回答"怎么做"）

| 编号 | 原则 | 一句话定义 |
|------|------|-----------|
| P1 | 可发现性 | Agent 通过 `--help`、schema、SKILL.md 发现能力，而非靠猜 |
| P2 | 确定性 | 相同输入产生相同输出，状态变更可预测 |
| P3 | 输出即产品 | 输出格式设计比功能设计更影响 Agent 效率 |
| P4 | Gotchas 驱动迭代 | Skill 的核心价值在持续积累的踩坑记录，而非 Day 1 文档 |
| P5 | 渐进式信息披露 | 用文件结构做上下文工程——SKILL.md 为精简入口，详情在 references/ |
| P6 | 约束意图而非步骤 | 说清目标和边界，把方法交给 Agent |

每条原则都包含边界条件——指出不完全适用的情况。详见 `${CLAUDE_PLUGIN_ROOT}/references/design-principles.md`，包含完整定义、设计理由、正面示例和边界条件。

## 关键反模式

避免以下三个最常见的 Agent-Native 设计错误：

**1. 工作流化的工具**（违反 C2）
将多步决策逻辑打包为单个工具（如 `classify_and_organize_files()`）。Agent 无法介入中间步骤，丧失推理优势。
- 修正：暴露原子操作（`read_file`、`move_file`、`tag_file`），让 Agent 自行组合。

**2. 先构建再暴露**（违反 C3）
按传统方式开发完整 GUI 产品后才考虑 Agent 接入，通常导致只有部分功能可通过工具访问。
- 修正：从一开始就并行设计工具层和 UI 层，共享同一数据层。

**3. 忽视输出设计**（违反 P3）
功能正确但输出冗余、格式不稳定。Agent 花费大量 token 解析无关信息。实证数据：结构化输出优化可将 Agent 解析时间降低 5-9 倍。
- 修正：实现 `--json`，使用标准信封结构 `{success, data, metadata, error}`。支持 `--fields` 按需选择输出字段。

## CLI 设计快速检查清单

实现或审查面向 Agent 使用的 CLI 工具时，逐项验证：

- [ ] `--json` 标志输出结构化数据（标准信封：`{success, data, metadata, error}`）
- [ ] `--help` 包含参数类型、默认值、约束范围和示例
- [ ] 命令命名遵循 `<工具> <资源> <操作>` 模式
- [ ] CLI 入口点进行输入验证（路径规范化、schema 校验、拒绝危险字符）
- [ ] 错误响应包含错误码（机器可读）+ 错误描述 + 恢复建议
- [ ] 退出码遵循约定（0=成功, 1=错误, 2=用法错误, 3=权限拒绝）
- [ ] 破坏性操作支持 `--dry-run`
- [ ] 支持 `--fields` 输出字段掩码（保护上下文窗口）

可运行的代码示例：`${CLAUDE_PLUGIN_ROOT}/examples/cli-json-output.py`（JSON 信封）和 `${CLAUDE_PLUGIN_ROOT}/examples/cli-help-design.py`（Agent 友好的 `--help`）。

## 安全要点

Agent 安全存在根本性张力：Agent 必须读取外部数据才能工作，但外部数据可能包含恶意指令（提示注入）。工具开发者的三条安全原则：

1. **将所有输入视为对抗性输入** —— 路径穿越检查、参数 schema 校验、拒绝 shell 元字符。使用 `subprocess.run([list])` 而非 `os.popen(string)`。
2. **声明最小权限** —— 精确指定工具所需权限（文件路径、网络域名、可执行文件），不多也不少。类似 Android 权限但粒度更细。
3. **为沙箱执行而设计** —— 不假设拥有完整主机访问权限。将文件操作限制在工作目录内，声明所需网络域名。如果工具无法在沙箱中运行，在 SKILL.md 中说明原因。

权限级别参考：L0 只读（自动允许）→ L1 限定范围写入（确认一次）→ L2 shell 执行（白名单或确认）→ L3 网络/凭证（始终确认）→ L4 不可逆操作（确认 + dry-run 必需）。

## 参考文件

需要深入指导时查阅：

### 参考文档

- **`${CLAUDE_PLUGIN_ROOT}/references/design-principles.md`** —— 十原则体系完整定义，包含设计理由、正面示例、边界条件、反模式清单和适用光谱。在做设计权衡决策或需要了解原则边界条件时阅读。
- **`${CLAUDE_PLUGIN_ROOT}/references/architecture-patterns.md`** —— 三层架构定义、协议选择矩阵（CLI+Skill vs MCP vs A2A vs OpenAPI）、按复杂度分级的架构方案（简单/中等/复杂）、展示层演进路线 P0-P3。在为新工具选择架构或评估协议方案时阅读。

### 示例代码

- **`${CLAUDE_PLUGIN_ROOT}/examples/cli-json-output.py`** —— 可运行的 Python 示例，演示标准 JSON 信封、`--fields` 字段掩码、`--quiet` 模式和退出码约定。运行：`uv run python ${CLAUDE_PLUGIN_ROOT}/examples/cli-json-output.py list --json`。
- **`${CLAUDE_PLUGIN_ROOT}/examples/cli-help-design.py`** —— 可运行的 Python 示例，演示双模 `--help`（人类文本 / Agent JSON）和 `schema` 子命令的机器可读 JSON Schema 自省。运行：`uv run python ${CLAUDE_PLUGIN_ROOT}/examples/cli-help-design.py --help`。

## Gotchas

<!-- 本段随实践持续增长。每当 Agent 在应用本指南时遇到问题，在此追加一行。 -->

（尚无 Gotchas 记录——在实践中发现时追加。）
