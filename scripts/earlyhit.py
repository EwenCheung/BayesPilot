"""R4-A7 / R4-A8 — the EarlyHit curve, and the gap that sizes the rest of the road.

    python3 scripts/earlyhit.py [n_sessions]

Runs on `train.jsonl` only. `MTTC` records when the agent SHIPPED the target; `EarlyHit@k` records
when its internal ranking first CONTAINED it. The area between the two curves is the Efficiency a
better stopping rule could still recover — and if it is small, Phase C is not worth building.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("R3_OFFLINE", "1")

from src.eval import datasets, harness  # noqa: E402
from src.copilot.agent import Agent as R4Agent  # noqa: E402
from src.eval.instrument import Recorder, TurnTrace, early_hit_curve, shipped_curve  # noqa: E402


class Instrumented(R4Agent):
    """Offline probe. Reads the agent's own state; the agent knows nothing about it."""

    def __init__(self, catalog_path, recorder: Recorder) -> None:
        super().__init__(catalog_path)
        self.recorder = recorder

    def _respond(self, session_id, user_message, turn, top_k):
        out = super()._respond(session_id, user_message, turn, top_k)
        shipped = [r["parent_asin"] for r in out["recommendations"]]
        self.recorder.record(session_id, TurnTrace(
            turn=turn,
            internal_ranking=list(self._last_internal[:64]),
            shipped=shipped,
            depth=len(shipped),
            stalls=self._stalls.get(session_id, 0),
            entropy=0.0,
        ))
        return out


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    flags = os.environ.get("R4_FLAGS", "exclude_shipped")
    os.environ["R4_FLAGS"] = flags
    sessions = datasets.fitting(n)

    harness.DATASET = datasets.TRAIN
    harness.load_world()
    harness._CACHE["world"] = (sessions,) + harness.load_world()[1:]

    recorder = Recorder()
    agent = Instrumented(str(harness.CATALOG), recorder)
    result = harness.run(agent)

    # The evaluator mints a fresh uuid per session and walks `samples` in order, so the recorder's
    # insertion order is sample order. Asserted rather than assumed.
    assert len(recorder.sessions) == len(sessions), "a session produced no turns"
    targets = {sid: s["ground_truth"]["parent_asin"]
               for sid, s in zip(recorder.sessions, sessions)}

    print(f"train.jsonl[:{n}]   flags={flags!r}   score {harness.score(result):.4f}\n")
    header = "  " + "".join(f"{t:>7d}" for t in range(1, 11))
    print(f"{'turn':<18s}{header}")
    for k in (1, 3, 10):
        curve = early_hit_curve(recorder, targets, k)
        print(f"{'EarlyHit@' + str(k):<18s}  " + "".join(f"{v:>7.3f}" for v in curve))
    ship = shipped_curve(recorder, targets)
    print(f"{'shipped (MTTC)':<18s}  " + "".join(f"{v:>7.3f}" for v in ship))

    e1 = early_hit_curve(recorder, targets, 1)
    e3 = early_hit_curve(recorder, targets, 3)
    print(f"\n{'gap @3 (knew - shipped)':<18s}" + "".join(f"{a - b:>7.3f}" for a, b in zip(e3, ship)))

    # ---- R4-A8: what a PERFECT stopping rule is worth -------------------------------------------
    # The raw gap conflates waste with justified patience: holding a rank-3 list for one turn to ship
    # it at rank 1 is correct (RR 0.333 -> 1.000 costs 0.02 of efficiency and gains 0.20 of MRR).
    # The honest bound is an ORACLE that ships the instant the target reaches internal rank 1 — it
    # cannot improve MRR (already 1.0 there) and cannot improve Hit, so every point it gains is pure
    # stopping efficiency. That is the ceiling on Phase C.
    oracle, actual = [], []
    for sid, trace in recorder.sessions.items():
        knew = tmeasure.first_hit(targets[sid], 1)
        shipped_at = tmeasure.first_shipped(targets[sid])
        oracle.append(knew if knew is not None else 11)
        actual.append(shipped_at if shipped_at is not None else 11)

    def eff(m): return max(0.0, min(1.0, (11.0 - m) / 10.0))
    m_now, m_oracle = sum(actual) / len(actual), sum(oracle) / len(oracle)
    print(f"\nR4-A8 — the value of a perfect stopping rule")
    print(f"  MTTC now                     {m_now:.3f}")
    print(f"  MTTC if it shipped the turn it reached internal rank 1   {m_oracle:.3f}")
    print(f"  turns recoverable            {m_now - m_oracle:.3f}")
    print(f"  => efficiency gain           {0.20 * (eff(m_oracle) - eff(m_now)):+.4f} of TechnicalScore")
    print(f"\n  where the rest of the loss actually is:")
    print(f"    never in internal top-10   {1 - early_hit_curve(recorder, targets, 10)[-1]:.4f}  (recall)")
    print(f"    in top-10, never rank 1    {early_hit_curve(recorder, targets, 10)[-1] - e1[-1]:.4f}  (ranking)")
    print(f"    EarlyHit@1 ceiling         {e1[-1]:.4f}")


if __name__ == "__main__":
    main()
