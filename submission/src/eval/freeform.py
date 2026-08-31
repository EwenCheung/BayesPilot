"""Runner for the free-form corpus in `data/freeform_v1/`.

Each row carries `free_form.initial_message` — a non-template first turn in one of eight language
styles (slang, shorthand, typos, emoji, self-correction…). The official evaluator knows nothing about
that field: it builds turn 1 from its own templates. So the substitution happens by wrapping the
**agent**, exactly as the paraphrase stress harness does, and the evaluator, the labels and the
exact-code hit check stay untouched.

⚠️ **Only turn 1 is supplied by the corpus.** `manifest.json` claims the generating policy was
"every agent-visible turn rewritten", but the rows contain a single message and the generator is not
in this repository, so later turns cannot be reproduced byte-for-byte. Two modes, and the difference
is reported rather than hidden:

* `later="template"` (default) — later turns keep the simulator's own wording. This is exactly what
  the shipped data supports, and it **understates** the intended difficulty.
* `later="stress"` — later turns go through `ParaphraseRewriter` at a chosen level. A defensible
  reconstruction, not the original; never quote it as a freeform number without saying so.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEFORM = ROOT / "data" / "freeform_v1"
RESPLIT = ROOT / "data" / "resplit_60_20_20"
COMBINE = ROOT / "data" / "combine"


def load(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def split(corpus: str, name: str) -> list[dict]:
    """`corpus` is freeform | resplit | combine; `name` is train | validation | test."""
    base = {"freeform": FREEFORM, "resplit": RESPLIT, "combine": COMBINE}[corpus]
    return load(base / f"{name}.jsonl")


class FreeFormAgent:
    """Agent proxy that swaps the simulator's turn-1 template for the corpus's free-form message.

    The evaluator calls `respond(session_id, user_message, turn, top_k)` and generates its own
    `user_message`; we intercept turn 1 and hand the agent the corpus text instead. Sessions are
    keyed by arrival order because the evaluator mints a fresh uuid per session and walks `samples`
    in order — asserted by the runner rather than assumed.
    """

    def __init__(self, agent, samples: list[dict], rewriter=None) -> None:
        self._agent = agent
        self._messages = [(s.get("free_form") or {}).get("initial_message") for s in samples]
        self._rewriter = rewriter
        self._order: list[str] = []
        self._index: dict[str, int] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        if session_id not in self._index:
            self._index[session_id] = len(self._order)
            self._order.append(session_id)
        self._agent.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        i = self._index.get(session_id)
        if turn == 1 and i is not None and i < len(self._messages) and self._messages[i]:
            user_message = self._messages[i]
        elif self._rewriter is not None and turn > 1:
            user_message = self._rewriter(user_message, turn)
        return self._agent.respond(session_id, user_message, turn, top_k)

    def __getattr__(self, item):
        return getattr(self._agent, item)


def coverage(samples: list[dict]) -> float:
    """Share of rows that actually carry a free-form opener — 0.0 for a purely template corpus."""
    if not samples:
        return 0.0
    return sum(1 for s in samples if (s.get("free_form") or {}).get("initial_message")) / len(samples)
