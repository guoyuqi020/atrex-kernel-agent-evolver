from __future__ import annotations

import json

from usage import ClaudeUsageObserver


def _message(identifier: str, total: int) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": identifier,
                "usage": {
                    "input_tokens": total - 3,
                    "output_tokens": 3,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }
    )


def test_observer_deduplicates_messages_without_enforcing_a_budget() -> None:
    observer = ClaudeUsageObserver()

    assert observer.observe(_message("one", 6)) is False
    assert observer.observe(_message("one", 6)) is False
    assert observer.observe(_message("two", 5)) is False

    report = observer.report(session_started=True)
    assert report["total_tokens"] == 11
    assert report["budget_tokens"] is None
    assert report["budget_exhausted"] is False
    assert report["model_request_count"] == 2
    assert report["usage_complete"] is True


def test_terminal_usage_replaces_stream_delta_sum() -> None:
    observer = ClaudeUsageObserver()
    observer.observe(_message("one", 6))
    observer.observe(
        json.dumps(
            {
                "type": "result",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 1,
                },
            }
        )
    )

    assert observer.report(session_started=True)["total_tokens"] == 28
