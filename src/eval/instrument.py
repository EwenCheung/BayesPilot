"""⚠️ OFFLINE ONLY. The agent must never import this module — `tests/test_r4_isolation.py` enforces it.

The road's headline instrument. `MTTC` says when the agent *shipped* the target; `FirstHit@k` says
when it *knew*. The gap between them is the Efficiency a better stopping rule could recover, and it is
the only honest way to size Phase C before building it.

⚠️ **The distinction is load-bearing and easy to lose.** The evaluator does
`if override_applied and target in ranked: break`, so a shipped target's rank never evolves across
turns — computed from shipped lists, `FirstHit@k` is definitionally MTTC and measures nothing. It has
to come from the agent's *internal* ranking, captured **before** the ship/hold decision, including on
turns where the agent ships nothing at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnTrace:
    turn: int
    internal_ranking: list[str]      # full internal order, BEFORE the ship/hold decision
    shipped: list[str]               # what actually went to the evaluator ([] when it held)
    depth: int
    stalls: int
    entropy: float


@dataclass
class SessionTrace:
    session_id: str
    turns: list[TurnTrace] = field(default_factory=list)

    def first_hit(self, target: str, k: int) -> int | None:
        """Earliest turn whose INTERNAL top-k contained the target."""
        for trace in self.turns:
            if target in trace.internal_ranking[:k]:
                return trace.turn
        return None

    def first_shipped(self, target: str) -> int | None:
        """Earliest turn the target was actually shipped — this is what MTTC records."""
        for trace in self.turns:
            if target in trace.shipped:
                return trace.turn
        return None


class Recorder:
    """Collects traces from an instrumented agent. Lives in the harness, never in the agent."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionTrace] = {}

    def record(self, session_id: str, trace: TurnTrace) -> None:
        self.sessions.setdefault(session_id, SessionTrace(session_id)).turns.append(trace)


def early_hit_curve(recorder: Recorder, targets: dict[str, str], k: int,
                    max_turn: int = 10) -> list[float]:
    """`EarlyHit@k(T)` for T = 1..max_turn: share of sessions whose internal top-k held the target
    by turn T. `targets` maps session_id -> ground-truth ASIN; offline only, obviously."""
    n = len(recorder.sessions)
    if not n:
        return [0.0] * max_turn
    firsts = [recorder.sessions[s].first_hit(targets[s], k) for s in recorder.sessions]
    return [sum(1 for f in firsts if f is not None and f <= t) / n for t in range(1, max_turn + 1)]


def shipped_curve(recorder: Recorder, targets: dict[str, str], max_turn: int = 10) -> list[float]:
    """The same curve for what was actually shipped — the ceiling EarlyHit must beat."""
    n = len(recorder.sessions)
    if not n:
        return [0.0] * max_turn
    firsts = [recorder.sessions[s].first_shipped(targets[s]) for s in recorder.sessions]
    return [sum(1 for f in firsts if f is not None and f <= t) / n for t in range(1, max_turn + 1)]
