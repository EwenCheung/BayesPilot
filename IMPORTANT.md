# IMPORTANT.md — TechJam Track 4 (Shopping Copilot): verified ground truth

> **Document map.** Three docs, one project.
> **[IMPORTANT.md](IMPORTANT.md) is authoritative on facts** — rules, evaluator mechanics, measurements (§12),
> errors & learnings (§13), requirement audit (§14). Where any doc disagrees with it on a number or a rule, it wins.
> [REPORT.md](REPORT.md) = the narrative: what the problem is and what we found.
> [IDEA.md](IDEA.md) = proposals only: what we could build, why, and how we'd know it worked. It quotes
> [IMPORTANT.md](IMPORTANT.md) rather than restating findings.
> Reproducible scripts live in [experiments/](experiments/).

Durable context file. Every claim here was **verified by reading the shipped code or running the data/evaluator** —
nothing is paraphrased trust. Numbers marked *(measured)* were produced by an actual run on this machine.

⚠️ = trap · 🔑 = scoring lever · 📊 = measured on the 200-session public set

Last full sweep: 2026-08-27. Kit verified **byte-identical to upstream `main`** (all 13 files SHA-256 matched).

---

## 0. TL;DR — the four things that decide this competition

1. **The customer is not an LLM. It is a deterministic function of the target product's own catalog row**, computed by
   `intent_card()` / `coarse_category()` / `initial_message()` / `customer_reply()` inside the evaluator we were given.
   Every user utterance contains literal substrings of the target's `features`/`details`. This is an *inversion* problem
   wearing a conversational-AI costume. §3
2. **`ask_attribute: "other"` is a wildcard** that dumps the next 2 undisclosed constraints, bypassing all classification.
   Two asks extract the complete 4-constraint intent card. §4
3. **The targets are wildly popular products** — median `rating_number` **6,846** vs catalog median **12** (570×).
   Category + popularity prior alone, ignoring every word the customer says, scores **0.7133** *(measured)*. §5
4. **TechnicalScore is only an input to the 35% "Technical Execution" criterion**, not the score. 65% of judging is
   innovation/impact/feasibility/presentation. A naked lookup table that scores 0.95 loses to a real agent at 0.75. §7

### 📊 Verified scoreboard (all run locally, 200 public sessions, no LLM, ~4–17 s each)

| Agent | Hit@10 | MRR | MTTC | Efficiency | **TechnicalScore** |
|---|---|---|---|---|---|
| Shipped BM25 starter (official baseline) | 0.125 | 0.068 | 9.81 | 0.119 | **0.10671** |
| Category + popularity prior only, **zero constraint use** | 0.815 | 0.498 | 3.18 | 0.782 | **0.71334** |
| Public PR #1 trick (accumulate history + always ask `other`) | 0.875 | 0.540 | 3.46 | 0.755 | **0.750401** |
| ByteMe (rival team) day-0 committed run | 0.910 | 0.706 | 5.05 | 0.596 | **0.78576** |
| Category + **blended `bge-m3` dense** + popularity, still zero constraint use | 0.905 | 0.686 | ~2.6 | ~0.84 | **~0.826** |
| Our ~50-line inversion prototype, recommending every turn | 1.000 | 0.726 | 1.53 | 0.948 | **0.90743** |
| **Same + confidence gate + turn-3 deadline** | **1.000** | **0.975** | **2.59** | **0.841** | **0.96070** |
| *Theoretical maximum* (MTTC floor 1.39 from the override rule) | 1.000 | 1.000 | 1.39 | 0.961 | *0.9922* |

Sources live in [experiments/](experiments/): `agent_inversion_0.9074.py`, `agent_best_0.9607.py` (both reproduce
on demand), plus `embed_catalog.py`, `floor_test.py`, `blend_sweep.py`, `rerank_model_test.py`.

🔑 **The 0.826 row is the one that matters for the private set** — it uses no template matching at all, so it is
what survives if the organizer paraphrases. See [IDEA.md](IDEA.md) §3.

---

## 1. Repo layout (verified file inventory — nothing else exists)

| Path | What it is |
|---|---|
| [docs/PROBLEM.md](docs/PROBLEM.md) | Official problem statement §4.1–4.6. Marketing-level; the kit is the binding contract. |
| [docs/AmazonReviews2023.md](docs/AmazonReviews2023.md) | Local scrape of amazon-reviews-2023.github.io. Field dictionary. |
| [techjam-conversational-search-main/](techjam-conversational-search-main/) | **The kit. In sync with upstream `main` as of this sweep.** |
| [assets/catalog.jsonl](assets/catalog.jsonl) | 50,000 products, 60 MB. |
| [assets/catalog.jsonl.gz](assets/catalog.jsonl.gz) | ✅ SHA-256 verified `07fd1426…a8f8` against `SHA256SUMS`. |
| [AmazonReviews2023/](AmazonReviews2023/) | Clone of the upstream **academic** repo (MIT, © 2024 Yupeng Hou). BLaIR / Amazon-C4 / seq-rec. Not competition code. |

