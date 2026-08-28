# R3 — acceptance criteria

Every ID names **the number it must hit** and **the test that proves it**. No implementation is written
before its ID exists here and its test fails for the right reason
([00-r3-spec.md](00-r3-spec.md) §9).

Status: `⬜ open` · `🟩 passed` · `🟥 failed` · `⬛ explained` (did not pass; the reason is understood
and recorded in [03-decisions.md](03-decisions.md)).

---

## Phase M — merge (blocks everything)

| ID | Criterion | Test | Status |
|---|---|---|---|
| M1 | R1's 59 pytest + R2's 38 unittest pass as one suite | `pytest tests/` | ⬜ |
| M2 | Unified harness reproduces starter `0.106710` and seed `0.9607` **exactly** | `tests/test_gates.py` | ⬜ |
| M3 | R1 clean = `0.9597`, R2 clean = `0.9707` on the unified harness | `src.eval.race --roads r1,r2` | ⬜ |
| M4 | Kit byte-identical to upstream before and after every run | `src/eval/kit_manifest.json` check | ⬜ |
| M5 | No module under `src/` imports `evaluator.local_evaluator` | `tests/test_imports.py` (AST) | ⬜ |
| M6 | Two subprocess index builds are byte-identical | `tests/test_determinism.py` | ⬜ |
| M7 | One `no_spec_phrase` definition applied to both roads; corrected numbers published | `04-merge-plan.md` §7 filled | ⬜ |
| M8 | 140/60 manifest: disjoint on sample ID **and** target ASIN, scenario-stratified, content-hashed | `tests/test_holdout.py` | ⬜ |

⚠️ **M3 is score-neutrality on clean only.** The stress and ablation numbers are *expected* to move —
that is the merge's output, not a regression (see [04-merge-plan.md](04-merge-plan.md) §5).

---

