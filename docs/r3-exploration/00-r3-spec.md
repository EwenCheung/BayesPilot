# R3 — Bayesian Fusion: the spec

**Branch:** `r3-exploration` · **Worktree:** `../r3-bayesian` · **Status:** spec written, nothing built

This document is **binding**. Behaviour that is in the code but not here is a bug in one of them.
Read [04-merge-plan.md](04-merge-plan.md) first — R3 cannot start until the merge lands and is proved
score-neutral.

---

## 1. The bet

R1 and R2 are not rivals. They are two kinds of **evidence** about one question — *which of these 50,000
products is the customer describing?* — and the right way to combine evidence is a posterior.

```
P₀(item) ∝ popularity                        the 570× target skew IS a prior
each turn:  P(item) ∝ P(item) · L(uₜ | item) every utterance is evidence
            search wide enough that Σ P over the pool ≥ τ_mass
            ask  argmax_a  H(P) − 𝔼_r[H(P | a,r)]
            ship the top-k where cumulative mass ≥ τ_ship
            convert when H(P) < τ_convert
```

Set `L` to hard 0/1 and you recover R1. Read the posterior as a score and ignore its normalisation and
you recover R2. **R3 is the generalisation both roads are special cases of** — that is the claim, and
§7 A1 is the test that proves it rather than asserting it.

### 1.1 Why this is not a bet on something new

Both roads independently converged on the same finding by opposite routes:

| Road | Finding | Number |
|---|---|---|
| R1 | removing the popularity prior is the single most damaging ablation under stress | **−0.2422** |
| R2 | *raising* popularity back up with a full constraint card, against intuition, helps | **+0.0091** |
| R2 | *"a prior matters most exactly where the evidence stops discriminating"* | its own §3.2 |

That is a Bayesian statement in both cases. R3's framing **describes what already empirically works**;
it does not gamble on a new mechanism. What it adds is that the prior, the evidence and the decision
become **one object with one number** instead of three hand-tuned subsystems.

---

## 2. What changed from IDEA.md §0.3 — read this

IDEA.md scopes R3's posterior to **ranking and stopping**. The measurements taken since say that is
aimed at the wrong place.

**Clean is saturated.** R2 reached MRR 0.9746 / MTTC 2.08 / score 0.9707. The theoretical maximum is
0.9922, so clean headroom is **0.0215** — and CLAUDE.md trap 7 says a 0.02 gap on 200 sessions is
noise. **R3 cannot win on the clean set, and a clean-only win is not a win** (§8).

**Every number that estimates the private set is a recall failure, not a ranking failure:**

| Condition | Hit@10 | Score |
|---|---|---|
| R1 @ L3 paraphrase | 0.820 | 0.7246 |
| R2 heavy paraphrase | 0.845 | 0.7961 |
| R2 `no_spec_phrase` | 0.890 | 0.8315 |
| — a teammate's non-inversion pipeline, same 200 sessions | **0.995** | 0.9044 |

15–18% of stressed sessions never had the target in the returned list at all. **A posterior that only
reorders cannot fix that**, because a posterior over a pool that excludes the target is worth zero no
matter how well calibrated it is.

**So R3's posterior does three jobs, not two:**

| Job | Replaces | Where the points are |
|---|---|---|
| **how wide to search** | R1's `hedge(keep=0.6)`, R2's fixed 4000 cap | ⬅ **here** |
| how to order | R2's two weight schedules + regime switch | saturated |
| when to stop / how deep | R1's NQC 0.35 + deadline 3, R2's 4-rung ladder | ~0.012 |

Opening the pool by **posterior mass** rather than a tuned constant is not a bolt-on: it is the most
natural thing a belief lets you do, and it is the only stage aimed at measured headroom. Dropping it
makes R3 a rename of R2 with Greek letters.

---

## 3. Architecture

R3 is **one system**, not a shim over two others.