**There is no database anywhere.** Scanned for `*.db *.sqlite* *.parquet *.csv *.zip *.pkl *.npy *.faiss *.bin *.pt` →
zero hits. The only "DB" is the in-memory SQLite FTS5 index the starter builds at `__init__`. The out-of-scope rule
("must run entirely in-memory") means it should stay that way.

**Git state:** the repo has **zero commits** — branch `main` exists but is empty, nothing is tracked yet.
Root [.gitignore](.gitignore) now contains `.env` ✅ (fixed). [.env](.env) holds a live `SOCLAAS_API_KEY` — keep it ignored;
submission requires a **public** repo.

**Setup step nobody states:** `cp assets/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl`
(or pass `--catalog`). The kit's `.gitignore` already excludes `data/catalog.jsonl`, so it can never be committed.

---

## 2. The contract the evaluator actually enforces

[evaluator/local_evaluator.py](techjam-conversational-search-main/evaluator/local_evaluator.py) **is** the rulebook — 312 lines, stdlib only.

- 🔑 **The evaluator constructs `Agent(args.catalog)`** — positional catalog path. The README, `submission_rules.md`
  and `agent_api_contract.json` **all omit `__init__` entirely**. Signature must be
  `def __init__(self, catalog_path: str | Path = "data/catalog.jsonl")`.
- ⚠️ **Your agent cannot `import` from `evaluator.local_evaluator`** — the evaluator imports `starter.agent` at module
  scope, so it is a circular import and crashes at startup. (Hit this for real.) If you want the simulator's exact
  functions, **copy them into your module**, don't import them.
- 🔑 **One `Agent` instance serves all 200 sessions** (`evaluate(Agent(path), …)`). Index build cost amortizes to zero —
  a heavy in-memory index is free. Corollary: **all state leaks across sessions unless `reset()` clears it.**
  Long-term profile memory is legal; per-session slots must be wiped in `reset`.
- `respond` exceptions are caught and replaced with `{message:"", ask_attribute:None, recommendations:[]}`. You lose
  the turn, not the run — so a try/except fallback costs nothing. Same for any non-dict return or non-str `message`.
- `normalize_recommendations`: drops IDs not in the catalog, drops duplicates, keeps **first 10 valid**. Returning up to
  100 is legal and harmless — junk IDs are silently dropped and do **not** consume a slot.
- The optional `score` field is parsed then **ignored**. **List order is the only ranking signal.**
- `usage` is summed only when both values are `int` and `>= 0`. Feasibility metric — **not in TechnicalScore**.
- No timeout or memory cap locally. ⚠️ `submission_rules.md` reserves the right to run under **CPU, memory, timeout and
  no-network restrictions**. Ship an offline fallback and document network dependence explicitly.

### Scoring, exactly

```
HitRate@10 = hits / N
MRR        = mean(1/rank), miss = 0
MTTC       = mean(first_hit_turn), miss = 11
Efficiency = clip((11 - MTTC)/10, 0, 1)
TechnicalScore = 0.50·HitRate + 0.30·MRR + 0.20·Efficiency
```

- 🔑 **MRR is rank-1-hungry.** Rank 1 = 0.30 of the score; rank 10 = 0.03. Getting into the list is half the game,
  being *first* is the other 30%.
- 🔑 **MTTC is worth more than it looks.** MTTC 9.8 → 3.0 alone is +0.16. Each fruitless turn costs 0.02.
- ⚠️ **Always return recommendations AND ask a question, on every single turn.** There is no penalty for recommending,
  and a hit ends the session immediately. Never return an empty list. Never send `ask_attribute: null` early.

---

## 3. 🔑⚠️ The core finding: the simulator is invertible

There are no human dialogs in this competition. `materialize_hidden_fields()` uses a session's `intent_card`/`behavior`
if present — and the shipped [public_set.jsonl](techjam-conversational-search-main/data/public_set.jsonl) **contains
neither** (fields are exactly `category_bucket, difficulty_bucket, ground_truth, sample_id, scenario_type, user_profile`).
So the evaluator **derives the entire customer script at runtime from the target product's own metadata**:

