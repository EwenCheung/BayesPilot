"""R3-A27 probe — is category resolution actually the bottleneck? (00-r3-spec.md §2.3)

Isolated from everything downstream: build the exact turn-1 utterance the simulator would emit, run it
through each resolver, and compare against the target's true coarse category. If the lexical resolver
does not degrade under paraphrase, the two-level-belief thesis (D10) is wrong and P2 should be replanned
rather than tuned.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.simulator import coarse_category
from src.eval import harness
from src.eval.stress import paraphrase
from src.r1.catalog import CatalogIndex


def opening(sample: dict, category: str) -> str:
    """Mirror of the evaluator's initial_message (kit line 154)."""
    if sample["scenario_type"] == "buying" and sample["intent_card"].get("hard_constraints"):
        return f"I'm looking for {category}. A key requirement is: {sample['intent_card']['hard_constraints'][0]}."
    if sample["scenario_type"] == "intent_override":
        return f"I'm looking for {category}. {sample['behavior']['override']['old_value']}"
    return f"I'm looking for {category}, but I'm still exploring."


def main() -> None:
    samples, _, categories, products = harness.load_world()
    index = CatalogIndex(str(harness.CATALOG))
    # the evaluator materialises the hidden intent card from the product before writing turn 1
    from evaluator.local_evaluator import materialize_hidden_fields

    print(f"{'level':<8s} {'exact':>7s} {'hedged':>7s} {'pool has target':>16s}")
    for level in (0, 1, 2, 3):
        exact = hedged = in_pool = 0
        misses: Counter = Counter()
        for s in samples:
            target = s["ground_truth"]["parent_asin"]
            truth = coarse_category(categories.get(target, []))
            card, behavior = materialize_hidden_fields(s, products)
            full = {**s, "intent_card": card, "behavior": behavior}
            message = paraphrase(opening(full, truth), level)

            got = index.best_category(message)
            if got == truth:
                exact += 1
            else:
                misses[s["scenario_type"]] += 1

            pool_key = index.hedge(message)
            if pool_key == truth or (pool_key and truth in pool_key.split(" | ")):
                hedged += 1
            if target in index.pool(pool_key):
                in_pool += 1
        n = len(samples)
        print(f"L{level:<7d} {exact/n:>7.3f} {hedged/n:>7.3f} {in_pool/n:>16.3f}"
              + (f"   misses by scenario: {dict(misses)}" if misses else ""), flush=True)


if __name__ == "__main__":
    main()
