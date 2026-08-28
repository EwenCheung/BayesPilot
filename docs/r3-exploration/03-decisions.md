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