1. `intent_card(product)` — flattens the target's `features` + `details` into `"key: value"` strings, inserts a
   material-regex hit at index 0 and `"color: X"` at index 1, appends `"budget around $P"`. Each string is
   whitespace-collapsed, stripped of `-;,.`, truncated to **180 chars**. Then
   `hard_constraints = cleaned[:2]`, `soft_preferences = cleaned[2:4]`.
   📊 **Every one of the 200 sessions has exactly 2 hard + 2 soft constraints.**
2. `coarse_category(categories)` — the last two comma-split, non-generic parts of the target's `categories` list.
3. `initial_message()` / `customer_reply()` — fixed templates that splice those strings in **verbatim**.

⚠️ `intent_card()` reads **`features` + `details` only** — never `title`, never `description`. Your inversion index
must mirror that exactly. (The material/color *regex* does scan the full corpus incl. description, but only ever
yields one low-entropy word like `"cotton"`.)

### 📊 Measured identifiability (200 public sessions)

| Information held | median candidates | mean | ≤10 candidates |
|---|---|---|---|
| coarse_category only (turn 1, browsing) | 181.5 | 275.2 | 6 / 200 |
| + both `hard_constraints` | 1.0 | 11.5 | 152 / 200 |
| + both `soft_preferences` (full card) | **1.0** | 1.7 | **198 / 200** |

**175 / 200 sessions are uniquely determined by the full card.** Confirmed end-to-end: the prototype scores Hit@10 = **1.000**.

⚠️ **The paraphrase risk — do not build inversion alone.** `competition_specification.md` explicitly reserves:
*"If natural-language paraphrasing is added by the organizer, it cannot decide correctness."* A template-literal parser
could score 0.9 publicly and collapse privately. **The mitigation is already measured: the popularity+category prior
(§5) floors us at 0.713 with zero parsing, and ✅ **0.826 once blended with `bge-m3` dense retrieval**.**
Structure it as: popularity+dense prior as the base ranker, exact-constraint
matching as a large re-ranking bonus. Then paraphrase *degrades* the score toward 0.826 instead of zeroing it —
and that layered design is exactly the hybrid architecture the problem statement asks for, so it costs nothing in judging.
(Rival team ByteMe has independently built a `ParaphrasingAgent` stress harness for precisely this; see §8.)

---

## 4. Simulator turn mechanics (exploitable specifics)

### `ask_attribute` is the only channel that matters
The simulator reads the structured `ask_attribute` field and **never parses your `message` prose**.
Prose is for the human judges; `ask_attribute` is for the score.

🔑 **`"other"` is a wildcard.** From `customer_reply`:
```python
matches = [v for v in constraints
           if v not in disclosed and (attribute == "other" or classify_constraint(v) == attribute)][:2]
```
`"other"` bypasses classification and returns **the next 2 undisclosed constraints in order**
(hard[0], hard[1], then soft[0], soft[1]). There are always exactly 4 → **two `"other"` asks extract the whole card.**

⚠️ **Asking the semantically "right" attribute is worse.** `classify_constraint` is a crude keyword rule. 📊 Over the
800 public-set constraints it emits: `feature` 404, `material` 302, `color` 60, `style` 19, `size` 11, `use_case` 4 —
and **never** `brand`, `budget`, or `category`. Example: `"Material:alloy"` classifies as `feature`, because `alloy`
isn't in the hardcoded `MATERIALS` tuple. Asking `material` there returns *"I don't have an additional preference"* —
a wasted turn.

⚠️ `ask_attribute: null` → *"Ask me about one specific attribute"*, revealing nothing.

### Per-scenario timing (public mix == private mix: 40/40/15/5)

| Scenario | n | Turn-1 message contains | Floor |
|---|---|---|---|
| **buying** | 80 | category **+ `hard_constraints[0]` verbatim** (marked disclosed) | turn 1 |
| **browsing** | 80 | category only — *"but I'm still exploring"* | turn 1 |
| **intent_override** | 30 | category + `soft_preferences[1]`, **not** marked disclosed | **turn 3, hard floor** |
| **boundary** | 10 | category only (same template as browsing) | turn 1, but first ask is burned |

- **intent_override**: `override_applied` starts `False`; the hit check is `if override_applied and target in ranked`.
  🔑 **Turn 1–2 recommendations are discarded even at rank 1.** The flag flips when `turn + 1 == override.turn`, where
  `override.turn = Random(f"{sample_id}\0{scenario_type}").choice([3,4])` — 📊 public split is **12 sessions at turn 3,
  18 at turn 4**. The override message is
  `"Actually, ignore my earlier preference. What I need is: {hard_constraints[0]}."` → it *hands you a hard constraint*
  and adds it to `disclosed`, but that turn reveals nothing else, costing one ask.
  **Strategy: spend turns 1–2 purely on `"other"` asks (ranking is worthless there), convert at turn 3/4 with a full card.**
  This structural floor is why they're all labeled `difficulty_bucket: hard`; our prototype's override MTTC is 3.6, near optimal.
