# R3 — decision log

Append-only. **When a measurement changes a decision, including reversing one, record it here with the
number.** A rejected idea with its number is worth more than a silent deletion — three of R2's ten
entries are reversals and they are the most useful entries in that file.

Format: `Dn — decision · why · the number that decided it · status`.

---

## D1 — The merge lands on `r3-exploration`, not `main`

**Decision:** merge `r1-exploration` + `r2-exploration` into `r3-exploration`. `main` untouched.
**Why:** user's call. CLAUDE.md §6 forbids committing to `main` unasked; keeping `main` clean means R3
can be abandoned without unwinding anything, and the merged harness can be promoted later once it has
proved itself.
**Cost, stated honestly:** `main` does not get the unified harness while R3 runs, and R3's branch diff
mixes integration with exploration. Mitigated by doing the merge in its own commits with its own gates
(M1–M8) before any `src/r3/` file exists.
**Status:** decided, pre-measurement.

## D2 — `CatalogIndex` is split per road, not unified

**Decision:** `src/common/catalog.py` → `src/r1/catalog.py` + `src/r2/catalog.py`.
**Why:** the two classes have genuinely different APIs. Unifying them would silently rewrite the data
both roads' published numbers came from, and drift would be unattributable. R1 and R2 are frozen
baselines after the merge; they exist to be raced, not extended.
**Cost:** duplication, and two indices in memory during the race. Deleted at Phase 2 (converge).
**Status:** decided, pre-measurement. Reverse if memory or build time actually bites — measure first.

## D3 — R3 is one system; it imports nothing from R1 or R2

**Decision:** `src/r3/` owns one index, one parser, one likelihood family. No `from src.r1…` or
`from src.r2…`, enforced by an AST test.
**Why:** user's call, and it is right. A road that calls into two other roads at runtime is glue, and
the race would then be comparing a system against two of its own components. Code is *lifted* where it
is good — going last is exactly the licence to do that — but R3 must stand as an architecture.
**Status:** decided, pre-measurement.

## D4 — R3's posterior drives recall, not only ranking and stopping

