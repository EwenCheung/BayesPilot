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

# Part 0 — Idea index and track assignment

**40 ideas** live in this file. Here they are in one list, then compiled into **5 parallel tracks + 1 foundation**
you can hand to separate worktrees.

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

## 0.2 ⚠️ Two ways to split the work — pick the right one

**Component split** (retrieval / policy / ranking / knowledge): everyone builds part of *one* system. Parallel,
but **there is no winner to pick** — you need all of them, and you merge everything.

**Competing-agent split** (below): every worktree builds a **complete, independently scoreable agent** that makes
a *different bet* about what wins. Parallel, **fully independent, and you pick the best score.**

You asked for the second. That is what §0.3 now describes. The A/B/C variants in Part I are *not* it either —
🅱️ = 🅰️ + more and 🅲 = 🅱️ + more, so they are sequential and two people would sit waiting.

**How duplication is avoided:** Track 0 ships a *complete working agent* at 0.9607. **Every track forks that and
changes one dimension.** Nobody rebuilds the plumbing; each track starts from a system that already scores and
pushes it in its own direction.

---

## 0.3 The tracks — four independent bets, one shared foundation

### Track 0 — Foundation ⛔ blocks all four, land it first (~half a day, then dissolve)
> **Mission:** ship one complete working agent plus the harness that scores it, so every fork starts from a
> known-good 0.9607 and every result is comparable.

- `src/` exporting the required `Agent` — `__init__(self, catalog_path=...)` positional and defaulted
- Port [experiments/agent_best_0.9607.py](experiments/agent_best_0.9607.py) into it
- `src/eval/compare.py` + the run registry (Part V) + ablation flags + the paraphrase stress wrapper
- **Freeze `src/contracts.py`** (§0.4) so the winning pieces can be merged later

**Done when:** `python3 -m evaluator.local_evaluator` reproduces **0.9607** from `src/`, plus one registry row
with a paraphrase-stressed score beside it.

---

### 🅰️ Track A — Symbolic Precision
> **The bet:** the catalog is structured data, so exact symbolic matching beats every learned method — and a
> zero-LLM agent wins on score, latency and feasibility at once.

**Build:** spec-phrase exact index · BM25 · popularity prior · LightGBM reranker · information-gain question
selection · NQC confidence gate · **slot decay** (§4.3) · **dynamic truncation** (§4.3) · **question-logic
self-refinement** (stop re-asking attribute types that returned nothing — Pillar III).
**Ideas:** 1, 3, 4, 11, 12, 17–19, 28–30
**Wins if:** it holds ≥0.95 clean *and* the paraphrase-stressed score stays respectable.
**Dies if:** stressed score falls below 0.826 — then it is strictly worse than B and becomes the offline fallback.
**Runtime deps:** none. No network, no models. ~4 s for 200 sessions.

### 🅱️ Track B — Dense Semantic
> **The bet:** meaning beats string matching. Embeddings plus query-side tricks survive any rewording the
> organizer throws at the private set.

**Build:** `bge-m3` blend with slot-scheduled weight · HyDE for cold Browsing turns · PRF/Rocchio for multi-turn
accumulation · MMR gated on entropy · optional sparse+ColBERT.
**Ideas:** 2, 5–7, 10, 13, 28
**Wins if:** it beats A *under paraphrase stress* — that is the whole point of this bet.
**Dies if:** it cannot clear the 0.905 blended hit@10 it starts from.
**Runtime deps:** embeddings (cacheable to disk → runs offline).

### 🅲 Track C — Knowledge Distillation
> **The bet:** the win is *offline*. Normalise the filthy catalog once and runtime retrieval becomes easy —
> Amazon's own COSMO/Rufus play.

**Build:** one LLM pass over 50k products → normalised attribute ontology + use-case tags + doc2query expansions.
Then structured filtering and cross-category scenario matching on top. Also owns the **synthetic session
generator** and paraphrase augmentation.
**Ideas:** 8, 24–27, 31, 32
**Wins if:** clean attributes lift Browsing sessions where A and B both struggle.
**Dies if:** the distilled layer adds nothing over raw text — measure before scaling past 5k products.
**Runtime deps:** none at runtime (artefacts are precomputed and cached).

### 🅳 Track D — LLM Reasoning
> **The bet:** the brief literally names *"Multi-Route Retrieval → LLM Semantic Ranking"* as the required
> pipeline. Lean into it: an LLM router, extractor and listwise judge.

