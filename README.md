# Shopping Copilot — TikTok TechJam 2026, Track 4

A multi-turn conversational shopping agent that locates a hidden target product in a frozen 50,000-item Amazon Clothing, Shoes & Jewelry catalog within 10 turns. The agent is fully deterministic, runs on NumPy alone with **zero LLM API calls**, **zero tokens**, and **\$0 model cost**.

---

## Results

| Metric | Value |
|---|---|
| **TechnicalScore** | **0.9744** |
| Hit@10 | 1.0000 |
| MRR | 0.9942 |
| MTTC | 2.19 |
| Efficiency | 0.8810 |

*Evaluated on `public_set.jsonl` (200 sessions) using the unmodified official evaluator.*

**Reference points:** Official starter agent = `0.1067` · Popularity-only baseline = `0.7133`

---

## Setup Instructions

### Prerequisites

- **Python**: 3.11+ (tested with 3.11.9)
- **OS**: macOS / Linux / Windows

### 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> The only runtime dependency is `numpy`. The catalog (`data/catalog.jsonl`) and all datasets are already included in the repository.

### 2. Environment Variables (Optional)

The shipped agent makes **zero network calls** by default. Environment variables are only needed if the optional LLM extraction tier is enabled (it is disabled in the submitted configuration).

```bash
cp .env.example .env
# Edit .env with your API keys only if using the LLM tier
```

| Variable | Description | Required |
|---|---|---|
| `SOCLAAS_API_KEY` | SoCLaaS API key for LLM tier | No (LLM tier disabled) |
| `SOCLAAS_BASE_URL` | SoCLaaS endpoint URL | No |
| `HF_TOKEN` | HuggingFace token | No |

### 3. Run with the Official Evaluator

```bash
python3 scripts/evaluation/evaluate.py \
    --agent agent:Agent \
    --catalog data/catalog.jsonl \
    --dataset data/public_set.jsonl \
    --offline
```

More evaluation options:

```bash
python3 scripts/evaluation/evaluate.py --all                    # all datasets
python3 scripts/evaluation/evaluate.py --dataset data/public_set.jsonl --ci --scenarios  # with CIs
```

---

## Architecture

The agent uses a 6-stage Bayesian pipeline — no trained model files, no network calls, pure NumPy:

```
Customer Message
    │
    ▼
┌──────────────────────────────────────────────┐
│  1. PARSE (cheapest tier first)              │
│     Template match → Ontology → (LLM tier)   │
│     Zero LLM calls on templated input.       │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  2. VERIFY before believing                  │
│     Proposed values resolve to real catalog   │
│     strings. Ambiguous spans become           │
│     probability mixtures.                     │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  3. CATEGORY POOL (Level 1)                  │
│     P(category | opener) over 1,115 shelves.  │
│     85% mass coverage. 50K → median 182 items.│
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  4. ITEM BELIEF (Level 2 Log-Posterior)      │
│     Exact card strings + attribute pairs +    │
│     token overlap + soft-card Jaccard.        │
│     Every factor bounded — no term zeros.     │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  5. SURVIVAL EVIDENCE                        │
│     Items shipped on prior turns are proven   │
│     wrong → set to -∞ in the posterior.       │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│  6. EXPECTED UTILITY DEPTH POLICY            │
│     V = 0.75·hope − cost; ship the largest k │
│     where 1/k > V. List length is derived.   │
└──────────────────────────────────────────────┘
```

### Key Design Decisions

- **Three-tier parse cascade:** Template regex (verbatim simulator patterns) → keyword/regex ontology → optional LLM router. On templated evaluator input, Tier 1 handles everything with zero model calls.
- **Catalog-grounded verification:** Every extracted constraint is validated against the actual catalog vocabulary. Unresolvable values are discarded; ambiguous values are carried as probability mixtures over real catalog strings.
- **Bayesian category pooling:** IDF-weighted posterior over 1,115 coarse categories reduces the search space from 50,000 to a median of 182 candidates while maintaining 100% target recall on the public set.
- **Bounded log-posterior scoring:** Four evidence channels (exact card strings, normalized attributes, token overlap, soft-card Jaccard) with gain parameters fitted by Bayesian optimization (Optuna TPE). All likelihoods are bounded below to prevent any single factor from eliminating candidates.
- **Information-theoretic depth policy:** Expected utility maximization determines how many items to recommend per turn — the agent withholds recommendations when asking another question has higher expected value.

---

## Project Structure

