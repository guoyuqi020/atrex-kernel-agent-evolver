# Runtime 接入

[English](quickstart.md) | 中文

Bundle 不是独立 Campaign 工具。Runtime 创建 Workspace，并调用一次 Manifest 声明的入口。当前兼容
传输使用以下配置：

```json
{
  "agent_backend": "claude",
  "reasoning_effort": "max",
  "session_settings": "",
  "repository": "git@github.com:guoyuqi020/atrex-kernel-agent-evolver.git",
  "commit": "<完整 Evolver Commit SHA>",
  "git_executable": "/usr/bin/git",
  "fetch_timeout_seconds": 120,
  "max_archive_bytes": 16777216,
  "command_prefix": [".venv/bin/python"],
  "max_bundle_files": 1024,
  "max_bundle_bytes": 8388608,
  "environment": {
    "values": {},
    "inherit": ["PATH"],
    "inherit_optional": ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CODEX_HOME"]
  },
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json",
  "timeout_seconds": 1800,
  "terminate_grace_seconds": 10,
  "max_diagnostic_bytes": 131072,
  "max_output_manifest_bytes": 16384
}
```

本地 Repository 与 Command Prefix 路径以 Runtime 配置文件为基准解析；生产环境应使用上面展示的
独立受控远端 Repository。Runtime 只 Fetch 配置的完整
Commit，拒绝 Link、Submodule 与不安全 Archive，把完整导出 Tree 封存进 Artifact Store，校验严格根
Manifest 与 Bundle 限制，再把 Manifest 持有的入口追加到 Command Prefix。派生内容 Digest 仍用于
完整性与 Provenance，但部署身份统一为 Git Commit。所选 Backend 的 Credential 只能通过 Runtime 显式继承
环境白名单传递。外层 Worker Timeout 必须大于 `atrex-evolver.json` 的
`agent_timeout_seconds`，使 Bundle 有机会先回收子进程。

Runtime 绑定 Backend、Lineage 所选 Model、Reasoning Effort 与 Backend-specific Session
Settings；空 Model 表示使用 Backend CLI 默认值。Evolver 仓库持有
Adapter 实现和版本化 Prompt。
缺少准确 Runtime Manifest、路径、Usage Report 目标或 Sentinel 时直接调用 `src/main.py` 必须失败关闭。

每次 Agent Session 都会在 Provider 启动前创建 `scratch/evolver-session/`。运行期间可以
实时查看未脱敏 Prompt、保留的 Provider stdout/stderr 和持续追加的 `conversation.jsonl`；
此时 `session.json` 为 `state: running`，`.runtime-live-session` 表示尚未封存或已被中断。
正常退出后 Bundle 会用保留事件 Transcript、标准化 `events.jsonl` 和最终 `session.json` 替换
实时投影，再由 Runtime 把整个目录封存为 Session Artifact。可捕获异常会保留已有的部分
Transcript，并标记为 `state: interrupted`。高频 Claude `system/thinking_tokens` 估算事件会被
省略，并在 `session.json.provider_event_filters` 中声明。

渲染后的 Session Context 会列出全部授权 Agent Repository、优化汇总、Session 目录和 Runtime State
目录，Evolver 直接读取这些不可变文件。可写的 `candidate/source/` 初始镜像 Active Source；
`candidate/runtime-state/{skills,tools}/` 初始取最近完成 Epoch 的获胜分支中、产出最佳 Kernel 的
Trajectory 在该 Epoch 最后一个 Attempt 结束后的终态 State；下一 Epoch 的 Active Branch 使用完全
相同的 State 种子。缺失终态检查点时，依次回退到该 Trajectory 的 Epoch 起始 State、Revision Seed
和空默认值。
选择 `evolve_from_history` 时，
Evolver 用所选历史 Agent 的 Source 替换 Candidate Source，并可从可见历史 Trajectory 中整理公共
种子；Runtime 独立验证 Base 和 Source/State 的真实 Diff，并把两个组件封存为一个逻辑 Agent Bundle。

持续维护 `scratch/evolution-report-draft.json`，然后调用：

```bash
python3 input/evolver/src/runtime_tools.py evolution-report \
  --request scratch/evolution-report-draft.json
```

失败时根据返回的 `issues`、`request_schema` 与 `recovery` 修正 Draft 后重试。第一次成功调用会发布
`scratch/evolution-report.json`；成功后不要再次调用。

Runtime 不提供 Usage 配额。Schema v2 Usage Report 仍是必需协议，固定使用 `budget=null`、
`budget_exhausted=false`。QoderCLI 记录 Credit，Claude、Codex 与 Pi 记录 Provider Token；
所选 Provider 原生单位的记账不完整时运行失败。