**Build:** LLM intent router · LLM slot extraction with regex fallback · `qwen3.6:35b` listwise rerank of top-20
(**this is the brief's named "LLM Semantic Ranking" stage — see [IMPORTANT.md](IMPORTANT.md) §14.1**) ·
LLM-authored customer prose · **long-term profile distillation** (Pillar III — build it, then report honestly that
the supplied profile carries almost no signal) · adaptive re-orchestration on stalled confidence.
**Ideas:** 14–16, 20, 22*, 32–35 (*cite, don't build)
**Wins if:** it pushes MRR toward 1.0 *and* holds up under stress. Best demo video and Innovation narrative.
**Dies if:** latency exceeds the organizer's timeout, or it cannot run offline. ⚠️ ~37 min sequential API time
for 1,000 sessions.
**Runtime deps:** live endpoint — **must degrade gracefully to A.**

---

### After the race
These are **not** mutually exclusive at submission time. Score all four, then **merge the winners** — they share
`contracts.py`, so a winning retriever from B drops into A's policy without a rewrite. Expect the final submission
to be a merge, not a single track.

⚠️ **The one dependency:** Track D and Track C's ML ideas (31, 32) want Track C's synthetic sessions. Both can
start on the 200 public sessions and swap in the 50k later — so it is a *nice-to-have*, not a blocker.

---

## 0.4 The interface contract — freeze this before branching

Independent forks only merge cleanly if the seams were agreed up front. **Track 0 writes `src/contracts.py` and
no track edits another track's directory.**

```python
# src/contracts.py — frozen by Track 0 before any branch is cut
from dataclasses import dataclass

@dataclass
class SessionState:
    turn: int
    category: str | None                    # coarse category, once known
    slots: dict[str, list[str]]             # attribute -> confirmed values
    slot_age: dict[str, int]                # turns since each slot was confirmed  (slot decay)
    disclosed: set[str]                     # raw constraint strings already revealed
    history: list[str]                      # customer utterances, in order
    profile: dict                           # anonymized user_profile
    long_term: dict                         # cross-session distilled preferences

@dataclass
class Candidate:
    asin: str
    route_scores: dict[str, float]          # 'spec' | 'dense' | 'bm25' | 'pop' -> raw score

@dataclass
class Ask:     attribute: str | None        # one of the 10 allowed, or None
@dataclass
class Convert: pass

# recall(state, k)            -> list[Candidate]
# rerank(state, cands)        -> list[str]
# decide(state, ranked, conf) -> Ask | Convert
```

## 0.5 Worktree setup

```bash
# after Track 0 lands on main
git worktree add ../track-a  track/a-symbolic
git worktree add ../track-b  track/b-dense
git worktree add ../track-c  track/c-knowledge
git worktree add ../track-d  track/d-llm
```

Each worktree runs the identical harness and appends to a shared `runs/registry.jsonl` on `main`.
**Every row must carry a clean score, a paraphrase-stressed score, and the four scenario breakdowns** — otherwise
you cannot tell which bet actually won.

---

# Part I — Three explorations

Three coherent systems, each with a hypothesis that can be falsified, each ownable in its own worktree. They are
not variations on a theme — they disagree about what actually wins this competition.

```bash
git worktree add ../track4-A variant/a-deterministic
git worktree add ../track4-B variant/b-hybrid
git worktree add ../track4-C variant/c-agentic
```

---

## 🅰️ Deterministic Precision — no LLM at runtime

> **Hypothesis:** the simulator is invertible enough that a well-engineered zero-LLM system wins on score,
> latency and feasibility simultaneously, and the LLM is a liability rather than an asset.

**Build:** spec-phrase exact index + BM25 + popularity prior + LightGBM reranker + information-gain question
selection + NQC confidence gate.

**Starting point:** [experiments/agent_best_0.9607.py](experiments/agent_best_0.9607.py) already does a crude
version of this. Port it into a clean `src/`, then replace its two magic numbers with principled criteria (Part II §C).

**Why it might win:** it is the only variant guaranteed to run if the organizer disables the network. ~4 s for all
200 sessions. Trivially reproducible. Feasibility & Practicality is 15% of judging and this maxes it.

**Why it might lose:** paraphrase-fragile, and a thin Innovation story — it is essentially a very good lookup.

**Kill criterion:** if the paraphrase stress harness drops it below 0.826, it is strictly worse than 🅱️ and
becomes the fallback path rather than a candidate.

---

## 🅱️ Hybrid Semantic — dense retrieval + distilled knowledge

> **Hypothesis:** a blended dense route and an offline-distilled attribute layer buy paraphrase robustness
> *without* giving up deterministic precision — so we score like 🅰️ on the clean set and survive a rewritten
> private set.

**Build:** 🅰️ plus —
- **Scheduled dense+popularity blend.** `bge-m3` embeddings, weight `w` scheduled on confirmed-slot count.
  This is the measured 0.826 floor and it is the load-bearing component.
- **COSMO-style offline distillation** — one LLM pass over 50k products producing three artefacts at once:
  normalised attributes (kills `"Material:alloy"` vs `"100% Polyester"` vs `"Textile"`), use-case tags
  (`"good for winter hiking"`), and doc2query expansions.
- **HyDE on cold Browsing turns** — have the LLM write the product description the customer is describing, embed
  *that*. Aimed squarely at our worst measured number (category-only dense retrieval, hit@10 0.185).
- **LLM slot extraction** with regex fallback.
- **MMR diversity** gated on entropy (Part II §B).

**Why it might win:** it is a genuinely good search system, it fills the brief's four pillars honestly, and its
robustness is measured rather than asserted.

**Why it might lose:** most moving parts, so most ways to be subtly broken.

**Kill criterion:** if the distillation and HyDE together fail to beat the plain blend on Browsing sessions, cut
them and 🅱️ collapses back toward 🅰️ plus embeddings.

**→ My pick for the primary submission.**

---

## 🅲 Agentic Reasoning — full LLM cascade

> **Hypothesis:** an LLM Router and Judge push MRR toward 1.0 and produce conversation quality that wins the
> qualitative 65% of judging, which the score alone cannot.

**Build:** 🅱️ plus an LLM Router (buying/browsing classification, route weighting), `qwen3.6:35b` listwise
re-rank of the top 20, LLM-authored customer-facing prose, and adaptive re-orchestration when confidence stalls.

**Why it might win:** best demo video, strongest Innovation narrative, highest MRR ceiling.

**Why it might lose:** ⚠️ **wall-clock and network dependence.** One rerank per turn over 1,000 sessions × ~2.6
turns ≈ **~37 min of sequential API time**, and the evaluator loop cannot be parallelised. Every call bets the
endpoint is reachable during official scoring.

**Expectation to set now:** 193/200 sessions are already rank-1 in the clean condition, so **expect little
clean-set gain.** Build it for robustness and narrative. If it moves the clean score a lot, suspect the harness
before celebrating.

**Kill criterion:** if latency exceeds whatever timeout the organizer imposes, swap the LLM reranker for E2Rank
(listwise quality at embedding cost) or drop to 🅱️.

---

## The merged north star

One codebase, three profiles, config-selected:

```
🅱️ ships  ·  🅲's LLM Judge fires only when confidence is low  ·  🅰️ is the guaranteed offline path
```

Uncertainty-gating the LLM keeps both the wall-clock and — more importantly — the *dependence on a reachable
endpoint* rare. The story *"excellent with a model, still strong without one"* is worth more to judges than any
single number.

---

# Part II — The component menu

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

# Part III — Open questions

1. **Does the LLM reranker add anything on top of the blend?** Its +0.19 MRR was measured on *popularity-ordered*
   candidates, before the dense blend existed. The blend independently lifts the same floor to 0.826. **The two
   gains may overlap — do not add them.** Cheap, high-value experiment; run it before budgeting effort on 🅲.
2. **Which offline encoder?** `bge-m3` local vs `Qwen3-Embedding-0.6B` (current MTEB leader) vs BLaIR (pretrained
   on this exact dataset). One afternoon on the §12.2 harness. The local path may beat the API path.
3. **How far do we lean on inversion?** Recommendation: keep it as one route behind the blend, and report the
   score with it *disabled* as a standing robustness number.
4. **Is the private set paraphrased?** The one answer that would reshape everything. Ask at the webinar.
5. **Team split.** Natural seams: (a) retrieval + fusion, (b) dialog state + policy, (c) eval harness + stress
   testing, (d) write-up + demo video.

---

# Part IV — Suggested build order

| # | Task | Why |
|---|---|---|
| 1 | Harness: `compare.py`, ablation flags, run registry (Part V) | Nothing is measurable without it |
| 2 | Port `agent_best_0.9607.py` into a clean `src/` | Locks in the floor |
| 3 | Full 50k `bge-m3` embeddings + scheduled blend | Reproduces the 0.826 floor — this is the insurance |
| 4 | Synthetic session generator (§D) | Unblocks every ML idea |
| 5 | Paraphrase stress harness | Tells us how much of §D we actually need |
| 6 | LightGBM reranker | Biggest MRR win per hour |
| 7 | NQC gate + information-gain questions | The research contribution |
| 8 | COSMO-style distillation | Paraphrase insurance + Browsing |
| 9 | HyDE on cold Browsing turns | Targets our worst number (0.185) |
| 10 | MMR gated on entropy | Fills an explicit brief requirement |
| 11 | LLM listwise re-rank, uncertainty-gated | Insurance, not a headline |
| 12 | **Local-weights offline path** | ⚠️ Disqualification risk — must not slide to the end |
| 13 | Write-up, ablation table, demo video | 65% of the marks |

⚠️ **Item 12 is not optional and must not be last.** Every LLM stage needs a working no-network implementation
from day one, or you discover too late that the architecture assumed a reachable endpoint.

---

# Part V — How to run and compare

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

# Part VI — Reading list

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

# Part VII — Recommendation

**Ship 🅱️.** Cascade architecture: five recall routes → scheduled dense+popularity blend (the 0.826 floor, weight
scheduled on slot count) → LightGBM rank → entropy-gated MMR and uncertainty-gated LLM re-rank. Policy by
**information gain** for what to ask and **NQC** for when to convert, replacing both magic numbers with standard
practice. Knowledge from one COSMO-style offline pass producing normalised attributes, use-case tags and doc2query
expansions. 🅰️ stays the guaranteed offline fallback; 🅲's Judge is an uncertainty-gated escalation on top.

Publish the ablation table including `no_spec_phrase` = 0.826. Being the team that found the generator was
invertible, **measured exactly what it was worth, and built a system that stands up without it** is a far better
story than the highest number.
