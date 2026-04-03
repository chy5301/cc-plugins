# agent-native-design-guide

Agent-Native 软件设计指南 —— 面向 AI Agent 用户的软件设计决策框架与架构模式。

## 核心命题

当软件的主要用户从人类变成 Agent 时，设计方式发生根本转变：

- **GUI → CLI**：Agent 不看像素，CLI 是 Agent 的母语
- **App → Skill**：产品形态从独立应用变成可调用的原子能力
- **资产 → 耗材**：软件从重资产变成按需生成、用完即弃的轻量耗材

## 内容概览

提供 1 个 Skill，包含三层渐进式信息架构：

| 层级 | 文件 | 说明 |
|------|------|------|
| 入口 | `skills/agent-native-design-guide/SKILL.md` | 决策框架 + 十原则速查表 + 反模式 + CLI 检查清单 |
| 参考 | `references/design-principles.md` | 十原则体系完整定义（4 核心 + 6 实践），含边界条件和适用光谱 |
| 参考 | `references/architecture-patterns.md` | 三层架构 + 协议选择矩阵 + 复杂度分级 + 展示层演进路线 |
| 示例 | `examples/cli-json-output.py` | 标准 JSON 信封结构、`--fields` 字段掩码、退出码约定 |
| 示例 | `examples/cli-help-design.py` | 双模 `--help`（人类文本 / Agent JSON）、`schema` 自省 |

## 安装

参见 [仓库 README](../README.md#安装)。

## 使用

安装后，当你在设计面向 Agent 的工具时，Skill 会自动触发。也可手动调用：

```
/agent-native-design-guide:agent-native-design-guide
```

运行示例代码：

```bash
uv run python examples/cli-json-output.py list --json
uv run python examples/cli-help-design.py --help --json
```

## 来源

本设计指南整合了三套来源：

1. **实践提炼**：从 Reader、Anecdote 等 Agent-Native 产品中提炼的五原则（Every.to）
2. **工程经验**：Anthropic 内部数百个 Skill 的九条写作原则
3. **第一性原理**：从 Agent 交互特性推导的设计原则 + 语义优先架构理论

## 关联项目

本 Plugin 的调研源头和开发工作区：[chy5301/agent-native](https://github.com/chy5301/agent-native)。该仓库包含完整的调研笔记、案例分析、工作流记录和设计产出过程。本目录是其 `skill/agent-native-design-guide/` 的打包发布副本。
