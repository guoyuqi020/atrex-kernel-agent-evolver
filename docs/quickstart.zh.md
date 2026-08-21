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

每次 Agent Session 启动后，`scratch/evolver-session/` 会在 `input/` 下保存未脱敏的最终
渲染 Prompt，在 `provider/` 下保存捕获的原始 Provider stdout/stderr，并使用
`conversation.jsonl` 保存完整可观测 Transcript，使用 `events.jsonl` 和 `session.json` 保存
标准化计量与完整性元数据。Runtime 会把整个
目录封存为 Session Artifact。

渲染后的 Session Context 包含 Runtime 注入检索 Client 的精确 Python 命令。在 Evolution
Workspace 中可追加以下子命令：

```bash
<injected-python> runtime-tools/evolver_tools.py history
<injected-python> runtime-tools/evolver_tools.py branches --epoch 1
<injected-python> runtime-tools/evolver_tools.py attempts --epoch 1 --branch challenger-0001
<injected-python> runtime-tools/evolver_tools.py kernels
<injected-python> runtime-tools/evolver_tools.py kernel-read --revision kernelrev_<id>
<injected-python> runtime-tools/evolver_tools.py agents
<injected-python> runtime-tools/evolver_tools.py agent-diff --base agentrev_<id> --candidate agentrev_<id>
<injected-python> runtime-tools/evolver_tools.py trace-paths --epoch 1
<injected-python> runtime-tools/evolver_tools.py candidate-reset --base agentrev_<historical-id>
```

所有命令只使用冻结的本地快照并返回 JSON，不联系 Runtime 服务。`candidate-reset` 是唯一写操作：
选择 `evolve_from_history` 时必须调用；它只接受已完成的 Lineage 历史，只原子替换
`candidate/`，并记录其 Base。

Runtime 不提供 Usage 配额。Schema v2 Usage Report 仍是必需协议，固定使用 `budget=null`、
`budget_exhausted=false`。QoderCLI 记录 Credit，Claude、Codex 与 Pi 记录 Provider Token；
所选 Provider 原生单位的记账不完整时运行失败。
