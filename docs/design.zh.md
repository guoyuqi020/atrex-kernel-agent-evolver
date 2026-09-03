# Evolver Bundle 设计

[English](design.md) | 中文

## 1. 角色与隔离

Evolver 是独立版本化的 Worker 实现，不是 Optimizer Candidate 内的组件。Runtime 在 Epoch
Checkpoint 完成后，于全新 Workspace 与进程中启动它。Optimizer 永远拿不到 Evolver 仓库、配置、Prompt、
Trace、Credential 或进程状态。

Runtime 物化以下 Workspace：

```text
run-<uuid>/
├── input/
│   ├── agents/                # 每个可见 Agent 版本，各一处
│   │   └── agent-v<N>/
│   │       ├── source/        # 精确版本化 Agent 仓库
│   │       └── runtime-state/ # 各 Trajectory 的 skills/tools
│   ├── evidence/              # 只读、已授权的运行 Evidence
│   │   └── agent-v<N>/
│   │       ├── optimization-summary.json
│   │       ├── sessions/      # 仅上一个已完成 Epoch 的双方分支
│   │       └── reports/       # 仅上一个已完成 Epoch 的双方分支
│   └── evolution-reports/     # 此前的 Agent 创建报告
├── candidate/                 # 可写 Agent Candidate
│   ├── source/                # 完整版本化 Bundle
│   └── runtime-state/         # 唯一一份公共 {skills,tools} 种子
└── scratch/                   # 可写 Report、Trace 与隔离 Agent 状态
```

Runtime 路径校验与进程 Capability 是当前可信边界，Prompt 指令只是纵深防御。Evolver 不获得
Runtime Gateway/Wiki Capability，也不能评测 GPU Kernel。OS Sandbox 明确推迟；在实现它之前，
不能把恶意 Agent 代码视为已被隔离。

Evolution Manifest 与 Evidence Prompt 通过内存传给外层 Bundle 进程，不会物化到 Agent 可见
Workspace。Evolver 不获得 Runtime HTTP Capability；全部授权输入都是 `input/` 下已经存在的不可变文件。

## 2. 版本化行为

完整 Git Commit 是部署行为身份，与 Optimizer Base 约定一致。Runtime 只 Fetch 该 Commit，校验 Git
Tree，安全导出并在启动前把整个 Snapshot 封存进内容寻址存储。`atrex-evolver-bundle.json` 声明唯一
入口；Runtime 还会派生整树内容 Digest 用于完整性与 Provenance。Link、Submodule、特殊文件、不安全
Archive 或超限都会被拒绝。部署后续可以固定另一个 Commit，但运行中的 Epoch 永远不能修改本仓库。

固定 stdin Sentinel 在兼容当前 Runtime 进程传输的同时，防止部署配置静默替换版本化 Prompt。

## 3. 输入与输出

入口只接受字段和路径映射完全匹配的 Evolution Manifest Schema 11。Manifest 必须标出恰好一个
Parent，并提供非空、无重复的 `visible_agents` Catalog。Runtime 会加入已保留的 Lineage Agent
历史，以及当前 Epoch 中此前已创建的 Challenger；每条 Catalog 条目提供其 Lineage 版本、Parent Link、
创建者、`relationship`（`active`、`challenger`、`current_epoch_challenger` 或 `lineage_history`）以及
适用时的 Challenger Ordinal。每个可见 Revision 只按版本落在一处：
`input/agents/agent-vN/` 存放其封存 Source 与逐 Trajectory Runtime State，
`input/evidence/agent-vN/` 存放 Runtime 对它的派生结论；任何目录名都不再编码 Epoch 角色。
每个版本都有优化效果汇总；只有在最近一个已完成 Epoch 中参赛的全部分支还额外拥有 `sessions/` 与
`reports/`，且都取自同一个 Epoch，因此可以直接对比。Parent 是带 `parent` 标记的那一项，也就是该
Epoch 的获胜方。每份汇总都写明该 Revision 的 `branch` 与 `outcome`；其中 `selection_reason` 记录最后一次
两两选择步骤，而不是多 Challenger 淘汰过程中的全部比较，因此不能把它当成每个失败 Revision 各自的
失败原因。Conversation 与 Attempt Report 均按
Trajectory 组织；Bootstrap 与更早 Epoch 的 Conversation 仍属于 Runtime 私有历史，当前 Epoch 的
Challenger 因尚未运行任何 Attempt 而两者皆无。可用的历史 Agent
创建 `EvolutionOutput` 投影成有序的 `input/evolution-reports/evo-N.json` Wrapper，其中关联 Source Base、
产出 Agent 以及各自在本 Workspace 的 Source/Runtime State 路径；完整 Evolution Trace 保持私有。各
Trajectory 持久积累的自适应 `skills/` 与 `tools/` 位于该版本源码旁边的
`runtime-state/` 下，把精确源码、累计优化效果与运行时状态放在一起。这些内容是非版本化
Lineage 状态，也是唯一的自适应 Skill/Tool 存储。根级 `skills/` 和 `tools/` 在版本化 Source 中
无效。Evolver 可以直接整理 `candidate/runtime-state/`，也可以修改控制未来如何使用状态的 Source
机制。Runtime 始终分别封存 Candidate Source 与 State，并把两者组合为同一个不可变 Agent Bundle；
后续每条新 Trajectory 都从这个 Bundle 的 State 初始化。State 是否相对输入发生修改不影响封存。
Catalog
同时明确提供 Parent Link、创建者、关系类型以及适用时的
Challenger Ordinal。
每份优化效果汇总将该 Agent Revision 最近一次完成的 Epoch 与累计战绩分开。最近 Epoch 部分统计
正确 Kernel、错误 Kernel 和未产出 Candidate Kernel 的 Attempt 数，并内嵌最佳正确 Kernel 的
权威 Gateway 逐 Shape 投影；累计部分统计已完成 Epoch 的参赛、获胜和失败次数。
Runtime 从匹配的不可变 Lineage Checkpoint 派生这份紧凑视图，不暴露 Agent-facing `epochs/` 目录，也不在
Evolution Workspace 中重复保存详细历史。
入口把环境路径绑定到
Manifest，并拒绝 Link 与越界路径。Usage Report 目标是必需输入，但不接受 Token Budget。

