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
    # Okapi BM25 over the lexical surface — BUILT, SWEPT, and SHIPPED OFF. The measurement is the
    # contribution, so both halves are recorded here.
    #
    # On data/train.jsonl[:3000] it looks like the best thing available, mean over L0/L2/L3:
    #   gain   0.0     2.0     3.0     4.0     6.0     8.0
    #   mean  .8558   .8742   .8747   .8744   .8724   .8696      (+0.0189 at the interior optimum)
    # All of that comes from L2/L3. The L0 row is flat: 0.9513 -> 0.9516.
    #
    # It does not hold out. On the clean discriminating sets it is monotonically NEGATIVE:
    #   gain          0.0      0.5      1.0      2.0
    #   dev  (2,000)  .9506    .9495    .9494    .9489
    #   public (200)  .9744    .9700    .9700    .9697
    #
    # ⚠️ A +0.0003 L0 row on 3,000 sessions did not survive contact with 2,000 held-out ones. The
    # private 800 are drawn from the same templated pipeline as the public 200, so clean text is the
    # distribution that decides, and the pre-registered gate forbids trading it for stress.
    # This is the third independent negative for a lexical route over this surface, and it holds
    # even after understand/tokens.py repaired the tokenizer — so the earlier negatives were not an
    # artefact of the damaged surface, which is what we suspected and can now rule out.
    bm25_gain: float = 0.0
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
    # ⚠️ DETERMINISTIC SUBMISSION (team decision). The language tier is built and works, but it is
    # switched OFF, so the submitted agent makes **zero network calls** and has no external
    # dependency, credential, quota or availability risk.
    #
    # This costs nothing on the evaluation. The tier only fires when tiers 1 and 2 both fail to read
    # a message, and the final 800 sessions use the same deterministic customer-message templates as
    # the public set ("No undisclosed natural-language paraphrases are introduced", Track 4 FAQ §1).
    # Measured: 0 calls and 0 tokens across public_set (200), dev (2,000), and
    # generated_template_set/test (2,800).
    # On free-form text it fired once per session and measured -0.0007, so it was not earning its
    # place there either.
    #
    # Set `llm_extract=True` (or `COPILOT_FLAGS=llm_extract`, or `evaluate.py --llm_call`) to re-enable it for experiments.
    llm_extract: bool = False   # escalation only: fires when tier 1 and tier 2 both fail on a message
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