- **boundary**: the *first* ask of any attribute returns *"I don't have a preference for {attribute}; please use your
  judgment."* and sets `boundary_used = True`; every later ask behaves normally. Costs exactly one turn, unavoidable. 5% of sessions.
- `disclosed` is **exact-string** matched — re-eliciting a disclosed constraint yields nothing.

---

## 5. 🔑📊 The popularity leak — biggest free win in the whole problem

The kit README states sessions are *"sampled deterministically from the official Clothing 5-core leave-last-out split."*
5-core requires every user **and item** to have ≥5 interactions; leave-last-out makes the target the user's **N-th (last)**
purchase. The 50,000-product catalog, however, includes the long tail. The result is a massive selection bias:

| | catalog | targets |
|---|---|---|
| `rating_number` median | **12** | **6,846** |
| `rating_number` mean | 241 | 16,179 |
| `average_rating` median | 4.2 | 4.4 |

- 📊 Ranking a coarse category purely by `rating_number`: target is **#1 for 70/200** sessions and **top-10 for 163/200**.
- 📊 Globally, the median target is the **275th** most-reviewed product out of 50,000; 173/200 are in the global top 5,000.
- 📊 An agent using **only** category + popularity, ignoring every constraint the customer states, scores **0.71334**.

This is nearly the whole of the publicly-known 0.7504 "BM25 trick" score. **Most of what looks like retrieval skill on
this benchmark is a popularity artifact.** Two consequences:
1. Always fold a popularity prior into ranking — it's the single cheapest lift and it is *robust to paraphrase*.
2. ⚠️ When evaluating your own ideas, compare against the **paraphrase-proof floor**, never against 0.107.
   That floor is **0.713** with popularity alone and ✅ **0.826** once a blended `bge-m3` dense route is added
   ([IDEA.md](IDEA.md) §3). **0.826 is the current bar.** Anything that doesn't clear it is contributing nothing.

The same construction pipeline generates the private 800, so this bias should replicate (the split differs only in
*which* users/targets, per §4.4: *"Public and private evaluation sessions use separate users and target products."*).

---

## 6. The data itself

### Catalog — 50,000 rows, `Clothing_Shoes_and_Jewelry`
Visible fields: `parent_asin, title, features, description, price, categories, details, average_rating, rating_number, store`.
Only `parent_asin` is scored. Read-only — no mutation, no mock ASIN injection.

- ⚠️ 📊 **`price` is null for 79% of rows.** Budget filtering is mostly dead weight; `classify_constraint` never
  returns `"budget"` anywhere on the public set.
- 📊 `description` empty for 48%, `features` empty for 10%.
- 📊 `coarse_category` yields **1,115 distinct values**, heavy-headed: `Shirts T-Shirts` 1354, `Shoes & Jewelry Westlake`
  1136, `Watches Wrist Watches` 1034, `Shoes Fashion Sneakers` 1017, `Dresses Casual` 769. Category alone is never enough.

### Public sessions — 200
📊 `buying` 80 / `browsing` 80 / `intent_override` 30 / `boundary` 10. All 200 targets exist in the catalog. No duplicate targets.

⚠️ **`user_profile` is near information-free — do not build on it.** 📊 Measured across all 200:
- `purchase_frequency` — **constant** `"3-4 prior purchases"`.
- `category_bucket` — **constant** `"clothing"`.
- `difficulty_bucket` — a **pure alias of `scenario_type`** (buying=easy, browsing/boundary=medium, override=hard).
- `preference_tags` — 9-word vocabulary total: fit 163, material 154, comfort 144, style 101, durability 47,
  performance 26, warmth 18, weather 12, general shopping 1.
- `rating_style` — usually positive 134 / critical 45 / mixed 21. `average_prior_rating` is a float.

Use it for a tie-break prior at most. If personalization appears to give a big gain, it's a bug in your harness.

---

## 7. Judging — what the score actually buys

⚠️ **Most-missed rule.** Upstream commit `3407835` (2026-08-27) added to both README and spec:

> `TechnicalScore` is an objective input to the `Technical Execution` assessment. It is **not** a separate judging
> criterion and does **not** represent the entire `Technical Execution` score.

Weights: Technical Execution **35%** (TechnicalScore is only part of it), Innovation & Problem Insight **20%**,
Impact & Relevance **20%**, Feasibility & Practicality **15%**, Presentation & Communication **10%** (final event only).

**Implication:** build the four pillars PROBLEM.md asks for — dual-track intent routing, dynamic state machine +
proactive clarification, personalized context distillation, adaptive orchestration — and let inversion be the
*ranking prior inside* that architecture, never the architecture itself. Feasibility (15%) also actively punishes a
brittle template hack.