## Phase P1 — the posterior core

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R3-A1a** | With a degenerate 0/1 likelihood and `ℓ_min → 0`, the posterior's candidate set equals R1's `survivors()` on ≥95% of the 200 sessions | `tests/test_generalisation.py` | ⬜ |
| **R3-A1b** | With flat calibration and R2's weights as log-likelihood coefficients, the posterior's top-10 equals R2's blend on ≥95% of sessions | `tests/test_generalisation.py` | ⬜ |
| R3-A9 | A term that abstains returns `{}` and provably cancels in the normalisation | `tests/test_likelihood.py` | ⬜ |
| R3-A10 | No evidence term can drive any item's posterior to zero (`ℓ_min > 0`) | `tests/test_likelihood.py` | ⬜ |
| **R3-A2** | Clean score ≥ `0.9607` (within 0.01 of R2's 0.9707) | `src.eval.race` | ⬜ |
| R3-A11 | Per-turn cost: posterior update + EIG over the pool < 50 ms p95 | `tests/test_latency.py` | ⬜ |

🔴 **KILL GATE.** If R3-A2 fails with hand-set likelihood parameters, the likelihood family is
mis-specified and calibration downstream cannot repair a wrong model. Stop, write the negative result,
ship the better of R1/R2 on the unified harness.

---

## Phase P2 — the level-1 category belief

**This is the phase the road exists for.** All measured headroom is here, and today both roads pick the
pool by counting shared words ([00-r3-spec.md](00-r3-spec.md) §2.3).

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R3-A27** | Level-1 category accuracy under L3 paraphrase ≥ **0.95** (R1 measures **0.85**) | `tests/test_category_belief.py` | ⬜ |
| **R3-A3** | Stressed Hit@10 ≥ **0.90** (best current: R2 `no_spec_phrase` 0.890, R1 L3 0.820) | `src.eval.race --stress` | ⬜ |
| R3-A12 | Clean score unchanged by widening (within 0.005) — the pool opens only when the belief is diffuse, exactly as R1's hedge measured 0.0000 on clean | `src.eval.race` | ⬜ |
| R3-A13 | `τ_mass` replaces `hedge(keep=0.6)`, the top-3 cutoff and the 4000 cap; none of those constants survive in `src/r3/` | `tests/test_constants.py` | ⬜ |
| R3-A14 | Pool size bounded: p95 candidates ≤ 8000, so R3-A11 still holds | `tests/test_latency.py` | ⬜ |
| R3-A28 | Per-constraint evidence terms, not one fused query — each constraint updates the belief independently | `tests/test_likelihood.py` | ⬜ |

⚠️ **R3-A27 is the isolated version of the fix and should be measured first**, before it is entangled
with level 2. If category accuracy does not move, the §2.3 diagnosis is wrong and P2 should be
re-planned rather than tuned.

## Phase P3 — calibration

| ID | Criterion | Test | Status |
|---|---|---|---|
| R3-A15 | Synthetic session generator produces correctly-labelled sessions for arbitrary catalog items; 100 hand-checked | `tests/test_synthetic.py` | ⬜ |
| R3-A16 | Calibrators are fitted **only** on synthetic sessions — never on `public_set.jsonl` | `tests/test_no_leak.py` | ⬜ |
| **R3-A7** | ECE and a reliability curve reported for the calibrated posterior | `docs/R3-RESULTS.md` | ⬜ |
| R3-A17 | Calibrated beats uncalibrated on the stressed number by ≥ 0.01, or calibration is reported as not earning its place | `src.eval.race --ablate no_calibration` | ⬜ |

---

## Phase P4 — entropy replaces the gates

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R3-A6** | Tuned-constant count materially below [00-r3-spec.md](00-r3-spec.md) §4's "before" (~45 → ~3 + fitted) | `tests/test_constants.py` | ⬜ |
| R3-A18 | Override sessions still ship nothing before the override lands; override MTTC ≥ 3.60 floor, not below | `tests/test_policy.py` | ⬜ |
| R3-A19 | EIG question selection reported **against** hardcoded `"other"`; a −0.001 delta is reported as a loss, not a win | `src.eval.race --ablate no_infogain` | ⬜ |
| R3-A20 | MTTC ≤ R2's 2.08 with MRR not worse | `src.eval.race` | ⬜ |

---

## Phase P5 — the model switch matrix

[00-r3-spec.md](00-r3-spec.md) §6.0 is the scope audit; §6.1 is the matrix. Every backend is measured on
**stressed** and **`no_spec_phrase`**, at **both** belief levels, on the same harness.

| ID | Criterion | Test | Status |
|---|---|---|---|
| R3-A21 | Embeddings are a **build-time** artifact; the runtime imports numpy only — no torch, no transformers | `tests/test_runtime_deps.py` (AST) | ⬜ |
| R3-A22 | Full matrix reported: `tfidf_svd` · `bge_m3` · `blair_base` · `blair_large` · `qwen3_emb_0.6b`, × {level 1, level 2} | `docs/R3-RESULTS.md` | ⬜ |
| **R3-A23** | 🔴 The winning backend beats `tfidf_svd` by ≥0.01 stressed, **or `tfidf_svd` ships** and the matrix is reported as a negative result | `03-decisions.md` D6 | ⬜ |
| R3-A29 | 🚫 No image or multi-modal model anywhere — PROBLEM.md §4.3 | `tests/test_scope.py` | ⬜ |
| R3-A30 | No vector DB; embeddings are one in-memory matrix. Peak RSS reported | registry row | ⬜ |
| R3-A31 | Every dependency declared with a version, split build-time vs runtime | `requirements*.txt` | ⬜ |
| **R3-A8** | Zero network calls on the default path; `R3_OFFLINE=1` is bit-identical to the networked run | `tests/test_offline.py` | ⬜ |

## Phase P6 — the race, then re-plan

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R3-A4** | Stressed and `no_spec_phrase` beat `max(R1, R2)` by more than the bootstrap CI | `src.eval.race --all --bootstrap` | ⬜ |
| **R3-A5** | Held-out 60 within its CI of the 140-tuned score | `src.eval.race --holdout` | ⬜ |
| R3-A24 | All four scenario breakdowns reported for all three roads | `docs/R3-RESULTS.md` | ⬜ |
| R3-A25 | `llm_call_failures`, latency p50/p95, token usage and estimated USD disclosed | registry row | ⬜ |
| R3-A26 | **Re-plan pass**: with the final numbers in hand, an explicit written review — is this the best available design, what would be reorganised, what is still open — before anything is called final | `docs/r3-exploration/SUMMARY.md` §"what I would change" | ⬜ |

⚠️ **R3-A26 is a real gate, not a formality.** The final answer is delivered only after re-running
everything on the final code and stating plainly what is still wrong with it.

---

## Standing honesty requirements

Every run recorded in `runs/registry.jsonl` must carry:

1. all four scenario breakdowns (⚠️ boundary is 10 sessions — report it, never read it alone);
2. a paraphrase-stressed score beside the clean one;
3. the `no_spec_phrase` ablation, in the **unified** definition;
4. the held-out 60 score;
5. `llm_call_failures`;
6. a git SHA;
7. a kit SHA-256 verification that passed.

A row missing any of these does not count.
