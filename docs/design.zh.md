# Evolver Bundle 设计

[English](design.md) | 中文

## 1. 角色与隔离

Evolver 是独立版本化的 Worker 实现，不是 Optimizer Candidate 内的组件。Runtime 在 Epoch
Checkpoint 完成后，于全新 Workspace 与进程中启动它。Optimizer 永远拿不到 Evolver 仓库、配置、Prompt、
Trace、Credential 或进程状态。

Runtime 物化以下 Workspace：

```text
run-<uuid>/
├── evolution-input.json       # 只读 EvolutionInputManifestV3
├── input/
│   ├── parent/                # 只读完整 Optimizer 仓库
│   ├── agents/                # 只读可见 Agent Revision 仓库
│   │   └── agentrev_<id>/
│   └── evidence/              # 只读 EvidenceViewManifestV1 Tree
│       ├── manifest.json      # role=evolver；只含已完成 Epoch
│       ├── bootstrap/
│       └── epochs/
├── candidate/                 # Parent 的完整可写副本
└── scratch/                   # 可写 Report、Trace 与隔离 Agent 状态
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

入口只接受字段和路径映射完全匹配的 Evolution Manifest Schema 3。Manifest 必须标出恰好一个
Parent，并提供非空、无重复的 `visible_agents` Catalog。Runtime 会加入已保留的 Lineage Agent
历史，以及当前 Epoch 中此前已创建的 Challenger；每个条目都解析到 `input/agents/` 下一个只读
仓库，并明确提供 Parent Link、创建者、关系类型以及适用时的当前 Epoch Challenger Ordinal。
入口同时要求严格 Evidence View 使用
匹配的 Lineage Checkpoint、`role="evolver"`、已完成的晋升 Agent Lineage 且无当前 Epoch。它把环境路径绑定到
Manifest，并拒绝 Link 与越界路径。Usage Report 目标是必需输入，但不接受 Token Budget。

Evidence 结构 Prompt Fragment 由 Runtime 编写和物化；本仓库只校验其固定路径与 Manifest 绑定的
Digest，再拼入最终 Prompt。

Coding Agent 输出 EvolutionOutputV2，包含 Parent 身份、Hypothesis、Expected Effect 和准确排序的
Changed Paths。Runtime 仍是权威方：它独立 Hash Parent 与
Candidate，校验真实修改集合和 Bundle Policy，封存来源，再运行配置的 Active/Challenger Pool
评估。

## 4. Token 与进程所有权

Claude Backend 按唯一 Provider Message 解析 stream-json Usage，存在终态 Usage 时以其为准，并对
未缓存输入、输出、Cache Read、Cache Write 各计一次。Token 数永远不会终止子进程；外层
SIGTERM/SIGINT 会转发给该进程组，Timeout 与 stdout/stderr 均受限。Report 使用空 Budget，已完成
模型请求若缺少完整 Provider Bucket 时失败关闭。

Session Artifact 把最终渲染 Prompt 原样保存到 `input/prompt.md`，把捕获的 Claude
stream-json 保存到 `provider/stdout.stream-json`，并把 Provider stderr 保存到
`provider/stderr.log`。Runtime 与 Evolver 不对这些文件做脱敏、Event 筛选或文本
改写；Provider 输出的 Reasoning、Tool 参数与结果、Credential 或其他敏感字段因此会原样
保留。`events.jsonl` 只是额外的标准化 Usage 索引；`session.json` 记录终止状态以及原始
Provider 捕获是否避免了截断。配置的 stdout/stderr 限制仍是安全上限：超限会使 Session 失败并
标记原始流不完整，不会把截断内容静默宣称为完整。Provider 未输出的环境 Credential 不会被
主动复制。

## 5. Evolver 自进化

首版按部署 Git Commit 固定。未来可以增加提出新 Evolver Commit 的自进化层，但必须使用与 Optimizer
不同的评测和晋升策略；未晋升 Evolver 不能原地改写自身，也不能改变可信 Runtime 边界。
