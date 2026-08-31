# BayesPilot — Two-Level Deterministic Offline Probabilistic Agent for Conversational Discovery

**TikTok TechJam 2026 — Track 4: Conversational E-Commerce Search Challenge**

- **Team Name**: Algo Lover
- **Team Members**: Alvin Saw, Daeren Kim, Ewen Cheung

---

## Executive Summary

**BayesPilot** is a deterministic, offline, probabilistic multi-turn shopping agent that locates a hidden target product in a frozen 50,000-item Amazon catalog within 10 turns.

Built purely on **NumPy and the Python standard library**, BayesPilot operates with **zero LLM calls**, **zero neural network weights**, **zero token costs**, and an ultra-low inference latency of **~7–17 ms per session**.

```text
TechnicalScore = 0.50 × Hit@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency     = clip((11 − MTTC) / 10, 0, 1)      # MTTC counts a miss as turn 11
```

---

## Benchmark Results

Evaluated with the official unmodified evaluation harness:

| Dataset | Sessions | Hit@10 | MRR | MTTC | **TechnicalScore** | Total Time | Latency / Session | LLM Calls | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `public_set.jsonl` | 200 | 1.0000 | 0.9942 | 2.19 | **0.9744** | 3.4s | 16.9 ms | 0 | \$0.00 |
| `resplit_60_20_20/test` | 2,800 | 0.9911 | 0.9783 | 2.64 | **0.9562** | 21.7s | 7.8 ms | 0 | \$0.00 |
| `freeform_v1/test` | 800 | 0.9912 | 0.9801 | 2.62 | **0.9572** | 10.1s | 12.7 ms | 0 | \$0.00 |

- **Official Baseline Comparison**: Official starter agent = `0.1067` · Popularity baseline = `0.7133` · **BayesPilot = 0.9744**

---

## High-Level Architecture

BayesPilot replaces opaque neural architectures with a mathematically grounded, two-level probabilistic discovery pipeline:

```
                  Customer Message
                         │
                         ▼
       ┌────────────────────────────────────┐
       │   1. Deterministic NLU & Ontology   │
       │   Template Matching → Catalog Term  │
       │   Verification (Zero LLM overhead)  │
       └─────────────────┬──────────────────┘
                         │
                         ▼
       ┌────────────────────────────────────┐
       │   2. Level 1: Category Posterior   │
       │   P(category | opener) over 1,115   │
       │   shelves (50K → median 182 items)  │
       └─────────────────┬──────────────────┘
                         │
                         ▼
       ┌────────────────────────────────────┐
       │   3. Level 2: Bounded Item Fusion   │
       │   Log-posterior scoring: card,      │
       │   specs, tokens & SoftCard Jaccard  │
       │   with lower-bound L_min = 0.02     │
       └─────────────────┬──────────────────┘
                         │
                         ▼
       ┌────────────────────────────────────┐
       │   4. Survival Evidence & Decay     │
       │   Prior shipped items set to -∞;   │
       │   Aging decay handles overrides    │
       └─────────────────┬──────────────────┘
                         │
                         ▼
       ┌────────────────────────────────────┐
       │   5. Optimal K (Expected Utility)   │
       │   Dynamic depth derived via U(k):  │
       │   (Turn 2, Rank 1) > (Turn 1, Rank 2)│
       └────────────────────────────────────┘
```

---

## Detailed Architecture

### 1. Level 1 — Category Posterior (Search Space Reduction)
* **Inspiration**: Narrow down product candidates using category as an early high-precision signal, slashing the search space before performing fine-grained item scoring.
* **Mechanism**: Computes a posterior distribution $P(c \mid \text{opener})$ over 1,115 product categories using category-IDF weighting, stemmed token overlap, and verbatim quote bonuses ($\text{bonus} = 3.0$).
* **Tau-Mass Pooling**: Selects the minimal set of categories covering **85% of posterior mass** ($\tau = 0.85$), pruning 50,000 catalog items down to a **median of 182 candidates** with 100% target recall on `public_set`.

### 2. Level 2 — Bounded Item Likelihood Fusion
* **Bounded Likelihood ($L_{\min} = 0.02$)**: Bounding evidence terms from below prevents soft mismatches from erroneously eliminating the true target.
* **Multi-Channel Evidence**:
  $$\log P(\text{item}) = \sum_t w_t \cdot \log L(e_t \mid \text{item})$$
  - Exact constraint strings (gain: 3.2)
  - Normalized attribute-value pairs (gain: 1.5)
  - Token overlap (gain: 0.9)
  - SoftCard Jaccard token matching against product intent-card strings (gain: 1.5, floor: 0.34)
* **Aging Decay & Intent Override**: Older preferences decay geometrically over turns, allowing changed customer constraints (Turn 3/4 Intent Overrides) to seamlessly override earlier statements.
* **Survival Evidence**: Evaluator stops immediately upon a target hit. A surviving session proves all previously recommended items are incorrect, setting their log-posterior to $-\infty$.

### 3. Optimal K — Expected Utility Formula $U(k)$
* **Mathematical Insight**: From the Technical Score formula:
  $$\text{Score}(\text{Turn 2, Rank 1}) = 0.50(1) + 0.30(1) + 0.20\left(\frac{11 - 2}{10}\right) = 0.980$$
  $$\text{Score}(\text{Turn 1, Rank 2}) = 0.50(1) + 0.30(0.5) + 0.20\left(\frac{11 - 1}{10}\right) = 0.850$$
  $$\implies (\text{Turn 2, Rank 1}) > (\text{Turn 1, Rank 2})$$
  **MRR weight (0.30) outweighs early turn speed (0.20).** Prematurely guessing with low confidence damages MRR more than asking another clarifying question.