```
agent.py                      # Submission entry point — from agent import Agent
README.md                     # This file
requirements.txt              # numpy only
.env.example                  # Environment variable template
data/
  catalog.jsonl               # Frozen 50,000-product catalog
  public_set.jsonl            # 200 official public evaluation sessions
  combine/                    # Combined training dataset (9,600 train + 3,200 val)
  freeform_v1/                # Free-form natural language sessions
  resplit_60_20_20/           # ASIN-disjoint 60/20/20 split (14,000 sessions)
demo/
  index.html                  # Interactive multi-turn session replay demo
scripts/
  evaluation/evaluate.py      # Evaluation CLI (all datasets, stress levels, ablations)
  training/hyperparameter_tuning.py   # Optuna TPE hyperparameter fitting
  earlyhit.py                 # EarlyHit@k curve analysis
  llm_tier.py                 # LLM tier impact measurement
src/
  simulator.py                # Mirror of evaluator's customer simulator
  copilot/
    agent.py                  # Core Agent class (reset, respond, fallback)
    flags.py                  # All submission hyperparameters and defaults
  retrieve/
    bm25.py                   # Okapi BM25 retrieval (ships disabled, gain=0.0)
    category.py               # Level 1: Bayesian category posterior
    index.py                  # 50K product catalog index
  rank/
    belief.py                 # Level 2: item log-posterior and depth policy
    likelihood.py             # Bounded log-likelihood evidence terms
    softcard.py               # Paraphrase-tolerant soft-card Jaccard matching
  state/
    session.py                # Constraint state, aging decay, slot management
  understand/
    attributes.py             # Attribute extraction from prose
    extract.py                # LLM constraint extractor (optional tier)
    intent.py                 # Intent pipeline, vocabulary resolution, state transactions
    llm.py                    # LLM client with caching (optional tier)
    parse.py                  # Three-tier parsing cascade
    tokens.py                 # Numeric-preserving tokenizer for BM25
  eval/
    harness.py                # Non-invasive test harness wrapping official evaluator
    stress.py                 # 5-level paraphrase stress engine
    ablations.py              # Ablation flag configurations
    compare.py                # TechnicalScore calculation and bootstrap CIs
    datasets.py               # Dataset paths and loaders
    freeform.py               # Free-form opener proxy
    holdout.py                # Stratified ASIN-disjoint split generator
    instrument.py             # Offline diagnostic recorder
    measure.py                # Standalone CLI evaluation tool
techjam-conversational-search-main/   # Official competition kit (unmodified)
  evaluator/
    local_evaluator.py        # Official local evaluator
  starter/
    agent.py                  # Official starter agent
  data/
    public_set.jsonl          # Official public sessions (kit copy)
  docs/
    evaluation_config.json    # Evaluation configuration
    agent_api_contract.json   # Agent API contract
```

---

## Method & Model Choice

| Aspect | Detail |
|---|---|
| **Approach** | Deterministic Bayesian retrieval + ranking pipeline |
| **Models used** | None at inference time (LLM tier disabled) |
| **External APIs** | None (zero network calls) |
| **Training** | Offline hyperparameter fitting via Optuna TPE on training split only |
| **Dependencies** | NumPy + Python standard library |

The agent is purely rule-based with Bayesian scoring. All 8 hyperparameters (evidence gains, category temperature, depth policy constants) were fitted offline using Tree-structured Parzen Estimator (TPE) optimization on the training split. No model weights or embeddings are loaded at runtime.

### Innovation Highlights

- **Buying vs. Browsing adaptation:** Depth policy adjusts recommendation aggressiveness based on stall detection and constraint density.
- **Intent Override handling:** Slot demotion/erasure with aging decay allows graceful recovery when the customer changes preferences mid-conversation.
- **Ambiguity as first-class data:** Instead of forcing a single interpretation, ambiguous customer statements are represented as probability mixtures in the posterior, preserving ranking accuracy.
- **Survival evidence:** Exploits the evaluator's stop-on-first-hit protocol — items shipped on prior turns are guaranteed wrong and excluded from future recommendations.

---

## Disclosure

| Metric | Value |
|---|---|
| **Latency** | ~4–20 ms per session (10-turn session, single-threaded) |
| **Token usage** | 0 prompt tokens, 0 completion tokens |
| **Estimated model cost** | \$0.00 |
| **Network dependencies** | None |
| **Fallback behavior** | Popularity-ordered fallback on any unexpected exception |

The shipped configuration (`src/copilot/flags.py`) sets `llm_extract=False`, making the agent fully offline and deterministic. No network calls, no API keys, and no model costs are incurred.

---

## Limitations

- **Category pool is chosen from the raw opener** — a misspelled or paraphrased category name may lead to a suboptimal pool. Not exercised by current evaluation corpora (correct spelling 99.5% of the time).
- **Depth policy reads only the stall counter**, not the shape of the belief distribution — a sharp posterior and a flat one produce the same recommendation list length.
- **Paraphrase robustness degrades sharply** — one unrecognized turn immediately expands recommendation depth from 1 to 10 with no intermediate state.
- **BM25 route ships disabled** (gain=0.0) because held-out evaluation showed it was slightly negative on this benchmark, despite the route being fully implemented.

---

## Demo

Open `demo/index.html` in any browser to view an interactive replay of multi-turn shopping sessions with the agent's internal reasoning visualized.

---

## License

Competition submission for TikTok TechJam 2026, Track 4.