`Parent` 只是一种角色，不是另一份仓库或目录。它就是带 `parent` 标记的那个可见 Agent，和其他每个版本
一样只在 `input/agents/agent-vN/` 保存一次；Runtime 把其 Source，以及最近完成 Epoch 获胜分支中产出最佳
Kernel 的 Trajectory 在该 Epoch 最后一个 Attempt 后的终态 State 复制到 Candidate；下一 Epoch 的
Active Branch 使用相同 State 种子。缺失终态时依次回退到该 Trajectory 的 Epoch 起始 State、
Revision Seed 和空默认值。对于
`evolve_from_history`，Evolver 替换 Source，并可从可见历史
Trajectory 中整理公共种子。终态输出只声明 `kernel_agent_revision_id`；Runtime 以该 Revision 的 Source
作为提案参考并验证其身份，
Runtime State 身份仍作为私有控制数据，并跨不可变 Source
与初始 Active State 计算真实 Diff。每个新 Revision 都把两个组件封存为一个逻辑 Agent Bundle。不需要也不
信任任何 Candidate 控制工具或旁路 Base 记录。

Evidence 结构 Prompt Fragment 由 Runtime 源码模板生成，通过内存传入外层 Bundle 后拼入最终 Prompt。

Coding Agent 输出统一格式的 `EvolutionOutput`。所有模式都使用 `kernel_agent_revision_id`、
`changed_paths` 与 `contributing_revision_ids`；`changed_paths` 只报告相对于 Source 根目录的排序路径。
复用要求空数组，仅修改 State 的新
Revision 也可以报告空数组。它可以从 Active 派生新 Revision、原样复用
一个可见历史 Revision，或从一个可见历史 Revision 派生新 Revision。创建新 Revision 的提案包含
相对于所选 Source Base 的准确排序 Changed Paths；Runtime 私下计算 State 修改。Candidate 也可以融合
多个可见 Agent 的内容；`contributing_revision_ids` 列出除 Source Base 以外所有被取用过 Source、Skill
或 Tool 的 Revision，且只能是已完成的 Lineage 历史或 Active。这是来源记录而非祖先关系：Source Base
与 Diff 目标仍是唯一那个声明的 Revision。每种
模式都可以包含有界、结构化的
`unimplemented_capabilities`，记录所需能力、预期 Kernel 优化收益以及本次无法实现的具体原因。
Runtime 会把这些不可信建议保留在 Evolution Evidence 中，供后续 Evolver 查看；它们不会授予
额外权限，也不参与胜负选择。Runtime 仍是权威方：它校验冻结可见范围，随后独立 Hash Base 与
Candidate，校验真实修改集合和
Bundle Policy，封存逐 Epoch 提案来源，再运行配置的
Active/Challenger Pool 评估。Revision 父子关系仍是树；复用和晋升是参赛事件，不是祖先边。

Agent 持续维护 `scratch/evolution-report-draft.json`，并调用只读 Bundle 中固定的
`python3 input/evolver/src/runtime_tools.py evolution-report --request
scratch/evolution-report-draft.json`。调用失败不会发布内容，而是返回 `issues`、准确的
`request_schema` 和有界 `recovery` 指令；Agent 可修改并重试。第一次成功调用会原子发布
`scratch/evolution-report.json`，之后再次调用会被拒绝。工具检查真实 Source Diff 与私有初始 State
快照；Coding Agent 退出后，外层 Bundle 和 Runtime 会再次独立校验。

## 4. Token 与进程所有权

Claude、Codex、QoderCLI 与 Pi 使用各自的非交互命令/Stream Adapter，并统一为一个 Session
Result。Claude/Qoder 解析 stream-json，Pi 聚合已 Settled 的 Message/Compaction Usage，Codex
观察隔离 Session Ledger 并捕获原始 Rollout。所有 Adapter 对未缓存输入、输出、Cache Read、
Cache Write 各计一次。Token 数永远不会终止子进程；外层
SIGTERM/SIGINT 会转发给该进程组，Timeout 与 stdout/stderr 均受限。Report 使用空 Budget，已完成
模型请求若缺少完整 Provider Bucket 时失败关闭。

Session Artifact 把最终渲染 Prompt 原样保存到 `input/prompt.md`，把捕获的 Provider Stream
保存到 `provider/stdout.stream-json`，并把 Provider stderr 保存到
`provider/stderr.log`。封存后的 `conversation.jsonl` 是阅读视图：Claude 优先使用原生内容，省去已被完整覆盖的 stdout 消息副本，保留不同的 thinking/text/tool 内容块、未被覆盖的 stdout 内容、诊断、压缩边界和终态结果。重复的初始 Prompt，以及原生队列、标题、文件历史等内部管理事件只从阅读视图中省去。封存前的实时视图仍跟随 stdout。原始 Provider 文件及规范化 usage 索引不变。CLI 未导出的 Provider 内置 System Prompt 会被
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
