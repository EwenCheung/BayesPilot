"""Ablation switches. Every term and stage behind one, so the honesty table is a run, not an argument."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Flags:
    exact: bool = True         # exact card-string evidence — the inversion route
    attribute: bool = True     # normalised (attribute, value) — partial credit for the same inversion
    lexical: bool = True       # generic token overlap; retrieval, not inversion
    prior: bool = True         # the popularity prior
    exact_gain: float = 3.2    # log-odds an exact match is worth; the R1<->R2 dial (fitted)
    prior_weight: float = 0.18 # scales log1p(rating) onto the evidence's units (fitted)
    belief_pool: bool = True   # level-1 posterior chooses the pool (else: argmax category, R1-style)
    infogain: bool = False     # ⚠️ OFF: measured worse at every stress level — see D18
    llm_extract: bool = True   # LLM constraint extraction, escalation only
    temperature: float = 2.0
    tau_mass: float = 0.9
    v_continue: float = 0.9   # expected reciprocal rank if the session continues (fitted)
    stall_decay: float = 0.35  # P(evidence still coming) after N barren turns = stall_decay ** N
    deadline: int = 3          # override silence ends here — structural, see agent._respond
    max_turns: int = 10        # the evaluator's hard limit; ship everything on the last turn

    @classmethod
    def from_env(cls) -> "Flags":
        """R3_FLAGS=no_exact,deadline=4,tau_convert=0.4"""
        flags = cls()
        for token in (os.environ.get("R3_FLAGS") or "").split(","):
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
