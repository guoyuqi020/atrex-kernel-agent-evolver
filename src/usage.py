"""Claude stream token accounting and Runtime TokenUsageReportV1 production."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def _counter(value: Mapping[str, object], *names: str) -> int | None:
    for name in names:
        item = value.get(name)
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            return item
    return None


@dataclass(frozen=True)
class TokenUsage:
    """Four disjoint provider token buckets, possibly unavailable."""

    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None

    @property
    def total_tokens(self) -> int | None:
        values = (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        )
        if all(value is None for value in values):
            return None
        return sum(value or 0 for value in values)

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.cache_read_tokens,
                self.cache_write_tokens,
            )
        )

    @classmethod
    def unavailable(cls) -> TokenUsage:
        return cls(None, None, None, None)


def usage_from_mapping(value: object) -> TokenUsage:
    if not isinstance(value, Mapping):
        return TokenUsage.unavailable()
    return TokenUsage(
        input_tokens=_counter(value, "input_tokens", "inputTokens", "input"),
        output_tokens=_counter(value, "output_tokens", "outputTokens", "output"),
        cache_read_tokens=_counter(
            value,
            "cache_read_input_tokens",
            "cacheReadInputTokens",
            "cacheRead",
        ),
        cache_write_tokens=_counter(
            value,
            "cache_creation_input_tokens",
            "cacheCreationInputTokens",
            "cacheWrite",
        ),
    )


def sum_usages(values: Sequence[TokenUsage]) -> TokenUsage:
    observed = tuple(value for value in values if value.total_tokens is not None)
    if not observed:
        return TokenUsage.unavailable()

    def component(name: str) -> int | None:
        parts = [getattr(value, name) for value in observed]
        if any(part is None for part in parts):
            return None
        return sum(int(part) for part in parts if part is not None)

    return TokenUsage(
        input_tokens=component("input_tokens"),
        output_tokens=component("output_tokens"),
        cache_read_tokens=component("cache_read_tokens"),
        cache_write_tokens=component("cache_write_tokens"),
    )


def usage_from_model_usage(value: object) -> TokenUsage:
    if not isinstance(value, Mapping):
        return TokenUsage.unavailable()
    return sum_usages(tuple(usage_from_mapping(item) for item in value.values()))


class ClaudeUsageObserver:
    """Consume stream-json lines, deduplicate requests, and stop at the quota."""

    def __init__(self, budget_tokens: int) -> None:
        if budget_tokens <= 0:
            raise ValueError("token budget must be positive")
        self._budget = budget_tokens
        self._deltas: list[TokenUsage] = []
        self._terminal = TokenUsage.unavailable()
        self._seen_message_ids: set[str] = set()
        self._model_request_count = 0
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def observe(self, line: str) -> bool:
        """Record one stdout line and return whether the process must be stopped."""
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return self.exhausted
        if not isinstance(raw, Mapping):
            return self.exhausted
        with self._lock:
            if raw.get("type") == "result":
                terminal = usage_from_mapping(raw.get("usage"))
                if terminal.total_tokens is None:
                    terminal = usage_from_model_usage(raw.get("modelUsage"))
                if terminal.total_tokens is not None:
                    self._terminal = terminal
                    self._events.append(self._event("terminal_usage", terminal))
                return self._exhausted_unlocked()
            message = raw.get("message")
            usage: object = raw.get("usage")
            if usage is None and isinstance(message, Mapping):
                usage = message.get("usage")
            parsed = usage_from_mapping(usage)
            if parsed.total_tokens is None:
                return self._exhausted_unlocked()
            message_id = (
                message.get("id")
                if isinstance(message, Mapping) and isinstance(message.get("id"), str)
                else None
            )
            if message_id is not None and message_id in self._seen_message_ids:
                return self._exhausted_unlocked()
            if message_id is not None:
                self._seen_message_ids.add(message_id)
            self._deltas.append(parsed)
            self._model_request_count += 1
            self._events.append(self._event("usage_delta", parsed))
            return self._exhausted_unlocked()

    @staticmethod
    def _event(kind: str, usage: TokenUsage) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": kind,
            "usage": {
                "uncached_input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    def _current_unlocked(self) -> TokenUsage:
        return (
            self._terminal
            if self._terminal.total_tokens is not None
            else sum_usages(self._deltas)
        )

    def _exhausted_unlocked(self) -> bool:
        total = self._current_unlocked().total_tokens
        return total is not None and total >= self._budget

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self._exhausted_unlocked()

    @property
    def usage(self) -> TokenUsage:
        with self._lock:
            return self._current_unlocked()

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple({**event, "sequence": index} for index, event in enumerate(self._events))

    def report(self, *, session_started: bool) -> dict[str, Any]:
        with self._lock:
            usage = self._current_unlocked()
            buckets = {
                "uncached_input_tokens": usage.input_tokens or 0,
                "output_tokens": usage.output_tokens or 0,
                "cache_read_tokens": usage.cache_read_tokens or 0,
                "cache_write_tokens": usage.cache_write_tokens or 0,
            }
            total = sum(buckets.values())
            return {
                "schema_version": 1,
                "budget_tokens": self._budget,
                "usage": buckets,
                "total_tokens": total,
                "budget_exhausted": total >= self._budget,
                "session_count": 1 if session_started else 0,
                "model_request_count": max(
                    self._model_request_count,
                    1 if self._terminal.total_tokens is not None else 0,
                ),
                "usage_complete": usage.complete,
            }
