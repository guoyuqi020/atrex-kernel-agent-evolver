# Atrex Kernel Agent Evolver

[English](README.md) | 中文

Atrex Kernel Agent Evolver 是一个独立版本化、固定加载的 Agent Bundle。它在一次 Runtime
创建的 Evolution Workspace 中提出一份提案：可以修改 Active、原样
复用一个可见历史 Revision、修改一个可见历史 Revision，或在证据不足以支持 Agent 可控改进时不创建
Challenger。它不属于被修改的
Optimizer Revision，Optimizer Session 看不到它，并且它没有 Gateway、Wiki、评测、调度、保留或
晋升权限。

一次调用会：

1. 严格校验 Runtime-private `EvolutionInputManifestV10` 和所有 Runtime 路径；
2. 直接从冻结文件系统读取完整 Parent、当前参赛仓库、历史 Agent 仓库、优化汇总、最近 Epoch
   Conversation 和 Runtime State；
3. 从历史派生时，把所选历史 Agent 的 Source 完整复制到 Candidate，并可从可见历史状态整理一份
   公共 Candidate 状态种子；
4. 使用仓库内固定 Prompt 启动一次全新的非交互 Coding Agent；
5. 从 `evolved`、`reuse`、`evolve_from_history`、`no_change` 中选择一种；需要创建新 Revision 时，只允许修改
   `candidate/`；
6. 输出未脱敏 Session Artifact，其中包含最终渲染 Prompt、保留的 Provider
   stdout/stderr、标准化 Usage 索引和严格 Provider Token Report；高频 Claude
   `system/thinking_tokens` 估算事件会被有意省略；
7. 提供本地 `evolution-report` 命令：Draft 失败时返回结构化修复指导，第一次成功时原子发布
   `EvolutionOutput`；随后 Runtime 再独立验证并封存提案。

## Agent Backend

版本 2 通过全新的非交互 CLI Adapter 支持 `claude`、`codex`、`qodercli` 和 `pi`。仓库配置
提供独立运行默认值；托管运行由 Runtime 注入权威 Backend、Lineage 所选 Model、Reasoning
Effort 与 Session Settings；空 Model 表示使用 Backend CLI 默认值。四种 Backend 输出相同的标准化 Trace 和 Provider Token 协议。Token 不设截止，Usage
仍是必需遥测，进程 Wall Time 与输出限制仍是安全边界。每次运行发布空 Budget 的
`TokenUsageReportV1`；Codex Usage 与原始 Rollout 从隔离 Session Ledger 获取。

Claude 使用全新 Session ID 并启用原生持久化，不恢复旧上下文。主会话和子会话 JSONL 分别保存在 `provider/claude-session.raw-jsonl`、`provider/claude-subagents/`，超时或失败时也尽力保留。`events.jsonl` 每个响应只保留最新 usage，并通过 `message_id`、`source_path` 关联原始工具调用。stdout 中间计数属于暂定值，重复更新替换旧值。只有原生逐响应计数与终态总账核对一致时，`session.json.response_usage_complete` 才为 true；缺失或不一致会标为 partial 并记录诊断，不用估算值替换终态总账。统计时不要重复累加 native/stdout 副本，也不要把终态总账再加到逐响应用量上。

封存后的 `conversation.jsonl` 是阅读视图：Claude 优先使用原生内容，省去已被完整覆盖的 stdout 消息副本，保留不同的 thinking/text/tool 内容块、未被覆盖的 stdout 内容、诊断、压缩边界和终态结果。重复的初始 Prompt，以及原生队列、标题、文件历史等内部管理事件只从阅读视图中省去。封存前的实时视图仍跟随 stdout。原始 Provider 文件及规范化 usage 索引不变。

Coding Agent 可以修改统一 `candidate/` Bundle 中任意 Agent 内容，包括实现、配置及
prompts、insights、skills、tools。每个自适应目录只有一份有效内容，并维护 README 索引。
Runtime 封存完整 Bundle 和自适应 Checkpoint，供后续优化使用。输入 Bundle 与逐 Trajectory 资源只读；
Evolver、Runtime 和部署策略不属于 Candidate，不能修改。
Optimizer Session 只能修改 Tools；Evolver 根据已完成 Conversation、Report 与权威结果整理 Prompts、
Insights 和 Skills。成熟、可重复的 Tool 可以沉淀为 Claude Skill，一次性或失败的 Helper 不应被提升。

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
