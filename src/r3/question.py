"""Expected information gain over the posterior (00-r3-spec.md §3).

R1 implemented EIG over a candidate SET with a popularity-weighted prior and measured it at -0.0010
against a hardcoded "other" — inside the noise, and it never won. Here the same objective runs over a
real distribution, which is the point: "the expected value of this question exceeded the others" is a
mechanism, where a magic string is not.

⚠️ **MEASURED AND SWITCHED OFF (D18).** It loses to a hardcoded `"other"` at every stress level:
0.9509 vs 0.9720 clean, 0.8426 vs 0.8845 at L2, 0.7899 vs 0.8297 at L3. R1 found the same sign at
-0.0010; here the cost is twenty to forty times larger, because R3 asks over a much wider pool.

The reason is structural, not a tuning failure. `"other"` makes the simulator return **the next two
undisclosed constraints**, while any named attribute returns at most one — and `classify_constraint`
never emits brand, budget or category at all, so a third of the attributes EIG can choose are dead
letters that burn a turn. No question-selection objective can beat "ask for strictly more evidence"
when one option literally returns twice as much of it.

Kept, behind `R3_FLAGS=infogain`, because the mechanism is worth showing and the measurement is the
point. It is not shipped.
"""
from __future__ import annotations

import math

ASKABLE = ("material", "color", "size", "style", "feature", "use_case", "other")


def _entropy(weights: list[float]) -> float:
    total = sum(weights)
    if total <= 0:
        return 0.0
    return -sum((w / total) * math.log(w / total) for w in weights if w > 0)


def best_question(index, state, belief) -> str:
    """Pick the attribute whose answer most reduces expected entropy of the item posterior."""
    post = belief.normalised()
    live = sorted(post, key=lambda a: -post[a])[:400]   # the tail cannot change the answer
    if not live:
        return "other"

    before = _entropy([post[a] for a in live])
    best, best_gain = "other", -1.0
    for attribute in ASKABLE:
        if state.asked.get(attribute) is False:      # already came back barren; never ask twice
            continue
        # partition by the answer the simulator WOULD give if each candidate were the target:
        # items producing the same answer form one group, so this is O(|live|) per attribute.
        groups: dict[object, list[float]] = {}
        for asin in live:
            if attribute == "other":
                signature = tuple(c for c in index.card[asin] if c not in state.disclosed)[:2]
            else:
                signature = tuple(sorted(v for k, v in index.pairs(asin) if k == attribute))
            groups.setdefault(signature, []).append(post[asin])
        expected = sum(sum(g) * _entropy(g) for g in groups.values())
        gain = before - expected
        if gain > best_gain:
            best, best_gain = attribute, gain
    return best
