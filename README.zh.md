# Atrex Kernel Agent Evolver

[English](README.md) | 中文

Atrex Kernel Agent Evolver 是一个独立版本化、固定加载的 Agent Bundle。它在一次 Runtime
创建的 Evolution Workspace 中，为 Optimizer 仓库提出一个 Challenger：可以修改 Active、原样
复用一个可见历史 Revision，或修改一个可见历史 Revision。它不属于被修改的
Optimizer Revision，Optimizer Session 看不到它，并且它没有 Gateway、Wiki、评测、调度、保留或
晋升权限。

一次调用会：

1. 严格校验 `EvolutionInputManifestV4` 和所有 Runtime 路径；
2. 读取完整 Parent 仓库、只读的可见 Agent Revision Catalog，以及严格、按 Epoch 组织且包含
   所有已完成分支、Kernel Artifact 与 Agent 胜负结果的 Evidence View；
3. 使用 Runtime 注入的工具查询冻结的 Agent/Kernel/Epoch 历史；从历史派生时，由受约束工具将
   可写 Candidate 原子切换到合格的历史仓库；
4. 使用仓库内固定 Prompt 启动一次全新的非交互 Coding Agent；
5. 从 `evolved`、`reuse`、`evolve_from_history` 中选择一种；需要创建新 Revision 时，只允许修改
   可写的完整 Candidate 仓库，且历史 Base 必须通过 Runtime Reset 操作加载；
6. 输出未脱敏 Session Artifact，其中包含最终渲染 Prompt、保留的 Provider
   stdout/stderr、标准化 Usage 索引和严格 Provider Token Report；高频 Claude
   `system/thinking_tokens` 估算事件会被有意省略；
7. 先校验带判别字段的 `EvolutionOutputV3`，再交给 Runtime 独立验证和封存提案。

## Agent Backend

版本 2 通过全新的非交互 CLI Adapter 支持 `claude`、`codex`、`qodercli` 和 `pi`。仓库配置
提供独立运行默认值；托管运行由 Runtime 注入权威 Backend、Lineage 所选 Model、Reasoning
Effort 与 Session Settings；空 Model 表示使用 Backend CLI 默认值。四种 Backend 输出相同的标准化 Trace 和 Provider Token 协议。Token 不设截止，Usage
仍是必需遥测，进程 Wall Time 与输出限制仍是安全边界。每次运行发布空 Budget 的
`TokenUsageReportV1`；Codex Usage 与原始 Rollout 从隔离 Session Ledger 获取。

Coding Agent 对 `candidate/` 拥有完整设计权限：可以增加、替换、重组或删除任何 Optimizer
内容，包括 Agent 架构、Backend 配置、Prompt、Skill、Workflow、Tool、Memory Policy、DSL
指导、测试和文档。当 Evidence 支持时，它可以整体替换现有设计，以提高 Agent 做 Kernel
优化的有效性或效率；最终仓库仍必须是有效的 Optimizer Bundle。Evolver、Runtime 与部署策略
不在 Candidate 内，或者只读，因此不能被它修改。

Evolution Report 还可以列出结构化的 `unimplemented_capabilities`：说明有价值但本次无法实现的
Agent 能力、预期的 Kernel 优化收益，以及无法实现的具体原因。这些内容只是建议，不会授予额外权限。

## 仓库契约

- `atrex-evolver-bundle.json` 声明唯一入口 `src/main.py`；
- `atrex-evolver.json` 提供 Backend 独立运行默认值、Prompt、超时与输出上限；
- `prompts/evolve.md` 定义 Evidence 驱动的 Agent Engineering 流程；
- Runtime 提供 Agent Binding、Evolution 输入/Candidate/输出路径、Token Report 路径，以及显式允许的
  Provider Credential 与隔离 Home；
- Runtime stdin 必须只包含 `Run the versioned Evolver Bundle once.`，不能替换版本化 Prompt。

详见[设计](docs/design.zh.md)和[Runtime 使用](docs/quickstart.zh.md)。

## 开发

```bash
python -m pytest -q
ruff check src tests
mypy src tests
python -m compileall -q src tests
```

本项目使用 [Apache License 2.0](LICENSE)。
