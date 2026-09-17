"""Resuming a rollout does not rebill its earlier token_count events."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backends.codex_ledger import CodexSessionLedgerObserver, observe_codex_usage
from backends.model import TokenUsage

THREAD = "01234567-89ab-cdef-0123-456789abcdef"


def _count(total_input: int, total_output: int) -> str:
    return (
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {"input_tokens": 10, "output_tokens": 2},
                        "total_token_usage": {
                            "input_tokens": total_input,
                            "output_tokens": total_output,
                        },
                    },
                },
            }
        )
        + "\n"
    )


@pytest.mark.parametrize("stream_cumulative", (False, True))
def test_resume_reports_only_this_invocations_usage_and_raw_content(
    tmp_path: Path,
    stream_cumulative: bool,
) -> None:
    path = tmp_path / "sessions" / f"rollout-{THREAD}.jsonl"
    path.parent.mkdir()
    path.write_text(_count(10, 2))
    observer = CodexSessionLedgerObserver(tmp_path)
    observer.begin_resume(THREAD)
    new_content = _count(20, 4)
    with path.open("a") as output:
        output.write(new_content)
    terminal = (
        TokenUsage(20, 4, 0, 0, 24, "exact")
        if stream_cumulative
        else TokenUsage(10, 2, 0, 0, 12, "exact")
    )
    events, usage, _capabilities, errors = observe_codex_usage(observer, THREAD, terminal)
    assert usage == TokenUsage(10, 2, 0, 0, 12, "exact")
    assert len(events) == 2 and not errors
    assert observer.capture_raw_rollout(THREAD, max_bytes=10000).decode() == new_content
