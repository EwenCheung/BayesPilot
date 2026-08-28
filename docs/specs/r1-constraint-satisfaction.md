# Spec — 🔵 R1 Constraint Satisfaction (the agent is a filter)

> **This file is the source of truth for R1's behaviour.**
> Behaviour change → update this spec → write the test → write the code. In that order.
> Facts and measurements come from [IMPORTANT.md](../../IMPORTANT.md); this file never restates them, it cites them.
> Road definition: [IDEA.md](../../IDEA.md) §0.3.

Status: implemented and measured — [docs/R1-RESULTS.md](../R1-RESULTS.md). Last revised 2026-08-29.

---

## 1. The bet

This is a database query wearing a conversational costume. The customer states hard facts; each one
eliminates products. Ranking exists only to break ties among survivors.

**Core structure: a shrinking candidate set `S`.** Not a scored list (that is R2), not a distribution (that is R3).

```
S ← products in the stated coarse category
each turn:
    slots ← parse(utterance)                 # accumulate · override erases · stale slots decay
    for each live slot:
        S' ← S ∩ matches(slot)
        S  ← S' if S' else S                 # relax, never empty
    ranked ← tie_break(S)                    # match count → log-popularity → dense → LLM listwise
    if converged(S) or turn ≥ deadline:  convert with dynamic top-k
    else:                                ask argmax_a  H(S) − E[H(S | a)]
```

**Wins if** its paraphrase-stressed score clears 0.826. **Dies if** it does not, or if Browsing leaves `S` huge.

---

## 2. Hard contracts (violating any of these forfeits runs, not points)

| # | Contract | Source |
|---|---|---|
| C1 | `Agent.__init__(self, catalog_path: str \| Path = "data/catalog.jsonl")` — positional, defaulted | IMPORTANT §2 |
| C2 | The agent tree **never imports** `evaluator.local_evaluator` — circular import, hard crash. Simulator functions are **copied** | IMPORTANT §13.1.1 |
| C3 | `respond` returns `{message: str, ask_attribute: str\|None, recommendations: list, usage: {...}}`, always, wrapped in try/except | IMPORTANT §2 |
| C4 | Never an empty `recommendations` list once conversion is legal; never `ask_attribute: null` while constraints remain undisclosed | IMPORTANT §2 |
| C5 | One `Agent` instance serves all sessions. `reset()` wipes per-session state, keeps the index and the long-term store | IMPORTANT §2 |
| C6 | The kit stays byte-identical to upstream. Every scored run verifies SHA-256 before and after | IMPORTANT §13.1.6 |
| C7 | Every LLM call site asserts on a parsed non-empty result and increments a failure counter on miss | IMPORTANT §13.1.3 |
| C8 | Every LLM/network path has an offline fallback, exercised by a test | PROBLEM §4.3, submission rules |
| C9 | Model IDs are pinned explicitly, never aliases (`default`, `test`, `ornith1.0:35b` are aliases) | IMPORTANT §13.1.4 |

---

## 3. Modules and their behaviour contracts

### 3.1 `src/common/simulator.py` — the mirror
A byte-faithful **copy** of the evaluator's `searchable_text`, `_flatten_values`, `_clean_constraint`,
`intent_card`, `coarse_category`, `classify_constraint`.

- **Contract:** for every product in the catalog, our functions return exactly what the evaluator's return.
- **Verified by:** golden test over ≥2,000 catalog rows, comparing against the evaluator module imported
  *by the test* (tests may import it; the agent may not — C2).
- **Why it exists:** this is the referee's own logic. Drift here silently invalidates everything downstream.

### 3.2 `src/common/catalog.py` — `CatalogIndex`
Built once at `Agent.__init__`, ~9 s for 50,000 rows, amortised to zero across 200 sessions (C5).