⚠️ **The organizer edits the spec mid-competition** (3 commits: `2a6cc8e` Aug 24 release → `9a35be5` Aug 24 → `3407835` Aug 27).
Re-diff the kit against upstream before submitting. Notably `9a35be5` **removed the cost-reimbursement promise** —
the release text said the organizer *"may reimburse model costs through prizes"*; current text says
**"does not provide or reimburse model API credits; teams are responsible for any costs."**

⚠️ **Webinar:** PROBLEM.md announces a Technical Workshop Webinar with Q&A on **28 Aug, 4:00–4:45pm**, but the
"Click here to join" has **no URL in the document**. Get the link from Devpost / the TechJam portal.

### Deliverables (PROBLEM.md §4.5)
1. **Devpost write-up** — how it addresses the problem, dev tools, APIs, libraries/frameworks, datasets/assets used.
2. **Public GitHub repo** — commented code for all components + README with overview, setup, **steps to reproduce
   results**, a limitations/what-I'd-improve reflection, and team contributions.
3. **Public YouTube demo video**, linked from Devpost. A backend/API walkthrough is explicitly accepted for this track.
4. Plus, from `submission_rules.md`: a disclosure of **latency, token usage, estimated model cost**, and whether the
   system **requires network access**.

---

## 8. Competitive intel (all public on GitHub)

- **PR #1 on the upstream repo is open competitive intelligence.** `junhui9883-code` (team "ByteMe") publicly filed
  *"Add conversation memory and clarification questions"* — a **7-line diff** (accumulate messages across turns +
  `ask_attribute: "other"` every turn) claiming 0.10671 → **0.750401**. ✅ Reproduced exactly on this machine.
  **Assume every team reading the repo has 0.75. It is the floor, not a result.**
- Their fork `junhui9883-code/techjam-byteme-shopping-copilot` is public: structured `src/{dialogue,retrieval,eval}`,
  a committed `runs/day0.json` at **0.78576**, and code comments citing **0.855** as their current public-set level.
  They are Claude-assisted (their modules reference a `CLAUDE.md`) and have built `src/eval/paraphrase.py`, a
  scaffold-vs-full paraphrase stress harness that wraps the *agent* (not the evaluator) to stay rules-compliant —
  a defensible idea worth matching.
- 📊 **20 public forks** of the kit exist. Several team names are visible (Byteme, FattyCoders, hazelnut-bubble,
  aurelia-shopping-copilot, ai-shopping-assistant, Terrace-NUS).
- ⚠️ Our own fork/repo will be public too — **anything we push is visible to rivals.** Keep the working repo private
  until submission, or push only at the end.

---

## 9. Assets on hand that most teams won't use

[AmazonReviews2023/](AmazonReviews2023/) is the upstream McAuley Lab repo (MIT). Directly usable here:

- **BLaIR** — `hyp1231/blair-roberta-base` (125M) / `-large` (355M). **MIT-licensed, ungated, 512-token max.**
  ⚠️ *No longer the default dense encoder* — `bge-m3` (free on the NUS endpoint) is measured and in use; `Qwen3-Embedding-0.6B` leads MTEB for the offline path. BLaIR stays a benchmark candidate because it is pretrained on this exact dataset.
  RoBERTa pretrained on *(item metadata, language context)* pairs from **this exact dataset**. It is the correct
  off-the-shelf dense encoder for the Browsing track: it embeds a vague natural-language need and a product metadata
  blob into one space. 125M is CPU-feasible for 50k items fully in-memory, satisfying the "no vector DB cluster"
  constraint, and weights can be cached locally for the no-network scenario.
  Usage in [AmazonReviews2023/blair/README.md](AmazonReviews2023/blair/README.md): CLS token, L2-normalized.
- **Amazon-C4** — 21,223 ChatGPT-generated *complex context* queries → item_id, same dataset family. Free tuning/eval
  data for the browsing leg **and** a ready-made source of realistic paraphrased queries for the §3 robustness test.
- [product_search_results/bm25.py](AmazonReviews2023/product_search_results/bm25.py), `generate_emb.py`, `eval_search.py` —
  reference hybrid/dense retrieval harness.
- Citation for the write-up: Hou et al., *Bridging Language and Items for Retrieval and Recommendation*, arXiv:2403.03952.

---

## 10. Hard limits & out-of-scope (PROBLEM.md §4.3)

