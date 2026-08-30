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
    semantic_backend: str = "blair"  # blair | svd  (D11 switch matrix)
    query_mode: str = "model"        # model = encode with BLaIR | prf = torch-free centroid
    semantic_gain: float = 0.0  # 0 disables the term entirely (and skips building the index)
    erase: str = "demote"      # override: demote (R1, best) | delete (R2) | keep — D23
    # Refit on the target-disjoint 8,400 train split and selected on the 2,800 validation split.
    # 0.10 scored 0.924447/0.927023 versus 0.920248/0.923199 for the legacy 0.18 value.
    prior_weight: float = 0.10       # scales log1p(rating) onto the evidence's units
    # ⚠️ Both below are R2 mechanisms, ported and MEASURED, and neither earns its place (D23).
    # Kept as switches so the negative reproduces; both default off.
    pool_normalised_prior: bool = False  # R2's "well reviewed FOR A HOOP EARRING" form
    idf_gain: float = 0.0                # R2's IDF lexical route as an evidence term
    belief_pool: bool = True   # level-1 posterior chooses the pool (else: argmax category, R1-style)
    infogain: bool = False     # ⚠️ OFF: measured worse at every stress level — see D18
    critical_questions: bool = False  # opt-in real-UX mode; specific asks score worse in the simulator
    temperature: float = 2.0
    tau_mass: float = 0.9
    v_continue: float = 0.9   # expected reciprocal rank if the session continues (fitted)
    stall_decay: float = 0.2        # P(evidence still coming) after N barren turns, PARAPHRASED
    stall_decay_clean: float = 0.8  # ...and when templates are still matching (fitted separately)
    deadline: int = 3          # override silence ends here — structural, see agent._respond
    max_turns: int = 10        # the evaluator's hard limit; ship everything on the last turn
    # --- green nodes: global rescue + fusion ---
    rescue_lexical: bool = False     # RAWLEX — global IDF/BM25 rescue across full catalog
    rescue_semantic: bool = False    # RAWSEM — global semantic rescue from raw text
    rescue_normalized: bool = False  # NORMSEM — global semantic rescue from LLM-normalized text
    rescue_top_k: int = 200          # how many rescue candidates each route contributes
    use_rrf: bool = False            # RRF — reciprocal-rank fusion across routes
    rrf_k: int = 60                  # RRF constant (standard default)
    rrf_weight_category: float = 1.0   # weight for category-pool Bayesian route in RRF
    rrf_weight_lexical: float = 0.5    # weight for lexical rescue route in RRF
    rrf_weight_semantic: float = 0.5   # weight for semantic rescue route in RRF

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
