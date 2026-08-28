"""Fusion — turn several route opinions into one ordering.

Two fusers. The scheduled linear blend is what ships; RRF is kept as the parameter-free baseline it is
usually claimed to be, because IMPORTANT.md §13.2.2 records it being BEATEN here (0.840 vs 0.905) and a
baseline you no longer run is a baseline you can no longer defend.

The schedule is the Router role: how much to trust each route is a function of how much the customer has
actually told us. At zero slots the customer has said nothing but a category, dense retrieval has nothing
to work with (measured: hit@10 0.185 on category alone) and popularity is the best available guess
(0.815). As slots accumulate the evidence routes take over.
"""
from __future__ import annotations

from .routes import Query

# weights: (popularity, spec_phrase, lexical, dense) indexed by number of confirmed slots, capped at 3+.
# Swept over 23 configurations (src/eval/sweep_fusion.py). Two findings the initial guess got wrong:
#
#   1. Popularity must stay STRONG even with a full constraint card. The first schedule decayed it to
#      0.32 on the theory that evidence should take over; that scored 0.9616. Raising it to 2.5 scored
#      0.9707. The reason is structural: once every stated constraint is matched, dozens of products tie,
#      and popularity is the only route that still carries information about which of them is the answer
#      (the 570x target skew is a genuine prior, not a tiebreak of convenience).
#   2. The optimum is a broad plateau, not a peak — everything in 0.969-0.971 across a 4x range of both
#      weights. That is evidence this is not a knife-edge fit to 200 sessions.
SCHEDULE: dict[int, tuple[float, float, float, float]] = {
    0: (1.00, 0.00, 0.20, 0.20),   # category only: popularity is the best guess available
    1: (2.73, 3.00, 0.30, 0.45),
    2: (2.58, 4.62, 0.30, 0.55),
    3: (2.50, 6.00, 0.30, 0.60),   # full card: spec leads, popularity breaks the ties
}


# ⚠️ The schedule above is tuned WITH exact matching available, and that assumption turned out to be
# load-bearing: with the spec route ablated the same weights score 0.7442, barely above the
# popularity-only floor, because a dominant popularity weight swamps the two routes that still have
# something to say.
#
# So the Router keys on evidence QUALITY, not only on slot count. When no candidate matches any stated
# constraint exactly we are either in a paraphrased session or looking at constraints the catalog does
# not phrase our way; either way the exact-match prior has nothing to contribute and the semantic routes
# should lead. This is PROBLEM.md Pillar III "runtime workflow re-orchestration" as a real mechanism
# rather than a gesture: the agent notices a strategy has stopped working and changes strategy.
# Tuned jointly on the two robustness conditions, which pull in OPPOSITE directions and so cannot both
# be maximised:
#
#   condition            best profile        its score   at the chosen profile
#   no_spec_phrase       popularity 1.5      0.8478      0.8315
#   stressed:full        popularity 0.45     0.8065      0.7961
#
# no_spec_phrase keeps clean template text and only loses exact matching, so the popularity prior is
# still sharp. Stressed text also mangles the constraint strings, so the semantic routes have to carry
# more. Chosen by best WORST case rather than best average — this profile is insurance, and insurance is
# judged on its bad day.
PARAPHRASE_SCHEDULE: dict[int, tuple[float, float, float, float]] = {
    0: (1.00, 0.00, 0.20, 0.20),
    1: (0.90, 0.80, 0.80, 0.98),
    2: (0.85, 0.90, 0.90, 1.22),
    3: (0.80, 1.00, 1.00, 1.40),
}

# A candidate matching even one constraint exactly scores at least 1/n_constraints, while partial token
# credit is capped at partial_credit (0.55) of that. This threshold sits between the two regimes.
EXACT_EVIDENCE_THRESHOLD = 0.60


def weights_for(n_slots: int, ablations: frozenset[str] = frozenset(),
                schedule: dict | None = None,
                spec_support: float | None = None) -> dict[str, float]:
    """Route weights for this turn.

    `spec_support` is the best spec-phrase score across the candidate pool — the Router's read on
    whether exact matching is working at all in this session. Pass None to disable the adaptive switch
    (that is the `no_adaptive` ablation).
    """
    table = schedule or SCHEDULE
    if (spec_support is not None and n_slots > 0
            and spec_support < EXACT_EVIDENCE_THRESHOLD and table is SCHEDULE):
        table = PARAPHRASE_SCHEDULE
    popularity, spec, lexical, dense = table[min(n_slots, 3)]
    weights = {"popularity": popularity, "spec_phrase": spec,
               "lexical": lexical, "dense": dense}
    for route in ablations:
        weights[route.removeprefix("no_")] = 0.0
    return weights


def blend(route_scores: dict[str, dict[str, float]], candidates: list[str],
          weights: dict[str, float]) -> dict[str, float]:
    """Scheduled linear blend.

    Route scores already land in [0,1] by construction, so no per-turn renormalization: preserving score
    MAGNITUDE is precisely why the blend beats RRF here — popularity is a strength signal, not merely an
    ordering. An abstaining route contributes nothing rather than zero, so abstention does not push
    candidates down relative to each other.
    """
    fused = {a: 0.0 for a in candidates}
    for name, scores in route_scores.items():
        weight = weights.get(name, 0.0)
        if weight == 0.0 or not scores:
            continue
        for asin, value in scores.items():
            fused[asin] += weight * value
    return fused


def rrf(route_scores: dict[str, dict[str, float]], candidates: list[str],
        weights: dict[str, float], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion baseline: sum 1/(k + rank). Discards magnitude, which is its weakness here."""
    fused = {a: 0.0 for a in candidates}
    for name, scores in route_scores.items():
        if weights.get(name, 0.0) == 0.0 or not scores:
            continue
        order = sorted(scores, key=lambda a: -scores[a])
        for rank, asin in enumerate(order, start=1):
            fused[asin] += 1.0 / (k + rank)
    return fused


def order(fused: dict[str, float], index, query: Query, shown: list[str] | None = None) -> list[str]:
    """Final ordering. Ties break on popularity, then asin, so the ordering is deterministic."""
    return sorted(fused, key=lambda a: (-fused[a], -index.log_pop[a], a))


def mmr(ranked: list[str], index, depth: int = 10, lam: float = 0.75) -> list[str]:
    """Greedy MMR over the head of the list — relevance vs coverage.

    ⚠️ Gated by the caller on entropy, never applied by default. We are scored on ONE hidden target in a
    top-10 list, so diversity only pays when it raises the chance the target is in the list at all. Under
    low uncertainty it strictly costs MRR (IDEA.md §B).
    """
    pool = ranked[:depth * 3]
    if len(pool) <= 1:
        return ranked
    picked = [pool[0]]
    rest = pool[1:]
    while rest and len(picked) < depth:
        best, best_value = rest[0], -1e9
        for candidate in rest:
            similarity = max(
                len(index.tokens[candidate] & index.tokens[chosen])
                / (len(index.tokens[candidate] | index.tokens[chosen]) or 1)
                for chosen in picked
            )
            value = lam * (1.0 - rest.index(candidate) / len(rest)) - (1.0 - lam) * similarity
            if value > best_value:
                best, best_value = candidate, value
        picked.append(best)
        rest.remove(best)
    return picked + [a for a in ranked if a not in picked]
