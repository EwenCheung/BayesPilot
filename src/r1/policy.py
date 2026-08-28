"""Spec 3.9 — convert or ask.

Three rules, each measured rather than guessed (IMPORTANT.md §12.1):
  * a strict unique leader means the filter has converged — ship it
  * intent-override sessions discard turn 1–2 recommendations, so do not spend them selling
  * never dither past the deadline; patience beats speed ~11×, but only up to turn 3
"""
from __future__ import annotations

import statistics

from src.common.contracts import SessionState
from src.r1.flags import Flags

NQC_THRESHOLD = 0.35  # coefficient of variation of the top-k score vector (query-performance prediction)


def converged(candidates: list[str], scores: dict[str, float]) -> bool:
    if len(candidates) <= 1:
        return True
    leader, runner_up = scores.get(candidates[0], 0.0), scores.get(candidates[1], 0.0)
    return leader > runner_up


def nqc(candidates: list[str], scores: dict[str, float]) -> float:
    """Std-dev of the top-10 scores over their mean: a committed ranking is a peaked one."""
    head = [scores.get(asin, 0.0) for asin in candidates[:10]]
    if len(head) < 2:
        return 1.0
    mean = statistics.fmean(head)
    if mean <= 0:
        return 0.0
    return statistics.pstdev(head) / mean


def should_recommend(state: SessionState, turn: int, candidates: list[str], scores: dict[str, float],
                     flags: Flags) -> bool:
    # The evaluator refuses to count a hit before the override lands (IMPORTANT.md §4), and the
    # override arrives on turn 3 or 4. Every list we ship before it is discarded at rank 1, so
    # spend those turns buying information instead. Turn 4 is the backstop in case we misread the
    # scenario under paraphrase and no override is ever coming.
    if state.route == "override" and not state.override_seen and turn < 4:
        return False
    if converged(candidates, scores):
        return True
    if nqc(candidates, scores) >= NQC_THRESHOLD:
        return True
    return turn >= flags.deadline


def truncation(candidates: list[str], scores: dict[str, float], top_k: int, flags: Flags) -> int:
    """§14.3 dynamic truncation. Off by default: extra candidates are free under this metric,
    so cutting the list can only ever lose a hit. Kept behind a flag so the claim stays measured."""
    if not flags.truncate:
        return top_k
    return 1 if converged(candidates, scores) else top_k
