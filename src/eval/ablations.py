"""One ablation vocabulary for every road (04-merge-plan.md §3.3).

An ablation name that means something different in each road produces numbers that look comparable and
are not. That is exactly what happened: `no_spec_phrase` = 0.9260 (R1) beside 0.8315 (R2) overstated R1
by roughly 0.09, because R1's switch disabled only its exact matcher while its normalised
`(attribute, value)` matcher went on reading the SAME inverted spec strings.

The definitions below are the contract. Each road translates them; none redefines them.

  no_spec_phrase  remove ALL credit derived from the simulator's inverted spec strings — exact AND
                  partial. Generic lexical/token overlap survives: that is a retrieval signal over
                  product text, not an inversion signal. ⚠️ This is the private-set insurance number.
  no_popularity   remove the log(rating_number) prior.
  no_dense        remove the semantic/embedding route.
  no_lexical      remove generic token-overlap retrieval.
"""
from __future__ import annotations

# name -> {road: how that road realises it}
SHARED: dict[str, dict[str, object]] = {
    "no_spec_phrase": {
        # both tiers: `phrases` is the exact inverted card string, `pairs` is the same string
        # normalised — partial credit for the same inversion.
        "r1": {"spec_phrase": False, "attribute": False},
        "r2": ("no_spec_phrase",),
    },
    "no_popularity": {"r1": {"popularity": False}, "r2": ("no_popularity",)},
    "no_dense": {"r1": {"dense": False}, "r2": ("no_dense",)},
    "no_lexical": {"r1": {"token": False}, "r2": ("no_lexical",)},
}


def r1_flags(*names: str):
    """R1's Flags with the named shared ablations applied."""
    from src.r1.flags import Flags

    flags = Flags.from_env()
    for name in names:
        assert name in SHARED, f"unknown ablation {name!r}; have {sorted(SHARED)}"
        for field, value in SHARED[name]["r1"].items():
            setattr(flags, field, value)
    return flags


def r2_ablations(*names: str) -> tuple[str, ...]:
    """R2's ablation tuple for the named shared ablations."""
    out: list[str] = []
    for name in names:
        assert name in SHARED, f"unknown ablation {name!r}; have {sorted(SHARED)}"
        out.extend(SHARED[name]["r2"])
    return tuple(out)
