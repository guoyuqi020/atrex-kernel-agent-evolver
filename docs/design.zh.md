# Evolver Bundle 设计

[English](design.md) | 中文

## 1. 角色与隔离

Evolver 是独立版本化的 Worker 实现，不是 Optimizer Candidate 内的组件。Runtime 在 Epoch
Checkpoint 完成后，于全新 Workspace 与进程中启动它。Optimizer 永远拿不到 Evolver 仓库、配置、Prompt、
Trace、Credential 或进程状态。

Runtime 物化以下 Workspace：

```text
run-<uuid>/
├── evolution-input.json       # 只读 EvolutionInputManifestV4
├── input/
│   ├── parent/                # 只读完整 Optimizer 仓库
│   ├── agents/                # 只读可见 Agent Revision 仓库
│   │   └── agentrev_<id>/
│   └── evidence/              # 只读 EvidenceViewManifestV1 Tree
│       ├── manifest.json      # role=evolver；所有已完成分支
│       ├── bootstrap/
│       └── epochs/
│           └── <epoch>/
│               ├── summary.json
│               ├── branches/ # Active 与所有 Challenger Attempt 历史
│               ├── kernels/  # 精确 Kernel Artifact 与 index.json
│               └── evolution/# 所有 Challenger 的 Evolver Trace
├── runtime-tools/              # 冻结的 Runtime 检索与 Candidate Reset 工具
│   ├── evolver_tools.py
│   ├── catalog.json        # 精确 vN/agent-vN Lineage Catalog
│   └── kernels/            # 全部历史精确 Kernel Artifact
├── candidate/                 # 所选 Base 的完整可写副本
└── scratch/                   # 可写 Report、Base 记录、Trace 与隔离 Agent 状态
```

Runtime 路径校验与进程 Capability 是当前可信边界，Prompt 指令只是纵深防御。Evolver 不获得
Runtime Gateway/Wiki Capability，也不能评测 GPU Kernel。OS Sandbox 明确推迟；在实现它之前，
不能把恶意 Agent 代码视为已被隔离。

## 2. 版本化行为

完整 Git Commit 是部署行为身份，与 Optimizer Base 约定一致。Runtime 只 Fetch 该 Commit，校验 Git
Tree，安全导出并在启动前把整个 Snapshot 封存进内容寻址存储。`atrex-evolver-bundle.json` 声明唯一
入口；Runtime 还会派生整树内容 Digest 用于完整性与 Provenance。Link、Submodule、特殊文件、不安全
Archive 或超限都会被拒绝。部署后续可以固定另一个 Commit，但运行中的 Epoch 永远不能修改本仓库。

固定 stdin Sentinel 在兼容当前 Runtime 进程传输的同时，防止部署配置静默替换版本化 Prompt。

## 3. 输入与输出

入口只接受字段和路径映射完全匹配的 Evolution Manifest Schema 4。Manifest 必须标出恰好一个
Parent，并提供非空、无重复的 `visible_agents` Catalog。Runtime 会加入已保留的 Lineage Agent
历史，以及当前 Epoch 中此前已创建的 Challenger；每个条目都解析到 `input/agents/` 下一个只读
仓库，并明确提供 Parent Link、创建者、关系类型以及适用时的当前 Epoch Challenger Ordinal。
入口同时要求严格 Evidence View 使用匹配的 Lineage Checkpoint、
`role="evolver"`、所有已完成 Epoch 的全部分支且无当前 Epoch。已完成 Summary 保留
Active、Challenger、胜出 Agent、起始 Kernel 与最佳 Kernel 身份；Branch Tree 保留每个
Attempt 与权威 Outcome；`kernels/` 对每个被引用的精确 Kernel Artifact 去重后物化一次。
入口把环境路径绑定到
Manifest，并拒绝 Link 与越界路径。Usage Report 目标是必需输入，但不接受 Token Budget。

