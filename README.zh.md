# Atrex Kernel Agent Evolver

[English](README.md) | 中文

Atrex Kernel Agent Evolver 是一个独立版本化、固定加载的 Agent Bundle。它在一次 Runtime
创建的 Evolution Workspace 中，为完整 Optimizer 仓库提出一个 Challenger。它不属于被修改的
Optimizer Revision，Optimizer Session 看不到它，并且它没有 Gateway、Wiki、评测、调度、保留或
晋升权限。

一次调用会：

1. 严格校验 `EvolutionInputManifestV4` 和所有 Runtime 路径；
2. 读取完整 Parent 仓库、只读的可见 Agent Revision Catalog，以及严格、按 Epoch 组织且包含
   所有已完成分支、Kernel Artifact 与 Agent 胜负结果的 Evidence View；
3. 使用 Runtime 注入的只读工具查询冻结的 Agent/Kernel/Epoch 历史；
4. 使用仓库内固定 Prompt 启动一次全新的非交互 Coding Agent；
5. 只允许修改可写的完整 Candidate 仓库；
6. 输出未脱敏 Session Artifact，其中包含最终渲染 Prompt、原始 Claude stream-json
   stdout/stderr、标准化 Usage 索引和严格 Provider Token Report；
7. 先校验 Agent 编写的 `EvolutionOutputV2`，再交给 Runtime 独立验证和封存 Candidate。

## 当前 Backend

版本 1 实现 Claude CLI stream-json Backend 和实时 Provider Token 计量，但没有 Token 截止。
Provider Usage 仍是必需遥测，进程 Wall Time 和输出限制仍是安全边界；Bundle 始终发布 Budget
为空的 `TokenUsageReportV1`。当前不虚假宣称支持 Codex：符合协议的 Codex Backend 必须观察
Session Ledger 并发布同样完整的记账。

Coding Agent 可以修改 `candidate/` 下任意有效的 Optimizer 文件，包括 Agent Backend 配置、
Prompt、Workflow、Tool Binding、Memory Policy 和 DSL 指导。Evolver、Runtime 与部署策略不在
Candidate 内，或者只读，因此不能被它修改。

## 仓库契约

- `atrex-evolver-bundle.json` 声明唯一入口 `src/main.py`；
- `atrex-evolver.json` 固定 Backend 行为、Prompt、超时与输出上限；
- `prompts/evolve.md` 定义 Evidence 驱动的 Agent Engineering 流程；
- Runtime 只提供 Evolution 输入/Candidate/输出路径、Token Report 路径，以及显式允许的
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