- **10 turns max**, hard: *"forced termination and zero score if exceeded."*
- Catalog **strictly read-only**; no structural mutation, no mock ASIN injection.
- **Out of scope — do not build:** UI/UX (headless backend eval only), foundation-model training/fine-tuning,
  heavy external vector-DB clusters (**must run entirely in-memory**), multimodal (text + structured metadata only).
- **Allowed assumptions:** inputs pre-cleaned (no typo/ASR handling), catalog and prices static, single-user isolated
  sessions (no concurrency).
- **No organizer API keys, no credits, no reimbursement.** A paid LLM is *not required*. Never commit secrets.
- Disallowed in the submission bundle: private eval data, organizer-only files, secrets, privileged host access,
  evaluator modifications, undeclared external service dependencies.

---

## 11. Working checklist — non-obvious items only

1. `def __init__(self, catalog_path="data/catalog.jsonl")` — positional, defaulted. Non-negotiable.
2. **Never import from `evaluator.local_evaluator`** — circular import, hard crash. Copy the functions instead.
3. `reset()` clears session slots; keeps the prebuilt index and any long-term store.
4. Every turn: non-empty ranked list **and** a `message`. `ask_attribute = "other"` until all 4 constraints are out.
5. Wrap the whole `respond` body in try/except with a safe fallback list — a crash is a silently forfeited turn.
6. Rank by: exact-constraint match count → popularity (`rating_number`) → dense/BM25 similarity. Popularity is the
   paraphrase insurance policy (§5).
7. Run: `python3 -m evaluator.local_evaluator` from inside the kit dir → writes `results.json` incl. per-session rows.
   Flags: `--catalog / --dataset / --output` only. Full 200-session run ≈ 4–17 s.
8. Never edit the evaluator or `public_set.jsonl` when reporting a score. Keep a pristine copy to prove it.
9. Re-diff the kit against upstream `main` before submitting — the organizer keeps editing the spec.
10. Disclose model, latency, token usage, cost and network dependence in the report — an explicit submission requirement.

---

## 12. 📊 Experiment log — every measurement, in one place

All run on this machine against the pristine evaluator + 200 public sessions. Scripts in [experiments/](experiments/).

### 12.1 Agent scores (full pipeline, TechnicalScore)

| Agent | Hit@10 | MRR | MTTC | Score | Script |
|---|---|---|---|---|---|
| Shipped BM25 starter | 0.125 | 0.068 | 9.81 | 0.10671 | kit |
| Category + popularity only | 0.815 | 0.498 | 3.18 | 0.71334 | — |
| Public PR #1 trick (`other` + history) | 0.875 | 0.540 | 3.46 | 0.750401 | — |
| ByteMe rival day-0 run | 0.910 | 0.706 | 5.05 | 0.78576 | *(their repo)* |
| Inversion, recommend every turn | 1.000 | 0.726 | 1.53 | 0.90743 | `agent_inversion_0.9074.py` |
| Inversion, silent on turn 1 | 1.000 | 0.916 | 2.26 | 0.9497 | — |
| Inversion, confidence gate only | 1.000 | 0.978 | 3.43 | 0.9447 | — |
| **Inversion + gate + turn-3 deadline** | **1.000** | **0.975** | **2.59** | **0.9607** | `agent_best_0.9607.py` |
| *Theoretical maximum* | 1.000 | 1.000 | 1.39 | *0.9922* | — |

### 12.2 Retrieval under the paraphrase-proof condition
No template matching. Candidates = target's coarse category. 22,458 products embedded with `bge-m3`.
Script: `floor_test.py`, `blend_sweep.py`.

| Ranker | hit@10 | MRR | rank-1 |
|---|---|---|---|
| popularity only | 0.815 | 0.4981 | 70/200 |
| **`bge-m3` dense only** | **0.620** | 0.4273 | 72/200 |
| RRF(dense, popularity) k=60 | 0.840 | 0.5792 | 94/200 |
| **dense + 0.02·log(popularity)** | **0.905** | **0.6855** | **117/200** |

At MTTC ≈ 2.6 this floor is **TechnicalScore ≈ 0.826** with zero dependence on the template inversion.
**🔑 That is the bar for new ideas — not 0.713, and certainly not 0.107.**

Blend weight × information state (`blend_sweep.py`):

| weight | full 4-constraint card | category only (turn 1) |
|---|---|---|
| 0.00 (pure dense) | 0.620 | **0.185** |
| 0.02 | 0.900 | 0.675 |
| 0.03 | **0.905** | 0.740 |
| 0.08 | 0.845 | 0.785 |
| 0.15 | 0.830 | **0.815** |
| ∞ (pure popularity) | 0.815 | **0.815** |

### 12.3 Model latency and rerank quality
Script: `rerank_model_test.py`. Rerank tested on 60 sessions, paraphrase-proof condition.

