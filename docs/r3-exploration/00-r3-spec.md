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
each turn:  P(·) ∝ P(·) · L(uₜ | ·)          every utterance is evidence
            search wide enough that Σ P(category) ≥ τ_mass       ← recall
            ask  argmax_a  H(P) − 𝔼_r[H(P | a,r)]                ← questions
            ship the top-k where cumulative mass ≥ τ_ship        ← depth
            convert when H(P) < τ_convert                        ← stopping
```

The belief is maintained at **two levels** — over the 1,115 coarse categories, and over the items in
whichever categories the first level says are plausible. §2.3 is why that matters more than the item
level alone.

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

IDEA.md scopes R3's posterior to **ranking and stopping**, over items. The measurements taken since say
that is aimed at the wrong level of the problem.

### 2.1 Clean is saturated

R2 reached MRR 0.9746 / MTTC 2.08 / score 0.9707. The theoretical maximum is 0.9922, so clean headroom
is **0.0215** — and CLAUDE.md trap 7 says a 0.02 gap on 200 sessions is noise. **R3 cannot win on the
clean set, and a clean-only win is not a win** (§8).

### 2.2 Every private-set estimate is a recall failure

| Condition | Hit@10 | Score |
|---|---|---|
| R1 @ L3 paraphrase | 0.820 | 0.7246 |
| R2 heavy paraphrase | 0.845 | 0.7961 |
| R2 `no_spec_phrase` | 0.890 | 0.8315 |
| — a teammate's **non-inversion** pipeline, same 200 sessions | **0.995** | 0.9044 |

15–18% of stressed sessions never had the target in the returned list at all. **A posterior that only
reorders cannot fix that**, because a posterior over a pool that excludes the target is worth zero no
matter how well calibrated it is. That last row is the most instructive number in the project: a
pipeline using *none* of the inversion trick beats R2-without-inversion on both recall **and** speed,
and loses only on MRR.

### 2.3 🔑 And the recall failure has one identified cause

R1 diagnosed it precisely in its own handover: *"At L3, the losses are pools that never contained the
target. Category resolution is 85% accurate there."* And in `catalog.py` itself: *"15% of
model-paraphrased openers resolve to the wrong category, and those are guaranteed misses."*

Here is what actually chooses the pool in both roads today:

```python
scored.append((category, hit * hit / (len(category_tokens) or 1)))   # R1: lexical token overlap
chosen = [c for c, s in ranked[:3] if s >= 0.6 * best]               # hedge: top-3, tuned constant
```

**Both roads build careful machinery on top of a pool chosen by counting shared words**, across 1,115
coarse categories, from a single opening sentence, with a tuned cutoff over an arbitrary top-3. It is
the earliest decision in the session, it is unrecoverable when wrong, and it is the least principled
line of code in either road.

R1 already measured that treating it probabilistically helps: hedging the union is worth **+0.0464 at
L3** and exactly **0.0000** on clean — it pays only when the wording is genuinely ambiguous, which is
precisely the private-set risk. That is a distribution over categories, implemented as a tuned
heuristic and stopped at the top 3.

### 2.4 So R3 is a two-level belief

```
level 1   P(category | evidence)     over 1,115 coarse categories    ← the recall fix
level 2   P(item | category, evidence) over the resulting pool       ← ranking + stopping
```

Level 1 is cheap (1,115 elements), it is where 15–18% of sessions are lost, and it turns R1's
`hedge(keep=0.6, top=3)` into *"search until the category posterior mass exceeds τ_mass"* — a derived
consequence rather than two tuned constants. Level 2 is the posterior IDEA.md described.

**This is the reorganisation.** Aiming a belief at the 50,000 items was aiming it where the problem is
already solved; aiming it at the 1,115 categories aims it at the one decision that silently forfeits
sessions. Both levels use the same machinery, so this is a change of emphasis and target, not extra
scope.

| Job | Replaces | Level | Headroom |
|---|---|---|---|
| **how wide to search** | R1's `hedge(keep=0.6, top=3)`, R2's fixed 4000 cap | 1 | ⬅ **all of it** |
| how to order | R2's two weight schedules + its regime switch | 2 | saturated |
| when to stop / how deep | R1's NQC 0.35 + deadline 3, R2's 4-rung ladder | 2 | ~0.012 |

---

## 3. Architecture

R3 is **one system**, not a shim over two others.

```
                       ┌───────────────────────────────────────┐
