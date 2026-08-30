# R4 — Early Convergence *(the agent is a scheduler)*

> **Road 🟠 R4, the fourth.** R1 is a filter, R2 is a ranker, R3 is a posterior — all three answer
> *"which item?"*. R4 asks a different question: *"is what I have good enough to ship **now**?"*
> This document is binding on the R4 worktree: no code lands without a spec entry here and a failing
> test naming its acceptance ID in [02-acceptance.md](02-acceptance.md).

## The bet

**The remaining loss is not a ranking failure, it is a stopping failure.** R3 already puts the target
at rank 1 in 88.4% of sessions and inside the top 3 in 94.6%. What it does badly is *know when it is
done*: 232 of 2,000 sessions either stall to turn 6+ or never convert, and those sessions carry every
point still available.

R4 makes the ship/ask decision the object of study, driven by a **calibrated estimate of where the
target sits in the current ranking**, and measured offline against **when the target first entered the
top 3** rather than only where it ended up.

---

## 1. Why this road exists — the measurement that motivates it

R1, R2 and R3 were all tuned and reported on the 200-session `public_set.jsonl`. `dev.jsonl` supplies
**2,000 sessions whose target ASINs are disjoint from the public set** (verified: 0 overlap), which is
the first large out-of-sample instrument this project has had.

📊 **R3 on `dev.jsonl`, clean, `R3_OFFLINE=1`, `PYTHONHASHSEED=0`** — `src.eval.race` with
`harness.DATASET` repointed:

| | Hit@10 | MRR | MTTC | Score |
|---|---|---|---|---|
| R1 | 0.976 | 0.8969 | 2.72 | 0.9224 |
| R2 | 0.974 | 0.8970 | 2.75 | 0.9212 |
| R3 | 0.970 | 0.9167 | 3.05 | 0.9188 |

Two facts follow, and both are new.

### 1.1 🔑 The headroom has moved from MRR to Efficiency

| Term | Lost | Note |
|---|---|---|
| **Efficiency** | **0.0332** | MTTC 3.05 against the 1.39 structural floor |
| MRR | 0.0250 | of which misses 0.0092, rank 2–10 only **0.0159** |
| Hit@10 | 0.0152 | 61 sessions never converge |