| Structure | Contents |
|---|---|
| `products` | `parent_asin → row` |
| `by_category` | coarse category → `[parent_asin]` (1,115 distinct categories) |
| `popularity` | `parent_asin → log1p(rating_number)` |
| `card_strings` | `parent_asin → frozenset` of its `intent_card` constraint strings |
| `phrase_index` | exact constraint string → `frozenset[parent_asin]` |
| `attr_index` | `(attribute, normalised value) → frozenset[parent_asin]` |
| `token_index` | content token → `frozenset[parent_asin]`, stopworded, df-capped |

- **Contract:** read-only after construction. No mutation, no synthetic ASINs (PROBLEM §4.3).
- **Fallback:** an unknown category yields the global popularity-ordered pool rather than an empty set.

### 3.3 `src/common/attributes.py` — normalised ontology
Turns a filthy constraint string into `(attribute, value)` pairs: `"Material: alloy"` → `("material","alloy")`,
`"100% Polyester"` → `("material","polyester")`, `"Sleeve type: Long Sleeve"` → `("style","long sleeve")`.

- **Contract:** deterministic, offline, order-independent. Unknown strings yield `("feature", <normalised text>)`,
  never an exception.
- **Why:** it is what makes matching survive rewording — the exact phrase index cannot.

### 3.4 `src/common/parse.py` — `parse(message, state) → SessionState`
Three tiers, tried in order, results merged (later tiers only add):

1. **Template tier** — the simulator's four literal templates (initial buying / browsing / override, `customer_reply`).
   Exact, free, and the only tier that recovers the verbatim constraint string.
2. **Ontology tier** — attribute/value extraction from arbitrary prose via `attributes.py`.
3. **LLM tier** — escalation whenever **no template matched**, which is exactly the paraphrase case.
   On clean text the templates always match, so this tier costs **zero calls** there (measured).
   The model's own attribute label is *not* trusted: its extracted phrase is fed back through the
   same normalisation cascade, so the catalog's vocabulary decides.

- **Contract:** never raises; returns the state unchanged if nothing parses. Tier used is recorded on the state
  for the ablation table.
- **Override handling:** the override sentence erases the slot it names and marks the new constraint disclosed
  (slot erasure, Pillar II).
- **Slot decay (§14.2):** every slot carries `slot_age`; weight `0.9 ** age` in ranking. An overridden slot
  decays to zero instantly.

### 3.5 `src/common/llm.py` — one client
Chat + embeddings against `SOCLAAS_BASE_URL`. Pinned models: chat `qwen3.6:35b`, embeddings `bge-m3` (C9).

- Content-hash disk cache (`.cache/llm/`), so a repeat run costs nothing and is reproducible.
- `failures` counter; `offline` mode via `R1_OFFLINE=1` or any network error → returns `None`, caller falls back.
- Token and latency accounting exposed for the required disclosure.

### 3.6 `src/r1/filter.py` — the candidate set
- `S` starts as the category pool; unknown category → global pool.
- Each live slot intersects `S` through the matcher cascade below. **An intersection that empties `S` is
  discarded** (relaxation) and the slot is recorded as unmatched.

| Matcher | Precision | Survives paraphrase |
|---|---|---|
| exact spec-phrase (`phrase_index`) | perfect | no |
| normalised attribute (`attr_index`) | high | mostly |
| token overlap (`token_index`) | low | yes |

- **Contract:** `S` is never empty. Matcher used per slot is recorded, so `no_spec_phrase` can be ablated.
- ⚠️ **Only exact matches may shrink `S`** (`shrink_min = 1.0`). Letting attribute-level matches filter
  measured **hit@10 0.89 → 0.79 under stress**, below the popularity-only baseline: the agent was
  deleting the target on the strength of a guess. Weak matchers contribute score, never removal.
- **Category recovery:** when the opener is reworded the template misses, so the pool is resolved by
  `CatalogIndex.best_category` — longest verbatim category name, else `hits² / |category tokens|`.
  Scoring by coverage alone lost 21 sessions under stress ("Shirts T-Shirts" outscoring "Shirts Tanks Tops").

