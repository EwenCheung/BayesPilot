# R1 — implementation plan and verification log

Companion to [r1-constraint-satisfaction.md](r1-constraint-satisfaction.md). Each step names the test that
proves it. Test-first throughout: the test was written and seen failing before the module existed.

| # | Step | Verified by | Status |
|---|---|---|---|
| 1 | Worktree, catalog link, pytest, pristine baseline reproduced (0.10671) | official evaluator run | ✅ |
| 2 | `src/common/simulator.py` — mirrored referee logic | `test_simulator_mirror.py` — 2,000 catalog rows, 4 functions, plus an AST guard that no agent module imports the evaluator | ✅ |
| 3 | `src/common/contracts.py` — `SessionState`, `Constraint`, decay, demotion | `test_parse.py::test_slot_decay_downweights_stale_constraints` | ✅ |
| 4 | `src/common/attributes.py` — normalised ontology + paraphrase cues | `test_catalog_and_attributes.py` (6 parametrised pairs, never-raises, paraphrase tolerance) | ✅ |
| 5 | `src/common/catalog.py` — lazy pool-scoped index, fuzzy category recovery | `test_catalog_and_attributes.py` (50,000 rows indexed, unknown category non-empty, cached pools, ordered card strings) | ✅ |
| 6 | `src/common/parse.py` — template / ontology / LLM tiers | `test_parse.py` (12 tests: every template, override erasure, dead-end memory, paraphrase, escalation policy) | ✅ |
| 7 | `src/common/llm.py` — cache, retries, failure counter, offline mode | `test_llm.py` (8 tests incl. empty-content-is-a-failure and malformed-permutation-falls-back) | ✅ |
| 8 | `src/r1/{filter,question,rank,policy,agent}.py` | `test_agent_contract.py` (8 tests: signature, shape, garbage input, reset isolation, override silence, patience-then-deadline, set shrinkage) | ✅ |
| 9 | `src/eval/{run,stress,compare,ablate,embed}.py` | `test_harness.py`, `test_stress.py` (scoring arithmetic vs the evaluator, seeded bootstrap, kit SHA manifest, every template destroyed at L2) | ✅ |
| 10 | Full 50,000-product `bge-m3` embedding | `.cache/embeddings.npz` (50000, 1024), 0 failures | ✅ |
| 11 | Measurement matrix — 27 runs, clean + 4 stress levels + 17 ablations | `runs/registry.jsonl`, every row with a bootstrap CI | ✅ |

## Defects this process caught

| Found by | Defect | Fix |
|---|---|---|
| scenario breakdown | override MRR 0.560 vs 0.98 elsewhere — override was deleting still-true constraints | demote to weight 0.35 instead of deleting (+0.024 overall) |
| two identical runs disagreeing | `card_strings` was a `set`; the information-gain model sampled it in hash order | ordered tuple in the simulator's own order, `PYTHONHASHSEED=0` |
| stress run below the popularity-only baseline | attribute-level matches were allowed to shrink `S` and filtered the target out | only exact matches may shrink (`shrink_min = 1.0`) |
| stress category audit | 21/200 pools resolved to the wrong category | `hits² / |category tokens|`, verbatim match first |
| `llm.failures` counter | 548/1042 embedding batches silently rate-limited at 12-way parallelism | 4 workers, content-hash cache made the retry free |
| `git status` on the kit | LLM cache was being written inside the kit (runs execute with `cwd=<kit>`) | absolute cache path, kit SHA re-verified after every run |
