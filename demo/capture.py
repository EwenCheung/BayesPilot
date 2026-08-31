"""Run the REAL agent on three REAL sessions and record every internal, for `demo/index.html`.

Nothing in the demo is staged: the customer text comes from the datasets, the target is the dataset's
hidden ground truth, the recommendations are whatever the agent actually returned, and every number
shown (pool size, V, depth, evidence contributions) is read out of the live objects mid-turn.

    PYTHONHASHSEED=0 python3 demo/capture.py      # writes demo/traces.js

⚠️ Runs the SHIPPED configuration: `exclude_shipped=True`, `bm25_gain=0.0`, LLM tier enabled (it fires
only where the deterministic tiers fail, which is what the free-form scenarios demonstrate).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402

import src.r4.agent as r4agent  # noqa: E402
from src.eval import freeform, harness  # noqa: E402
from src.r3.likelihood import constraint_terms  # noqa: E402
from src.r4.belief import SelectiveBelief  # noqa: E402
from src.r4.softcard import softcard_terms  # noqa: E402
from src.r5.agent import Agent  # noqa: E402

_, CID, CATS, PRODS = harness.load_world()

SCENARIOS = [
    ("override", "Free-form · intent override", "data/freeform_v1/test.jsonl", "train_01099"),
    ("buying",   "Free-form · buying intent",   "data/freeform_v1/test.jsonl", "train_09421"),
    ("browsing", "Templated · browsing intent", "data/public_set.jsonl",       "public_0006"),
    # ⚠️ A session the agent LOSES, kept deliberately. It runs the full 10 turns and shows the depth
    # ladder widening 1 -> 2 -> 3 -> 4 -> 5 -> 10 as the customer stops revealing anything new.
    ("hard",     "Free-form · runs out of turns", "data/freeform_v1/test.jsonl", "train_02730"),
    # "I don't know what I want yet" — the shopper has a product in mind but names no requirement.
    # Nine turns of the agent drawing it out of them.
    ("undecided", "Free-form · undecided shopper", "data/freeform_v1/test.jsonl", "train_07067"),
]

LAST = {}


class Recording(SelectiveBelief):
    def update(self, state, flags, semantics=None, lexical=None):
        super().update(state, flags, semantics, lexical)
        LAST["belief"] = self


def rows(index, state, belief, asin):
    """Per-term evidence contributions for ONE item — the expandable panel's content."""
    out = []
    for c in state.live():
        w = c.weight(state.turn)
        if w <= 0:
            continue
        exact = constraint_terms(index, c, [asin], belief.flags_snapshot)
        soft = softcard_terms(index, c, [asin], belief.flags_snapshot)
        out.append({
            "text": c.text, "attribute": c.attribute, "tier": c.tier,
            "weight": round(w, 3), "demoted": c.demoted,
            "exact": round(w * exact[asin], 3) if exact else None,
            "soft": round(w * soft[asin], 3) if soft else None,
        })
    return out


