"""R4 ablation switches — R3's flags, plus the mechanisms this road adds.

Every new mechanism defaults **off**, so a default-constructed R4 is R3. That is not a stylistic
choice: R4-A1 requires R4 to reproduce R3 bit-for-bit with its new parts disabled, and a flag that
defaults on makes that test unwritable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.r3.flags import Flags as R3Flags

# Re-fitted on train.jsonl (12,000 sessions, targets disjoint from every evaluation set) by
# `scripts/fit_r4.py`. R3's values were fitted on a 120-session split of the official 200, which R4
# now saturates. Only three of the six moved; `prior_weight` moved to zero. See 03-decisions.md D14.
TRAIN_FITTED = {"prior_weight": 0.0, "v_continue": 0.75, "tau_mass": 0.85}


@dataclass
class Flags(R3Flags):
    # --- re-fitted on train.jsonl, overriding R3's public-set-fitted values (D14) -----------------
    prior_weight: float = TRAIN_FITTED["prior_weight"]
    v_continue: float = TRAIN_FITTED["v_continue"]
    tau_mass: float = TRAIN_FITTED["tau_mass"]

    # --- R4-A0: survival is evidence ---------------------------------------------------------
    # The evaluator breaks on first hit, so surviving a turn PROVES every item shipped that turn is
    # not the target. R3 re-ships them anyway: measured, 43/43 sessions alive at turn 5 shipped a
    # depth-1 list identical to turn 4's, which had already been proven wrong. See 03-decisions.md D8.
    exclude_shipped: bool = False


    # --- Phase T: soft card matching, the paraphrase-tolerant twin of the exact term ------------
    # 0.0 = off. Token-Jaccard against each item's OWN card strings, which is what the simulator
    # quotes from. Separate from exact_gain so a snap can never outvote a verbatim match.
    # Use R4's own extraction prompt (src/r4/extract.py) instead of the shared EXTRACT_SYSTEM.
    # No effect offline: R3_OFFLINE=1 leaves agent.llm None, so there is nothing to wrap.
    aligned_extract: bool = True

    # Fitted on train.jsonl. ⚠️ 2.5 scored a marginally better objective (0.8558 vs 0.8546) but
    # REGRESSED clean by 0.0086; the pre-registered gate (R4-A31) forbids trading L0 for stress, and
    # the objective gap is inside noise while the L0 gap is not. See 03-decisions.md D15.
    soft_card_gain: float = 1.5
    soft_card_floor: float = 0.34   # below this, overlap is noise (mirrors likelihood.TOKEN_FLOOR)

    truncate: int = 0          # Phase D — 0 = always ship 10. MEASURED NEGATIVE (D4), default off.

    @classmethod
    def from_env(cls) -> "Flags":
        """`R3_FLAGS` is read first so inherited settings keep working, then `R4_FLAGS` overrides.

        Same grammar as R3: `no_<flag>` disables, `<flag>` enables, `name=value` sets.
        """
        flags = cls()
        for var in ("R3_FLAGS", "R4_FLAGS"):
            for token in (os.environ.get(var) or "").split(","):
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