⚠️ **This contradicts a standing claim.** [IMPORTANT.md §0](../../IMPORTANT.md) and
[REPORT.md Part 6](../../REPORT.md) both say *"all remaining headroom is MRR (+0.075 available vs
+0.012 from speed)"*. That was computed where Hit@10 = 1.000 and MTTC = 2.59. On 2,000 disjoint
sessions **speed is the largest single pot.** The docs are stale on this point; see
[03-decisions.md D1](03-decisions.md#d1).

### 1.2 🔑 The failure is perfectly bimodal

Cross-tabulating rank against turn over all 2,000 sessions:

```
(rank 1, turn ≤ 4) : 1768        (rank ≥ 2, turn ≥ 6) : 171        (miss) : 61
(rank 1, turn ≥ 6) :    0        (rank ≥ 2, turn ≤ 4) :   0
```

Every rank-1 hit lands on turns 1–4. Every rank-2-or-worse hit lands on turns 6–10. **Turn 5 is
empty.**

✅ **R4-A0 resolved this, and it was a bug worth more than the rest of the road put together.**
`depth()` admits item *k* only when `1/k > horizon`, and `stalls` cannot reach 3 before turn 6 — so
turns 4 and 5 re-ship a depth-1 list whose top item has not changed since turn 3. The session still
being alive is *proof* that item is not the target: 43 of 43 sessions alive at turn 5 shipped a
guaranteed miss. The general form is stronger than the bug — the evaluator breaks on first hit, so
**surviving a hit-checked turn proves every item shipped on it is not the target**, and a posterior
should absorb that. Implemented as `exclude_shipped`; it takes held-out `dev` test **0.9175 →
0.9473** with no fitted parameter. See [03-decisions.md D8](03-decisions.md#d8), and
[D9](03-decisions.md#d9) for the two versions that were unsound first.

### 1.3 🔑 The discriminator is constraint selectivity, not popularity or metadata richness

For each target, the ambiguity of its intent card = how many of the 50,000 catalog items share its
**most selective** constraint string:

| bucket | n | median ambiguity | best constraint shared by >500 items | median `rating_number` |
|---|---|---|---|---|
| rank 1, early | 1768 | **1** | 6.4% | 24 |
| slow / low rank | 171 | **189** | 40.9% | 25 |
| miss | 61 | **578** | 54.1% | **7** |

When `intent_card()` draws `"Department: Womens"` and `"Item Weight: 3.2 ounces"` instead of
`"leather"`, inversion cannot discriminate, and the popularity prior — R3's single largest
contributor — floats a popular impostor to rank 1 while the true target (median `rating_number` 7)
sinks. **The mechanism that carries the road is the one that kills its failures.**

🔑 **And for those sessions more turns cannot help.** The simulator holds exactly four constraint
strings; two `"other"` asks exhaust them. If all four are generic there is no further information in
the universe, so stalling to turn 6–10 is pure waste. **Detecting exhaustion is worth more than
asking better questions.**

---

## 2. What R4 changes, and what it does not

The proposal this road is built from is in the conversation record. Three of its parts are new and
load-bearing; three re-derive machinery R3 already has; one is measured-negative. Recording that split
here is the point of the document — see [03-decisions.md](03-decisions.md) for each.

| Proposed | Verdict | Where |
|---|---|---|
| Offline `FirstHit@3` / `EarlyHit@3(T)` metrics | ✅ **build** — the instrument this project lacks | §3 |
| Calibrated runtime top-k confidence | ✅ **build** — R3's #1 unbuilt item, now with a motivating failure | §4 |
| Exhaustion detection → ship early | ✅ **build** — the largest measured pot | §5 |
| Persistent candidate pool with history score | ⚠️ **already R3** — a posterior *is* accumulated evidence | [D2](03-decisions.md#d2) |
| Soft persistence, decay, no hard removal | ⚠️ **already R3** — `ℓ_min > 0`, every factor bounded below | [D2](03-decisions.md#d2) |
| Ask the attribute that best separates candidates | 🔴 **measured worse, and the simulator cannot answer it** | [D3](03-decisions.md#d3) |
| Dynamic truncation (show 3 or 5, not 10) | 🔴 **measured negative**, build behind a flag and report it | [D4](03-decisions.md#d4) |

### 2.1 ⚠️ Two premise corrections that change the design

**The evaluator breaks on first hit.** From `evaluate()`:

```python
if override_applied and target in ranked:
    best_rank = ranked.index(target) + 1
    hit_turn  = turn
    break
```

So the worked example *"Turn 1: A → #4, Turn 2: A → #2, Turn 3: A → #3"* **cannot happen for the
target**. The moment the target appears anywhere in a shipped list the session ends at that rank. A
target's rank never evolves across turns unless you never shipped it — or it is one of the 15%
`intent_override` sessions, where turns 1–2 are discarded.

Consequence: **`FirstHit@3` must be measured on the agent's *internal* ranking, never on shipped
lists.** Instrumented offline, it is a genuine and useful curve. Read off shipped lists it is
definitionally identical to the existing MTTC. This distinction is frozen in
[01-contracts.md §3](01-contracts.md).

**Top-3 confidence is the wrong gate; top-1 confidence is.** Reciprocal rank pays 1.000, 0.500,
0.333 for ranks 1, 2, 3. An agent that ships as soon as it believes the target is *somewhere* in the
top 3 will routinely ship rank 2 and 3 and give away 0.15–0.20 of RR per session. The correct object
is the full distribution `p₁ … p_k`, and the correct decision is expected utility over it — which is
what R3's policy already computes. **R4's contribution is making those `p_i` calibrated**, not
replacing the policy with a threshold.

---

## 3. Offline instrument: the EarlyHit curve

Ground truth is available offline, so instrument the agent's internal ranking every turn regardless of
whether it ships.

```
FirstHit@k(session) = min turn t such that target ∈ internal_ranking(t)[:k],  else ∞
EarlyHit@k(T)       = share of sessions with FirstHit@k ≤ T
```

📊 Baseline, R3 on `dev.jsonl` — the **shipped** curve, which is the ceiling the internal curve must
beat (the internal curve can only be earlier, never later):

| by turn | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 10 |
|---|---|---|---|---|---|---|---|---|
| cumulative converted | 11.6% | 52.9% | 79.5% | 88.4% | 88.4% | 92.8% | 94.5% | 97.0% |

The flat step at turn 5 is §1.2's anomaly made visible. **The goal of R4 is to raise the left-hand
side of this curve**: if the internal ranking has the target in the top 3 at turn 2 but the agent does
not ship until turn 6, that gap is pure recoverable Efficiency.

⚠️ **These metrics are diagnostic only and must never reach the agent at runtime.** A test enforces
it ([R4-A2](02-acceptance.md)).

---

## 4. Runtime: calibrated top-k confidence

R3's policy already maximises `U(k) = Σ_{i≤k} p_i/i + (1 − Σ_{i≤k} p_i)·V`. The `p_i` come from the
posterior and **have never been shown to be probabilities** — [SUMMARY §7](../r3-exploration/SUMMARY.md)
lists this as R3's top open item and names "confidently wrong" as the road's failure mode. §1.3 is
that failure mode caught in the act: on high-ambiguity sessions the posterior is confident and wrong.

R4 fits a calibrator `p̂ = g(features)` on the 50,000-product synthetic session generator
([IDEA.md §D](../../IDEA.md)), using isotonic regression, and reports a reliability curve and ECE.

Feature set — all observable at runtime, none derived from ground truth:

| Feature | Rationale |
|---|---|
| `p₁`, `p₁ − p₂`, `p₃ − p₄` | the posterior's own margin |
| **evidence selectivity** (min catalog frequency of matched constraint strings) | 🔑 §1.3's discriminator; a pre-retrieval QPP feature |
| share of stated constraints matched | partial-credit signal |
| NQC — std-dev of top-k posterior scores | standard query-performance prediction |
| turn index, consecutive barren turns | the stall signal R3 already uses |
| category posterior mass | level-1 confidence |
| rank stability of the top 3 across turns | the proposal's persistence signal, as a *feature* rather than a score |

🔑 **Selectivity is the feature that matters** and it is computable offline for all 50,000 products in
one pass. Everything else is already in R3's state.

---

## 5. Policy: exhaustion detection

Two regimes, separated by whether more conversation can still yield information:

```
if all four constraint strings are disclosed AND selectivity is low:
        the card is exhausted — no question can help — SHIP the best list now
else:
        continue the existing expected-utility policy
```

📊 **The direction is already confirmed.** `stall_decay_clean` is fitted at 0.8 on the 200-session set;
on `dev.jsonl`:

| | Hit@10 | MRR | MTTC | Score |
|---|---|---|---|---|
| baseline `stall_decay_clean=0.8` | 0.9695 | 0.9167 | 3.05 | 0.9188 |
| `stall_decay_clean=0.4` | **0.9740** | 0.9159 | **2.77** | **0.9263** |

**+0.0075 with Hit up and MRR flat** — a fitted constant that overfit 200 sessions. ⚠️ 0.4 was chosen
by looking at all of `dev.jsonl`, which spends it for this parameter. R4 re-fits on a train split and
reports on a held-out split ([01-contracts.md §4](01-contracts.md)).

This is also PROBLEM.md §4.3's *"compress decision paths"* in the brief's own vocabulary, and its
*"slot decay over time"* — both listed as unaddressed in [IMPORTANT.md §14](../../IMPORTANT.md).

---

## 6. Architecture

R4 is **not a rewrite.** It is R3's posterior with a calibrated head and a different stopping rule.

```
user_message
     │
     ▼
  parse (template → ontology → LLM escalation)          ← unchanged from R3
     │
     ▼
  LEVEL 1  P(category | evidence)  → pool by mass       ← unchanged from R3
     │
     ▼
  LEVEL 2  P(item | pool, evidence)                     ← unchanged from R3
     │      prior_weight·log1p(rating) + Σ w_t·log L(e_t | i)
     │
     ├──► selectivity(evidence)  ────────┐              ← NEW  §4
     │                                   ▼
     ├──► exhaustion(disclosed, turn) ─► CALIBRATOR  p̂₁ … p̂ₖ    ← NEW  §4
     │                                   │
     ▼                                   ▼
  POLICY   ship k maximising U(k) over the CALIBRATED p̂    ← NEW head, same formula
     │     exhausted → ship now                             ← NEW  §5
     ▼
  recommendations (always 10 — see D4)
```

Everything above the two NEW boxes is lifted from `src/r3/` unchanged. If the calibrator is the
identity and exhaustion never fires, **R4 must reproduce R3 bit-for-bit** — that is [R4-A1](02-acceptance.md),
and it is the test that keeps this road honest about what it is contributing.

---

## 7. What R4 is measured on

⚠️ **Not the clean 200-session score.** It is saturated and a 0.02 gap there is noise. R4 is judged on
`dev.jsonl`, split, with the clean 200 reported only as a non-regression check.

| Metric | Reference | Target |
|---|---|---|
| **`dev.jsonl` held-out score** | R3 = 0.9188 | ≥ 0.9263 |
| **`EarlyHit@3(2)`** — internal top-3 by turn 2 | unmeasured | the road's headline curve |
| **MTTC** | 3.05 | ≤ 2.80 |
| **Hit@10** | 0.9695 | ≥ 0.9695, must not fall |
| ECE / reliability curve | unmeasured | the calibration claim, evidenced |
| L2 / L3 paraphrase | R3 = 0.8857 / 0.8299 | must not regress |
| clean 200 | R3 = 0.9731 | within noise |

## 8. Kill criteria

R4 **dies** if:
- calibration does not improve held-out `dev` score over R3's 0.9188 by more than the bootstrap CI
  width, **and** the reliability curve shows the posterior was already calibrated — meaning the
  premise of §4 was wrong; or
- exhaustion detection cannot beat the single tuned constant `stall_decay_clean=0.4`, meaning the
  machinery buys nothing a scalar did not; or
- Hit@10 falls below R3's 0.9695 — trading recall for speed is the one trade this metric never rewards.

R4 **wins** if the EarlyHit@3 curve moves left with Hit@10 held flat.

## 9. Non-negotiables

1. `Agent.__init__(self, catalog_path="data/catalog.jsonl")` — positional, defaulted.
2. **Never import `evaluator.local_evaluator` from agent code** — circular import, hard crash.
3. Every turn returns a non-empty `message` and a valid `ask_attribute`; `respond` is wrapped in
   try/except.
4. Ground-truth-derived quantities never reach runtime. Enforced by test, not by discipline.
5. The kit stays byte-identical to upstream; the harness never writes to `starter/agent.py`.
6. Every number in this file cites the run that produced it. No number without a source.
7. **Tune on `dev` train, report on `dev` test.** A threshold chosen while looking at the test split
   has spent it.