```
                       ┌───────────────────────────────────────┐
utterance ─── parse ──►│  Evidence  eₜ = (constraints, category)│
                       └────────────────┬──────────────────────┘
                                        ▼
              ┌──────────────────── BELIEF ────────────────────┐
              │  log P(item) = log P₀(item) + Σₜ log L(eₜ|item)│
              │  P₀ ∝ log1p(rating_number), pool-normalised     │
              └───┬───────────────┬───────────────┬────────────┘
    pool width ───┘               │ order         └─── H(P), mass
    Σ P ≥ τ_mass                  ▼                     │
    (RECALL)              top-k by P (RANK)              ▼
                                                  ask / ship / convert
                                                      (POLICY)
```

One number — the posterior — drives all three. There is no separate confidence signal, no separate
regime switch, and no separate stopping heuristic.

### 3.1 The likelihood family

`L(e | item)` is a product of independent **evidence terms**, each a bounded factor in `[ℓ_min, 1]`
so that no single term can zero out an item (an item that survives no evidence must still be
reachable — this is R1's relaxation rule, expressed as arithmetic instead of a special case):

| Term | Signal | Origin |
|---|---|---|
| `exact` | the constraint string appears verbatim in the item's own spec phrases | R1's sharp matcher |
| `attribute` | the normalised `(attribute, value)` pair matches | R1's ontology matcher |
| `lexical` | IDF-weighted content-token overlap | R2's lexical route |
| `semantic` | cosine between the rewritten query and the item embedding | R2's dense route |

**These are R3's terms, written in R3's vocabulary against R3's index.** They are informed by R1 and R2
and in places lifted from them, but `src/r3/` imports nothing from `src/r1/` or `src/r2/` — see
[01-contracts.md](01-contracts.md) §3, which is enforced by a test, not by discipline.

🔑 **A term with no evidence contributes a flat factor, automatically.** R2 needed a hand-coded regime
switch (`spec_support < 0.60` → load a second weight table) to stop a dominant popularity weight from
swamping the routes that still had something to say. In a posterior, a term that assigns the same
likelihood to every candidate *cancels in the normalisation*. The regime switch is not implemented
better — it stops existing. That is the clearest single argument for this road.

### 3.2 Calibration

Each term's raw score is mapped to a likelihood by a monotone calibrator fitted **offline on synthetic
sessions**, never on the 200 public sessions.

The simulator is a deterministic function of the catalog ([IMPORTANT.md](../../IMPORTANT.md) §4), so a
correctly-labelled session can be generated for **any of the 50,000 products, free**. That turns a
200-example problem into a 50,000-example one and is the only supervision in this project that does not
consume the evaluation set.

Uncalibrated, `H(P)` is an arbitrary number and every threshold in §3 goes back to being hand-tuned —
which is what R3 exists to remove. **Calibration is load-bearing, not polish.**

Reported with it: a reliability curve and expected calibration error. R3's named failure mode in
IDEA.md is *"confidently wrong"*; ECE is that failure mode with a number on it, and no other road has
one.

---

## 4. What R3 deletes

The Innovation exhibit is a count, and it must be reported before and after.

| Deleted | Was | Replaced by |
|---|---|---|
| R2 `SCHEDULE` | 16 tuned weights | likelihood terms |
| R2 `PARAPHRASE_SCHEDULE` | 12 tuned weights | — (the regime switch stops existing, §3.1) |
| R2 `spec_support < 0.60` regime threshold | 1 | — |
| R2 depth ladder | 4 rungs + 3 cutoffs | `τ_ship` on cumulative mass |
| R1 NQC `0.35` | 1 | `τ_convert` on `H(P)` |
| R1 deadline `turn ≥ 3` | 1 | `τ_convert` (the override floor stays — it is structural, §5) |
| R1 `hedge(keep=0.6)` + `cap=4000` | 2 | `τ_mass` |
| R1 `shrink_min`, attribute `0.6`, token `0.3`, `demote 0.35`, decay `0.9` | 5 | calibrated likelihood |

**~45 hand-tuned constants → 3 thresholds (`τ_mass`, `τ_ship`, `τ_convert`) plus the calibrator's fitted
parameters**, and the calibrator is fitted on synthetic data rather than chosen by hand on the
evaluation set. If the final count is not materially lower than this table claims, R3 has failed at the
thing it is for even if the score is fine — record that outcome honestly.

---

## 5. What R3 does *not* touch

These were measured and are structural. Re-deriving them is not exploration, it is repeating work.

- **The override floor.** The evaluator discards every list shipped before the override utterance lands
  on turn 3–4, *even at rank 1*. R1's override MTTC of 3.60 is the floor, not a tuning failure. R3 keeps
  the "stay silent during an override until it lands" rule as a hard constraint on the policy.
- **Override demotes, it does not delete.** The overridden preference is `soft_preferences[1]` — still a
  true constraint of the same target. Deleting it cost R1 0.05 MRR on override sessions. In R3 this is
  natural: it is evidence with a lower weight, not evidence that was retracted.
- **`ask_attribute: "other"` is near-optimal.** R1's information-gain selection re-derived it and lost by
  0.0010. R3 keeps EIG (it is now exact over a real distribution, which is the point) but must *report*
  the delta against hardcoded `"other"` and not pretend a −0.001 is a win.
- **The supplied `user_profile` is near information-free** (−0.0469 in R1). Present as a prior update
  because Pillar III names it; expected to be worth ~0 and must be reported as such.
- **Hosted LLM listwise reranking reduces MRR** — replicated independently in two codebases. R3 does not
  build one. An LLM tier is kept for *extraction only*, escalation-gated (R1: identical clean score,
  identical wall-clock, +0.07 under stress).

---

## 6. Models

Rules: *"For official final scoring, organizer policy may disable network access"* (submission_rules
§Model Policy); out of scope is *"full-model training"* and *"infrastructure-heavy vector databases"*
(competition_specification). A pretrained encoder run locally is neither.

### 6.1 The semantic term — BLaIR, measured against the incumbents

R2 measured `bge-m3` (API, 1024-d) ≈ TF-IDF→SVD (local, 256-d): 0.9676 vs 0.9707, statistically
identical. It concluded dense is not worth a network dependency. Both that finding and the teammate's
independent one are about **generic** encoders.

**[`hyp1231/blair-roberta-base`](https://huggingface.co/hyp1231/blair-roberta-base)** (125M, RoBERTa
architecture) is pretrained on **Amazon Reviews 2023 — this exact corpus** — and the upstream repo is
already vendored at [`AmazonReviews2023/blair/`](../../AmazonReviews2023/blair/). It is the one encoder
whose training distribution matches the failure R3 is attacking: vocabulary mismatch between how a
customer words a constraint and how the catalog words it (`made of alloy` → `Material: alloy`). TF-IDF
cannot bridge that at all; a generic encoder bridges it weakly.

**Deployment shape — this is the part that makes it cheap:**

- `torch` + `transformers` are **build-time only**. One offline pass embeds all 50,000 products.
- The artifact is `50000 × 768` float16 ≈ **77 MB**, loaded by numpy.
- **Runtime needs numpy alone. Zero network calls.** Strictly better than R2's `bge-m3` path under the
  "network may be disabled" rule, and not a vector database — it is one matrix and one matmul.

Measured against `bge-m3` and TF-IDF/SVD on the same harness, on **stressed and `no_spec_phrase`**, not
on clean. **Kill:** if BLaIR does not beat TF-IDF/SVD by ≥0.01 on the stressed number, drop it and keep
SVD — the prior from two independent measurements is that dense does not help here, and a 2.5 GB
build-time dependency needs to earn its place.

### 6.2 The calibrator — LightGBM / isotonic, already installed

`lightgbm 4.6.0` and `scikit-learn 1.7.2` are already present. The principled use here is **not** a
black-box reranker bolted on top of a Bayesian story — that would compete with the posterior instead of
composing with it. It is to fit `P(evidence | item)` on the free synthetic sessions (§3.2). Isotonic
regression is the first thing to try; LightGBM only if a monotone map is measurably insufficient.

### 6.3 Rejected without building

- **Cross-encoder / LLM reranker.** Two independent measurements say listwise reranking *reduces* MRR
  here. Not where the points are.
- **`Qwen3-Embedding-0.6B`.** MTEB leader, but generic — BLaIR's domain match is the specific hypothesis
  worth testing. Fall back to this only if BLaIR wins and we want to know whether domain or scale did it.

---

## 7. Acceptance

Full list with numbers and tests in [02-acceptance.md](02-acceptance.md). The gates that decide the
road:

| ID | Gate |
|---|---|
| **R3-A1** | With a degenerate 0/1 likelihood the posterior orders **identically** to R1's filter; read as a score with flat calibration it orders identically to R2's blend. The generalisation claim is tested, not asserted. |
| **R3-A2** | Clean score within 0.01 of R2's 0.9707 on the unified harness. |
| **R3-A3** | Stressed Hit@10 ≥ 0.90 (best current: 0.890). This is the recall gate and the road's reason to exist. |
| **R3-A4** | `no_spec_phrase` and stressed scores beat `max(R1, R2)` by more than the bootstrap CI. |
| **R3-A5** | Held-out 60 score within its CI of the 140-tuned score. Generalisation, not a bootstrap. |
| **R3-A6** | Tuned-constant count materially below §4's "before". |
| **R3-A7** | ECE reported with a reliability curve. |
| **R3-A8** | Zero network calls on the default path; `R3_OFFLINE=1` is bit-identical. |

---

## 8. Kill criteria — agreed before building

**R3 wins only if** it beats `max(R1, R2)` on the **stressed** and **`no_spec_phrase`** numbers by more
than the bootstrap CI, *while* staying within 0.01 of the best clean score.

**A clean-set win under 0.02 is not a win.** It is noise, and claiming it would be the exact failure
CLAUDE.md trap 7 exists to prevent.

**R3 dies if** the posterior core (P1) cannot reach R2 − 0.01 clean with hand-set likelihood parameters.
That means the likelihood family is mis-specified, and no amount of calibration downstream repairs a
wrong model. Stop, write it up as a negative result, ship the better of R1/R2 on the unified harness.

**The merge is worth doing either way.** It closes R1 defects #1 and #2 and R2's open `A8` — today
`no_spec_phrase` = 0.9260 (R1) and 0.8315 (R2) are *not the same ablation*, and R1's L2 0.8594 against
R2's heavy 0.7961 are *different rewriter programs*. There is currently no race, only two scoreboards.

---

## 9. Working rules — binding

Spec-driven then test-driven, in this order, no steps skipped:

1. **Spec first** — amend this file or [01-contracts.md](01-contracts.md); give it an ID in
   [02-acceptance.md](02-acceptance.md) with the number it must hit and the test that proves it.
2. **Test second** — write it naming that ID, watch it fail *for the right reason*, then implement.
3. **Implement third** — the minimum that makes the test pass.
4. **Measure fourth** — the official evaluator, appending a row to `runs/registry.jsonl`.
5. **Record fifth** — when a measurement changes a decision, *including reversing one*, append to
   [03-decisions.md](03-decisions.md). A rejected idea with its number is worth more than a silent
   deletion.

**A run counts only if** it carries all four scenario breakdowns, a paraphrase-stressed score beside the
clean one, the `no_spec_phrase` ablation, `llm_call_failures`, a git SHA, a pristine kit, and the
held-out 60 score.

---

## 10. Baselines — every claim is measured against these

| | Score | |
|---|---|---|
| Shipped BM25 starter | 0.1067 | never compare against this |
| Popularity + category only | 0.7133 | ignores everything the customer says |
| **Paraphrase-proof floor** | **0.826** | ⚠️ the bar |
| Seed prototype | 0.9607 | |
| R1 clean / L2 / L3 | 0.9597 / 0.8594 / 0.7246 | ⚠️ stress numbers not comparable to R2's until the merge |
| R2 clean / `no_spec_phrase` / heavy | 0.9707 / 0.8315 / 0.7961 | ⚠️ same caveat |
| Theoretical maximum | 0.9922 | MTTC floors at 1.39 — override sessions cannot convert before turn 3 |
