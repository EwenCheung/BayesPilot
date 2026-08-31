# Shopping Copilot — TikTok TechJam 2026, Track 4

A multi-turn conversational shopping agent that locates a hidden target product in a frozen 50,000-item Amazon Clothing, Shoes & Jewelry catalog within 10 turns. The agent is fully deterministic, running on NumPy alone with **zero LLM API calls**, **zero tokens**, and **\$0 model cost**.

---

## Results

| Dataset | Sessions | Hit@10 | MRR | MTTC | **TechnicalScore** | Total Time | Latency / Session |
|---|---:|---:|---:|---:|---:|---:|---:|
| `public_set.jsonl` | 200 | 1.0000 | 0.9942 | 2.19 | **0.9744** | 3.4s | 16.9 ms |
| `resplit_60_20_20/test` | 2,800 | 0.9911 | 0.9783 | 2.64 | **0.9562** | 21.7s | 7.8 ms |
| `freeform_v1/test` | 800 | 0.9912 | 0.9801 | 2.62 | **0.9572** | 10.1s | 12.7 ms |

*Evaluated with the official evaluation harness. Zero LLM API calls, 0 tokens, \$0 cost.*

**Reference points:** Official starter agent = `0.1067` · Popularity-only baseline = `0.7133`

---

## Setup Instructions

### Prerequisites

- **Python**: 3.11+ (tested with 3.11.9)
- **OS**: macOS / Linux / Windows

### 1. Environment Setup

```bash
cd submission

python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> **Note:** The only runtime requirement is `numpy`. All datasets and the 50,000-product catalog (`data/catalog.jsonl`) are already included inside `submission/data/`.

### 2. Environment Variables (Optional)

The agent runs offline by default (`llm_extract=False`). Environment variables are only needed if testing the optional LLM extraction tier.

```bash
cp .env.example .env
# Edit .env only if experimenting with the optional LLM tier
```

| Variable | Description | Required |
|---|---|---|
| `SOCLAAS_API_KEY` | SoCLaaS API key for LLM tier | No (LLM tier disabled) |
| `SOCLAAS_BASE_URL` | SoCLaaS endpoint URL | No |
| `HF_TOKEN` | HuggingFace token | No |

### 3. Run Evaluation

From the `submission/` directory:

```bash
# Evaluate on public_set.jsonl
python3 scripts/evaluation/evaluate.py \
    --agent agent:Agent \
    --catalog data/catalog.jsonl \
    --dataset data/public_set.jsonl \
    --offline

# Evaluate on all test datasets with bootstrap confidence intervals
python3 scripts/evaluation/evaluate.py --all --ci --scenarios
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

## Repository Structure

```
README.md                       # Project documentation & evaluation instructions
submission/                     # Self-contained submission bundle
  agent.py                      # Submission entry point (from agent import Agent)
  requirements.txt              # numpy only
  .env.example                  # Environment variable reference
  data/
    catalog.jsonl               # Frozen 50,000-product catalog
    public_set.jsonl            # 200 official public evaluation sessions
    combine/                    # Combined training dataset (9,600 train + 3,200 val)
    freeform_v1/                # Free-form natural language sessions
    resplit_60_20_20/           # ASIN-disjoint 60/20/20 split (14,000 sessions)
  demo/
    index.html                  # Interactive multi-turn session replay visualizer
  participant_kit/              # Official competition kit
    evaluator/                  # Official local evaluator engine
    starter/                    # Official starter agent baseline
    docs/                       # Competition specs and API contracts
    data/                       # Official public evaluation set
  scripts/
    evaluation/evaluate.py      # Benchmark evaluation CLI
    training/hyperparameter_tuning.py   # Bayesian hyperparameter fitting (Optuna)
    earlyhit.py                 # EarlyHit@k curve analysis
    llm_tier.py                 # LLM tier impact measurement
  src/
    simulator.py                # Customer simulator
    copilot/                    # Core agent and hyperparameter flags
    retrieve/                   # Category posterior & catalog index
    rank/                       # Bayesian belief scoring & depth policy
    state/                      # Conversational state & aging decay
    understand/                 # NLU parsing cascade & entity verification
    eval/                       # Evaluation harness & diagnostic tools
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
| **Latency** | ~4–20 ms per session (full multi-turn session, single-threaded) |
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

## Interactive Demo

Open `submission/demo/index.html` in any web browser to view an interactive multi-turn session replay with the agent's internal belief distribution, candidate rankings, and turn-by-turn reasoning visualizer.

---

## License

Competition submission for TikTok TechJam 2026, Track 4.