utterance ─── parse ──►│  Evidence  eₜ = (constraints, category)│
                       └────────────────┬──────────────────────┘
                                        ▼
        ┌───────────── LEVEL 1 — belief over categories ──────────────┐
        │  log P(c) = log P₀(c) + Σₜ log L(eₜ | c)      1,115 elements│
        │  pool = smallest set of categories with Σ P(c) ≥ τ_mass     │
        └────────────────────────────┬────────────────────────────────┘
                                     ▼
        ┌───────────── LEVEL 2 — belief over items ───────────────────┐
        │  log P(i) = log P₀(i) + log P(c(i)) + Σₜ log L(eₜ | i)      │
        │  P₀ ∝ log1p(rating_number), pool-normalised                 │
        └───┬─────────────────────┬──────────────────┬────────────────┘
            │ top-k by P          │ H(P)             │ cumulative mass
            ▼                     ▼                  ▼
          RANK                 convert            ship-depth
                                      └─ EIG question selection ─┘
```

One object — the belief — drives pool width, ordering, question choice and conversion. There is no
separate confidence signal, no separate regime switch, no separate stopping heuristic, and no tuned
hedge.

### 3.1 The likelihood family

`L(e | ·)` is a product of independent **evidence terms**, each a bounded factor in `[ℓ_min, 1]` so
that no single term can zero out a candidate (an item that matches no evidence must still be
reachable — this is R1's relaxation rule expressed as arithmetic instead of a special case):

| Term | Signal | Level | Origin |
|---|---|---|---|
| `exact` | the constraint string appears verbatim in the candidate's spec phrases | 2 | R1's sharp matcher |
| `attribute` | the normalised `(attribute, value)` pair matches | 2 | R1's ontology matcher |
| `lexical` | IDF-weighted content-token overlap | 1, 2 | R2's lexical route |
| `semantic` | cosine against the encoded category name / item blob | **1**, 2 | R2's dense route, retargeted |

🔑 **The `semantic` term at level 1 is the specific fix for §2.3.** Resolving 1,115 category names by
cosine instead of by shared word count is ~20 lines and R1 estimated it at **+0.03** without building
it. It also costs almost nothing: 1,115 encoded names is a 1,115 × d matrix, encoded once.

🔑 **Each constraint contributes its own evidence term, rather than one fused query.** This is the
lesson taken from the non-inversion pipeline that beats R2 on recall — per-constraint routes, not one
blended query vector. In a posterior it is not a design choice bolted on; it is what independent
evidence *means*.

🔑 **A term with no evidence contributes a flat factor and cancels in the normalisation.** R2 needed a
hand-coded regime switch (`spec_support < 0.60` → load a second weight table) to stop a dominant
popularity weight swamping the routes that still had something to say. In a posterior that switch is
not implemented better — **it stops existing.** That is the single clearest argument for this road.

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
| **R1 `hedge(keep=0.6)` + top-3 + `cap=4000`** | **3** | **`τ_mass` on the level-1 category belief — §2.3** |
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

### 6.0 Scope audit — [docs/PROBLEM.md](../PROBLEM.md) §4.3, verbatim

| PROBLEM.md says | Consequence for R3 |
|---|---|
| **Out:** *"Training or full-parameter fine-tuning of base foundational LLMs."* | We train **no** LLM. A pretrained encoder used for inference is not training. Fitting a calibrator or a gradient-boosted model is not a foundational LLM. |
| **Out:** *"Deploying heavy external industrial vector DB clusters (must run entirely in-memory for light execution)."* | Embeddings are **one numpy matrix and one matmul**, in-process. No FAISS server, no Milvus, no Pinecone. Peak RSS is reported in the registry. |
| ⚠️ **Out:** *"Multi-Modal Processing (restricted strictly to text catalogs, structured metadata, and text dialogs)."* | 🚫 **No image models.** The catalog carries product images and CLIP-style retrieval would be an easy, natural, and disqualifying reach. Text and structured metadata only. |
| **Out:** UI/UX development | Headless. Not our concern. |
| **Limit:** catalog is strictly read-only, no mock ASIN injection | Synthetic sessions (§3.2) generate **dialogs**, never catalog rows. The catalog file is never written. |
| **In (§4.3):** *"Fine-tuning prompt strategies or local scoring logic for the LLM ranking stage."* | The learned calibrator is explicitly in scope. |
| **In (§4.4):** *"keyword retrieval, rule-based methods, dense retrieval, hybrid retrieval, reranking, **local models**, and external model APIs"* | A local pretrained encoder is explicitly supported, not merely tolerated. |
| **Disclosure (§ Submission):** name *"Hugging Face Transformers, PyTorch, scikit-learn"* | These are anticipated dependencies. Every one used gets declared, with version, in the manifest. |

**Nothing in PROBLEM.md blocks anything below.** Where it is silent, we are free — and it is silent on
encoder choice, on gradient-boosted models, and on offline precomputation.

### 6.1 The semantic term is a switch, and the switch is the experiment

The `semantic` term has one interface and interchangeable backends. It is measured as a **matrix**, not
chosen by argument, on the **stressed** and **`no_spec_phrase`** numbers — never on clean, where
everything ties.

| Backend | d | Where | Runtime dep | Prior |
|---|---|---|---|---|
| `tfidf_svd` | 256 | local, built at startup | scikit-learn | R2's incumbent; scored 0.9707, tied `bge-m3` |
| `bge_m3` | 1024 | API, precomputed | numpy | R2 measured 0.9676 — no gain, costs a network bet |
| **`blair_base`** | 768 | local, precomputed | **numpy** | untested — the hypothesis |
| `blair_large` | 1024 | local, precomputed | numpy | untested — does scale help, if base does? |
| `qwen3_emb_0.6b` | 1024 | local, precomputed | numpy | untested — is it domain fit, or just a better encoder? |

Each is measured at **both levels**: as the level-1 category resolver (1,115 names — cheap, and where
§2.3 says the points are) and as the level-2 item term. It is entirely possible that a backend wins at
one level and loses at the other; that result would itself be worth reporting.

**Why BLaIR is the hypothesis:** [`hyp1231/blair-roberta-base`](https://huggingface.co/hyp1231/blair-roberta-base)
(125M, RoBERTa) is pretrained on **Amazon Reviews 2023 — this exact corpus** — and the upstream repo is
already vendored at [`AmazonReviews2023/blair/`](../../AmazonReviews2023/blair/). R2 and a teammate both
measured dense underperforming here, but **both used generic encoders.** The failure R3 attacks is
vocabulary mismatch between how a customer words a constraint and how the catalog words it (`made of
alloy` → `Material: alloy`); a corpus-matched encoder is the specific tool for that, and TF-IDF cannot
bridge it at all.

**Why it is cheap:** `torch` and `transformers` are **build-time only**. One offline pass embeds the
50,000 products and the 1,115 category names; the artifact is 50000 × 768 float16 ≈ **77 MB**.
**Runtime is numpy.** Zero network calls — strictly better than R2's `bge-m3` path under *"organizer
policy may disable network access"* (submission_rules §Model Policy).

🔴 **Kill (R3-A23):** the winning backend must beat `tfidf_svd` by ≥0.01 on the stressed number, or
`tfidf_svd` ships and the whole matrix is reported as a negative result. Two independent measurements
say dense does not help here; that prior has to be paid for, not assumed away.

### 6.2 The calibrator — already installed

`lightgbm 4.6.0` and `scikit-learn 1.7.2` are present; `torch` and `transformers` are not (≈2.5 GB, and
build-time only — see 6.1).

The principled use is **not** a black-box reranker bolted on top of a Bayesian story — that would
compete with the posterior instead of composing with it, and it would be unexplainable in a write-up
whose entire claim is *one derived mechanism*. It is to fit `P(evidence | ·)` on the free synthetic
sessions (§3.2). **Isotonic regression first**; LightGBM only if a monotone map is measurably
insufficient, and only with that measurement recorded.

### 6.3 Rejected without building

- **Cross-encoder / LLM listwise reranker.** Two independent codebases measured listwise reranking
  *reducing* MRR here (R2: 0.9642 vs 0.9707; a teammate's separate 10-session ablation agreed). R1
  measured −0.0053 clean. Not where the points are. An LLM tier survives for **extraction only**,
  escalation-gated, where R1 measured identical clean cost and +0.07 under stress.
- **Any image or multi-modal model.** Out of scope by PROBLEM.md §4.3. See §6.0.
- **A vector database.** Out of scope by PROBLEM.md §4.3, and unnecessary at 50,000 × 768.

---

## 7. Acceptance

Full list with numbers and tests in [02-acceptance.md](02-acceptance.md). The gates that decide the
road:

| ID | Gate |
|---|---|
| **R3-A1** | With a degenerate 0/1 likelihood the posterior orders **identically** to R1's filter; read as a score with flat calibration it orders identically to R2's blend. The generalisation claim is tested, not asserted. |
| **R3-A27** | Level-1 category accuracy under L3 paraphrase ≥ **0.95** (R1 measures 0.85 today). The §2.3 fix, isolated from everything downstream. |
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
