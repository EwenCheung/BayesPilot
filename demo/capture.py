"""Run the REAL agent on REAL sessions and record every internal, for `demo/index.html`.

Nothing in the demo is staged: the customer text comes from the datasets, the target is the dataset's
hidden ground truth, the recommendations are whatever the agent actually returned, and every number
shown is read out of the live objects mid-turn.

    PYTHONHASHSEED=0 python3 demo/capture.py && python3 demo/build.py

⚠️ Runs the SHIPPED configuration, which is deterministic: `src/copilot/flags.py` defaults, so
`llm_extract` is False and the agent makes **zero network calls**. Earlier traces were captured while
the language tier was on and showed it firing on free-form openers; the submission no longer does
that, so those traces described a system that is not the one being graded.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "techjam-conversational-search-main"))

from evaluator.local_evaluator import evaluate  # noqa: E402

import src.copilot.agent as copilot  # noqa: E402
from src.copilot.agent import Agent  # noqa: E402
from src.eval import freeform, harness  # noqa: E402
from src.rank.belief import Belief  # noqa: E402
from src.rank.likelihood import constraint_terms  # noqa: E402
from src.rank.softcard import softcard_terms  # noqa: E402

SCENARIOS = [
    ("override",  "Free-form · intent override",   "data/freeform_v1/test.jsonl", "train_01099"),
    ("buying",    "Free-form · buying intent",     "data/freeform_v1/test.jsonl", "train_09421"),
    ("browsing",  "Templated · browsing intent",   "data/public_set.jsonl",       "public_0006"),
    # A session the agent LOSES, kept deliberately: it runs the full 10 turns and shows the depth
    # ladder widening 1 -> 2 -> 3 -> 4 -> 5 -> 10 as the customer stops revealing anything new.
    ("hard",      "Free-form · runs out of turns", "data/freeform_v1/test.jsonl", "train_02730"),
    # "I don't know what I want yet" — a shopper with a product in mind but no stated requirement.
    ("undecided", "Free-form · undecided shopper", "data/freeform_v1/test.jsonl", "train_07067"),
]

LAST: dict = {}


class Recording(Belief):
    """Captures the belief object the agent built this turn — it is a local inside `_respond`."""

    def update(self, state, flags, *args, **kwargs):
        super().update(state, flags, *args, **kwargs)
        LAST["belief"] = self
        LAST["flags"] = flags


def evidence(index, state, belief, asin):
    """Per-term contributions for ONE item — the expandable panel's content."""
    flags = LAST["flags"]
    out = []
    for c in state.live():
        weight = c.weight(state.turn)
        if weight <= 0:
            continue
        exact = constraint_terms(index, c, [asin], flags)
        soft = softcard_terms(index, c, [asin], flags)
        out.append({"text": c.text, "attribute": c.attribute, "tier": c.tier,
                    "weight": round(weight, 3), "demoted": c.demoted,
                    "exact": round(weight * exact[asin], 3) if exact else None,
                    "soft": round(weight * soft[asin], 3) if soft else None})
    return out


def capture(name, title, path, sample_id):
    samples = [json.loads(line) for line in (ROOT / path).open()]
    sample = next(s for s in samples if s["sample_id"] == sample_id)
    target = sample["ground_truth"]["parent_asin"]
    is_freeform = bool((sample.get("free_form") or {}).get("initial_message"))

    copilot.Belief = Recording                     # patched before the agent builds one
    agent = Agent(str(harness.CATALOG))
    assert agent.llm is None, "expected the deterministic path — llm_extract should default False"

    turns = []
    original = agent._respond

    def wrapped(sid, msg, turn, top_k):
        # items PROVEN wrong BEFORE this turn — the only ones the exclusion rule can actually zero
        proven_before = {a for a, p in agent._shipped.get(sid, {}).items() if p}
        LAST.pop("belief", None)
        clock = time.perf_counter()
        result = original(sid, msg, turn, top_k)
        elapsed_ms = (time.perf_counter() - clock) * 1000.0

        state = agent.sessions[sid]
        belief = LAST["belief"]
        post = belief.normalised()
        order = belief.ranked()
        flags = agent.flags

        stalls = agent._stalls.get(sid, 0)
        decay = flags.stall_decay if state.paraphrased() else flags.stall_decay_clean
        hope = decay ** stalls
        V = max(0.0, flags.v_continue * hope - 0.0667)
        shipped = [r["parent_asin"] for r in result["recommendations"]]

        turns.append({
            "turn": turn, "message": msg,
            "escalated": False, "llm_out": [],       # deterministic submission: the tier is off
            "route": state.route, "category": state.category,
            "template_hits": state.template_hits,
            "constraints": [{"text": c.text, "attribute": c.attribute, "value": c.value,
                             "tier": c.tier, "weight": round(c.weight(state.turn), 3),
                             "demoted": c.demoted} for c in state.constraints],
            "pool_size": len(belief.candidates),
            "top_categories": [[c, round(m, 4)] for c, m in
                               agent.categories.ranked(state.history[0])[:3]],
            "entropy": round(belief.entropy(), 4),
            "stalls": stalls, "decay": decay, "hope": round(hope, 4), "V": round(V, 4),
            "depth": len(shipped),
            "excluded": sum(1 for a in proven_before if a in belief.log_p),
            "ranking": [{"asin": a, "title": agent.index.title[a], "p": round(post[a], 4),
                         "logp": round(belief.log_p[a], 3), "is_target": a == target}
                        for a in order[:10] if belief.log_p[a] != float("-inf")],
            "evidence": evidence(agent.index, state, belief, order[0]) if order else [],
            "shipped": [{"asin": a, "title": agent.index.title[a], "is_target": a == target}
                        for a in shipped],
            "hit": target in shipped,
            "reply": result["message"], "ask": result["ask_attribute"],
            "ms": round(elapsed_ms, 1),
            "prompt_tokens": result["usage"]["prompt_tokens"],
            "completion_tokens": result["usage"]["completion_tokens"],
        })
        return result

    agent._respond = wrapped
    subject = freeform.FreeFormAgent(agent, [sample]) if is_freeform else agent
    session = evaluate(subject, [sample], *harness.load_world()[1:])["sessions"][0]

    return {"id": name, "title": title, "sample_id": sample_id, "source": path,
            "scenario_type": sample["scenario_type"],
            "style": (sample.get("free_form") or {}).get("style"),
            "freeform": is_freeform, "target": target,
            "target_title": agent.index.title[target],
            "profile": sample.get("user_profile", {}),
            "hit": session["hit"], "best_rank": session["best_rank"],
            "first_hit_turn": session["first_hit_turn"], "turns": turns}


def main() -> None:
    data = [capture(*s) for s in SCENARIOS]
    out = ROOT / "demo" / "traces.js"
    out.write_text("window.DEMO_TRACES = " + json.dumps(data, indent=1) + ";\n")
    for d in data:
        sent = [t["turn"] for t in d["turns"] if t["hit"]]
        print(f"{d['id']:<10} {d['sample_id']:<13} turns={len(d['turns']):<3} hit={str(d['hit']):<5} "
              f"rank={d['best_rank']} sent_on={sent or '-'} llm_calls=0")
    print(f"-> {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
