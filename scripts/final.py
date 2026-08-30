"""Compatibility entry point for the locked deterministic evaluation.

Running this file evaluates test only. Public requires the explicit final-only command:

    python scripts/evaluate_locked.py --acknowledge-golden-final
"""
from scripts.evaluate_locked import main


if __name__ == "__main__":
    main()
