# Runtime 接入

[English](quickstart.md) | 中文

Bundle 不是独立 Campaign 工具。Runtime 创建 Workspace，并调用一次 Manifest 声明的入口。当前兼容
传输使用以下配置：

```json
{
  "agent_provider": "atrex-evolver-claude",
  "agent_version": "<固定 Evolver Commit>",
  "model": "claude-default",
  "command_argv": ["../src/atrex-kernel-agent-evolver/src/main.py"],
  "prompt": "Run the versioned Evolver Bundle once.",
  "prompt_transport": "stdin",
  "isolated_home_environment_keys": ["HOME"],
  "session_trace_relative_path": "scratch/evolver-session",
  "token_usage_report_relative_path": "scratch/token-usage.json"
}
```

命令路径以 Runtime 配置文件为基准解析。生产环境应只读挂载固定 Evolver Checkout，并使用其绝对
入口路径。Claude Credential 只能通过 Runtime 显式继承环境白名单传递。外层 Worker Timeout 必须
大于 `atrex-evolver.json` 的 `agent_timeout_seconds`，使 Bundle 有机会先回收子进程。

缺少准确 Runtime Manifest、路径、配额或 Sentinel 时直接调用 `src/main.py` 必须失败关闭。

每次 Agent Session 启动后，`scratch/evolver-session/` 会在 `input/` 下保存未脱敏的最终
渲染 Prompt，在 `provider/` 下保存捕获的原始 Claude stdout/stderr，并使用
`events.jsonl` 和 `session.json` 保存标准化计量与完整性元数据。Runtime 会把整个
目录封存为 Session Artifact。
