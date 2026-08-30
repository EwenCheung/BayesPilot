# R4 — decision log

Append-only. One entry per decision that a measurement caused or reversed. A rejected idea with its
number is worth more than a silent deletion.

D1–D5 are **pre-decisions**: taken from measurements made before any R4 code existed, recorded here so
the road starts from evidence rather than from the proposal's assumptions.

---

## D1

**The headroom moved from MRR to Efficiency, and two root docs are stale.**

[IMPORTANT.md §0](../../IMPORTANT.md) and [REPORT.md Part 6](../../REPORT.md) both state *"all
remaining headroom is MRR (+0.075 available vs +0.012 from speed)"*. That was computed on
`public_set.jsonl` where Hit@10 = 1.000 and MTTC = 2.59.

📊 On `dev.jsonl` (2,000 sessions, target ASINs disjoint from public), R3 clean:

| Term | Lost | |
|---|---|---|
| Efficiency | **0.0332** | MTTC 3.05 vs the 1.39 floor |
| MRR | 0.0250 | misses 0.0092 + rank 2–10 **0.0159** |
| Hit@10 | 0.0152 | 61 never converge |

**Decision:** R4 targets Efficiency and Hit first, ranking last. A perfect reranker that promoted
every rank-2-to-10 hit to rank 1 is worth **≤ 0.0159** — that is the hard ceiling on the entire "rank
it higher" family, and it bounds how much LLM reranking can ever buy here.

**Consequence outside R4:** IMPORTANT.md and REPORT.md carry a recommendation that the larger sample
contradicts. Per [IMPORTANT.md §13.3.1](../../IMPORTANT.md) — *"when a measurement changes a
recommendation, update every document carrying that recommendation in the same pass"* — this needs a
reconciliation pass. Not done here; R4 is not licensed to edit the root docs.

---

## D2

**"Persistent candidate pool" is what a posterior already is — adopted as a *feature*, rejected as an
architecture.**

The proposal asks for a candidate pool carried across turns, with a persistence/history score, soft
decay, and hard removal on contradiction. Each part already exists in R3:

| Proposed | R3 equivalent |
|---|---|
| carry candidates across turns | the posterior *is* accumulated evidence — `P(i) ∝ prior × Π L(e_t \| i)` |
| persistence / history score | multiplying likelihoods across turns; an item consistent with every utterance accumulates mass |
| decay when less relevant | `stall_decay`, split on whether templates are still matching |
| hard contradiction removes a candidate | 🔴 **deliberately rejected.** Every factor is bounded below (`ℓ_min > 0`) so no evidence can zero an item |

