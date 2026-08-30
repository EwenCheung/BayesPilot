"""Which category scorer actually wins at L3? Measure, don't argue.

Naive Bayes over raw message tokens scored 0.525 against the lexical baseline's 0.825: the scaffold
words ("sure", "yet", "somewhere") and the constraint payload ("cotton") outvote the one token that
carries the category. The question is what to do about it.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.attributes import tokens
from src.common.simulator import coarse_category
from src.eval import harness
from src.eval.stress import paraphrase
from src.r1.catalog import CatalogIndex
from src.r3.category import CategoryBelief


def openings(level):
    from evaluator.local_evaluator import materialize_hidden_fields
    samples, _, categories, products = harness.load_world()
    out = []
    for s in samples:
        target = s["ground_truth"]["parent_asin"]
        truth = coarse_category(categories.get(target, []))
        card, behavior = materialize_hidden_fields(s, products)
        if s["scenario_type"] == "buying" and card.get("hard_constraints"):
            msg = f"I'm looking for {truth}. A key requirement is: {card['hard_constraints'][0]}."
        elif s["scenario_type"] == "intent_override":
            msg = f"I'm looking for {truth}. {behavior['override']['old_value']}"
        else:
            msg = f"I'm looking for {truth}, but I'm still exploring."
        out.append((paraphrase(msg, level), truth, target, s["scenario_type"]))
    return out


def main():
    belief = CategoryBelief(str(harness.CATALOG))
    index = CatalogIndex(str(harness.CATALOG))
    cats = belief.categories
    n_cat = len(cats)

    # document frequency of a token ACROSS categories -> how discriminative it is
    df = {w: len(p) for w, p in belief.postings.items()}
    idf = {w: math.log(n_cat / (1 + d)) for w, d in df.items()}
    name_tokens = {c: tokens(c) for c in cats}

    def name_overlap(msg):
        """R1's scorer, as a distribution instead of an argmax."""
        want = tokens(msg)
        out = {}
        for c in cats:
            hit = len(want & name_tokens[c])
            if hit:
                out[c] = hit * hit / (len(name_tokens[c]) or 1)
        return out

    def nb(msg, min_idf=0.0):
        words = [w for w in tokens(msg) if w in belief.postings and idf[w] >= min_idf]
        la = math.log(0.35)
        den = [math.log(t + 0.35 * belief.vocabulary) for t in belief.total]
        sc = [belief.log_prior[i] + len(words) * (la - den[i]) for i in range(n_cat)]
        for w in words:
            for i, c in belief.postings[w]:
                sc[i] += math.log(c + 0.35) - la
        return sc

    def idf_weighted(msg, min_idf=0.0):
        """Σ idf(w) · log P(w | c) — informative words count more, generic ones barely at all."""
        words = [w for w in tokens(msg) if w in belief.postings and idf[w] >= min_idf]
        sc = [0.0] * n_cat
        for w in words:
            weight = idf[w]
            contrib = defaultdict(float)
            for i, c in belief.postings[w]:
                contrib[i] = weight * math.log(1 + c / belief.total[i] * 1e4)
            for i, v in contrib.items():
                sc[i] += v
        return sc

    def softmax_pick(scores):
        return cats[max(range(n_cat), key=lambda i: scores[i])]

    def combined(msg, w_name=6.0, min_idf=2.0):
        """Name evidence and product-language evidence are two likelihood terms, not rivals."""
        sc = idf_weighted(msg, min_idf)
        for c, v in name_overlap(msg).items():
            sc[belief._idx[c]] += w_name * v
        return sc

    variants = {
        "R1 lexical (baseline)": lambda m: index.best_category(m),
        "naive Bayes, all words": lambda m: softmax_pick(nb(m)),
        "naive Bayes, idf>=2": lambda m: softmax_pick(nb(m, 2.0)),
        "idf-weighted LM": lambda m: softmax_pick(idf_weighted(m)),
        "idf-weighted LM, idf>=2": lambda m: softmax_pick(idf_weighted(m, 2.0)),
        "name only (as dist)": lambda m: max(name_overlap(m) or {"": 0}, key=lambda k: name_overlap(m).get(k, 0)) or cats[0],
        "combined w=3": lambda m: softmax_pick(combined(m, 3.0)),
        "combined w=6": lambda m: softmax_pick(combined(m, 6.0)),
        "combined w=12": lambda m: softmax_pick(combined(m, 12.0)),
        "combined w=25": lambda m: softmax_pick(combined(m, 25.0)),
    }

    data = {lvl: openings(lvl) for lvl in (0, 3)}
    print(f"{'variant':<26s} {'L0':>7s} {'L3':>7s}")
    for name, fn in variants.items():
        row = []
        for lvl in (0, 3):
            right = sum(fn(msg) == truth for msg, truth, _, _ in data[lvl])
            row.append(right / len(data[lvl]))
        print(f"{name:<26s} {row[0]:>7.3f} {row[1]:>7.3f}", flush=True)


if __name__ == "__main__":
    main()
