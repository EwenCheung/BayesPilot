"""Submission entry point: `from agent import Agent`.

`local_evaluator.py` constructs `Agent(args.catalog)` positionally, with no keyword arguments and no
environment. Everything the graded configuration needs is therefore a default in
`src/copilot/flags.py` — nothing here reads `os.environ` to reach the measured setup.

    python3 scripts/evaluation/evaluate.py          # reproduce the public-set result
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.copilot.agent import Agent  # noqa: E402,F401

__all__ = ["Agent"]
