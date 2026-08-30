# R4 — acceptance criteria

Every ID names **the number it must hit** and **the test that proves it**. No implementation is
written before its ID exists here and its test fails for the right reason
([00-r4-spec.md §9](00-r4-spec.md)).

Status: `⬜ open` · `🟩 passed` · `🟥 failed` · `⬛ explained` (did not pass; reason recorded in
[03-decisions.md](03-decisions.md)).

All numbers are on `dev.jsonl` under `R3_OFFLINE=1 PYTHONHASHSEED=0` unless stated otherwise.
**Fitting set is `train.jsonl` (12,000).** Baseline R3 on train = **0.9235**; on the dev test set
0.9188 and on public 200 0.9731, both read for reporting only.

---

## Phase F — foundation (blocks everything) — 🟩 **COMPLETE**

📊 Result: `exclude_shipped` takes held-out `dev` test **0.9175 → 0.9473 (+0.0298)**, non-overlapping
bootstrap CIs, and improves every one of the six measured conditions. Full table in
[03-decisions.md D8](03-decisions.md#d8); the two failed versions are [D9](03-decisions.md#d9).

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R4-A0** 🟩 | The turn-5 gap is explained **and fixed**. Cause: `depth()` adds item *k* only when `1/k > horizon`, and `stalls` cannot reach 3 before turn 6 — so turns 4–5 re-ship a depth-1 list whose top item has not changed, which the session being alive already proved wrong. Fix: `exclude_shipped`. | D8, D9 | 🟩 |
| **R4-A1** 🟩 | 🔑 With every new flag off, R4 reproduces R3 **bit-for-bit** — 0 of 200 and **0 of 2000** sessions differ on rank AND turn. | `tests/test_r4_reduces_to_r3.py` | 🟩 |
| **R4-A2** 🟩 | No ground-truth ASIN reaches `Agent.respond`; `src/r4/` imports no offline-only module. | `tests/test_r4_isolation.py` (AST + signature) | 🟩 |
| **R4-A3** 🟩 | Dataset contract: `train.jsonl` 12000 / `dev.jsonl` 2000 / public 200, target ASINs **mutually disjoint**, identical 40/40/15/5 mix, and **no fitting code names an evaluation set** (AST-enforced). Supersedes the deleted `devsplit.py`. | `tests/test_datasets.py` | 🟩 |
| **R4-A4** 🟩 | `src/r4/` imports from `src/r3/` only; no import of `src/r1/` or `src/r2/`, and never the evaluator. | `tests/test_r4_isolation.py` (AST) | 🟩 |

🔴 **KILL GATE on R4-A1.** If R4 cannot reproduce R3 exactly with its new parts disabled, the two
systems differ somewhere unaccounted for and every subsequent delta is uninterpretable. Stop and find
it before measuring anything.

---

## Phase I — the offline instrument — 🟩 **COMPLETE** (and it killed Phase C)

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R4-A5** 🟩 | `TurnTrace.internal_ranking` captured **before** the ship/hold decision — a held turn still records a full ranking. | `tests/test_instrument.py` | 🟩 |
| **R4-A6** 🟩 | `FirstHit@k` differs from MTTC on ≥ 20% of sessions — the turn-2 gap is **0.241**. | `tests/test_instrument.py` | 🟩 |
| **R4-A7** 🟩 | `EarlyHit@{1,3,10}(T)` published for T = 1…10 beside the shipped curve, on `train.jsonl`. | `scripts/earlyhit.py`, [D12](03-decisions.md#d12) | 🟩 |
| **R4-A8** 🟥 | The recoverable Efficiency is quantified — **and it is +0.0033**, below the CI width. Oracle stopping (ship the instant the target hits internal rank 1) moves MTTC only 2.704 → 2.538. 🔴 **Gate fires: Phase C is not built.** | [D12](03-decisions.md#d12) | 🟥 |

⚠️ **R4-A8 is the go/no-go for Phase C.** If the internal ranking has the target in the top 3 barely
earlier than the agent ships, there is nothing for a better stopping rule to recover and the road
should stop here with that negative result written up.

---

## Phase S — selectivity-scaled prior

⚠️ **Re-aimed by [D13](03-decisions.md#d13).** The original IDs assumed a recall problem and an
exhaustion mechanism. Probing the full internal ranking showed the target is in the level-1 pool in
**3000 of 3000** sessions — there is no recall failure — and that the residual is level 2 ranking the
target at median position **69 of 335**. Exhaustion is not the lever; the prior's weight is.

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R4-A9** 🟩 | Selectivity computed **at runtime from the pool** — no offline table needed, since `constraint_terms` already returns per-candidate matches. `flatness()` = pool fraction matched by the most selective live constraint. | `tests/test_selectivity.py` | 🟩 |
| **R4-A10** ⬜ | `flatness` is **bimodal between wins and losses** — median materially higher for misses than for rank-1 hits. If it is not, the gate is scaling by noise and no tuning can rescue the mechanism. | `scripts/` sweep + `tests/test_selectivity.py` | ⬜ |
| **R4-A11** ⬜ | `prior_damp > 0` beats `prior_damp = 0` on the train objective (mean of L0/L2/L3), **and does not regress L0**. Scaling the prior must not cost the 96% that already work. | `scripts/fit_r4.py` sweep | ⬜ |
| **R4-A12** ⬛ | Exhaustion must beat a refitted `stall_decay_clean`. **Re-fit on train: it does not matter.** 0.8/0.6/0.4/0.2 span 0.9473-0.9492 on train[:4000] and 0.9505 vs 0.9509 on all 12000 — inside overlapping CIs. Its earlier apparent +0.0075 on dev was compensating for the re-shipping bug (D11). Constant left at its R3 default. | `scripts/fit_r4.py` | ⬛ |

🔴 **KILL GATE on R4-A10.** If `flatness` does not separate wins from losses, the mechanism is
scaling the prior by noise. Record the negative and stop — the residual 1.5% would then need a
different signal entirely, not a better-tuned one.

---

## Phase C — calibration — 🔴 **NOT BUILT.** R4-A8 capped it at +0.0033; see [D12](03-decisions.md#d12).

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R4-A13** ⬛ | *(not built — R4-A8)* Isotonic calibrator fitted on synthetic sessions from the 50k generator, never on `dev` test. | `tests/test_calibrate.py` | ⬜ |
| **R4-A14** | Reliability curve and **ECE published**. This is the claim R3 made and never evidenced. | `docs/R4-RESULTS.md` §4 | ⬜ |
| **R4-A15** | Calibrated ECE < uncalibrated ECE on the held-out split. If the posterior was already calibrated, record it — that is a real result and kills §4 of the spec. | `tests/test_calibrate.py` | ⬜ |
| **R4-A16** | 🔑 On the **high-ambiguity** subset specifically, calibrated confidence is lower than uncalibrated. §1.3 says the posterior is confidently wrong exactly there; calibration must fix that or it has not addressed the failure. | `tests/test_calibrate.py` | ⬜ |
| **R4-A17** | Per-turn cost of features + calibrator < 10 ms p95; total run stays within 2× R3's wall-clock. | `tests/test_latency.py` | ⬜ |

---

## Phase R — the verdict

| ID | Criterion | Target | Status |
|---|---|---|---|
| **R4-A18** | Held-out `dev` test score | **> 0.9263**, CI-separated from R3's 0.9188 | ⬜ |
| **R4-A19** | Hit@10 does not regress | **≥ 0.9695** | ⬜ |
| **R4-A20** | MTTC | **≤ 2.80** (from 3.05) | ⬜ |
| **R4-A21** | `EarlyHit@3(2)` moves left vs the R3 baseline | measured, published | ⬜ |
| **R4-A22** | L2 / L3 paraphrase do not regress | ≥ 0.8857 / 0.8299 | ⬜ |
| **R4-A23** | Clean 200-session score does not regress | within noise of 0.9731 | ⬜ |
| **R4-A24** | Bootstrap CI, 1,000 resamples, reported beside every headline number | — | ⬜ |
| **R4-A25** | Registry row in `runs/registry.jsonl`, pinned to a git SHA, with all four scenario breakdowns | — | ⬜ |

⚠️ **R4-A19 is not negotiable.** Hit@10 carries weight 0.50. Trading recall for speed is the one
trade this metric never rewards, and it is the most likely way for this road to look good on MTTC
while losing.

---

## Phase D — the named brief requirements

Built because PROBLEM.md names them, measured honestly, reported even when negative
([IMPORTANT.md §14](../../IMPORTANT.md)).

| ID | Criterion | Expected | Status |
|---|---|---|---|
| **R4-A26** | Dynamic truncation implemented behind `truncate` (default 0) | measured **negative**; k=7 → Hit 0.9630 vs 0.9695, k=3 → 0.9455 | ⬜ |
| **R4-A27** | The exact score cost of `truncate ∈ {3,5,7}` published, not the lower bound | `docs/R4-RESULTS.md` §5 | ⬜ |
| **R4-A28** | "Slot decay over time" (§4.3) named and measured — exhaustion detection is its implementation | — | ⬜ |
| **R4-A29** | "Compress decision paths" (§4.3) mapped onto the stopping rule in the write-up | — | ⬜ |
