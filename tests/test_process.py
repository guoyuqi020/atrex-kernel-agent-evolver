from __future__ import annotations

import sys
import time
from pathlib import Path

from process import run_bounded


def test_output_overflow_terminates_agent_process_group(tmp_path: Path) -> None:
    result = run_bounded(
        [sys.executable, "-c", "import time; print('x' * 4096, flush=True); time.sleep(30)"],
        cwd=tmp_path,
        environment={},
        timeout_seconds=10,
        max_stdout_chars=128,
        max_stderr_chars=128,
        stdout_observer=lambda _line: False,
    )

    assert result.output_overflow is True
    assert len(result.stdout) == 128
    assert result.returncode != 0


def test_timeout_terminates_agent_process_group(tmp_path: Path) -> None:
    started = time.monotonic()
    result = run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        environment={},
        timeout_seconds=1,
        max_stdout_chars=128,
        max_stderr_chars=128,
        stdout_observer=lambda _line: False,
    )

    assert result.timed_out is True
    assert result.returncode != 0
    assert time.monotonic() - started < 5
