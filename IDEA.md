# IDEA.md — Directions we can explore

> **Document map.** Three docs, one project.
> **[IMPORTANT.md](IMPORTANT.md) is authoritative on facts** — rules, evaluator mechanics, measurements (§12),
> errors & learnings (§13), requirement audit (§14). Where any doc disagrees with it on a number or a rule, it wins.
> [REPORT.md](REPORT.md) = the narrative: what the problem is and what we found.
> **[IDEA.md](IDEA.md) = this file: proposals only.** What we could build, why, and how we'd know it worked.
> It quotes [IMPORTANT.md](IMPORTANT.md) rather than restating findings.
> Reproducible scripts live in [experiments/](experiments/).

**This file contains no findings.** Every number quoted here is sourced from
[IMPORTANT.md §12](IMPORTANT.md); every mistake already made is in [IMPORTANT.md §13](IMPORTANT.md). Read those first.

**Where we stand:** starter `0.1067` · paraphrase-proof floor `0.826` · our prototype `0.9607` · max `0.9922`.
Hit@10 is already 1.000, so **all remaining headroom is MRR** (+0.075 available vs +0.012 from speed).

---

---

# How to start

**Three exploration roads. R1 and R2 run in parallel; R3 fuses them afterwards.**

```
        ┌──────────────────────────┐
        │  Phase 0 — shared setup  │   harness · catalog index · paraphrase stress · embeddings
        └────────────┬─────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   🔵 R1 filter            🟢 R2 ranker          ← parallel worktrees, race them
   candidate set           scored list
         └───────────┬───────────┘
                     ▼
              🟣 R3 posterior                    ← starts after both; reuses their parts
        prior × R1-likelihood × R2-likelihood
```

| Road | One line | When |
|---|---|---|
| 🔵 **R1** | The agent is a **filter** — shrink a candidate set until one item survives. | now, parallel |
| 🟢 **R2** | The agent is a **ranker** — score everything, order it, take the top 10. | now, parallel |
| 🟣 **R3** | The agent is a **posterior** — R1 and R2 become evidence terms in one belief. | after both |

**Why R3 waits:** it is not a third guess, it is the *principled merge*. Popularity becomes the prior, R1's exact
matching and R2's dense similarity become likelihood terms, and entropy replaces the hand-tuned confidence gate.
It has nothing to fuse until R1 and R2 exist — so building it first would mean building them badly, twice.

```bash
# Phase 0 lands on main first
git worktree add ../r1-constraint idea/r1-constraint
git worktree add ../r2-rank       idea/r2-rank
# after R1 and R2 have results:
git worktree add ../r3-bayesian   idea/r3-bayesian
```

