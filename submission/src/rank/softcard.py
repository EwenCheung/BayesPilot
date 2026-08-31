"""Soft card matching — the paraphrase-tolerant twin of the exact card-string term.

**Why this exists.** The exact term is `constraint.text in index.card[asin]`, and `card[asin]` is a
tuple, so that is *equality*, not substring. One reworded character and the strongest evidence in the
system (gain 3.2) goes silent. Measured at L4 (model-written paraphrase, 300 dev sessions): 97% of
sessions still have the target **in the pool**, only 3% lose it to category resolution — and 44.7% of
sessions hit at rank 2+ against 2.4% on clean text. **The target is being retrieved and not ranked
first**, which is a matching-precision problem, not a retrieval one.

**Why token-Jaccard against the item's own card strings, specifically.** R3's `lexical` term already
does token overlap, but against *everything* an item has — title, store, categories, features — so
the signal is diluted. The simulator quotes from the four card strings and nothing else, so those are
the only text worth matching against.

📊 Measured ceiling, pool-scoped (~335 items), on `train.jsonl`:

| | L3 rule rewriter | LLM rewriter |
|---|---|---|
| card string recovered at rank 1 | 72.2% | 57.9% |
| recovered in top 5 | 96.1% | 85.8% |
| **target item ranked #1 on paraphrased text alone** | 59.3% | **46.7%** |

Against R4's current 34.7% rank-1 at L4, that is real headroom.

⚠️ **A confident wrong snap is worse than no snap**, because it feeds the same channel as a genuine
match. Two guards: the gain is separate from and normally below `exact_gain`, and matches below
`soft_card_floor` are discarded rather than scored weakly.
"""
from __future__ import annotations

from src.understand.attributes import tokens
from src.rank.likelihood import _bounded


def _jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def card_tokens(index, asin: str) -> tuple[frozenset[str], ...]:
    """Token sets for one item's own card strings, cached on the index.

    Cached because a session touches a handful of pools and each pool is scored every turn; without
    it this is the hot loop.
    """
    cache = getattr(index, "_card_tokens", None)
    if cache is None:
        cache = index._card_tokens = {}
    got = cache.get(asin)
    if got is None:
        got = cache[asin] = tuple(frozenset(tokens(s)) for s in index.card[asin] if s)
    return got


def softcard_terms(index, constraint, candidates: list[str], flags) -> dict[str, float]:
    """Log-likelihood of one constraint under each candidate, by best card-string overlap.

    Returns `{}` when the term abstains — same contract as `constraint_terms`, so a term with no
    opinion contributes a constant to every log-posterior and cancels in the normalisation.
    """
    gain = getattr(flags, "soft_card_gain", 0.0)
    floor = getattr(flags, "soft_card_floor", 0.34)
    if gain <= 0:
        return {}
    want = frozenset(tokens(constraint.text))
    if not want:
        return {}

    out: dict[str, float] = {}
    saw_evidence = False
    for asin in candidates:
        # ⚠️ Skip anything the EXACT term already scored. Both fire on a verbatim match, and paying
        # twice for one piece of evidence would let a single constraint outvote three others.
        if constraint.text in index.card[asin]:
            out[asin] = _bounded(0.0, gain)
            continue
        best = 0.0
        for card in card_tokens(index, asin):
            score = _jaccard(want, card)
            if score > best:
                best = score
        if best >= floor:
            saw_evidence = True
            out[asin] = _bounded(best, gain)
        else:
            out[asin] = _bounded(0.0, gain)

    return out if saw_evidence else {}
