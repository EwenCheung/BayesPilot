# R2 — Retrieve & Rank

> **Road 🟢 R2 of three.** See [IDEA.md §0.3](../../IDEA.md). R1 is a filter, R2 is a ranker, R3 is a
> posterior. This document is binding on the R2 worktree: no code lands without a spec entry here and a
> failing test naming its acceptance ID in [02-acceptance.md](02-acceptance.md).

## The bet

**Meaning beats matching.** Score every candidate, order the list, and let good retrieval absorb whatever
rewording the organizer applies to the private set. R1 asks *"which products satisfy these constraints?"*
and intersects sets. R2 asks *"how well does each product explain what this customer said?"* and sorts.

The difference is not cosmetic. R1's `frozenset & frozenset` returns zero when a constraint string is
reworded by one character. R2 degrades continuously: a paraphrased constraint still scores partial token
overlap, still has a dense-similarity score, and popularity never moved at all.

## Why this road exists

[IMPORTANT.md §3](../../IMPORTANT.md) records the paraphrase risk: the spec reserves the right to add
natural-language paraphrasing, and a template-literal parser could score 0.96 publicly and collapse
privately. R2 is the hedge, and it is also literally the pipeline
[PROBLEM.md §4.2](../PROBLEM.md) Pillar I asks for: *"Multi-Route Retrieval → LLM Semantic Ranking"*.

## Architecture

```
user_message
     │
     ▼
  parse(msg, state) ──────────────► SessionState
     │                               slots · slot_age · disclosed · history
     ▼
  query = rewrite(state)
     │
     ├──► popularity route     log(rating_number)          paraphrase-proof
     ├──► spec-phrase route    soft phrase/token overlap   high precision, paraphrase-fragile
     ├──► lexical route        BM25 over catalog text      middle ground
     └──► dense route          SVD (offline) | bge-m3      semantic, survives rewording
     │
     ▼
  fuse(routes, w = f(confirmed_slots))     scheduled linear blend; RRF as baseline
     │
     ▼
  rerank    LightGBM → MMR (entropy-gated) → LLM listwise (escalation only)
     │
     ▼
  policy    NQC confidence → convert (ship 10) or ask ("other") + dynamic truncation
```

Four bounded roles, not agents ([IDEA.md §F](../../IDEA.md)): Router picks weights, State owns slots,
Cascade retrieves and ranks, Judge converts or asks.

## What R2 is measured on

⚠️ **R2's headline is not the clean score.** R1 already sits at 0.9607 with 193/200 sessions at rank 1;
the entire remaining clean-set headroom is ~7 sessions, inside the ±0.02 noise band that
[IMPORTANT.md §13.3](../../IMPORTANT.md) tells us to distrust. R2 is judged on:

| Metric | Meaning | Reference |
|---|---|---|
| `no_spec_phrase` ablation | private-set insurance — the score with inversion switched off | est. 0.826, **never measured end-to-end** |
| paraphrase-stressed score | what survives rewording | R1 unknown, expected to fall hard |
| clean score | sanity, not the point | R1 = 0.9607 |
| 4 scenario breakdowns | boundary is 10 sessions and is noise alone | — |

## Kill criteria

R2 **dies** if, after the dense route and the fusion schedule are in:
- its `no_spec_phrase` score does not clear **0.7133** (popularity + category alone), meaning the retrieval
  routes contribute nothing; or
- its stressed score is not better than R1's stressed score, meaning the hedge does not hedge.

R2 **wins** if it beats R1 under stress, whatever the clean numbers say.

## Non-negotiables

1. `Agent.__init__(self, catalog_path="data/catalog.jsonl")` — positional, defaulted.
2. **Never import from `evaluator.local_evaluator` inside the agent** — circular import, hard crash.
   Simulator functions are copied into [src/common/simulator.py](../../src/common/simulator.py).
   *Harness scripts may import it; only the agent module may not.*
3. Every turn returns a non-empty `message` and a valid `ask_attribute`.
4. `respond` is wrapped in try/except with a safe fallback — an exception is a silently forfeited turn.
5. Every LLM call asserts on a parsed non-empty result and increments `llm_call_failures` on failure
   ([IMPORTANT.md §13.1.3](../../IMPORTANT.md) — a silent model failure is indistinguishable from a model
   that is not helping).
6. The dense route must have an **offline backend**. The submission may be scored with network disabled,
   and unlike the reranker the dense route cannot simply be skipped — it has to embed the live query.
7. The kit stays byte-identical to upstream. The harness never writes to `starter/agent.py`.