That last row is a real disagreement, not an oversight. Hard removal is R1's behaviour, and R1 loses
badly under paraphrase (L3 0.7241 vs R3's 0.8299) precisely because one reworded character makes a
`frozenset &` return empty. **Re-introducing hard removal would re-introduce R1's failure mode.**

**Decision:** do not rebuild the pool. Take **rank stability of the top 3 across turns** as one input
feature to the calibrator ([00-r4-spec.md §4](00-r4-spec.md)) — that is the part of the idea R3 does
not already have, because R3 never looks at how its own ranking has moved.

---

## D3

**"Ask the attribute that best separates the candidates" — rejected twice over.**

*Measured, already:* this is expected-information-gain question selection. R3 built it, measured it,
and shipped it **off** — −0.021 clean, −0.040 L3 (R3 D18). CLAUDE.md lists it among four things not to
re-propose without new evidence.

*And structurally, the simulator cannot answer it.* From `customer_reply()`:

```python
matches = [v for v in constraints
           if v not in disclosed and (attribute == "other" or classify_constraint(v) == attribute)][:2]
```

- The customer holds exactly **four** constraint strings and nothing else. There is no attribute to
  probe that is not already one of those four.
- `classify_constraint` is a crude keyword rule that over 800 public constraints emitted `feature` 404,
  `material` 302, `color` 60, `style` 19, `size` 11, `use_case` 4 and **never** `brand`, `budget` or
  `category`. Asking the semantically correct attribute frequently returns *"I don't have an additional
  preference"* and burns the turn.
- `"other"` bypasses classification entirely and returns the next two undisclosed constraints, so **two
  asks exhaust the card**. No selection policy can beat two `"other"`s at extraction.

**Decision:** rejected. The reformulation that *is* supported by evidence is the opposite one — not
"ask a better question" but **"detect that no question can help and stop asking"** ([D6](#d6) / spec
§5). Once all four strings are disclosed, further turns are provably information-free.

---

## D4

**Dynamic truncation is measured-negative. Build it, default it off, publish the cost.**

Rank is the index in *your own* submitted list (`ranked.index(target) + 1`), so truncation cannot
promote anything — it only deletes slots. There is no penalty for a long list: invalid IDs are dropped
without consuming a slot and length is never scored.

📊 R3 on `dev.jsonl`, lower bound (ignores later-turn recovery):

| depth | Hit@10 | MRR |
|---|---|---|
| **10** | **0.9695** | **0.9167** |
| 8 | 0.9655 | 0.9162 |
| 7 | 0.9630 | 0.9159 |
| 5 | 0.9560 | 0.9148 |
| 3 | 0.9455 | 0.9125 |

Slots 8–10 are free lottery tickets worth ~0.003 of score; cutting to 3 costs ~0.012.

**Decision:** always ship 10. Implement truncation behind `flags.truncate` (default 0) because
PROBLEM.md §4.3 names *"custom dynamic truncation"* as in scope, measure it exactly (R4-A27), and
report the negative. Omitting a named requirement reads as a missing pillar; including it without the
measurement is an unevidenced claim. **Measuring it and saying so is the strongest position
available** — the same argument [IMPORTANT.md §14.1](../../IMPORTANT.md) makes for the LLM ranking
stage.

---

## D5

**`FirstHit@3` must be read off the internal ranking, and `runs/*.json` manifests are not actually
committed.**

Two defects caught while specifying the instrument.

**(a) The evaluator breaks on first hit.** `if override_applied and target in ranked: … break`. So a
target's rank cannot evolve across turns — the proposal's worked example (*"Turn 1 #4 → Turn 2 #2 →
Turn 3 #3"*) is impossible for the target unless the agent never shipped it. Computed on shipped
lists, `FirstHit@3` is definitionally MTTC. **It is only informative when computed on the agent's
internal ranking, captured before the ship/hold decision** ([01-contracts.md §3](01-contracts.md)).
R4-A6 tests that it actually differs from MTTC; if it does not, the instrument is measuring nothing.

**(b) `runs/holdout.json` was never committed.** `.gitignore` has `runs/*` with only
`!runs/registry.jsonl` un-ignored, while `src/eval/holdout.py`'s docstring says the manifest *"is
generated once and committed"* and that `content_hash()` locks it. The lock currently holds only
because `build()` is seed-deterministic — not because the artefact is under version control, which is
what the docstring claims. R4 must un-ignore `runs/devsplit.json` (and retro-fix `runs/holdout.json`)
or repeat the defect.

---

## D6

**Exhaustion detection: direction confirmed, value not yet fitted.**

📊 `stall_decay_clean` is fitted at 0.8 on the 200-session set. On `dev.jsonl`:

| | Hit@10 | MRR | MTTC | Score |
|---|---|---|---|---|
| 0.8 (shipped) | 0.9695 | 0.9167 | 3.05 | 0.9188 |
| **0.4** | **0.9740** | 0.9159 | **2.77** | **0.9263** |

**+0.0075, with Hit@10 up and MRR flat.** A constant fitted on 200 sessions did not generalise to
2,000.

⚠️ **0.4 was chosen by reading all 2,000 sessions and is therefore spent as a fitted value.** It
stands as a *direction* — ship earlier when stalled — and as the bar the machinery must beat
(R4-A12). The value is re-fitted on the `dev` train split and reported on test.

The mechanism this points at: for the 232 slow/miss sessions the four constraint strings are already
disclosed and generic ([spec §1.3](00-r4-spec.md)), so no further turn can yield information. Shipping
at turn 3 instead of turn 6–10 costs nothing in MRR and recovers Efficiency directly.

---

## D7

**The road's premise is falsifiable at R4-A8, and that gate comes before any calibration work.**

R4's whole thesis is that the internal ranking finds the target meaningfully earlier than the agent
ships it. **That has not been measured** — it cannot be, without the instrument.

If `EarlyHit@3(T)` turns out to sit barely above the shipped curve, then the agent is already
shipping about as soon as it knows, there is no recoverable Efficiency, and R4 stops with that
negative written up. Phase C is not started until R4-A8 has a number.

Recording this now so the gate is not quietly skipped once the instrument exists and the calibration
work looks more interesting.

---

## D8

**R4-A0 answered: turn 5 is empty because the depth ladder freezes, and the agent re-ships a list it
has already been told is wrong.**

Probed 400 `dev.jsonl` sessions, logging depth, stalls and the shipped top-1 per turn.

| turn | shipped depths | top-1 vs previous turn |
|---|---|---|
| 3 | `{1: 185}` | changed 167 · **SAME 18** |
| 4 | `{1: 71}` | changed 10 · **SAME 61** |
| **5** | `{1: 43}` | changed 0 · **SAME 43 (100%)** |
| 6 | `{1: 2, 2: 41}` | changed 1 · SAME 42 |
| 7 | `{2: 2, 3: 22}` | changed 1 · SAME 23 |

The mechanism is arithmetic, not a heuristic. `depth()` adds item *k* only when `1/k > horizon`, and
`horizon = v_continue · stall_decay^stalls − turn_cost`. With the shipped constants that gives

| stalls | horizon | depth |
|---|---|---|
| 0–2 | 0.833 → 0.509 | **1** |
| 3 | 0.394 | 2 |
| 4 | 0.302 | 3 |

`stalls` only starts incrementing once the four constraint strings are exhausted (turn 4 for both
buying and browsing), so it does not reach 3 until turn 6. **Turns 4 and 5 therefore ship a depth-1
list whose top item has not changed** — and the session being alive is proof that item is not the
target. 43 of 43 sessions alive at turn 5 re-shipped a guaranteed miss.

🔑 **The general statement is stronger than the bug.** The evaluator does
`if override_applied and target in ranked: break`, so surviving a hit-checked turn is a *measurement*:
every item in that list is proven not to be the target. R3 discards that observation. A posterior
should absorb it — `P(item | survived) = 0`.

**Decision:** implement it as evidence, behind `exclude_shipped`. Measured, `R3_OFFLINE=1`,
`PYTHONHASHSEED=0`:

| condition | R3 | R4 + `exclude_shipped` | Δ |
|---|---|---|---|
| dev train (1200) | 0.9196 | 0.9472 | **+0.0275** |
| **dev test (800)** | **0.9175** | **0.9473** | **+0.0298** |
| dev test L2 | 0.5113 | 0.6478 | **+0.1365** |
| dev test L3 | 0.4220 | 0.5361 | **+0.1140** |
| public 200 clean | 0.9731 | 0.9801 | +0.0070 |
| public 200 L3 | 0.8299 | 0.8505 | +0.0206 |

On the full 2,000: Hit@10 0.9695 → **0.9835**, MRR 0.9167 → **0.9697**, MTTC 3.05 → **2.77**, score
0.9188 → **0.9472**, bootstrap CIs `(0.9108, 0.9268)` and `(0.9414, 0.9527)` — **non-overlapping**.

The rule has **no fitted parameters**, which is why train and test agree to 0.002. It is a correctness
fix, not a tuning gain, and R4-A12's target of 0.9263 is already cleared without touching
`stall_decay_clean`.

---

## D9

**Two failed versions of the same rule, and both failures were about *soundness*, not scoring.**

The exclusion is only valid on turns the evaluator actually hit-checked. `intent_override` sessions
discard turns 1–2 even at rank 1, so an item shipped there is **not** proven wrong — and it is
disproportionately likely to *be* the target, since it was the agent's top pick.

**Attempt 1 — guard on `state.route`.** Cost **−0.0125** at L3 on the public set: 9 of 30
`intent_override` sessions turned from rank-1 hits into outright misses. Paraphrase degrades route
detection, the guard silently opened, and the agent erased the right answer before the override
landed.

**Attempt 2 — soften it.** Replace hard exclusion with a large finite penalty for unproven ships, on
the reasoning that R3's own rule (D2) is that no evidence may zero an item. **Worse: −0.0607 on public
clean**, override MRR 0.983 → 0.504. Sweeping the penalty made the cause unmistakable:

| `shipped_penalty` | public clean | override MRR |
|---|---|---|
| 10.0 | 0.9124 | 0.504 |
| 1 000 000 | 0.9105 | 0.476 |
| **0.0** | **0.9801** | **1.000** |

🔑 **"Penalise what is probably wrong" is worse than "ignore it".** An unchecked turn's top item is the
one *most* likely to be the target; penalising it buries the right answer. The correct rule is binary
— hard-exclude what is proven, do nothing at all to what is not. `shipped_penalty` stays as a flag,
defaulted to 0.0, so the negative reproduces.

**The actual defect, and it is a one-liner.** `SessionState.route` **defaults to `"browsing"`**, so
`route != "override"` is not evidence of anything — it is also exactly what an unparsed opener looks
like. Under L3 the opener template does not match, the route keeps its default, and the guard reads
the default as proof. The test has to be *positive*:

```python
if turn >= OVERRIDE_SETTLED:          # override.turn ∈ {3,4}: by turn 4 it has landed, always
    proven = True
elif state.category is None or state.paraphrased():
    proven = False                    # never actually read the opener — assume nothing
else:
    proven = state.route != "override" or state.override_seen
```

`state.category` is set only inside the matched-opener branch, so it is the positive signal that the
route was read rather than defaulted. This took public-200 L3 from **−0.0110 to +0.0206** and left
every other condition unchanged.

⚠️ **Generalisable lesson: a default value is not a measurement.** Any guard that reads a field
which has a sensible default is silently true whenever parsing failed — which is precisely the
condition under which the guard was needed.

---

## D10

**The `dev.jsonl` stress numbers are far below the public set's, and the rewriter is the suspect.**

R3 scores 0.8299 at L3 on the 200 public sessions but **0.4220** at L3 on the 800 dev test sessions —
a gap of 0.41 that no property of the agent explains. Both roads are measured under the same
`ParaphraseRewriter`, so the *deltas* in D8 remain valid, but the *levels* do not transfer.

The likely cause is that the rewriter's substitution vocabulary was built against `public_set.jsonl`'s
categories and payload strings, so on dev's disjoint targets it either rewrites nothing or mangles
text far more aggressively than it does on the set it was written for.

**Not investigated here** — it does not affect any R4 conclusion, because every comparison in D8 is
R3-vs-R4 under an identical rewriter. Recorded because **`docs/R3-RESULTS.md`'s published L1–L3
numbers are stated as properties of the roads, and this suggests they are partly properties of the
rewriter.** Anyone quoting them on a new dataset should re-derive them first.

---

## D11

**Correction pass: `train.jsonl` is the fitting set, and two values had to be re-derived.**

A 12,000-session `train.jsonl` was added, with target ASINs disjoint from both `dev.jsonl` and the
public 200 and the same 40/40/15/5 mix. The standing rule is now: **fit on train, report on dev and
public.** Phase F predated it and two of its values were chosen by reading evaluation sets.

**(a) `devsplit.py` deleted.** It carved `dev.jsonl` into 1200 train / 800 test. Splitting an
evaluation set does not make it a training set — it spends it either way. Replaced by
`src/eval/datasets.py` plus `tests/test_datasets.py`, which AST-checks that no fitting code so much as
*names* `dev.jsonl` or `public_set.jsonl`.

**(b) `shipped_penalty = 0.0` — re-derived on train, conclusion unchanged.** The original sweep was on
the public 200. Repeated on `train.jsonl[:4000]`:

| `shipped_penalty` | train score |
|---|---|
| **0.0** | **0.9487** |
| 2 | 0.9334 |
| 10 | 0.8847 |

Independently reproduces D9's finding. The value is now legitimately fitted.

**(c) 🔑 `stall_decay_clean = 0.4` — withdrawn. The gain was an artefact of the bug it was masking.**

| `stall_decay_clean` | train[:4000] | all 12,000 |
|---|---|---|
| 0.8 (R3 default) | 0.9487 | 0.9505 `(0.9482, 0.9525)` |
| 0.6 | 0.9492 | **0.9509** `(0.9490, 0.9527)` |
| 0.4 | 0.9488 | — |
| 0.2 | 0.9473 | — |

The whole range spans 0.002 and the two full-train CIs overlap almost completely. On `dev` before the
fix, 0.4 looked worth **+0.0075** ([D6](#d6)) — because shipping deeper *earlier* partially
compensated for re-shipping a list already proven wrong. Once `exclude_shipped` removes that waste,
the constant stops mattering. **Left at R3's default of 0.8**; D6 is superseded.

⚠️ **Generalisable: a tuning gain measured on top of a bug is a measurement of the bug.** The +0.0075
was real on the data and would have been shipped as a fitted constant, permanently encoding a
workaround for a defect that a correctness fix removes for free.

### The result, re-established under the rule

Fitted on `train.jsonl` (12,000), R3 constants otherwise untouched:

| | Hit@10 | MRR | MTTC | Score | 95% CI |
|---|---|---|---|---|---|
| R3 | 0.9733 | 0.9223 | 2.99 | 0.9235 | (0.9203, 0.9264) |
| **R4 `exclude_shipped`** | **0.9867** | **0.9735** | **2.75** | **0.9505** | (0.9482, 0.9525) |

Then read **once** for reporting:

| condition | R3 | R4 | Δ |
|---|---|---|---|
| dev 2000 clean | 0.9188 | 0.9472 | **+0.0284** |
| dev 2000 L2 | 0.5065 | 0.6478 | **+0.1413** |
| dev 2000 L3 | 0.4250 | 0.5435 | **+0.1185** |
| public 200 clean | 0.9731 | **0.9801** | +0.0070 |
| public 200 L2 | 0.8857 | 0.9072 | +0.0215 |
| public 200 L3 | 0.8299 | 0.8505 | +0.0206 |

Public 200 reaches **Hit@10 1.0000 and MRR 1.0000** — every session converts at rank 1, MTTC 2.00.
Train and both test sets agree to within 0.003 on the delta, which is what a change with no fitted
parameters should look like.

---

## D12

**Phase I built, and R4-A8 kills Phase C. A perfect stopping rule is worth +0.0033.**

`scripts/earlyhit.py` on `train.jsonl[:4000]`, `exclude_shipped` on. `EarlyHit@k(T)` is the share of
sessions whose **internal** ranking held the target by turn T; `shipped` is what MTTC records.

| turn | 1 | 2 | 3 | 4 | 5 | 6 | 10 |
|---|---|---|---|---|---|---|---|
| EarlyHit@1 | 0.207 | 0.675 | 0.890 | 0.932 | 0.949 | 0.957 | 0.964 |
| EarlyHit@3 | 0.285 | 0.783 | 0.940 | 0.960 | 0.965 | 0.968 | 0.980 |
| EarlyHit@10 | 0.416 | 0.874 | 0.970 | 0.979 | 0.981 | 0.982 | 0.986 |
| **shipped** | 0.115 | 0.541 | 0.886 | 0.931 | 0.948 | 0.961 | 0.986 |

R4-A6 passes: the curves differ from MTTC on far more than 20% of sessions — the gap at turn 2 is
**0.241**. So the instrument measures something real.

⚠️ **But the raw gap is not recoverable value, and reading it as such would have been the mistake this
phase existed to prevent.** Holding a rank-3 list one more turn to ship it at rank 1 is *correct*:
RR 0.333 → 1.000 gains 0.20 of MRR and costs 0.02 of Efficiency. Most of that 0.241 is justified
patience, and the tell is in the numbers — by turn 3, shipped (0.886) has almost exactly caught
EarlyHit@1 (0.890). **The agent already ships within a turn of the target reaching internal rank 1.**

The honest bound is an oracle that ships the instant the target reaches internal rank 1. It cannot
improve MRR (already 1.0 there) or Hit, so everything it gains is pure stopping efficiency:

| | |
|---|---|
| MTTC now | 2.704 |
| MTTC under oracle stopping | 2.538 |
| turns recoverable | 0.166 |
| **⇒ ceiling on a perfect stopping rule** | **+0.0033** |

🔴 **R4-A8 fires. Phase C is not built.** The spec set this gate precisely so calibration would not be
built on a hope: *"If the internal ranking has the target in the top 3 barely earlier than the agent
ships, there is nothing for a better stopping rule to recover."* A calibrated posterior cannot beat an
oracle, so **+0.0033 is the hard ceiling on all of Phase C** — less than the bootstrap CI width
(±0.002 either side) and a fraction of what `exclude_shipped` already delivered (+0.027).

### Where the loss actually is — and it redirects the road

| | share | nature |
|---|---|---|
| never in internal top-10 | **1.38%** | **recall** — retrieval never surfaced it |
| in top-10 but never rank 1 | **2.22%** | **ranking** — surfaced, never promoted |
| stopping inefficiency | 0.166 turns | **+0.0033** |

**The remaining loss is recall and ranking, not stopping.** Both point at
[§1.3's selectivity finding](00-r4-spec.md) — when the intent card's constraint strings are shared by
hundreds of catalog items, the evidence cannot discriminate and the popularity prior promotes an
impostor. That is **Phase S**, not Phase C.

**Decision:** skip Phase C. Go to Phase S with the target restated as *raise `EarlyHit@1`'s ceiling
from 0.964*, which is a recall-and-ranking problem, rather than *close the gap to `shipped`*, which is
worth 0.0033.

---

## D13

**Phase S re-aimed: there is no recall problem. Every remaining failure is ranking inside the pool.**

D12 split the residual loss into "recall" (never in internal top-10) and "ranking" (in top-10, never
rank 1). That split was made from the top-10 window, which turns out to have been the wrong lens.
Probing the **full** internal ranking on `train.jsonl[:3000]` with `exclude_shipped` on:

| outcome | n | share | final internal rank of the target |
|---|---|---|---|
| hit at rank 1 | 2884 | 96.13% | median 1, p90 1 |
| hit at rank 2+ | 71 | 2.37% | median 2, p90 6 |
| **miss — in pool, ranked deep** | **45** | **1.50%** | **median 69, p90 206** |
| **miss — not in pool** | **0** | **0.00%** | — |

🔑 **Level 1 never fails.** The category posterior put the target in the pool in 3000 of 3000
sessions, mean pool size 335. Nothing is lost to retrieval. **The entire residual is level 2 putting
the right item at rank 69 of 335.**

That kills the "recall" half of D12's decomposition — those 1.38% were not un-retrieved, they were
under-ranked past position 10 — and it means Phase S is a pure ranking problem with a known
signature ([§1.3](00-r4-spec.md)): the missed targets are the ones whose constraint strings are
generic *and* whose `rating_number` is low (median 7, against 24 for rank-1 hits).

The causal chain, and each link is already measured:

1. generic constraints match most of the pool, so the evidence terms are near-constant;
2. `likelihood.py` is *designed* so a term with no opinion cancels in the normalisation — correctly;
3. with the likelihoods silent, the **popularity prior alone decides the ranking**;
4. the target is unpopular, so it sinks.

**Decision:** make the prior's weight a function of the evidence's selectivity rather than a
constant. `src/r4/belief.py` adds `flatness()` — the fraction of the pool matched by the *most
selective* live constraint — and `SelectiveBelief`, which scales the prior by `1 - prior_damp *
flatness`. Sharp evidence keeps the prior as a tie-break; flat evidence quietens it.

⚠️ **Scaling, never removal.** `no_popularity` costs R3 0.028 and R1 0.242; the prior remains the
single most valuable signal overall. `prior_damp = 0` reproduces R3's `Belief` exactly, which is what
keeps R4-A1 meaningful — verified, the reduction test still passes with `SelectiveBelief` in place.

### A bug in the detector, caught by its own test

The first `flatness()` counted a candidate as "matched" when its likelihood sat above `log(L_MIN)`.
That floor **never binds**: `_bounded` returns `log(max(L_MIN, exp(s·g - g)))`, and at the shipped
`exact_gain = 3.2` even `s = 0` gives `exp(-3.2) = 0.041 > L_MIN = 0.02`. So every candidate scored
above the floor and the function returned 1.0 — maximally flat — for perfectly sharp evidence. A unit
test with one match in a hundred caught it immediately; an end-to-end sweep would have reported
"prior_damp buys nothing" and been believed. The correct threshold is `_bounded(0, gain)`, the value a
non-match actually receives.

---

## D14

**🔑 The popularity prior is re-fitted to ZERO on train, and Phase S's adaptive mechanism is subsumed
by that. This reverses a headline finding of the whole project.**

R4 inherited six constants from R3, every one fitted on a 120-session split of the official 200 — a
set R4 now saturates (Hit 1.0000 / MRR 1.0000, so it cannot discriminate anything). `scripts/fit_r4.py`
re-derives all six on `train.jsonl`, R3's staged order, R3's identical objective (mean of L0/L2/L3).

**Three of six moved. One moved catastrophically.**

| constant | R3 (official-200 fit) | train fit | |
|---|---|---|---|
| **`prior_weight`** | **0.18** | **0.00** | 🔑 the entire story |
| `v_continue` | 0.90 | 0.75 | marginal, +0.0008 |
| `tau_mass` | 0.90 | 0.85 | marginal, +0.0013 |
| `stall_decay` | 0.20 | 0.20 | unchanged |
| `stall_decay_clean` | 0.80 | 0.80 | unchanged — **D11 confirmed a third time** |
| `exact_gain` | 3.20 | 3.20 | unchanged |

⚠️ **`prior_weight` won at the low edge of the swept range `(0.10, 0.18, 0.26, 0.40)`, so the sweep was
extended downward. A boundary optimum is not an optimum.** It kept improving all the way to zero:

| `prior_weight` | L0 | L2 | L3 | obj |
|---|---|---|---|---|
| **0.00** | 0.9499 | **0.7759** | **0.7214** | **0.8157** |
| 0.02 | 0.9508 | 0.7762 | 0.7032 | 0.8101 |
| 0.05 | 0.9508 | 0.7595 | 0.6755 | 0.7953 |
| 0.10 | 0.9502 | 0.7172 | 0.6244 | 0.7639 |
| 0.18 (R3's) | 0.9483 | 0.6632 | 0.5593 | 0.7236 |

**Deleting the popularity prior outright is worth +0.092 on the objective**, and L0 is flat across the
whole range (0.9483 → 0.9499) — this is not trading clean accuracy for robustness, it is free.

### Why this contradicts IMPORTANT.md §5, and why both can be true

[IMPORTANT.md §5](../../IMPORTANT.md) calls the popularity leak *"the biggest free win in the whole
problem"*; R3 measured `no_popularity` at −0.028 and R1 at −0.242. Those measurements were taken
**without `exclude_shipped`**, and that is the whole explanation.

The prior's value was producing a good *first* guess. Once surviving a hit-checked turn proves the
shipped items wrong ([D8](#d8)), the agent eliminates popular impostors by iteration instead — it no
longer needs the prior to start well, because starting wrong is now cheap. What remains of the prior
is only its bias, and that bias points the wrong way: the missed targets have median `rating_number`
**7** against 24 for the rank-1 hits ([§1.3](00-r4-spec.md)).

🔑 **A signal's value is conditional on the rest of the system.** The popularity prior was genuinely
worth +0.24 to R1 and is worth ≤ 0 to R4, and neither measurement is wrong.

### Phase S: the diagnosis was right and the mechanism still dies

[R4-A10](02-acceptance.md) passed cleanly — `flatness` separates outcomes ~2.8×:

| outcome | n | median flatness |
|---|---|---|
| rank 1 | 2404 | **0.190** |
| hit rank 2+ | 62 | 0.475 |
| miss | 34 | **0.527** |

And damping helps at any fixed prior weight (+0.005 at 0.10, +0.009 at 0.18). But every adaptive
configuration loses to simply deleting the prior:

| config | obj |
|---|---|
| **prior 0.00, damp 0** | **0.8157** |
| prior 0.10, damp 1.0 | 0.7692 |
| prior 0.10, damp 0 | 0.7639 |
| prior 0.18, damp 1.0 | 0.7325 |
| prior 0.30, damp 1.0 | 0.6877 |

**Decision:** `prior_damp` ships **off**. `src/r4/belief.py` stays, because the negative is worth
reproducing and `flatness()` is the diagnostic that explains D14 — but the mechanism earns nothing
over one constant going to zero. That is exactly what the kill gate existed to detect: the limit case
of the idea beat every partial version of it.

⚠️ **Risk note.** The objective weights L0/L2/L3 equally, so this is fitted assuming paraphrase is
likely. If the private set is *not* paraphrased, `prior_weight = 0` costs nothing (L0 is flat); if it
is, it gains ~0.09. The asymmetry is favourable in both directions, which is the only reason a
reversal this large is being shipped on one re-fit.

### Consequence for R4-A1

A default R4 is no longer numerically R3, so `tests/test_r4_reduces_to_r3.py` now resets the six
inherited constants to R3's values before comparing. The test was always about proving the copied
`_respond` has not drifted — not that the constants match — and it still passes on 200 and 12,000.