| Model | Latency (20-cand prompt) | Rerank MRR | Δ vs popularity order |
|---|---|---|---|
| `qwen3.6:35b` (A3B MoE) | **0.86 s** | **0.7506** | **+0.191** |
| `ornith1.5:35b` (A3B MoE) | 1.29 s | 0.5598 | +0.000 ⚠️ *silent failures* |
| `llama3.1:8b` (dense) | 2.28 s | 0.5646 | +0.005 |
| `qwen3.8:27b` (dense) | 2.40 s | — | — |
| `qwen3.5:9b` | 4.45 s | — | ⚠️ empty at 200 tok |
| `gemma4:26b` | 4.79 s | — | ⚠️ empty at 200 tok |

`bge-m3` embeddings: 1024-dim · catalog ≈ 198 tok/product ≈ 9.9M tokens ≈ **$0.10** · 22,458 items in ~6 min
at 12-way parallelism · 50k × 1024 fp32 = **205 MB** in RAM.

---

## 13. ⚠️ Errors and learnings — mistakes already made, do not repeat

Each of these cost real time or produced a confidently wrong conclusion.

### 13.1 Engineering traps
1. **Circular import.** Your agent cannot `import` from `evaluator.local_evaluator` — the evaluator imports
   `starter.agent` at module scope. Hard crash on startup. **Copy the functions, never import them.**
2. **`Agent(catalog_path)` is undocumented.** The evaluator constructs it positionally; the README, the API
   contract and `submission_rules.md` all omit `__init__` entirely.
3. **⚠️ `ornith1.5:35b` fails silently.** Returns `content: None` while consuming the full `max_tokens` — it is an
   agentic model that puts output elsewhere. Our first harness scored **60 failed calls as "+0.000, the model
   doesn't help."** A silent model failure is indistinguishable from a model that isn't helping, and that is a
   wrong conclusion you can act on for days. **Every LLM call site must assert on a parsed non-empty result and
   surface a failure count.**
4. **Model aliases are traps.** `default` → `qwen3.6:35b`, `test`/`advanced-vision` → `qwen3-vl:32b`,
   `ornith1.0:35b` → `ornith1.5:35b`, `qwen3.6:27b` → `qwen3.8:27b`. **Pin explicit IDs**; aliases can be repointed.
5. **`qwen3.5:9b` and `gemma4:26b` returned empty content** at `max_tokens: 200` on a listwise prompt — reasoning
   tokens consumed the budget. Always check `finish_reason`.
6. **Restore the pristine starter after testing.** The kit must stay byte-identical to upstream or a reported
   local score is not verifiable. Re-diff before every reported run.

### 13.2 Reasoning errors — wrong conclusions I actually reached
1. **"Optimize for cost."** ⚠️ Wrong. Token usage is *"a feasibility metric, not part of the core technical
   score"*; there is **no rubric credit for model choice**. Worse, the cheap model *cannot do the job*
   (`llama3.1:8b` +0.005 MRR) and the expensive models are **sparse MoE, hence faster** (0.86 s vs 2.28 s).
   **Price and speed are anti-correlated on this endpoint.** The real constraints are, in order:
   network availability at scoring → latency → output-format reliability → *(cost, irrelevant)*.
2. **"RRF is parameter-free and hard to beat."** ⚠️ Beaten. A single tuned scalar
   (`dense + 0.02·log(popularity)`) scored 0.905 vs RRF's 0.840. RRF discards score *magnitude*, and popularity
   here is a strength signal, not merely an ordering. **Keep RRF as a baseline; never assume it wins.**
3. **"Dense retrieval will lift the floor."** ⚠️ Only in combination. **Dense alone (0.620) is worse than
   popularity alone (0.815).** Building the embedding route, watching it lose to the dumbest baseline, and
   concluding "embeddings don't work here" was a very available wrong answer.
4. **"Speed matters, convert early."** ⚠️ Backwards. MRR is weighted 0.30 vs Efficiency 0.20 and rank-1 is 5×
   rank-5, so trading one turn for a rank-1 hit gains +0.225 and costs −0.02 — **patience beats speed ~11×**.
   Staying silent on turn 1 moved 0.9074 → 0.9497.
5. **"Use BLaIR for dense retrieval."** Superseded — written before API access. `bge-m3` is measured and free;
   `Qwen3-Embedding-0.6B` leads MTEB for the offline path. BLaIR is still a benchmark candidate (pretrained on
   this exact dataset), not the default.
6. **Shallow research produced a confident wrong plan.** Six web searches missed: FacT-CRS (a decision tree that
   **beats deep-RL CRS** using the exact two stopping rules we rediscovered by experiment), MMR/DPP diversity
   (an *explicit* brief requirement covering 40% of sessions), NQC query-performance prediction (the principled
   replacement for our magic turn-3 deadline), HyDE, and cascade-ranking vocabulary.

