"""The ablation vocabulary — one name, one meaning.

An ablation name that means something different in two places produces numbers that look comparable
and are not. That is exactly what happened once: `no_spec_phrase` read 0.9260 beside 0.8315 and
overstated one side by ~0.09, because one switch disabled only the exact matcher while its normalised
`(attribute, value)` matcher went on reading the SAME inverted spec strings.

  no_spec_phrase  remove ALL credit derived from the simulator's inverted spec strings — exact AND
                  partial. Generic lexical/token overlap survives: that is a retrieval signal over
                  product text, not an inversion signal. ⚠️ This is the private-set insurance number.
  no_soft_card    remove the paraphrase-tolerant twin of the exact term.
  no_lexical      remove generic token-overlap retrieval.
  no_exclude      re-ship items a live session has already proven wrong.
  bm25            switch the Okapi BM25 evidence term on at its fitted gain.
"""
from __future__ import annotations

ABLATIONS: dict[str, dict[str, object]] = {
    "no_spec_phrase": {"exact": False, "attribute": False},
    "no_soft_card": {"soft_card_gain": 0.0},
    "no_lexical": {"lexical": False},
    "no_exclude": {"exclude_shipped": False},
    "bm25": {"bm25_gain": 2.0},
}


def flags(*names: str):
    """`Flags` with the named ablations applied. Unknown names raise rather than silently no-op."""
    from src.copilot.flags import Flags

    out = Flags.from_env()
    for name in names:
        assert name in ABLATIONS, f"unknown ablation {name!r}; have {sorted(ABLATIONS)}"
        for field, value in ABLATIONS[name].items():
            setattr(out, field, value)
    return out
