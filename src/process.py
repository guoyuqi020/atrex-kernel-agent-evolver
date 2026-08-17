"""Bounded subprocess ownership for one Coding Agent session."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

READ_CHUNK_CHARS = 64 * 1024


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_overflow: bool
    externally_terminated: bool


def _terminate_group(process: subprocess.Popen[str], *, force: bool = False) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)


def run_bounded(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    max_stdout_chars: int,
    max_stderr_chars: int,
    stdout_observer: Callable[[str], bool],
) -> ProcessResult:
    """Run a child process group, relay outer termination, and bound captured output."""
    if not command:
        raise ValueError("Agent command cannot be empty")
    if timeout_seconds <= 0 or max_stdout_chars <= 0 or max_stderr_chars <= 0:
        raise ValueError("Agent process limits must be positive")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        _terminate_group(process, force=True)
        raise RuntimeError("Agent process pipes are unavailable")
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    stop_requested = threading.Event()
    overflow = threading.Event()
    externally_terminated = threading.Event()

    def read_stream(
        stream: TextIO,
        target: list[str],
        limit: int,
        observer: Callable[[str], bool] | None,
    ) -> None:
        captured = 0
        try:
            while True:
                chunk = stream.readline(READ_CHUNK_CHARS)
                if not chunk:
                    return
                remaining = limit - captured
                if remaining <= 0:
                    overflow.set()
                    stop_requested.set()
                    return
                target.append(chunk[:remaining])
                captured += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    overflow.set()
                    stop_requested.set()
                    return
                if observer is not None and observer(chunk):
                    stop_requested.set()
        finally:
            stream.close()

    stdout_thread = threading.Thread(
        target=read_stream,
        args=(process.stdout, stdout_parts, max_stdout_chars, stdout_observer),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=read_stream,
        args=(process.stderr, stderr_parts, max_stderr_chars, None),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    previous_handlers: dict[signal.Signals, Any] = {}

    def relay(signum: int, _frame: FrameType | None) -> None:
        externally_terminated.set()
        stop_requested.set()
        _terminate_group(process)

    handled_signals = (signal.Signals(signal.SIGTERM), signal.Signals(signal.SIGINT))
    for signum in handled_signals:
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, relay)

    timed_out = False
    terminated_at: float | None = None
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                timed_out = True
                stop_requested.set()
            if stop_requested.is_set():
                if terminated_at is None:
                    terminated_at = now
                    _terminate_group(process)
                elif now - terminated_at >= 5:
                    _terminate_group(process, force=True)
            time.sleep(0.05)
        returncode = process.wait()
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        if process.poll() is None:
            _terminate_group(process, force=True)
            process.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
    return ProcessResult(
        returncode=returncode,
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
        timed_out=timed_out,
        output_overflow=overflow.is_set(),
        externally_terminated=externally_terminated.is_set(),
    )
