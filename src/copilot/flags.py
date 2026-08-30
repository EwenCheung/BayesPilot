"""Every term and stage behind one switch, so the honesty table in SUMMARY.md is a run, not an argument.

Values are the ones `scripts/fit_r4.py` chose on `data/train.jsonl` (12,000 sessions, targets disjoint
from every evaluation set). R3's originals were fitted on a 120-session split of the official 200, a
set the agent now saturates.

⚠️ **The defaults ARE the submission.** `local_evaluator.py` constructs `Agent(catalog_path)`
positionally with no environment, so whatever is written here is what gets scored. This used to be
false for `exclude_shipped` — it defaulted off while every published number switched it on, so a
constructed agent reproduced nothing (SUMMARY.md D2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Flags:
    # --- evidence terms -------------------------------------------------------------------------
    exact: bool = True          # exact card-string evidence — the inversion route
    attribute: bool = True      # normalised (attribute, value) — partial credit for the same inversion
    lexical: bool = True        # generic token overlap; retrieval, not inversion
    exact_gain: float = 3.2     # log-odds an exact match is worth; the filter <-> blend dial (fitted)
    soft_card_gain: float = 1.5  # token-Jaccard against the item's OWN card strings (+0.062 L2, +0.073 L3)
    soft_card_floor: float = 0.34   # below this, overlap is noise (mirrors likelihood.TOKEN_FLOOR)
    bm25_gain: float = 0.0      # Okapi BM25 over the lexical surface — OFF pending held-out confirmation
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # --- level 1, the pool ----------------------------------------------------------------------
    temperature: float = 2.0
    tau_mass: float = 0.85      # widen the pool until this much posterior mass is covered

    # --- state ----------------------------------------------------------------------------------
    erase: str = "demote"       # override: demote (best) | delete | keep — deleting cost -0.05 MRR

    # --- policy ---------------------------------------------------------------------------------
    # Survival is evidence: the evaluator breaks on first hit, so an item shipped on a hit-checked
    # turn in a session that is still alive is PROVEN not to be the target. +0.027 train, +0.028 dev.
    exclude_shipped: bool = True
    v_continue: float = 0.75    # expected reciprocal rank if the session continues (fitted)
    stall_decay: float = 0.2        # P(evidence still coming) after N barren turns, BLIND channel
    stall_decay_clean: float = 0.8  # ...and while templates are still matching (fitted separately)
    deadline: int = 3           # override silence ends here — structural, see agent._respond
    max_turns: int = 10         # the evaluator's hard limit; ship everything on the last turn

    # --- the language tier ----------------------------------------------------------------------
    llm_extract: bool = True    # escalation only: fires when tier 1 and tier 2 both fail on a message
    verify: bool = True         # resolve every model-proposed value against real catalog vocabulary
    ambiguity: bool = True      # carry an unresolved span as a probability mixture, not a guess

    @classmethod
    def from_env(cls) -> "Flags":
        """`COPILOT_FLAGS=no_exact,bm25_gain=2.0,deadline=4` — `no_x` disables, `x` enables, `x=v` sets."""
        flags = cls()
        for token in (os.environ.get("COPILOT_FLAGS") or "").split(","):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                name, _, value = token.partition("=")
                current = getattr(flags, name)
                setattr(flags, name, type(current)(value))
            elif token.startswith("no_"):
                setattr(flags, token[3:], False)
            else:
                setattr(flags, token, True)
        return flags