### 3.7 `src/r1/question.py` — what to ask
Expected information gain over `S`: for each allowed attribute, partition `S` by the answer the simulator
*would* give and score `H(S) − E[H(S|a)]`.

- **Contract:** never asks an attribute that already returned "no additional preference" this session
  (Pillar III self-refinement, §14.5).
- Expected result: `"other"` wins on the clean set — derived, not hardcoded (IMPORTANT §4).

### 3.8 `src/r1/rank.py` — tie-break cascade
`weighted match count → dense cosine (flag) → log-popularity → LLM listwise rerank (flag)`.
Dense vectors come from `src/eval/embed.py` (all 50,000 products, `bge-m3`, float16, 102 MB in RAM).
The LLM rerank fires **only when the deterministic path has no strict unique leader** — a call skipped
is a call that cannot time out during official scoring.
Popularity is the paraphrase insurance (IMPORTANT §5) and is never ablated by default.

### 3.9 `src/r1/policy.py` — convert or ask
- **Convergence:** strict unique leader (top score > runner-up), or `|S| == 1`, or NQC (std-dev of the top-k
  score vector) above threshold.
- **Deadline:** convert unconditionally at `turn ≥ 3` (IMPORTANT §12.1 measured this beats turn-4 and no-deadline).
- **Override sessions:** recommendations on turns 1–2 are discarded by the evaluator, so R1 stays silent and
  spends them extracting (IMPORTANT §4).
- **Dynamic truncation (§14.3):** `k = 1` on a strict unique leader, `k = 10` otherwise.

### 3.10 `src/eval/` — the referee
- `run.py` — SHA-256 the kit → swap our agent into `starter/agent.py` → run the official evaluator → restore →
  re-verify SHA. A run whose SHA check fails is not recorded.
- `stress.py` — paraphrase wrapper around **the agent, not the evaluator**. Four levels:
  `L0` clean · `L1` scaffold reworded, constraint payloads verbatim (tests the parser) ·
  `L2` scaffold + payloads reworded, `key: value` flipped and synonym-swapped (tests the matcher) ·
  `L3` model-written rewrite, cached, falling back to `L2` when the endpoint is unreachable.
- `ablate.py` — `no_spec_phrase` (the honesty metric), `no_llm`, `no_dense`, `no_popularity`, `no_infogain`.
- `compare.py` — registry rows to `runs/registry.jsonl`, bootstrap 95% CI (1,000 resamples, seeded),
  scenario breakdown.

---

## 4. Acceptance criteria

R1 is done when all of these hold, measured on the 200 public sessions with the pristine kit:

| # | Criterion | Threshold |
|---|---|---|
| A1 | Clean TechnicalScore | ≥ 0.9607 (must not regress the incumbent) |
| A2 | **Paraphrase-stressed (L2) TechnicalScore** | ≥ 0.826 — the road's own kill criterion |
| A2b | **Model-written paraphrase (L3) TechnicalScore** | ≥ 0.826 — ❌ **measured 0.7246**; see [R1-RESULTS.md](../R1-RESULTS.md) |
| A3 | `no_spec_phrase` ablation reported | any value; it is the private-set insurance estimate |
| A4 | All four scenario breakdowns reported | buying / browsing / intent_override / boundary |
| A5 | Bootstrap 95% CI reported | 1,000 seeded resamples |
| A6 | `llm_call_failures` reported | a silent failure must be distinguishable from a useless model |
| A7 | Offline path (`R1_OFFLINE=1`) scores within noise of the deterministic run | no crash, no empty turns |
| A10 | Reported runs are bit-reproducible | `PYTHONHASHSEED=0`; card strings are ordered, not sets |
| A8 | Kit SHA-256 unchanged after every scored run | byte-identical to upstream |
| A9 | Latency p50/p95, token usage, estimated USD disclosed | required by the submission rules |

## 5. Explicitly out of scope for R1

Dense retrieval as a *primary* route (that is R2), posterior/entropy conversion (that is R3), any catalog
mutation, any evaluator modification, UI, and fine-tuning of foundation models (PROBLEM §4.3).