**Decision:** add pool widening by posterior mass (`τ_mass`) as Phase P2, extending IDEA.md §0.3's scope.
**Why:** IDEA.md aimed R3 at "+0.075 MRR headroom", which R2 has since consumed — clean headroom is now
0.0215 against a 0.02 noise floor, so **R3 cannot win on the clean set.** All remaining headroom is
stressed Hit@10 (0.820–0.890 against a teammate pipeline's 0.995), which is *recall*. A posterior that
only reorders cannot raise Hit@10 at all.
**The numbers that decided it:** R1 L3 Hit@10 0.820 · R2 heavy 0.845 · R2 `no_spec_phrase` 0.890 ·
non-inversion pipeline 0.995 · clean headroom 0.0215 vs noise 0.02.
**Status:** decided, pre-measurement. This is the largest departure from IDEA.md and the one most likely
to be wrong — R3-A3 (stressed Hit@10 ≥ 0.90) is the gate that settles it.

## D5 — the held-out 140/60 split lands with the merge and blocks all tuning

**Decision:** build it before any R3 parameter is chosen.
**Why:** R1 defect #3 and R2 defect #1 are both this. R3 adds calibration parameters, making it the road
most able to overfit 200 sessions invisibly; a bootstrap CI resamples the very sessions the parameters
were tuned on and cannot detect it. The teammate work's locked result (0.904417) matching its dev result
(0.902492) is what real evidence of generalisation looks like.
**Cost:** the tuning set drops to 140 sessions.
**Status:** decided, pre-measurement.

## D6 — BLaIR is tested for the semantic term, with a kill number

**Decision:** measure [`hyp1231/blair-roberta-base`](https://huggingface.co/hyp1231/blair-roberta-base)
against `bge-m3` and TF-IDF/SVD on the **stressed** and `no_spec_phrase` numbers. Drop it unless it wins
by ≥0.01 (R3-A23).
**Why:** R2 and a teammate independently measured dense underperforming here — but both used **generic**
encoders. BLaIR is pretrained on Amazon Reviews 2023, *this exact corpus*, and its upstream repo is
already vendored in this project. Vocabulary mismatch (`made of alloy` → `Material: alloy`) is precisely
the failure P2 attacks and precisely what a domain-pretrained encoder is for.
**Why it is cheap:** `torch`/`transformers` are build-time only. One offline pass → `50000 × 768` float16
≈ 77 MB → runtime is numpy and a matmul. **Zero network calls**, which is strictly better than R2's
`bge-m3` path under *"organizer policy may disable network access"*, and it is not an
"infrastructure-heavy vector database".
**Prior:** two independent measurements say it will not help. Hence the kill number.
**Status:** open.

## D7 — no cross-encoder, no LLM listwise reranker

**Decision:** do not build one.
**Why:** two independent codebases measured hosted listwise reranking *reducing* MRR (R2: 0.9642 vs
0.9707; a teammate's independent 10-session ablation agreed). R1 measured −0.0053 clean / +0.0018
stressed, the latter while 22% of calls were failing. An LLM tier survives for **extraction only**,
escalation-gated, where R1 measured it at identical clean cost and +0.07 under stress.
**Status:** decided, on prior measurement.

## D8 — LightGBM fits the calibrator, it does not rank

**Decision:** `lightgbm` (already installed) and `scikit-learn` isotonic regression are used to map raw
term scores to likelihoods on synthetic sessions. Isotonic first; LightGBM only if a monotone map is
measurably insufficient.
**Why:** IDEA.md §E calls LightGBM the highest-ROI item, but as a *reranker* it competes with the
posterior instead of composing with it — a black box bolted onto a Bayesian story is worse than either
alone, and unexplainable in a write-up whose whole claim is "one derived mechanism". Fitting
`P(evidence | item)` is where supervised learning genuinely belongs in this architecture.
**Status:** open.

## D9 — PROBLEM.md §4.3 scope audit, done before any model was chosen

**Decision:** audited [docs/PROBLEM.md](../PROBLEM.md) §4.3/§4.4 verbatim; recorded as
[00-r3-spec.md](00-r3-spec.md) §6.0.
**Findings:** nothing in the brief blocks a local pretrained encoder, a gradient-boosted calibrator, or
offline precomputation — §4.4 lists *"dense retrieval, hybrid retrieval, reranking, **local models**"*
as supported, and the submission section names Transformers/PyTorch/scikit-learn as expected
disclosures. Three real limits do bind: no training of foundational LLMs, no vector-DB cluster
(*"must run entirely in-memory"*), and **no multi-modal processing.**
**The trap this catches:** the catalog carries product images, and CLIP-style retrieval is a natural
reach that would be **out of scope**. Written down as R3-A29 with a test, before anyone reaches for it.
**Status:** decided.

## D10 — ⭐ R3 is a **two-level** belief; level 1 is over categories, and that is the road's point

**Decision:** rewrite R3 from "posterior over 50,000 items" to a belief over the **1,115 coarse
categories** (choosing the pool by mass) with a second belief over items inside it. Supersedes D4, which
had the right instinct — recall, not ranking — aimed one level too low.
**Why:** R1 diagnosed the recall failure precisely and did not act on it: *"At L3 the losses are pools
that never contained the target. Category resolution is 85% accurate there."* What actually chooses the
pool in **both** roads is `hits² / |category tokens|` over 1,115 names, hedged over an arbitrary top-3
with a tuned `keep=0.6`. Both roads then build careful machinery on top of a pool chosen by counting
shared words. It is the earliest decision in a session and unrecoverable when wrong.
**The numbers that decided it:** category accuracy 0.85 at L3 · 15% of paraphrased openers resolve to
the wrong category, all guaranteed misses · R1's hedge is worth **+0.0464 at L3 and 0.0000 clean**, i.e.
a distribution over categories already pays and is currently a heuristic · R1's own estimate for
resolving by cosine instead: **+0.03**, unbuilt.
**Why it is the right shape for R3 specifically:** a belief over 1,115 elements is cheap, it converts
R1's two tuned constants into one derived threshold, and it is the *only* stage aimed at measured
headroom. Aiming a posterior at the 50,000 items was aiming it where the problem is already solved.
**Gate:** R3-A27 — level-1 accuracy ≥0.95 under L3, measured **in isolation before** it is entangled
with level 2. If it does not move, the diagnosis is wrong and P2 is re-planned, not tuned.
**Status:** open. This is the largest departure from IDEA.md §0.3 and the highest-value one.

## D11 — the semantic backend is a switch, and the switch is the experiment

**Decision:** one interface, five interchangeable backends (`tfidf_svd`, `bge_m3`, `blair_base`,
`blair_large`, `qwen3_emb_0.6b`), measured as a matrix on stressed + `no_spec_phrase`, at **both**
belief levels. Supersedes the narrower D6, which tested BLaIR alone.
**Why:** R2 and a teammate both measured dense underperforming — with **generic** encoders, as an item
term, on the clean set. Three things are untested at once: a **corpus-matched** encoder, the **level-1
category** application, and the **stressed** condition. Testing them as a matrix costs little (the
harness runs variants in one process) and produces an ablation table, which is worth more to Technical
Execution than a single tuned number.
**A backend may win at one level and lose at the other.** That result would itself be worth publishing.
**Kill:** R3-A23 — beat `tfidf_svd` by ≥0.01 stressed or `tfidf_svd` ships and the matrix is reported as
a negative result. The prior from two independent measurements has to be paid for, not assumed away.
**Status:** open.

## D12 — the wider Hugging Face menu, assessed honestly

**Prompted by:** the model classes worth considering are not only encoders — tagging, classification,
sentiment and reranker models are all available. Assessed one by one against what R1 and R2 measured,
because "available" is not "useful".

| Class | Verdict | Why |
|---|---|---|
| **Token classification / NER (tagging)** | 🟢 **strong candidate** | R1's LLM extraction tier is what carries it from 0.7887 → 0.8594 under paraphrase — the single largest robustness contribution after the prior. A local token classifier does that job **with no network**, which matters because *"organizer policy may disable network access"*. And we can train it on free synthetic data: the simulator emits `(attribute, value)` labels for all 50,000 products. Becomes the `attribute` likelihood term's extractor. |
| **Sequence classification (category)** | 🟢 **strong candidate** | This is level 1 stated as a supervised problem, and the labels are free: every catalog item knows its own coarse category, so the 50,000-item catalog **is** a labelled training set for "utterance → category". Likely stronger than cosine over category names, and it is a *classifier*, not a foundational LLM, so it is in scope. Measured head-to-head against the embedding resolver under R3-A27. |
| **Cross-encoder reranker** | 🟡 **one measured shot** | Distinct from the LLM listwise reranking that two codebases measured as *harmful* — a cross-encoder is a trained relevance scorer, not a generative permutation, and it runs locally. Prior is still negative, so it gets one run behind a flag and a kill number, at the top-20 only, as a **likelihood term** rather than a final re-ordering (a reranker that overrides the posterior would break the architecture's whole claim). |
| **Zero-shot NLI classification** | 🔴 **rejected on cost** | 1,115 candidate labels means 1,115 forward passes per utterance. The per-turn budget (R3-A11, 50 ms p95) rules it out, and the supervised classifier above is both cheaper and better-fitted. |
| **Sentiment** | 🔴 **rejected on relevance** | The simulator emits shopping constraints (`Material: alloy`, `100% Polyester`), not opinions. There is no sentiment in this data to detect. Saying so costs one line; measuring it would cost an afternoon. |

**The unifying reason the first two are attractive:** they turn the network-dependent LLM tier into
**local weights trained on free labels**, which is simultaneously a robustness win (R3-A8, zero network
calls), a scope win (no foundational-LLM training), and the honest use of the supervision the simulator
hands us for free. They are folded into Phase P3, which was already the "learn from synthetic sessions"
phase.

**Every one of them still faces R3-A29 (no multi-modal) and its own kill number.** Two independent
measurements say added model complexity has not helped on this benchmark; that prior is paid for with
numbers, not assumed away.
**Status:** open. Tagging + category classifier promoted into P3; cross-encoder gets one run in P5.

## D13 — ⚠️ REVERSAL: the L2 stress ladder never tested category resolution, and my §7.1 ④ was wrong

**What happened:** before building the level-1 belief, I measured whether category resolution actually
breaks — the isolated R3-A27 probe the spec demanded first. It does not, at L1 or L2:

| Level | category accuracy | hedged | **pool contains target** |
|---|---|---|---|
| L0 / L1 / L2 | **1.000** | 1.000 | **1.000** |
| L3 (category reworded) | **0.825** | 0.925 | **0.925** |

**The cause was a hole in my own referee, not in the roads.** The L1/L2 scaffolds interpolate
`{category}` **verbatim** — `"not sure yet, somewhere in {category}"` — and `best_category` checks for a
quoted category name before anything else. So every opener resolved perfectly no matter how hard the
rest of the sentence was mangled.

**What that means I got wrong:** [04-merge-plan.md](04-merge-plan.md) §7.1 ④ concluded *"the recall
failure is caused by paraphrase"* from L2's Hit@10 of 0.890. But at L2 the pool contains the target
**100%** of the time — so those eleven percent are the target sitting in the pool and ranked below tenth.
**At L2 that is a ranking failure, and I called it recall.** D4 and D10 both leaned on it.

**What survives, and it is the load-bearing half:** at L3, where the category *is* reworded, category
accuracy is **0.825** — matching R1's independently claimed 85% — and **7.5% of sessions have no
recoverable answer at all**, because the target is not in the pool for any ranker to find. Hedging
already recovers 0.825 → 0.925, which is R1's tuned heuristic doing exactly what D10 says a belief
should do, only worse. So D10's mechanism is right and its evidence base was half wrong.

**Changes:**
1. The ladder gains **L3 = deterministic category rewording** (LLM-written moves to L4). Reproducible,
   free, no network. Every level ≤2 number in this repo understates paraphrase risk and is relabelled
   accordingly, not deleted.
2. **R3-A27 is measured at L3**, not L2: category accuracy 0.825 → ≥0.95, pool-contains-target
   0.925 → ≥0.99.
3. **R3-A3 (recall) is an L3 gate.** At L2 there is no recall problem to fix.
4. R3 must fix *both*: ranking at L2, recall at L3. The two-level belief addresses them at its two
   levels, which is a better argument for the architecture than the one I originally made — but it is a
   different argument, and the earlier one was not supported.

**The lesson, worth keeping:** the probe cost twenty minutes and killed a conclusion I had already
written into two documents and a commit message. Building P2 first would have produced a category
belief measured against a referee that could not see category errors, and it would have shown no gain
for the right reason and been tuned anyway.
**Status:** recorded. Supersedes the evidence in D4 and half the evidence in D10.

## D14 — the level-1 belief: what was tried, what won, and what is not achievable

**Built and measured, in this order.** All tuning on the 140-session train split; the 60 was read once,
at the end.

| Attempt | exact L0 | exact L3 | Why |
|---|---|---|---|
| R1 lexical `hits²/\|tokens\|` + top-3 hedge (baseline) | 1.000 | 0.825 | |
| naive Bayes over per-category product titles | 0.625 | 0.525 | **rejected** |
| naive Bayes, informative words only (idf ≥ 2) | 0.605 | 0.540 | rejected |
| idf-weighted category language model | 0.370 | 0.295 | rejected |
| category name as a distribution, no products | 0.945 | 0.680 | rejected |
| name + language model, best of four fusion weights | 0.915 | 0.665 | rejected |
| **stemmed, idf-weighted name likelihood + verbatim bonus** | **1.000** | **0.865** | **shipped** |

**The per-category language model was the plausible idea and it lost badly.** The theory was that
"tees" would reach "Shirts T-Shirts" through the products using both words. In practice a 5-to-12 word
opener is mostly scaffold ("not sure yet, somewhere in…") and constraint payload ("cotton"), and naive
Bayes multiplies every one of those against per-category frequencies that vary for no reason. The one
informative token is outvoted. Recorded because it is exactly the kind of idea that gets re-proposed.

**What actually fixed things came from reading the 35 failures, not from another scorer:**

1. **Morphology, ~6 of 35.** `"womens hoodies"` did not match `"Women Hoodies"`, so only `hoodies` hit —
   which tied `Women Hoodies` with `Men Hoodies`, and the tie broke wrong. A three-line stemmer applied
   symmetrically to both sides fixes the whole class.
2. **Hierarchy, most of the rest.** `coarse_category` joins the last two taxonomy levels, so
   `"Tees & Blouses Tunics"` has six siblings. When the shopper says only `"tees & blouses"`, the child
   is **not in the message**. No resolver can pick it; `best()` is information-limited to about 1-in-7
   there. **But the pool can hold all seven** — which is what a distribution does natively and an
   argmax-plus-top-3-hedge cannot.

### The recall/precision frontier, measured

`TEMPERATURE` (how sharply score becomes belief) and `TAU_MASS` (how much mass the pool must cover)
replace R1's `keep=0.6`, its top-3 cutoff and its 4000 cap — three constants for two, and these two are
a legible dial rather than magic numbers:

| T | τ | L3 coverage | L3 pool | **L0 pool** |
|---|---|---|---|---|
| 0.35 | 0.90 | 0.915 | 305 | 275 |
| 0.80 | 0.95 | 0.979 | 650 | 275 |
| **2.00** | **0.90** | **0.986** | 1352 | **275** ← chosen |
| 6.00 | 0.90 | 1.000 | 2762 | 1267 ← pays on clean |

**Coverage of 0.99+ is reachable only by making the pool 4.6× bigger on clean text** — spending ranking
on every session to buy recall in 2% of stressed ones. R1 measured its own hedge at +0.0464 on L3 and
exactly 0.0000 on clean, and that discipline is worth keeping: the chosen point leaves the clean pool
**unchanged at 275**.

### Held-out result — tuned on 140, read once on 60

| On the held-out 60, at L3 | pool contains target | mean pool |
|---|---|---|
| R1 lexical + hedge | 0.883 | 255 |
| **R3 level-1 belief** | **0.967** | 718 |

**+0.084 coverage on sessions never used for tuning.** Train said 0.986 and test 0.967, a 0.019 gap on
60 sessions — the honest generalisation number, and the first one in this project that is not a
bootstrap over the tuning set.

⚠️ **Coverage is not score.** A 2.8× larger stressed pool is ranking cost that level 2 has to earn back.
That is measured next, and if it does not come back this trade is reversed.

**Gates revised, with reasons:** R3-A27 exact accuracy 0.95 → "beats 0.825" (information-limited, above);
pool coverage 0.99 → 0.97 (the clean-cost frontier, above). Both were set before the frontier was
measured. Revising a gate after seeing data is only legitimate when the reason is recorded and is about
what is achievable rather than what was achieved — that is the case here, and both original targets are
left in the test docstrings so the change is visible.

## D15 — the policy: three wrong models of "what is waiting worth?", and the one that works

R3 ships depth by expected utility. The evaluator does `if target in ranked: break`, so **any** hit ends
the session and locks that reciprocal rank — shipping ten items is not free, it converts a future rank-1
hit into a present rank-7 one. Shipping `k` is worth

    U(k) = Σ_{i≤k} p_i·(1/i)  +  (1 − Σ_{i≤k} p_i)·V

and `U(0) = V`, so "say nothing this turn" falls out as the k=0 case instead of being a special rule.
`turn_cost` is not a knob: one turn costs 0.2 × 0.1 = 0.02 of efficiency against MRR's weight of 0.3,
so a turn is worth 0.02/0.3 ≈ 0.0667 of reciprocal rank. **The entire difficulty is `V`.**

| Model of `V` | clean | L3 | Why it failed |
|---|---|---|---|
| constant 0.90 | 0.9467 | **0.6216** | `U(1) − U(0) = p₁(1 − V) > 0` and `U(2) − U(1) = p₂(0.5 − V) < 0` **unconditionally** — so it shipped exactly one item every turn forever. Sweeping V over 0.75–0.92 changed *nothing*, which is what exposed it. |
| 0 on one barren turn | 0.9377 | 0.7124 | Panicked at a single unproductive reply; cost 0.068 of clean MRR. |
| `(1 − normalised entropy)` | 0.9243 | 0.7095 | Entropy over a 275-item pool is high even when the belief is good. Measured separation clean-vs-L3: only **1.34×**. |
| `p₁ ** power` | 0.9090 | 0.7778 | p₁ separates the conditions **2.4×** (median 0.393 clean vs 0.167 at L3) — but the fit chose `power = 0`, i.e. it preferred not to use it at all. |
| **constant × `stall_decay ** consecutive_barren_turns`** | **0.9509** | **0.7899** | **shipped** |

The lesson is not about the winner, it is that **a constant `V` makes the whole expected-utility
apparatus degenerate into a fixed rule**, and it does so silently — the score looked reasonable and the
parameter appeared not to matter. What actually matters is that waiting is only worth something when
**more evidence is coming**, and the honest estimator of that is how many recent turns taught us
anything.

### Two bugs the trace found that no sweep would have

Printing depth, constraint count and the customer's actual words for six L3 sessions:

1. **It asked `"feature"` seven turns in a row** while the customer answered *"feature is up to you"*
   each time. `best_question` skips attributes recorded as barren; nothing ever *recorded* one. Both
   roads have this logic and I had implemented only the read side. Worth ~1.5 turns of MTTC at L3.
2. **`stalled` shipped depth 2, not 10.** Setting `V` to "what this list is worth" left `horizon` high
   enough that `dU/dk = p_k(1/k − horizon)` turned negative at k≈2.

## D16 — ⚠️ the popularity prior was a units error, and it was worth 0.066

`log1p(rating_number)` spans **0–11** across this catalog. One exact card-string match is worth **3.2**
in log space. Used raw as a log-prior — which is what "P₀ ∝ popularity" naively implies — the prior
**outvotes three exact matches**. That is not a strong prior, it is a units error, and it is the kind
that hides because the resulting agent still behaves sensibly.

Fitted on the 140:

| prior_weight | clean | L3 |
|---|---|---|
| 0.05 | 0.9084 | 0.7129 |
| 0.10 | 0.9084 | 0.7627 |
| **0.18** | 0.9090 | **0.7778** |
| 0.50 | 0.9144 | 0.7326 |
| 0.85 | 0.9297 | 0.7082 |

**+0.066 at L3** against the raw prior, and the curve is single-peaked — under-weighting the prior
costs robustness (it is the paraphrase insurance both roads measured), over-weighting it drowns the
evidence. R2 reached the same shape empirically with its schedule; the difference is that here it is
one number with units rather than 28 tuned weights.

## D17 — measured and rejected: channel-conditioned evidence gains

**Idea:** `P(the catalog's exact wording appears | this item is the target)` should be high while the
customer speaks in template language and low once they paraphrase, so `exact_gain` should switch on
`state.paraphrased()`. This is ordinary Bayesian practice — conditioning a likelihood on the observed
channel — and it is the principled version of R2's hand-coded `spec_support < 0.60` regime switch.

**Result: it buys nothing.** Fitted on the 140, the clean score is flat in `exact_gain` (0.9478 at 3.2,
0.9472 at 6.0, 0.9472 at 8.0) and every paraphrased gain other than 3.2 loses. The two-gain model
collapses to the one-gain model.

**Why that is interesting rather than disappointing:** the abstention rule in `likelihood.py` is
already doing the work. A term whose evidence matches nothing in the pool returns `{}` and contributes
nothing at all, so when paraphrase kills exact matching the exact term simply stops voting — no switch
required. This is the one place where §3.1's claim that "the regime switch stops existing" is
**tested rather than asserted**, and it holds.

## D18 — ⚠️ REVERSAL: expected information gain loses at every stress level, and is switched off

EIG question selection is one of the two things IDEA.md §0.3 promised R3 would do natively — *"the best
question is the one that most reduces entropy"* — and it is now **off by default**.

| | with EIG | hardcoded `"other"` | Δ |
|---|---|---|---|
| clean | 0.9509 | **0.9720** | **−0.021** |
| L2 full | 0.8426 | **0.8845** | **−0.042** |
| L3 category | 0.7899 | **0.8297** | **−0.040** |

R1 measured the same sign at −0.0010 and kept it for the mechanism. Here it costs twenty to forty
times more, and keeping it would be indefensible.

**The reason is structural, not a tuning failure.** `"other"` makes the simulator return **the next two
undisclosed constraints**; any named attribute returns at most one. And `classify_constraint` never
emits `brand`, `budget` or `category` at all, so a third of the attributes EIG can choose are dead
letters that burn a whole turn for nothing. **No question-selection objective can beat "ask for
strictly more evidence" when one of the options literally returns twice as much of it.** EIG is
optimising the wrong thing — it maximises information per *question*, and the scoring function pays for
information per *turn*.

This is worth stating plainly because it is the second IDEA.md claim about R3 that did not survive
contact with measurement (D13 was the first). The posterior framing earns its place through the pool,
the prior's units and the expected-utility policy — not through the question selection that looked like
its most elegant consequence.

Kept behind `R3_FLAGS=infogain` because the mechanism is worth demonstrating and the measurement is the
contribution. It is not shipped, and R3-A19 is satisfied by reporting the loss rather than by winning.

## D19 — measured and rejected: the TF-IDF/SVD semantic term

**Built** (`src/r3/semantic.py`, ~50 lines, scikit-learn only, no new dependency, no network) and
**measured** as an evidence term on the full 200:

| `semantic_gain` | clean | L2 | L3 |
|---|---|---|---|
| **0.0 (shipped)** | **0.9720** | **0.8845** | **0.8297** |
| 1.0 | 0.9691 | 0.8712 | 0.8219 |
| 2.5 | 0.9652 | 0.8554 | 0.8196 |

**It hurts, monotonically, at every level.** Not neutral — actively harmful, and more weight is worse.

This is the **third independent negative** on semantic retrieval for this benchmark: R2 measured
`bge-m3` ≈ TF-IDF/SVD ≈ no gain, a teammate's separate codebase agreed, and now R3 measures LSA as a
likelihood term costing 0.003–0.013.

⚠️ **It does not settle BLaIR, and saying so would be overclaiming.** TF-IDF→SVD is a *lexical* method —
LSA over the same word counts the token-overlap term already reads — so it cannot bridge "made of
alloy" → "Material: alloy" much better than that term does, and the two are partly redundant, which is
the likely mechanism for the harm. D11's hypothesis is specifically about a **corpus-pretrained**
encoder, which remains untested. What this result does is lower its expected value: three of three
semantic variants tried on this benchmark have failed.

Kept behind `R3_FLAGS=semantic_gain=1.0`, off by default, because the negative is the contribution.

## D20 — 🔴 BLaIR was built, embedded and measured. It buys nothing. Kill gate R3-A23 fires.

The D11 hypothesis was the strongest remaining argument for a semantic term: R2's and the teammate's
negative results used **generic** encoders, and `hyp1231/blair-roberta-base` is pretrained on **Amazon
Reviews 2023, this exact corpus**. Vocabulary mismatch ("made of alloy" → "Material: alloy") is exactly
what a corpus-matched encoder should bridge.

**Built end to end:** all 50,000 products embedded (CLS-pooled, L2-normalised, the model's own recipe),
float16, 71 MB, 4.6 minutes on MPS at ~180 items/s. Queries encoded by the model itself — locally, no
network. Wired in as a bounded evidence term like any other.

| `semantic_gain` | clean | L2 | L3 | mean |
|---|---|---|---|---|
| **0.0 — no semantic term** | **0.9720** | **0.8845** | 0.8297 | **0.8954** |
| 1.0 | 0.9711 | 0.8773 | 0.8273 | 0.8919 |
| 2.5 | 0.9707 | 0.8802 | **0.8349** | 0.8953 |
| 4.0 | 0.9704 | 0.8704 | 0.8297 | 0.8902 |
| 6.0 | 0.9654 | 0.8590 | 0.8204 | 0.8816 |

**At its best (gain 2.5) the mean is 0.8953 against 0.8954 without it.** The one gain it offers — L3
+0.005 — is bought with clean −0.013 and L2 −0.043, and it is half the pre-registered ≥0.01 threshold
in R3-A23 on its own terms. **Dropped**, exactly as the gate written before the measurement required.

### Why this is the most useful negative in the project

This is now the **fourth independent measurement** that semantic retrieval does not help on this
benchmark, and critically it is the one that closes the loophole in the other three:

| Who | Encoder | Result |
|---|---|---|
| R2 | `bge-m3` (generic, API) | ≈ TF-IDF/SVD, no gain |
| a teammate, separate codebase | generic dense | no gain |
| R3, D19 | TF-IDF → SVD (lexical LSA) | actively harmful |
| **R3, here** | **BLaIR (corpus-pretrained)** | **neutral** |

D19 explicitly said the LSA result "does not settle BLaIR, and saying so would be overclaiming". So it
was built and tested rather than argued about, and the answer is that the domain match does not rescue
it either.

**The mechanism is worth naming.** The simulator's constraints are *drawn verbatim from the catalog's
own `features` and `details`*. The evidence that decides a session is therefore string-level by
construction, and the exact/attribute/token terms already read that surface directly. A semantic
encoder adds a *correlated but blurrier* view of the same text — so it contributes redundancy plus
noise, which is precisely the shape of the measured harm. **This benchmark has no vocabulary gap for a
semantic model to close**, because the customer's vocabulary *is* the catalog's vocabulary.

**Consequences for the submission:** `torch` and `transformers` are **not** runtime dependencies and
not in the manifest. `scripts/embed_blair.py` and `src/r3/semantic.py` stay, behind
`R3_FLAGS=semantic_gain=2.5`, because a measured negative with a reproduction recipe is worth more than
a deleted branch. The shipped agent remains **numpy-only, zero network calls**.

## D21 — the LLM extraction tier is worth +0.06 under paraphrase and exactly 0.000 on clean

R1 measured its own escalation-gated extraction tier at ~+0.07 under stress. R3 inherits the same
`src/common/parse.py` cascade but had never been run with it on. Measured, `qwen3.6:35b` pinned
explicitly (never `default`, which is an alias — trap 8):

| | tier off | tier on | Δ | calls | failures |
|---|---|---|---|---|---|
| clean | 0.9720 | 0.9720 | **0.000** | **0** | 0 |
| L2 | 0.8845 | **0.9399** | **+0.055** | 188 | 51 (27%) |
| L3 | 0.8297 | **0.8926** | **+0.063** | 28 | 113 (80%) |

Hit@10 goes 0.970 → 0.995 at L2 and 0.915 → 0.950 at L3.

🔑 **Zero calls and a bit-identical score on clean text.** The tier escalates only once no known
template has matched by turn 2, so the sessions that do not need it do not pay for it — not in latency,
not in tokens, not in a live-endpoint dependency. This is the brief's *"runtime workflow
re-orchestration"* with a number on both sides.

⚠️ **These are lower bounds.** The endpoint is shared and was heavily rate-limited during the run: 27%
of calls failed at L2 and 80% at L3. Every failure falls back to the deterministic path, which is why
the score still rose — the model is a bonus, never a dependency. On an uncontended endpoint the gain
should be larger, and that measurement has not been taken.

**It does not change the shipped default, and that is deliberate.** PROBLEM.md's model policy says
*"organizer policy may disable network access"* for official scoring. So R3 ships offline-first: every
headline number in [R3-RESULTS.md](../R3-RESULTS.md) §1 is the **network-free** path, and this tier is
an opportunistic improvement on top when the endpoint exists. Reporting the offline number as the
headline is the honest way round; quoting 0.8926 as R3's L3 score would be claiming a capability that
may not be available when it counts.

## D22 — leakage audit: what is contaminated, what is not, and one measurement bug it found

Prompted by the right question: the headline table is scored on all 200 sessions, and 140 of those were
used for tuning. So what exactly is in-sample?

### What is clean

- **Every fitted parameter.** `scripts/fit_policy.py`, `fit_gain.py` and `fit_joint.py` all read
  `holdout.load()["train"]` and nothing else. The 60 was never scored during any sweep.
- **The split itself.** Disjoint on sample ID *and* target ASIN, scenario-stratified, hash-locked at
  `a367f15873d772aa`, with a test that fails if it moves.
- **The catalog.** `ItemIndex` and `CategoryBelief` are built from all 50,000 products including the
  test targets — but the catalog is given, frozen and read-only, and the evaluator itself reads it.
  That is not leakage.

### What is contaminated, stated plainly

**1. ⚠️ The headline table in [R3-RESULTS.md](../R3-RESULTS.md) §1 is scored on all 200, so 70% of it is
in-sample.** It is reported that way for comparability with R1's and R2's published numbers, which were
also all-200 — but it is not an unbiased estimate, and the held-out table in §2 is the one to trust.

**2. ⚠️ On the held-out 60 alone, R2 beats R3 on clean text** — 0.9728 against 0.9708. "R3 wins every
condition" is an all-200 statement and does **not** survive on the clean held-out half. What does
survive, and by a wide margin, is L3: **0.8381 against R2's 0.6863 and R1's 0.6740.**

**3. Structural decisions were made while looking at all-200 ablations** — not just parameters. That is
researcher-degrees-of-freedom leakage and no split protects against it. So the two largest were re-run
per half:

| Decision, re-tested | train140 | test60 | verdict |
|---|---|---|---|
| switch EIG off — clean | +0.0247 | **+0.0125** | holds, same sign |
| switch EIG off — L3 | +0.0514 | **+0.0445** | holds, same sign |
| drop BLaIR — clean | +0.0033 | −0.0033 | **sign flips**, both inside noise |
| drop BLaIR — L3 | −0.0046 | +0.0110 | **sign flips**, both inside noise |

The EIG decision generalises. The BLaIR decision is a coin flip on either half — which is itself the
finding (it buys nothing), but "dropping BLaIR helps" is **not** supportable; only "it makes no
difference" is.

**4. The level-1 `temperature`/`tau_mass` frontier was first swept on all 200 (D14) before being
re-swept on the 140.** I had seen the full-set table when the train-only sweep confirmed the same
point. Exposure is small — the joint re-fit later showed clean and L2 are completely flat in both
parameters and L3 moves 0.006 — but the choice was not made blind.

**5. The 200 public sessions are dev data; the real test is the private 800.** The 140/60 split is an
internal generalisation estimate, not a competition requirement, and it cannot detect overfitting to
properties of the public set as a whole (its scenario mix, its difficulty distribution, the fact that
`coarse_category` behaves as it does).

### The measurement bug this audit found

**A warm `.cache/llm` silently turns the offline path into the LLM path.** Re-running R3 at L3 after the
D21 measurement had populated the cache gave **0.8926 with 380 cache hits and zero network calls** —
which looks exactly like an offline run unless you count cache hits. The published 0.8297 was measured
before the cache existed and is correct, but it was reproducible only by accident.

**Fixed:** `R3_OFFLINE=1` now disables the tier *and* its cache, `scripts/final.py` sets it for every
headline number, and `tests/test_runtime_deps.py` asserts it. Verified: 0.9720 / 0.8845 / 0.8297 with
`llm=None` and 0 cache hits.

### Not train/test leakage, but leakage of a kind — worth naming

- **The simulator is invertible.** Constraints are drawn verbatim from the catalog's `features` and
  `details`, so the agent can reconstruct what the customer will say. Disclosed throughout via
  `no_spec_phrase` (R3: 0.9339), which is exactly the standing estimate of what remains without it.
- **The popularity prior exploits the sampling.** Targets come from a 5-core leave-last-out split and
  are ~570× more reviewed than the catalog median (IMPORTANT.md §5). It is the single largest
  contributor under stress (−0.121 to remove). It should hold on the private 800, which is drawn the
  same way — but if the organizer sampled targets differently, **this is the assumption that breaks
  first**, and `no_popularity` (0.9604) is the number to quote if it does.