* **Expected Utility Equation**:
  $$U(k) = \sum_{i=1}^k \frac{p_i}{i} + \left(1 - \sum_{i=1}^k p_i\right) \left(V_{\text{continue}} \cdot \text{hope} - \text{turn\_cost}\right)$$
  The agent derives list length $k$ dynamically by choosing the largest $k$ where marginal value $1/k > V$.

### 4. Hyperparameter Tuning via TPE (Tree-structured Parzen Estimator)
* Rather than manual trial-and-error or blind grid search, all 8 hyperparameter constants (evidence gains, category temperature, depth policy thresholds) were fitted offline using **Optuna's Tree-structured Parzen Estimator (TPE)** on the training split with noise-gated bootstrap confirmation.

### 5. Pruned / Rejected Components (Empirical Negative Results)
* **Dense / Semantic Embeddings (BLaIR, SVD)**: Evaluated extensively and deleted. Catalog intent matching is exact and keyword-grounded; semantic embeddings introduced noise and reduced Hit@10.
* **Heavy LLM Tier / LLM Router**: Removed. Evaluator messages follow structured patterns; deterministic ontology extraction achieves higher accuracy at $0$ token cost and $100\times$ lower latency.
* **GBDT / LightGBM Rerankers**: Overhead in runtime and complexity without statistically significant gains over bounded Bayesian fusion.

---

## Project Structure

```
README.md                               # Project documentation & architecture report
submission/                             # Standalone submission directory
  agent.py                              # Entry point exporting Agent
  requirements.txt                      # numpy only
  evaluation_results.json               # Full evaluation logs & timings
  data/
    catalog.jsonl                       # Frozen 50,000-product catalog
    public_set.jsonl                    # 200 official public evaluation sessions
    combine/                            # 12.8K combined training sessions
    freeform_v1/                        # Free-form natural language split
    resplit_60_20_20/                   # ASIN-disjoint 60/20/20 split
  demo/
    index.html                          # Interactive multi-turn replay visualizer
  participant_kit/                      # Official competition kit
    evaluator/local_evaluator.py        # Official local evaluator engine
    starter/agent.py                    # Starter agent baseline
    docs/                               # Specification & API contracts
    data/public_set.jsonl               # Official dataset copy
  scripts/
    evaluation/evaluate.py              # Multi-dataset evaluation CLI
    training/hyperparameter_tuning.py   # Bayesian hyperparameter fitting (Optuna)
    earlyhit.py                         # EarlyHit@k curve analysis
    llm_tier.py                         # Diagnostic tool
  src/
    simulator.py                        # Customer simulator
    copilot/
      agent.py                          # Core Agent class (reset, respond, fallback)
      flags.py                          # All submission hyperparameters & defaults
    retrieve/
      bm25.py                           # Okapi BM25 implementation (ships disabled)
      category.py                       # Level 1: Category posterior distribution
      index.py                          # 50K catalog vocabulary index
    rank/
      belief.py                         # Level 2: Item log-posterior & depth policy
      likelihood.py                     # Bounded log-likelihood evidence fusion
      softcard.py                       # Paraphrase-tolerant SoftCard matching
    state/
      session.py                        # Conversational state & aging decay
    understand/
      attributes.py                     # Attribute extraction from prose
      extract.py                        # Attribute extraction helpers
      intent.py                         # Intent pipeline & catalog resolution
      parse.py                          # Deterministic ontology parsing cascade
      tokens.py                         # Numeric-preserving tokenizer
    eval/
      harness.py                        # Non-invasive evaluator harness
      stress.py                         # Paraphrase stress engine
      ablations.py                      # Ablation test suite
      compare.py                        # TechnicalScore bootstrap CI calculator
      datasets.py                       # Dataset loader utilities
```

---

## Setup & Reproduction Instructions

### Prerequisites
- **Python**: 3.11+
- **OS**: macOS / Linux / Windows

### 1. Environment Setup

```bash
cd submission

python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Run Evaluation

```bash
# Evaluate on public_set.jsonl (200 sessions)
python3 scripts/evaluation/evaluate.py \
    --agent agent:Agent \
    --catalog data/catalog.jsonl \
    --dataset data/public_set.jsonl \
    --offline

# Run full evaluation across all benchmark datasets
python3 scripts/evaluation/evaluate.py --all --ci --scenarios
```

---

## Cost, Latency & Resource Disclosures

| Metric | Measured Value |
|---|---|
| **Inference Latency** | **7.8 – 16.9 ms** per multi-turn session |
| **Prompt Tokens** | **0** |
| **Completion Tokens** | **0** |
| **Model Cost** | **\$0.00** |
| **GPU / MPS Requirements** | None (Runs purely on standard CPU) |
| **External Network APIs** | None (100% offline & reproducible) |
| **Runtime Fallback** | Safe popularity-ordered fallback on any unexpected exception |

---

## Interactive Demo

An interactive multi-turn session visualizer is provided in `submission/demo/index.html`. Open it in any web browser to explore turn-by-turn belief updates, candidate rankings, category posterior masses, and depth policy decisions.

---

## License

Competition submission for TikTok TechJam 2026, Track 4.
