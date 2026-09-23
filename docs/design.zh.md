# Evolver Bundle 设计

[English](design.md) | 中文

## 1. 角色与隔离

Evolver 是独立版本化的 Worker 实现，不是 Optimizer Candidate 内的组件。Runtime 在 Epoch
Checkpoint 完成后，于全新 Workspace 与进程中启动它，但首次调用后持续 resume 同一 Lineage/Backend
的原生对话。当轮 Evidence、Candidate、身份和报告上下文覆盖旧路径假设；上一轮 Candidate 修改和
任意 scratch 文件不会继承。Optimizer 永远拿不到 Evolver 仓库、配置、Prompt、
Trace、Credential 或进程状态。

Runtime 物化以下 Workspace：

```text
run-<uuid>/
├── input/
│   ├── agents/                # 每个可见 Agent 版本，各一处
│   │   └── agent-v<N>/
│   │       ├── src/ and configuration
│   │       └── {prompts,skills,tools}/
│   ├── evidence/              # 只读、已授权的运行 Evidence
│   │   ├── review/             # Runtime 派生的审计、对照与摩擦索引
│   │   └── agent-v<N>/
│   │       ├── resources/trajectories/trajectory-NNNNNNNN/
│   │       ├── optimization-summary.json
│   │       ├── sessions/      # 仅上一个已完成 Epoch 的双方分支
│   │       └── reports/       # 仅上一个已完成 Epoch 的双方分支
│   └── evolution-reports/     # 此前的 Agent 创建报告
├── candidate/                 # 可写 Agent Candidate
│   ├── src/ and configuration
│   └── {prompts,skills,tools}/
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

入口接受固定路径的 Evolution Manifest schema 11、唯一 Parent 和非空 `visible_agents` Catalog。
条目包含 Lineage 版本、Revision ID、Parent、创建者、关系类型、完整 Bundle 的 `path`、汇总路径、
可选 Session/Report 路径及 `resources_path`。关系为 `active`、`challenger`、
`current_epoch_challenger` 和 `lineage_history`。`parent: true` 是上一个完成 Epoch 的获胜者，
不一定是该 Epoch 的 Active 分支。

每个 `input/agents/agent-vN/` 都是完整只读 Bundle。Parent 将实现与获胜最佳 Kernel Trajectory 的
终态资源组合；缺失时回退到 Epoch 起始 State、Revision Seed 和打包默认内容。下一 Active 使用相同
起始资源。其他可见 Bundle 使用各自 Revision Seed。Runtime 将完整 Parent 复制到可写 `candidate/`，
直接包含实现与三个自适应目录，每个目录只有一份有效内容。

每个版本在 `input/evidence/agent-vN/` 下都有优化效果汇总；仅上一个完成 Epoch 的参赛者还暴露该
Epoch 的 Conversation 与 Attempt Report，按 Trajectory 分组。汇总将最近 Epoch 的正确、错误、无
Candidate Attempt 数及最佳正确 Kernel 的逐 Shape 权威 Gateway 结果，与累计参赛、胜、负次数分开。
`selection_reason` 描述最后一次两两选择，不代表多 Challenger 淘汰过程的每一步。
Bootstrap 与更早 Epoch 的 Conversation 保持私有。

`review/` 包含三个保守的 Runtime 投影：上一版 Evolution 的 Changed Path 审计、最近 Epoch 的跨
Trajectory 对照，以及 Workflow 摩擦索引。它们只记录可机械观察的发现、调用、失败、报告引用、准确
ID 重叠和归一化后的重复构造，是导航索引而不是因果或语义结论。Evolver 修改 Candidate 前，需要沿
重要条目检查对应 Session、Report、Direction、Experiment 和权威结果。

各 Trajectory 的补充学习资源位于
`input/evidence/agent-vN/resources/trajectories/trajectory-NNNNNNNN/`，供 Evolver 比较和融合合格
Agent 的 prompts、skills、tools。三目录必须维护随内容变化同步更新的 README。任务专属事实和搜索
结论只保留在 Runtime Journal 与 Report；静态且与任务无关的参考资料放在 Skill references 中。
Optimizer 只能修改 Tools。只有真实 Session 使用和结果表明某个 Tool 已形成可复用流程时，Evolver
才把它沉淀为 `skills/<name>/SKILL.md`，同时消除冗余副本并更新两个索引。Runtime 在下一次 Claude
Optimizer Session 启动前，把 Skill 目录安装到该 Session 的私有 CLI Home。

历史报告 `input/evolution-reports/evo-N.json` 用 `parent.path`、`generated_agent.path` 指向完整 Bundle；
`report.contributing_paths` 保留原始 Session 相对路径，不保证当前资源仍等于历史快照。报告是 Agent 的设计意图，不代表提案获胜；
完整 Evolution Trace 保持 Runtime 私有。

七字段 `EvolutionOutput` 包含 `proposal_type`、`kernel_agent_revision_id`、`hypothesis`、
`expected_effect`、`changed_paths`、`contributing_paths`、`unimplemented_capabilities`。

- `evolved`：修改已准备好的 Parent Bundle。
- `reuse`：选择合格历史版本原样复用，Candidate 不变，Changed Paths 为空。
- `evolve_from_history`：先用所选完整历史 Bundle 的可写副本替换 Candidate，再修改；Runtime 校验 Base。
- `no_change`：没有证据支持 Agent 可控改进时保持 Active 不变，Candidate 不变；Runtime 关闭剩余
  Challenger 名额，Epoch 仍正常执行。
- `changed_paths` 是相对于所选 Bundle 根目录的准确排序 Diff，包括三目录改动。新版本必须有真实变化。
- 贡献来源是实际吸收的 Bundle/Resources 路径，包括 Parent 其他 Trajectory。Runtime 封存准确内容；
  按可见范围与参赛资格校验，不按是否属于 Base 排除。
- 未实现能力说明具体需求、预期收益及无法实现的原因，不授予权限或选择优势。

持续维护 `scratch/evolution-report-draft.json`，通过
`python3 input/evolver/src/runtime_tools.py evolution-report --request scratch/evolution-report-draft.json`
提交。错误返回 `issues`、`request_schema` 和 `recovery`，不发布；首次成功原子生成
`scratch/evolution-report.json`。Runtime 独立校验完整 Bundle Diff，导入完整 Bundle 和三目录
Checkpoint。效果由下一 Epoch 评估，而非 Evolver 自测。Optimizer 的实现权限与继承规则不变。

`contributing_paths` 记录实际吸收内容的、排序且去重的 Workspace 相对文件或目录路径，允许
`input/agents/agent-vN/` 和 `input/evidence/agent-vN/resources/`，包括 Parent 其他 Trajectory 的资源。
仅阅读和自动继承 Parent 不算贡献。路径必须存在、无链接或越界，且属于合格已评估历史或 Parent，
不能引用同 Epoch 尚未评估的 Challenger。`reuse` 要求 `[]`。Runtime 在 Evolution Trace 中保存归属
和准确内容快照；该字段不改变 Bundle Base 或 Revision 祖先关系。

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
