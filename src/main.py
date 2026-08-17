#!/usr/bin/env python3
"""Execute exactly one Runtime-authored Evolution session."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config import EvolverConfig
from context import EvolutionContext, validate_launch_input
from session import execute, safe_error


def run() -> int:
    repository = Path(__file__).resolve().parents[1]
    validate_launch_input(sys.stdin.read())
    config = EvolverConfig.load(repository)
    context = EvolutionContext.load()
    return execute(context, config)


def main() -> int:
    try:
        return run()
    except BaseException as error:
        print(json.dumps(safe_error(error), sort_keys=True), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