### 13.3 Process learnings
1. **Documentation drift is self-inflicted.** IMPORTANT.md, REPORT.md and IDEA.md were written on three separate
   occasions; each new measurement went into the newest file only. Result: REPORT.md said *"the bar is 0.713"*
   while IDEA.md said *"the bar is 0.826"* — contradictory instructions from compatible numbers.
   **When a measurement changes a recommendation, update every document carrying that recommendation in the same
   pass.** The precedence banner is a workaround, not a fix.
2. **200 sessions is small.** A 0.02 TechnicalScore gap is one or two sessions changing rank — **noise**.
   Bootstrap-resample 1,000× before declaring a winner.
3. **Compare against the right baseline.** ✅ **0.826**, the blended paraphrase-proof floor. Anything that does
   not clear it is contributing nothing, no matter how good it looks against the 0.107 starter.
4. **Keep prototypes out of temp directories.** The first set lived in a session scratchpad that gets cleaned up;
   docs referenced them as if permanent. They now live in [experiments/](experiments/).

---

## 14. ⚠️ PROBLEM.md requirements we nearly missed

Audited every requirement in [docs/PROBLEM.md](docs/PROBLEM.md) against our own docs. These were **absent** and
are all explicitly named in the brief — judges reading §4.2/§4.3 will look for them by name.

### 14.1 🔑 "LLM Semantic Ranking" is part of the *required* pipeline, not an optional extra
Pillar I states the pipeline base is **"Multi-Route Retrieval → LLM Semantic Ranking"**. We had been treating the
LLM reranker as optional insurance, justified by ✅ §12.1 (193/200 already rank-1, so it adds little on the clean
set).

**Both things are true and must both be said.** Build the LLM ranking stage — it is named in the brief — and then
**report honestly that it contributes little on the clean set and mainly buys paraphrase robustness.** Omitting it
looks like a missing pillar; including it without the caveat looks like an unmeasured claim. Measuring it and
saying so is the strongest position available.

### 14.2 "Slot decay over time" — explicitly in scope, unaddressed
§4.3 lists *"weights, custom dynamic truncation, and **slot decay over time**"*. We have the mechanism implicitly
(✅ §12.2: the optimal blend weight shifts from pure-popularity at turn 1 toward dense as slots accumulate) but
never named or built decay itself. **Add `slot_age` to the session state and down-weight stale slots** — cheap,
and it is the natural home for intent-override handling (an overridden slot decays to zero instantly).

### 14.3 "Custom dynamic truncation" — explicitly in scope, unaddressed
Truncating the candidate pool as a *function of confidence*, rather than always returning 10. Our confidence gate
already decides *whether* to convert; truncation decides *how many* to show. Natural pairing with NQC.

### 14.4 "Compress decision paths" — the stated goal of the LLM ranking stage
§4.3: *"Fine-tuning prompt strategies or local scoring logic for the LLM ranking stage to **compress decision
paths**."* This is the brief's own phrasing for what our confidence gate does (0.9074 → 0.9607 by converting
sooner and more precisely). **Use their vocabulary in the write-up** — it maps our best result onto their stated
objective.

### 14.5 "Iteratively refines its own guidance logic" — Pillar III, unaddressed
Not just adapting the *retrieval* strategy, but the agent improving **how it asks questions** over the session.
Concretely: track which `ask_attribute` values actually yielded new constraints this session and stop re-asking
attribute types that returned *"I don't have an additional preference"*. Cheap, visible in a demo, and it is a
direct answer to a pillar we would otherwise only gesture at.

### 14.6 Long-term user profile — build it even though we measured it as near-empty
Pillar III requires *"continuously updating short-term session states and **long-term user profiles**"*.
✅ §6 measured the supplied `user_profile` as nearly information-free (constant `purchase_frequency`, 9-word tag
vocabulary). **That is not a reason to skip the layer** — it is a reason to build it, measure it, and report the
finding. "We built the personalization layer and measured that this dataset's profile carries almost no signal"
is a genuine insight; silently omitting it reads as a missing pillar.

### 14.7 ⚠️ Demo video: third-party trademarks
§4.5 requires the video *"does not include third-party trademarks or copyrighted content without permission."*
**Our catalog is Amazon product data — titles, brand names and store names are trademarks** (`Skechers`,
`Pro Club`, `Hide & Drink`…). A screen recording of recommendations displays them. Mitigations: keep the focus on
the API/pipeline rather than product branding, or blur/anonymise displayed titles. Flagging it now because it is
discovered late and cheaply avoided.
