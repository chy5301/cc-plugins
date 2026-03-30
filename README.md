# cc-plugins

Claude Code 插件集合。

## 包含的插件

| 插件 | 说明 |
|------|------|
| [structured-workflow](./structured-workflow/) | 大型工程任务的结构化管理工作流。提供分析→规划→执行→回顾→归档全生命周期管理。 |
| [gitee-toolkit](./gitee-toolkit/) | Gitee 一站式工具箱。集成 Gitee MCP Server 与 DevOps Skills，覆盖 PR、Issue、Release、仓库探索等操作。 |
| [agent-native-design-guide](./agent-native-design-guide/) | Agent-Native 软件设计指南。提供面向 AI Agent 的软件设计决策框架、十原则体系和架构模式。 |

## 安装

### 方式 1：通过 Marketplace 安装（推荐）

在 Claude Code 中依次执行：

```
/plugin marketplace add chy5301/cc-plugins
/plugin install structured-workflow@cc-plugins
/plugin install gitee-toolkit@cc-plugins
/plugin install agent-native-design-guide@cc-plugins
```

### 方式 2：本地加载

克隆仓库后，启动 Claude Code 时指定插件目录：

```bash
git clone https://github.com/chy5301/cc-plugins.git
claude --plugin-dir /path/to/cc-plugins/structured-workflow
```
