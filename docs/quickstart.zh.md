# Runtime 接入

[English](quickstart.md) | 中文

Bundle 不是独立 Campaign 工具。Runtime 创建 Workspace，并调用一次 Manifest 声明的入口。当前兼容
传输使用以下配置：

```json
{
  "agent_provider": "atrex-evolver-claude",
  "bundle_root": "../src/atrex-kernel-agent-evolver",
  "bundle_sha256": "<规范 Bundle SHA-256>",
  "command_prefix": ["../.venv/bin/python"],
  "max_bundle_files": 1024,
  "max_bundle_bytes": 8388608,
  "model": "claude-default",
  "prompt": "Run the versioned Evolver Bundle once.",
  "prompt_transport": "stdin",
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json"
}
```

每次有意修改 Bundle 后生成新 Digest：

```bash
atrex-kernel-agent-runtime digest-evolver-bundle \
  --path src/atrex-kernel-agent-evolver
```

Bundle 与 Command Prefix 路径以 Runtime 配置文件为基准解析。Runtime 会校验严格根 Manifest，拒绝
Link 与特殊文件，对全部影响行为的普通文件做 Hash，在启动前比较 Digest，并把 Manifest 持有的入口
追加到 Command Prefix。Claude Credential 只能通过 Runtime 显式继承环境白名单传递。外层 Worker
Timeout 必须大于 `atrex-evolver.json` 的 `agent_timeout_seconds`，使 Bundle 有机会先回收子进程。

缺少准确 Runtime Manifest、路径、配额或 Sentinel 时直接调用 `src/main.py` 必须失败关闭。

每次 Agent Session 启动后，`scratch/evolver-session/` 会在 `input/` 下保存未脱敏的最终
渲染 Prompt，在 `provider/` 下保存捕获的原始 Claude stdout/stderr，并使用
`events.jsonl` 和 `session.json` 保存标准化计量与完整性元数据。Runtime 会把整个
目录封存为 Session Artifact。