Runtime 还会在 `runtime-tools/` 下注入限定快照的检索与 Candidate 控制 Client 和 Catalog。Catalog 提供
精确的 Lineage 内 Kernel/Agent 版本标签、Provenance、评测事实和每个历史 Kernel Artifact
路径。Client 提供有界 JSON `history`、`branches`、`attempts`、`kernels`、`kernel-read`、
`agents`、`agent-diff` 和 `trace-paths` 命令。唯一写操作
`candidate-reset --base <agentrev>` 只接受 Manifest 中标为 `lineage_history` 的 Revision，先构造
完整可写副本，再原子替换 `candidate/`，并在 `scratch/candidate-base.json` 记录 Base。它只使用
本次冻结 Workspace，不授予 Registry、Gateway、Wiki、评测或晋升权限。

Evidence 结构 Prompt Fragment 由 Runtime 编写和物化；本仓库只校验其固定路径与 Manifest 绑定的
Digest，再拼入最终 Prompt。

Coding Agent 输出带判别字段的 `EvolutionOutputV3`：可以从 Active 派生新 Revision、原样复用
一个可见历史 Revision，或从一个可见历史 Revision 派生新 Revision。创建新 Revision 的提案包含
相对于所选 Base 的准确排序 Changed Paths。每种模式都可以包含有界、结构化的
`unimplemented_capabilities`，记录所需能力、预期 Kernel 优化收益以及本次无法实现的具体原因。
Runtime 会把这些不可信建议保留在 Evolution Evidence 中，供后续 Evolver 查看；它们不会授予
额外权限，也不参与胜负选择。Runtime 仍是权威方：它校验冻结可见范围，并要求 Candidate Base
记录必须与提案形态一致；随后独立 Hash Base 与 Candidate，校验真实修改集合和
Bundle Policy，封存逐 Epoch 提案来源，再运行配置的
Active/Challenger Pool 评估。Revision 父子关系仍是树；复用和晋升是参赛事件，不是祖先边。

## 4. Token 与进程所有权

Claude、Codex、QoderCLI 与 Pi 使用各自的非交互命令/Stream Adapter，并统一为一个 Session
Result。Claude/Qoder 解析 stream-json，Pi 聚合已 Settled 的 Message/Compaction Usage，Codex
观察隔离 Session Ledger 并捕获原始 Rollout。所有 Adapter 对未缓存输入、输出、Cache Read、
Cache Write 各计一次。Token 数永远不会终止子进程；外层
SIGTERM/SIGINT 会转发给该进程组，Timeout 与 stdout/stderr 均受限。Report 使用空 Budget，已完成
模型请求若缺少完整 Provider Bucket 时失败关闭。

Session Artifact 把最终渲染 Prompt 原样保存到 `input/prompt.md`，把捕获的 Provider Stream
保存到 `provider/stdout.stream-json`，并把 Provider stderr 保存到
`provider/stderr.log`。`conversation.jsonl` 合并准确 Runtime 输入、每条保留的 Provider stdout
Event、Codex 原始 Rollout（如有）和捕获终态。CLI 未导出的 Provider 内置 System Prompt 会被
明确标记为不可获取。Runtime 与 Evolver 不对保留事件做脱敏或文本改写；它们只省略高频 Claude
`system/thinking_tokens` 估算事件，并通过 `session.json.provider_event_filters` 明确声明，最终权威
Usage 仍保存在 `events.jsonl`。Provider 输出的 Reasoning、Tool 参数与结果、Credential 或其他敏感字段因此会原样
保留。`events.jsonl` 只是额外的标准化 Usage 索引；`session.json` 记录终止状态以及原始
Provider 捕获是否避免了截断。配置的 stdout/stderr 限制仍是安全上限：超限会使 Session 失败并
标记原始流不完整，不会把截断内容静默宣称为完整。Provider 未输出的环境 Credential 不会被
主动复制。

## 5. Evolver 自进化

首版按部署 Git Commit 固定。未来可以增加提出新 Evolver Commit 的自进化层，但必须使用与 Optimizer
不同的评测和晋升策略；未晋升 Evolver 不能原地改写自身，也不能改变可信 Runtime 边界。
