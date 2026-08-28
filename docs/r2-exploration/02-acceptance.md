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


---

## Measured outcomes

Run `python3 -m src.eval.final`; raw log in `runs/final.log`, rows in `runs/registry.jsonl`.
Kit verified pristine on the run that produced these.

| ID | Gate | Result | |
|---|---|---|---|
| R2-A0 | starter 0.10671 · R1 0.9607, exact | both exact, kit untouched | ✅ |
| R2-A1 | 0 simulator mismatches over 50,000 rows | 0 | ✅ |
| R2-A2 | accumulate, erase on override, decay | 15 unit tests | ✅ |
| R2-A3 | ≥ 0.7133 popularity floor | 0.6919 | ⚠️ see note |
| R2-A4 | paraphrase-proof floor, end-to-end | **0.8315** (docs estimated 0.826) | ✅ |
| R2-A5 | contract conformance | 9 unit tests | ✅ |
| R2-A6 | blend > RRF | 0.9707 vs 0.8625 | ✅ |
| R2-A7 | clean vs R1 0.9607 | **0.9707**, CI [0.9630, 0.9774] | ✅ tie |
| R2-A8 | R2 stressed > R1 stressed | **0.7961 vs 0.0000** | ✅ decisive |
| R2-A9 | runs offline | offline backend is the default; 0.9707 | ✅ |
| R2-A10 | LLM rerank measured, failures reported | see `runs/rerank_retry.log` | ✅ |

⚠️ **R2-A3 note.** The popularity-only configuration scores 0.6919 through R2's pipeline against the
0.7133 reference. Hit@10 (0.815) and MRR (0.4981) match the reference *exactly*; the whole gap is MTTC
(4.25 vs 3.18). That is R2's confidence-scaled truncation behaving correctly on a route that carries no
confidence signal: with only popularity, the fused scores are smooth, the leader margin is tiny, and the
policy ships a shallow list for longer. It is the ablation being handicapped by a policy built for
richer evidence, not a retrieval regression — so the gate is recorded as explained rather than passed.

**Bootstrap.** R2 [0.9630, 0.9774] and R1 [0.9543, 0.9666] overlap. The clean difference is **not
significant** and must be reported as a tie.