Each road is free to combine as many of the 40 components in §0.1 as it wants — that is the exploration.
Detail in [§0.3](#03-three-exploration-roads).

---

# Part 0 — Idea index and track assignment

**40 ideas** live in this file — they are *components*, not rival solutions. §0.1 indexes all of them; §0.3
compiles them into **three genuinely rival architectures**, one per worktree.

## 0.1 The full index

**Recall — how we find candidates (9)**
1. **Spec-phrase exact index** — hash catalog `features`/`details` strings, match stated requirements verbatim. ⚪ built
2. **`bge-m3` dense** — 1024-d embeddings of the catalog; the semantic route. ⚪ measured
3. **Popularity prior** — log `rating_number`; paraphrase-proof and startlingly strong alone. ⚪ built
4. **BM25 / FTS5** — classic keyword scoring, already in the starter. ⚪ built
5. **HyDE** — LLM writes the product the customer describes, embed *that* instead of the query.
6. **PRF / Rocchio / RM3** — push the query vector toward what you just retrieved, re-query.
7. **BGE-M3 sparse + ColBERT** — same model also emits learned-sparse and token-level vectors.
8. **Doc2Query expansion** — predict the queries each product answers, add them to its indexed text.
9. **Generative retrieval / semantic IDs (TIGER)** — RQ-VAE item codes, generated rather than matched. 🔴 stretch

**Ranking — how we order them (7)**
10. **Scheduled linear blend** — `dense + w·log(pop)`, `w` a function of confirmed slots. Beat RRF.
11. **RRF** — `Σ 1/(k+rank)`; keep as the parameter-free baseline.
12. **LightGBM / LambdaMART** — gradient-boosted ranker over ~20 engineered features.
13. **MMR / DPP diversity** — trade relevance for coverage; fills the brief's "diverse retrieval" requirement.
14. **LLM listwise rerank** — `qwen3.6:35b` permutes the top 20.
15. **E2Rank** — embedding model as a listwise reranker; reranker quality at cosine cost.
16. **Cross-encoder** — joint `(query, product)` scoring; highest ceiling, needs training data.

**Policy — ask or convert? (7)**
17. **Confidence gate + deadline** — convert on a strict unique leader, hard stop turn 3. ⚪ built
18. **NQC / query-performance prediction** — std-dev of retrieval scores as a real confidence signal.
19. **Information-gain question selection** — ask whatever most reduces candidate-set entropy.
20. **BED-LLM** — LLM proposes questions, Bayesian machinery scores them.
21. **Bandits / EVOI** — ask-vs-convert as explore/exploit with regret bounds.
22. **Deep RL (EAR / SCPR / UNICORN)** — the dominant CRS literature. ⛔ cite as beaten, don't build.
23. **MCTS (SAPIENT)** — multi-turn lookahead. ⛔ our horizon is ~3 turns.

**Knowledge — what we precompute (4)**
24. **Normalised attributes** — one clean ontology over filthy `details` strings.
25. **Use-case tags** — `"good for winter hiking"`; makes vague Browsing queries retrievable.
26. **Synthetic session generator** — a labelled dialog for any of the 50,000 products, free.
27. **Paraphrase augmentation** — rewrite those sessions with an LLM; makes the paraphrase risk the training target.

**Machine learning — what we train (5)**
28. **Learned blend weight** `w(slots, scenario)` — replaces hand-tuning.
29. **LightGBM reranker** on synthetic data — highest ROI on the list.
30. **Score calibration** (Platt) — turns confidence into a real probability for expected-utility decisions.
31. **Cross-encoder** on paraphrase-augmented sessions.
32. **Slot-extraction distillation** — strong teacher, tiny local student, no network at runtime.

**Harness — how it fits together (3)**
33. **Cascade ranking** — `recall → pre-rank → rank → re-rank`; the production pattern, and the right vocabulary.
34. **Four bounded roles** — Router / State / Cascade / Judge. ⛔ not a multi-agent swarm.
35. **Adaptive re-orchestration** — when confidence stalls, the Router changes strategy mid-session.

**Robustness — how we avoid fooling ourselves (5)**
36. **Paraphrase stress harness** — wrap the agent, not the evaluator; report stressed score beside clean.
37. **Ablation switches** — every route behind a flag; `no_spec_phrase` is the honesty metric.
38. **Offline fallback** — local weights, exercised by a test from day one.
39. **Deterministic caching** — content-hash keys; wall-clock is the binding constraint.
40. **Latency + token accounting** — a required disclosure; instrument early.

---

## 0.2 One idea per worktree — what counts as "an idea"

The 40 items in §0.1 are **components**, not ideas. You cannot race MMR against HyDE; you would use both.

**An idea, here, means a different answer to "what kind of problem is this?"** — a different core data structure,
a different loop, a different failure mode. Each such idea is one worktree. Inside a worktree you are free to
combine as many of the 40 components as you like; that is the exploration.

⚠️ **Earlier drafts of this file got that wrong.** Tracks A/B/C/D were four *emphases of the same architecture*
(retrieve → rank → decide), and §0.3 even said *"expect the final submission to be a merge."* If they all merge,
there is no winner to pick. Those are superseded by the three below, which genuinely conflict.

---

## 0.3 Three exploration roads

They disagree about what the agent fundamentally *is*: a filter, a ranker, or a belief.
**R1 and R2 are rivals and run in parallel. R3 fuses them and runs after.**

### Track 0 — Foundation ⛔ shared, land it first (~half a day)
> **Mission:** one harness and one catalog index so all three ideas are measured identically.

- `src/common/` — catalog loading, the parsed `SessionState`, coarse-category index, popularity table
- `src/eval/compare.py` — run registry, ablation flags, paraphrase stress wrapper, bootstrap CI
- Port [experiments/agent_best_0.9607.py](experiments/agent_best_0.9607.py) as `R1`'s starting point

⚠️ **Do not force a shared internal pipeline.** The three ideas decompose differently — R3 has no "retrieval"
step at all — so the only frozen seams are `SessionState`, the catalog index, and the kit's `Agent` boundary.
See §0.4.

---

### 🔵 R1 — Constraint Satisfaction *(the agent is a filter)*

> **The bet:** this is a database query, not a ranking problem. The customer states hard facts; each one
> eliminates products. Rank only to break ties among survivors.

**Core structure:** a shrinking candidate **set**.
```
S = all products in the stated category
each turn:  S ← S ∩ {products matching the new constraint}
            if |S| small or one item strictly dominates → convert
            else ask the attribute that best splits S
```

**Strategies to explore inside this worktree:** spec-phrase exact index (1) · normalised attribute ontology (24)
to make matching survive rewording · information-gain question selection over `S` (19) · popularity as tie-break
(3) · LightGBM to order the survivors (12) · slot decay and un-intersection for intent override · BM25 as the
fallback when `S` empties.

**Status:** ✅ already at **0.9607** — this is the incumbent to beat.
**Pillars:** I filter-track native (browsing weak) · II set intersection *is* accumulation · III weak.
**Wins if:** it survives paraphrase stress. **Dies if:** stressed score < 0.826, or Browsing sessions leave `S` huge.

---

### 🟢 R2 — Retrieve & Rank *(the agent is a ranker)*

> **The bet:** meaning beats matching. Score everything, order it, and let good retrieval absorb any rewording
> the organizer applies. This is literally the pipeline the brief specifies.

**Core structure:** a scored **list**.
```
each turn:  q ← rewrite(state)
            candidates ← ⋃ routes(q)          # spec, bm25, dense, popularity
            scores ← fuse(candidates)          # scheduled blend, weight = f(slots)
            ranked ← rerank(scores)            # LightGBM → MMR → LLM listwise
            convert when the score distribution has committed (NQC)
```

**Strategies to explore:** `bge-m3` dense (2) · HyDE for cold Browsing turns (5) · PRF/Rocchio for multi-turn
accumulation (6) · sparse + ColBERT (7) · doc2query (8) · scheduled blend vs RRF (10, 11) · LightGBM (12) ·
MMR gated on entropy (13) · LLM listwise rerank (14) — the brief's named *"LLM Semantic Ranking"* stage ·
E2Rank (15) · cross-encoder (16) · NQC (18).

**Status:** ✅ paraphrase-proof floor **0.826** measured.
**Pillars:** I is the brief verbatim · II via query rewriting · III via weight scheduling. All four covered.
**Wins if:** it beats R1 *under stress*. **Dies if:** MRR stalls — a ranker that never commits caps out.

---

### 🟣 R3 — Bayesian Fusion = R1 + R2 *(the agent is a posterior)* — **starts after both**

> **The bet:** R1 and R2 are not really rivals — they are two kinds of evidence about the same question, and the
> right way to combine them is a posterior. Ranking and asking then become one problem: every utterance is
> evidence, the best question is the one that most reduces entropy, and you convert when the distribution peaks.

**Core structure:** a **posterior** over the catalog.
```
P₀(item) ∝ popularity                          # the 570× target skew IS a prior
each turn:  P(item) ∝ P(item) · L(utterance | item)
            ask argmax_a  H(P) − 𝔼_r[H(P | a,r)]      # expected information gain
            convert when H(P) < threshold
```

**Why it reuses rather than replaces:** R1 and R2 drop straight in as terms.

| From | Becomes |
|---|---|
| popularity prior (the 570× target skew) | `P₀(item)` — the prior |
| R1's exact constraint matching | a sharp likelihood `L₁(utterance \| item)` |
| R2's dense similarity + fused route scores | a soft likelihood `L₂(utterance \| item)` |
| R1's information-gain question selection | the EIG objective, now exact over a real distribution |
| R1's confidence gate + R2's NQC | replaced by one number: entropy of `P` |

Set `L₁` hard 0/1 and you recover R1. Read the posterior as a score and you recover R2. **Nothing built in the
first two worktrees is thrown away** — which is exactly why R3 goes last.

**Strategies to explore:** popularity as prior (3) · exact-match and dense as competing likelihood models (1, 2) ·
expected information gain (19) · BED-LLM for question proposal (20) · EVOI/bandits (21) · Platt calibration of
the likelihood (30) · long-term profile as a prior update (Pillar III, natively).

**Status:** not built, and **cannot start until R1 and R2 produce components to fuse.** Highest ceiling.
**Pillars:** all four fall out of one mechanism — the cleanest Innovation story available to us.
**Wins if:** MRR approaches 1.0 *and* MTTC drops, because entropy converts at exactly the right moment.
**Dies if:** the likelihood model is mis-specified and the posterior confidently backs the wrong item.
⚠️ Cost check first: a 50,000-element vector update per turn is trivial; the EIG expectation over candidate
answers is the part to keep cheap.

---

### Scoring the race
All three implement the same `Agent` and run the same harness. Compare on **clean score, paraphrase-stressed
score, and the four scenario breakdowns** — a winner on clean alone has not won. Expect them to fail differently:
R1 on Browsing, R2 on precision, R3 on calibration. **That divergence is the useful output**, whichever wins.

---

## 0.4 What is shared, and what is not

⚠️ **Do not impose a common internal pipeline.** R3 has no retrieval stage; forcing `recall/rerank/decide` on it
would flatten the very difference you are trying to measure. Freeze only these:

```python
# src/common/contracts.py — Track 0 freezes this; the three ideas share nothing else
from dataclasses import dataclass

@dataclass
class SessionState:
    turn: int
    category: str | None                  # coarse category, once known
    slots: dict[str, list[str]]           # attribute -> confirmed values
    slot_age: dict[str, int]              # turns since confirmed  (slot decay, §4.3)
    disclosed: set[str]                   # raw constraint strings already revealed
    history: list[str]                    # customer utterances, in order
    profile: dict                         # anonymized user_profile
    long_term: dict                       # distilled cross-session preferences (Pillar III)

# Also shared (expensive, identical for everyone):
#   CatalogIndex  — products, coarse-category map, popularity table, spec-phrase table
#   parse(msg, state) -> SessionState     — utterance → slots, so all three see the same input
#   the eval harness + run registry
#
# NOT shared: how each idea stores candidates, scores them, or decides to convert.
```

Each worktree owns `src/r1/`, `src/r2/`, `src/r3/` and touches nothing else.

## 0.5 Worktree setup

```bash
# after Track 0 lands on main
git worktree add ../r1-constraint  idea/r1-constraint
git worktree add ../r2-rank        idea/r2-rank
git worktree add ../r3-bayesian    idea/r3-bayesian
```

Each runs the identical harness and appends to `runs/registry.jsonl` on `main`.

**If you only have capacity for one at a time:** R1 first — it is already at 0.9607 and gives the race an
incumbent. Then R2, then R3. The order matters more than the parallelism: **R3 cannot start until both exist.**

---

# Part I — The component menu

Ideas each variant can draw on. Effort · gain · risk.

## §A Recall — cast the net

| Idea | What | Effort | Gain | Risk |
|---|---|---|---|---|
| **Spec-phrase exact index** | Hash catalog `features`/`details` strings; match stated requirements verbatim. | ⚪ done | very high | ⚠️ paraphrase |
| **`bge-m3` dense** | 1024-d, free, ~$0.10 for the catalog. Essential *in blend*. | 🟢 low | high | none |
| **Popularity prior** | log `rating_number`. Paraphrase-proof. | ⚪ done | high | none |
| **BM25 / FTS5** | Free, already in the starter. Third opinion for fusion. | ⚪ done | med | none |
| **HyDE** | LLM writes the product the customer describes; embed that. Targets our 0.185 worst case. | 🟢 low | high | latency |
| **PRF / Rocchio / RM3** | Push the query vector toward the top-k retrieved, re-query. 1971, ~10 lines, still a cornerstone. | 🟢 low | med | none |
| **BGE-M3 sparse + ColBERT** | Same model emits learned-sparse and token-level vectors. Needs local `FlagEmbedding`. | 🟡 med | med-high | RAM |
| **Doc2Query expansion** | Predict the queries a product answers; add to its indexed text. Merges with §D distillation. | 🟡 med | med | LLM time |
| **Generative retrieval / semantic IDs (TIGER)** | RQ-VAE hierarchical item codes, generated. Deployed at Tmall. | 🔴 high | low here | high |

## §B Ranking — order what you caught

| Idea | What | Effort | Gain | Risk |
|---|---|---|---|---|
| **Scheduled linear blend** | `dense + w·log(pop)`, `w = f(slots, scenario)`. Beat RRF. | 🟢 low | very high | tuning |
| **RRF** | `Σ 1/(k+rank)`. Keep as the parameter-free baseline. | 🟢 low | med | none |
| **LightGBM / LambdaMART** | ~20 features incl. route ranks, match counts, log-popularity, and the EAR/SCPR state vector (candidate count, turn, entropy, attribute scores). Seconds to train, microseconds to infer, interpretable. | 🟢 low | high | ⚠️ §E scope |
| **MMR / DPP diversity** | Greedy `λ·relevance − (1−λ)·max-sim-to-picked`. Fills the brief's *"diverse dense retrieval"* requirement. | 🟢 low | med (browsing) | costs MRR if ungated |
| **LLM listwise rerank** | `qwen3.6:35b`, top-20 permutation. | 🟢 low | insurance | latency, network |
| **E2Rank** | Embedding model continued-trained on a listwise objective — reranker quality at cosine cost. | 🟡 med | med | new dep |
| **Cross-encoder** | Joint `(query, product)` scoring. Highest ceiling. Train on §D synthetic data. | 🟡 med | high | training time |

⚠️ **Diversity needs a gate, not faith.** We are scored on one hidden target in a top-10 list, so diversity only
pays when it raises the chance the target is in the list at all — a hedge under high uncertainty. Under low
uncertainty it strictly costs MRR. **Proposal: apply MMR only on Browsing turns with high entropy, never after
the candidate set is peaked.** Clean experiment, useful result either way.

## §C Policy — ask or convert?

| Idea | What | Effort | Gain | Risk |
|---|---|---|---|---|
| **Confidence gate + deadline** | Convert when the leader strictly beats the runner-up; hard deadline turn 3. | ⚪ done | proven | magic numbers |
| **NQC / query-performance prediction** | Std-dev of top-k retrieval scores as a confidence signal. One `numpy.std`, no training. **Replaces the magic deadline with standard IR practice.** | 🟢 low | med | calibration |
| **Information-gain question selection** | Pick the question that maximally reduces candidate-set entropy. FacT-CRS's criterion; exact over our candidate set. | 🟡 med | med | none |
| **BED-LLM** | LLM proposes candidate questions, Bayesian machinery scores them. | 🟡 med | med | latency |
| **Bandits / EVOI** | Ask-vs-convert as explore/exploit with regret bounds. Mostly a framing win. | 🟡 med | low | overkill |
| **Deep RL (EAR / SCPR / UNICORN)** | The dominant CRS literature — and beaten by a decision tree. **Cite as beaten, don't build.** | 🔴 high | low | ⛔ |
| **MCTS (SAPIENT)** | Plan several turns ahead. Real 2024 method, but our horizon is ~3 turns. | 🔴 high | low | ⛔ |

🔑 **The strongest research framing available to us:** rebuild the confidence gate *as* expected information gain,
so "deadline at turn 3" becomes *"the expected value of another question fell below the cost of a turn."* Same
behaviour, principled derivation, far better write-up. FacT-CRS uses exactly these two stopping rules.

## §D Knowledge — the "LLM wiki"

COSMO (Amazon, SIGMOD 2024) is the production blueprint and powers Rufus: an LLM hypothesises commonsense
relations, critic classifiers filter them, a distilled LM serves at scale.

**Our version — one offline pass, three artefacts:**
1. **Normalised attributes** → makes slot-filling work *and* makes spec-phrase matching paraphrase-tolerant.
2. **Use-case tags** → the brief's *cross-category scenario matching*; makes vague Browsing queries retrievable.
3. **Doc2Query expansions** → permanent fix for vocabulary mismatch.

**🔑 Free supervision at scale.** The simulator is a deterministic function of the catalog, so we can generate a
correctly-labelled session for **any of the 50,000 products**, offline, for free — turning a 200-example problem
into a 50,000-example one. Then **paraphrase those sessions with `qwen3.6:35b` and train on the paraphrased
versions**, which makes the paraphrase risk the training objective rather than the threat.

⚠️ Use a strong model for the paraphrasing — stilted rewrites teach nothing transferable. Sample several *styles*
per session (terse, chatty, reordered, synonym-substituted); 5k sessions × 5 styles generalises further than 25k
bland rewrites. Pilot on 5k before the full run, and hand-check 100 outputs before committing to 50k.

## §E Machine learning — where it earns its place

1. **Scheduled blend weight** — learn `w(slots, scenario)` from the synthetic set instead of hand-tuning two points.
2. **LightGBM reranker** — highest ROI on this list; targets the MRR headroom directly.
3. **Calibration** — Platt-scale the ranker score into a probability so convert-vs-ask is real expected utility.
4. **Cross-encoder** on paraphrase-augmented sessions — higher ceiling, hardens the weak spot.
5. **Slot-extraction distillation** — teacher `qwen3.6:35b` (one-off, so use the best), student a tiny local model.

⚠️ **Scope call.** Out of scope is *"training or full-parameter fine-tuning of base foundational LLMs"*. A
gradient-boosted ranker, a small cross-encoder, or a distilled classifier is **not a foundational LLM** and is
standard IR practice. I read this as permitted — but **state plainly in the README what was trained and why we
believe it is in scope.** LightGBM alone is unambiguous and captures most of the gain. Ask at the webinar if unsure.

## §F Harness — how the pieces sit together

The production pattern has a name: **cascade ranking** — `recall → pre-rank → rank → re-rank`. Our five routes are
recall; the blend is pre-rank; LightGBM is rank; MMR/LLM is re-rank. Use this vocabulary in the write-up.

⚠️ **Do not build a multi-agent swarm.** The 2026 production consensus: *"failure in multi-agent systems is
structural, not a prompting bug"*, and free-form agent teams survived only in bounded, instrumented niches. What
survives is staged pipelines with explicit routing — which is what Rufus itself does.

**Four bounded roles, not agents:**
```
Router  → buying vs browsing; which routes fire; the blend weight w
State   → slots; accumulate / override-erase; entropy; NQC; question choice
Cascade → 5 recall routes → blend → LightGBM → MMR / LLM re-rank
Judge   → convert or ask
```
**Adaptive orchestration, concretely** (Pillar III): if NQC has not improved across two turns, the Router changes
strategy — widen the category, drop the least-supported slot, raise `w` back toward the prior, or flip from the
filter track to the dense track.

## §G Robustness

| Idea | Why |
|---|---|
| **Paraphrase stress harness** | Wrap the *agent*, not the evaluator. Two levels: scaffold-only, and scaffold+synonyms. Use `qwen3.6:35b` for realistic rewrites. |
| **Ablation switches** | Every route behind a flag. `no_spec_phrase` is our standing honesty metric. |
| **Offline fallback** | Local weights, exercised by a test from day one — not retrofitted the night before. |
| **Deterministic caching** | Content-hash keys on embeddings, distillations, rerank results. |
| **Latency + token accounting** | Required disclosure. Instrument on day one. |

---

# Part II — Open questions

1. **Does the LLM reranker add anything on top of the blend?** Its +0.19 MRR was measured on *popularity-ordered*
   candidates, before the dense blend existed. The blend independently lifts the same floor to 0.826. **The two
   gains may overlap — do not add them.** Cheap, high-value experiment; run it before R2 invests in LLM reranking.
2. **Which offline encoder?** `bge-m3` local vs `Qwen3-Embedding-0.6B` (current MTEB leader) vs BLaIR (pretrained
   on this exact dataset). One afternoon on the §12.2 harness. The local path may beat the API path.
3. **How far do we lean on inversion?** Recommendation: keep it as one route behind the blend, and report the
   score with it *disabled* as a standing robustness number.
4. **Is the private set paraphrased?** The one answer that would reshape everything. Ask at the webinar.
5. **Team split.** Natural seams: (a) retrieval + fusion, (b) dialog state + policy, (c) eval harness + stress
   testing, (d) write-up + demo video.

---

# Part III — Suggested build order

**Phase 0 — shared (blocks everything, ~half a day)**

| # | Task | Why |
|---|---|---|
| 1 | `src/common/`: catalog index, `SessionState`, `parse()` | All three ideas must see identical input |
| 2 | `src/eval/compare.py`: registry, ablations, **paraphrase stress**, bootstrap CI | Without it the race has no referee |
| 3 | Port `agent_best_0.9607.py` as R1's seed | Gives the race an incumbent to beat on day one |
| 4 | Full 50k `bge-m3` embeddings, cached | R2 needs them; R3 wants them as a likelihood term |

⚠️ **Build the paraphrase harness in Phase 0, not later.** It is the referee: a winner on the clean set alone
tells you nothing about the private set.

**Phase 1 — the race (parallel worktrees)**

| Worktree | When | First move | Then |
|---|---|---|---|
| 🔵 R1 | parallel | Normalised attributes so matching survives rewording | Info-gain question selection over the surviving set |
| 🟢 R2 | parallel | Scheduled dense+popularity blend (the 0.826 floor) | HyDE for cold Browsing, then LightGBM, then LLM rerank |
| 🟣 R3 | **after both** | Wrap R1's matcher and R2's scorer as likelihood terms | EIG question selection, then entropy-based conversion |

**Phase 2 — converge**

| # | Task |
|---|---|
| 1 | Score all three: clean, stressed, four scenario breakdowns, bootstrap CI |
| 2 | Fold the losers' best components into the winner |
| 3 | Cover any pillar the winner leaves thin — see [IMPORTANT.md](IMPORTANT.md) §14 |
| 4 | **Local-weights offline path** ⚠️ never let this slide to the end |
| 5 | Write-up with the ablation table, demo video, Devpost |

# Part IV — How to run and compare

## Setup
```bash
cp assets/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl
set -a && . ./.env && set +a          # SOCLAAS_API_KEY / SOCLAAS_BASE_URL
```

## Score one agent
```bash
cp <your-agent>.py techjam-conversational-search-main/starter/agent.py
cd techjam-conversational-search-main && python3 -m evaluator.local_evaluator --output runs/<name>.json
# flags: --catalog PATH  --dataset PATH  --output PATH   (that is all of them)
```
~4–17 s for all 200 sessions. ⚠️ **Restore the pristine starter afterwards** — the kit must stay byte-identical to
upstream or a reported score is not verifiable.

## The run registry (`src/eval/compare.py`)
```json
{"variant":"B-hybrid","git_sha":"abc1234","timestamp":"...",
 "hit_rate_at_10":0.0,"mrr":0.0,"mttc":0.0,"efficiency":0.0,"technical_score":0.0,
 "scenario":{"buying":{},"browsing":{},"intent_override":{},"boundary":{}},
 "paraphrase":{"clean":0.0,"scaffold":0.0,"full":0.0},
 "ablations":{"no_spec_phrase":0.0,"no_dense":0.0,"no_llm":0.0,"no_popularity":0.0,"no_mmr":0.0},
 "models":{"rerank":"qwen3.6:35b","extract":"qwen3.6:35b","embed":"bge-m3"},
 "llm_call_failures":0,
 "cost":{"prompt_tokens":0,"completion_tokens":0,"usd":0.0},
 "latency":{"p50_ms":0,"p95_ms":0,"total_s":0}}
```

**A run counts only if:**
1. Evaluator and `public_set.jsonl` SHA-256 verified against upstream.
2. All four scenario breakdowns reported — boundary is 10 sessions and is noise alone.
3. **Paraphrase-stressed score reported beside the clean score.** Winning clean and losing stressed is not winning.
4. **`no_spec_phrase` ablation reported** — that is the private-set insurance estimate.
5. `llm_call_failures` reported — a silent model failure looks exactly like a model that isn't helping.
6. Pinned to a git SHA. No SHA, no row.

**Permanent reference rows:** starter `0.1067` · popularity `0.7133` · public trick `0.7504` ·
**blended floor `0.826`** · prototype `0.9607` · max `0.9922`.
⚠️ **Judge new ideas against 0.826.**

**Before declaring a winner:** bootstrap-resample the 200 sessions 1,000× and report a confidence interval.
A 0.02 gap is one or two sessions changing rank.

## Pre-submission checklist
- [ ] Kit re-diffed against upstream `main` (the organizer edits the spec mid-competition)
- [ ] `Agent.__init__(self, catalog_path=...)` positional and defaulted
- [ ] No import from `evaluator.local_evaluator` (circular import → hard crash)
- [ ] Runs with the network disabled; local weights cached; fallback documented
- [ ] `usage` reports real token counts; latency and estimated USD disclosed
- [ ] No secrets committed — [.env](.env) stays git-ignored
- [ ] README: overview, setup, **exact reproduction steps**, limitations, contributions
- [ ] **Ablation table in the write-up** — the credibility exhibit
- [ ] Demo video: public YouTube, one full multi-turn session, linked from Devpost
- [ ] ⚠️ Demo video contains no third-party trademarks — Amazon product titles/brands are trademarked ([IMPORTANT.md](IMPORTANT.md) §14.7)
- [ ] All four pillars visibly built, including the ones we measured as low-value (LLM ranking stage, long-term profile) — §14
- [ ] Devpost: tools, APIs, libraries, datasets, model/cost/latency disclosure

---

# Part V — Reading list

### Load-bearing
- **Is Decision Tree All You Need? (FacT-CRS)** — a tree beats deep-RL CRS; info-gain splitting; the two stopping
  rules we rediscovered. [arXiv 2208.14614](https://arxiv.org/pdf/2208.14614)
- **Are We Really Making Much Progress?** — 11 of 12 neural recommenders beaten by simple methods.
  [arXiv 1907.06902](https://arxiv.org/abs/1907.06902v3)
- **COSMO** — Amazon's production commonsense KG, SIGMOD 2024. §D blueprint.
  [paper](https://assets.amazon.science/8f/0a/0bfafe8843bf98a007a5328f2ae2/cosmo-a-large-scale-e-commerce-common-sense-knowledge-generation-and-serving-system-at-amazon.pdf)
- **The technology behind Rufus** — production reference for our exact problem.
  [Amazon Science](https://www.amazon.science/blog/the-technology-behind-amazons-genai-powered-shopping-assistant-rufus)
- **Cascade Ranking for Operational E-commerce Search** — [arXiv 1706.02093](https://arxiv.org/pdf/1706.02093)
- **HyDE** — [Haystack docs](https://docs.haystack.deepset.ai/docs/hypothetical-document-embeddings-hyde)
- **BGE-M3** — [HF](https://huggingface.co/BAAI/bge-m3) · [docs](https://bge-model.com/bge/bge_m3.html)

### Policy / questions
- **UNICORN** — unified ask/recommend policy via graph RL. [ResearchGate](https://www.researchgate.net/publication/353186016_Unified_Conversational_Recommendation_Policy_Learning_via_Graph-based_Reinforcement_Learning)
- **SAPIENT** — MCTS for multi-turn CRS. [arXiv 2410.09580](https://arxiv.org/pdf/2410.09580)
- **BED-LLM** — Bayesian experimental design with LLMs. [arXiv 2508.21184](https://arxiv.org/pdf/2508.21184)
- **EVOI meets Bandit Learning** — [OpenReview](https://openreview.net/forum?id=xT9Jy2d6Sd)
- **QPP / coherence-based predictors (NQC)** — [arXiv 2310.11405](https://arxiv.org/pdf/2310.11405)
- **CRSPapers** — curated CRS list. [GitHub](https://github.com/Zilize/CRSPapers)

### Ranking & diversity
- **RankZephyr** — [arXiv 2312.02724](https://arxiv.org/pdf/2312.02724)
- **How Good are LLM-based Rerankers?** EMNLP 2025, 22 methods — [ACL](https://aclanthology.org/2025.findings-emnlp.305.pdf)
- **E2Rank** — embedding as listwise reranker. [arXiv 2510.22733](https://arxiv.org/pdf/2510.22733) · [GitHub](https://github.com/Alibaba-NLP/E2Rank)
- **Result Diversification survey** — [arXiv 2212.14464](https://arxiv.org/pdf/2212.14464)
- **SMMR** SIGIR 2025 — [ACM](https://dl.acm.org/doi/10.1145/3726302.3730250)
- **Qwen3 Embedding** — MTEB leader. [arXiv 2506.05176](https://arxiv.org/pdf/2506.05176)

### Conversational search
- **A Survey on Conversational Recommender Systems** — [ACM CSUR](https://dl.acm.org/doi/10.1145/3453154)
- **AdaCQR** — [arXiv 2407.01965](https://arxiv.org/pdf/2407.01965)
- **ConvSDG** — synthetic session generation; validates §D. [arXiv 2403.11335](https://arxiv.org/pdf/2403.11335)
- **PRF for dense retrieval** — [arXiv 2106.11251](https://arxiv.org/pdf/2106.11251)
- **Learning Contextual Retrieval for Robust Conversational Search** — [EMNLP 2025](https://aclanthology.org/2025.emnlp-main.602.pdf)

### Data & stretch goals
- **Amazon ESCI** — 130k queries, 2.6M judgements. [GitHub](https://github.com/amazon-science/esci-data)
- **Amazon-C4** — 21k complex-context queries. [HF](https://huggingface.co/datasets/McAuley-Lab/Amazon-C4)
- **TIGER** — [NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/file/20dcab0f14046a5c6b02b61da9f13229-Paper-Conference.pdf)
- **BLaIR** — pretrained on our exact dataset. [arXiv 2403.03952](https://arxiv.org/abs/2403.03952)

### Multi-agent reality check
- **Multi-Agent in Production 2026: What Actually Survived** — [Medium](https://medium.com/@Micheal-Lanham/multi-agent-in-production-in-2026-what-actually-survived-f86de8bb1cd1)
- **Uno-Orchestra** — parsimonious agent routing. [arXiv 2605.05007](https://arxiv.org/pdf/2605.05007)

---

# Part VI — Recommendation

**Race R1 against R2 in parallel. Then build R3 from whatever both produced.**

R1 is the incumbent at 0.9607 and already works; R2 owns the measured 0.826 paraphrase-proof floor and the
brief's named pipeline. They fail in opposite directions — R1 on Browsing, R2 on precision — so the race tells
you which failure is cheaper. R3 then fuses them into one posterior, which is both the cleanest Innovation story
and the most direct route to the remaining MRR headroom (+0.075, where all the remaining points are).

Whatever wins, publish the ablation table including `no_spec_phrase` = 0.826. Being the team that found the
generator was invertible, **measured exactly what it was worth, and built something that stands up without it**
is a far better story than the highest number.

⚠️ **Report the losers too.** Three architectures measured on the same harness, with their different failure
modes named (R1 on Browsing, R2 on precision, R3 on calibration), is a stronger Technical Execution and Problem
Insight exhibit than one tuned number with no alternatives explored.
