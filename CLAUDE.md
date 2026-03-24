# CLAUDE.md

## 项目概述

cc-plugins 是一个 Claude Code 插件集合仓库，通过 `.claude-plugin` 体系发布到 marketplace。当前包含两个插件：**structured-workflow**（大型工程任务的结构化管理工作流）和 **gitee-toolkit**（Gitee 一站式工具箱）。

仓库本身不包含可构建或可测试的应用代码——所有内容都是 Markdown 命令定义、Python 辅助脚本和 JSON 配置。

## 仓库结构

```
.claude-plugin/marketplace.json    # Marketplace 元数据，注册所有插件
structured-workflow/               # structured-workflow 插件根目录
  .claude-plugin/plugin.json       # 插件元数据（名称、版本、描述）
  skills/                          # 7 个 Skills（task-init, task-exec, task-adjust 等）
  scripts/                         # Python 辅助脚本（init_project.py, abort_workflow.py 等）
  references/                      # 参考文档（methodology.md 核心方法论、任务格式、异常处理等）
gitee-toolkit/                     # gitee-toolkit 插件根目录
  .claude-plugin/plugin.json       # 插件元数据
  .mcp.json                        # MCP Server 配置（远程 HTTP 连接 Gitee API）
  skills/                          # 14 个 Gitee DevOps Skills（基于 oschina/gitee-agent-skills v1.0.0）
```

## 插件架构关键概念

- **技能（skills/）**：`SKILL.md` 通过 frontmatter 的 `description` 字段控制自动激活条件；`disable-model-invocation: true` 禁止自动触发（仅手动调用）
- **脚本（scripts/）**：通过 `uv run` 执行的 Python 脚本，处理文件系统操作（初始化目录结构、归档、清理等）
- **引用（references/）**：被命令在运行时通过 `${CLAUDE_PLUGIN_ROOT}/references/` 路径动态加载的参考文档
- **`${CLAUDE_PLUGIN_ROOT}`**：Claude Code 运行时自动解析的变量，指向插件根目录

## 开发约定

- 命令文件使用中文编写，面向 Claude Code 作为执行者
- Python 脚本使用 `uv run` 执行，不依赖预装环境
- 版本号维护在各插件的 `.claude-plugin/plugin.json` 的 `version` 字段
- `structured-workflow` 的自动执行功能（`/task-auto`）依赖外部插件 `ralph-loop`
- `gitee-toolkit` 的 Skills 基于 [oschina/gitee-agent-skills](https://github.com/oschina/gitee-agent-skills) v1.0.0 独立维护，不自动同步上游

### 版本号更新

当用户提到提交或发布时，如果本次变更涉及插件功能/行为的修改，需在提交前更新对应插件的 `plugin.json` 中的 `version` 字段（遵循 semver）。

### Commit 规范（项目级补充）

本仓库包含多个插件，commit message 的 scope 应标注插件名称，例如：
- `feat(structured-workflow): 新增阶段回顾的变更审计功能`
- `fix(structured-workflow): 修复 task-auto 退出条件判断`

如果变更涉及仓库根目录（如 marketplace.json、README.md），scope 使用 `root`：
- `docs(root): 更新安装说明`

## 修改插件时的注意事项

- 修改 skill 行为时，确保与 `references/methodology.md` 中描述的核心原则保持一致（七项核心原则、六步执行协议等）
- skill 间通过 `docs/workflow/` 下的状态文件（workflow.json、TASK_STATUS.md、TASK_PLAN.md、TASK_ANALYSIS.md）进行信息传递
- `references/` 下的文档被多个 skill 引用，修改时需检查所有引用方
- marketplace.json 和 plugin.json 需要保持同步（插件名称、描述等）
- 修改 `gitee-toolkit/.mcp.json` 中的远程 MCP Server 地址时需同步测试连通性
- gitee-toolkit 的 Skills 基于 oschina/gitee-agent-skills v1.0.0 独立维护，修改时注意与上游的差异
- marketplace.json 中 gitee-toolkit 的描述需与 `gitee-toolkit/.claude-plugin/plugin.json` 保持同步
