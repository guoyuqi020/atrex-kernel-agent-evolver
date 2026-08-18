# Runtime 接入

[English](quickstart.md) | 中文

Bundle 不是独立 Campaign 工具。Runtime 创建 Workspace，并调用一次 Manifest 声明的入口。当前兼容
传输使用以下配置：

```json
{
  "agent_provider": "atrex-evolver-claude",
  "repository": "git@github.com:guoyuqi020/atrex-kernel-agent-evolver.git",
  "commit": "<完整 Evolver Commit SHA>",
  "git_executable": "/usr/bin/git",
  "fetch_timeout_seconds": 120,
  "max_archive_bytes": 16777216,
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

本地 Repository 与 Command Prefix 路径以 Runtime 配置文件为基准解析；生产环境应使用上面展示的
独立受控远端 Repository。Runtime 只 Fetch 配置的完整
Commit，拒绝 Link、Submodule 与不安全 Archive，把完整导出 Tree 封存进 Artifact Store，校验严格根
Manifest 与 Bundle 限制，再把 Manifest 持有的入口追加到 Command Prefix。派生内容 Digest 仍用于
完整性与 Provenance，但部署身份统一为 Git Commit。Claude Credential 只能通过 Runtime 显式继承
环境白名单传递。外层 Worker Timeout 必须大于 `atrex-evolver.json` 的
`agent_timeout_seconds`，使 Bundle 有机会先回收子进程。

缺少准确 Runtime Manifest、路径、Usage Report 目标或 Sentinel 时直接调用 `src/main.py` 必须失败关闭。

每次 Agent Session 启动后，`scratch/evolver-session/` 会在 `input/` 下保存未脱敏的最终
渲染 Prompt，在 `provider/` 下保存捕获的原始 Claude stdout/stderr，并使用
`events.jsonl` 和 `session.json` 保存标准化计量与完整性元数据。Runtime 会把整个
目录封存为 Session Artifact。

Runtime 不提供 `ATREX_TOKEN_BUDGET`。Usage Report 仍是必需协议，固定使用
`budget_tokens=null`、`budget_exhausted=false`；Provider 记账不完整时运行失败。
