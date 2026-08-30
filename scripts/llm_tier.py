"""R3 with the LLM extraction tier on. R1 measured its own tier at ~+0.07 under stress; R3 has never
been run with it. Escalation-gated: it fires only once no template has matched by turn 2, so clean
text should cost exactly zero calls."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import harness, race                    # noqa: E402
from src.eval.stress import ParaphraseRewriter        # noqa: E402

if __name__ == "__main__":
    print(f"{'level':<6s} {'tier':<5s} | {'hit':>6s} {'MRR':>7s} {'MTTC':>6s} {'SCORE':>7s} | "
          f"{'calls':>6s} {'fails':>6s}")
    for level in (0, 2, 3):
        for on in (False, True):
            agent = race.ROADS["r3"]()
            agent.flags.llm_extract = on
            if not on:
                agent.llm = None
            subject = harness.StressedAgent(agent, ParaphraseRewriter(level)) if level else agent
            r = harness.run(subject, dataset=harness.TRAIN_DATASET)
            calls = getattr(agent.llm, "calls", 0) if agent.llm else 0
            fails = getattr(agent.llm, "failures", 0) if agent.llm else 0
            print(f"L{level:<5d} {'on' if on else 'off':<5s} | {r['hit_rate_at_10']:>6.3f} "
                  f"{r['mrr']:>7.4f} {r['mttc']:>6.2f} {harness.score(r):>7.4f} | "
                  f"{calls:>6d} {fails:>6d}", flush=True)