def capture(name, title, path, sample_id):
    samples = [json.loads(l) for l in open(ROOT / path)]
    sample = next(s for s in samples if s["sample_id"] == sample_id)
    target = sample["ground_truth"]["parent_asin"]
    freeform_row = bool((sample.get("free_form") or {}).get("initial_message"))

    agent = Agent(str(harness.CATALOG))
    agent.flags.exclude_shipped = True
    agent.flags.bm25_gain = 0.0
    r4agent.SelectiveBelief = Recording

    llm_log = []
    if agent.llm is not None:
        inner = agent.llm
        class Tap:
            def extract(self, m):
                out = inner.extract(m); llm_log.append((m, out)); return out
            def totals(self): return inner.totals()
            def __getattr__(self, k): return getattr(inner, k)
        agent.llm = Tap()

    turns = []
    original = agent._respond

    def wrapped(sid, msg, turn, top_k):
        n = len(llm_log)
        LAST.pop("belief", None)
        # ⚠️ Items PROVEN wrong before this turn — the only ones the exclusion rule can actually zero.
        # Counting `_shipped` AFTER the turn instead was wrong: it includes the item just shipped,
        # which is marked proven for FUTURE turns and was not excluded from this one.
        proven_before = {a for a, p in agent._shipped.get(sid, {}).items() if p}
        clock = time.perf_counter()
        result = original(sid, msg, turn, top_k)
        elapsed_ms = (time.perf_counter() - clock) * 1000.0
        state = agent.sessions[sid]
        belief = LAST.get("belief")
        belief.flags_snapshot = agent.flags
        post = belief.normalised()
        order = belief.ranked()

        stalls = agent._stalls.get(sid, 0)
        decay = agent.flags.stall_decay if state.paraphrased() else agent.flags.stall_decay_clean
        hope = decay ** stalls
        V = max(0.0, agent.flags.v_continue * hope - 0.0667)

        shipped = [r["parent_asin"] for r in result["recommendations"]]
        cats = agent.categories.ranked(state.history[0])[:3]

        turns.append({
            "turn": turn,
            "message": msg,
            "escalated": len(llm_log) > n,
            "llm_out": [[a, v] for a, v, _ in (llm_log[n][1] if len(llm_log) > n else [])],
            "route": state.route,
            "category": state.category,
            "template_hits": state.template_hits,
            "constraints": [{"text": c.text, "attribute": c.attribute, "value": c.value,
                             "tier": c.tier, "weight": round(c.weight(state.turn), 3),
                             "demoted": c.demoted} for c in state.constraints],
            "pool_size": len(belief.candidates),
            "top_categories": [[c, round(m, 4)] for c, m in cats],
            "entropy": round(belief.entropy(), 4),
            "stalls": stalls, "decay": decay, "hope": round(hope, 4), "V": round(V, 4),
            "depth": len(shipped),
            "excluded": sum(1 for a in proven_before if a in belief.log_p),
            "ranking": [{"asin": a, "title": agent.index.title[a],
                      "p": round(post[a], 4), "logp": round(belief.log_p[a], 3),
                      "is_target": a == target} for a in order[:10]
                     if belief.log_p[a] != -math.inf],
            "evidence": rows(agent.index, state, belief, order[0]) if order else [],
            "shipped": [{"asin": a, "title": agent.index.title[a], "is_target": a == target}
                        for a in shipped],
            "hit": target in shipped,
            "reply": result["message"],
            "ask": result["ask_attribute"],
            # ⚠️ Wall-clock for THIS turn only — the 50k index is built once in __init__ and excluded.
            # Captured with R1_LLM_NOCACHE=1 so an LLM turn shows a real network round trip, not a
            # disk-cache hit. `usage` is the agent's own per-turn delta, the same field the evaluator
            # sums, so these are the numbers a submission would disclose.
            "ms": round(elapsed_ms, 1),
            "prompt_tokens": result["usage"]["prompt_tokens"],
            "completion_tokens": result["usage"]["completion_tokens"],
        })
        return result

    agent._respond = wrapped
    subject = freeform.FreeFormAgent(agent, [sample]) if freeform_row else agent
    res = evaluate(subject, [sample], CID, CATS, PRODS)
    session = res["sessions"][0]

    return {
        "id": name, "title": title, "sample_id": sample_id,
        "source": path, "scenario_type": sample["scenario_type"],
        "style": (sample.get("free_form") or {}).get("style"),
        "freeform": freeform_row,
        "target": target, "target_title": agent.index.title[target],
        "profile": sample.get("user_profile", {}),
        "hit": session["hit"], "best_rank": session["best_rank"],
        "first_hit_turn": session["first_hit_turn"],
        "turns": turns,
    }


def main():
    data = [capture(*s) for s in SCENARIOS]
    out = ROOT / "demo" / "traces.js"
    out.write_text("window.DEMO_TRACES = " + json.dumps(data, indent=1) + ";\n")
    for d in data:
        print(f"{d['id']:<9} {d['sample_id']:<13} turns={len(d['turns'])} "
              f"hit={d['hit']} rank={d['best_rank']} llm_turns="
              f"{sum(t['escalated'] for t in d['turns'])}")
    print(f"-> {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
