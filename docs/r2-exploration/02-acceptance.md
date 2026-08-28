# Acceptance criteria

Every criterion has an ID. Every test names its ID in the docstring. No implementation lands before its
test fails for the right reason.

Fast tests: `python3 -m unittest discover tests -v` (no evaluator, seconds).
Gates: `python3 -m unittest tests.test_gates -v` (runs the real evaluator, ~1 min each).

| ID | Criterion | Gate | Proven by |
|---|---|---|---|
| **R2-A0** | The harness is trustworthy: it reproduces two independently known numbers through our own runner, without touching `starter/agent.py`. | starter = **0.10671**, R1 = **0.9607**, both exact | `test_gates.test_a0_harness_calibration` |
| **R2-A1** | Simulator functions copied into `src/common/simulator.py` are byte-equivalent in behaviour to the evaluator's, over all 50,000 catalog rows. | 0 mismatches | `test_simulator_parity` |
| **R2-A2** | State accumulates across turns and **erases** on override rather than stacking a contradiction. | unit | `test_state` |
| **R2-A3** | The ranker skeleton reproduces the popularity-only baseline through the full R2 pipeline. | ≥ **0.7133** | `test_gates.test_a3_popularity_floor` |
| **R2-A4** | The paraphrase-proof floor, measured **end-to-end through the evaluator** for the first time — `no_spec_phrase`, real turns, real elicitation. The 0.826 in the docs is an offline estimate built from an oracle query over a public-set-derived pool; this replaces it. | report actual; ≥ **0.7133** or R2 is dead | `test_gates.test_a4_no_spec_phrase_floor` |
| **R2-A5** | Agent contract conformance: positional `__init__`, `reset` clears session state, `respond` always returns a valid dict with non-empty `message` and legal `ask_attribute`, and survives a poisoned catalog row. | unit | `test_contract` |
| **R2-A6** | Fusion: the scheduled linear blend beats RRF on the same candidates and routes. | blend > RRF | `test_gates.test_a6_blend_beats_rrf` |
| **R2-A7** | Full R2 clean score. | report vs R1 **0.9607** | `test_gates.test_a7_clean` |
| **R2-A8** | Paraphrase stress: R2's stressed score exceeds R1's stressed score. **This is the race.** | R2 > R1 stressed | `test_gates.test_a8_stress_race` |
| **R2-A9** | The dense route has a working offline backend and the agent runs with the network disabled. | runs, score reported | `test_gates.test_a9_offline` |
| **R2-A10** | LLM listwise rerank: measured on top of the blend, with `llm_call_failures` reported. Answers [IDEA.md Part II Q1](../../IDEA.md) — does its +0.19 MRR overlap with the blend's gain? | report Δ and failures | `test_gates.test_a10_llm_rerank` |

## Rules for a reported number

1. Kit verified unmodified (`git status` clean under `techjam-conversational-search-main/`).
2. All four scenario breakdowns present.
3. Stressed score reported beside clean. Winning clean and losing stressed is not winning.
4. `no_spec_phrase` reported — the private-set insurance estimate.
5. `llm_call_failures` reported.
6. Bootstrap CI over 1,000 resamples before any winner is declared. A 0.02 gap is one or two sessions.
