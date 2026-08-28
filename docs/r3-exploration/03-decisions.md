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
