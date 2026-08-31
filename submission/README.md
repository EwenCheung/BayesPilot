# BayesPilot — Two-Level Deterministic Offline Probabilistic Agent for Conversational Discovery

**TikTok TechJam 2026 — Track 4: Conversational E-Commerce Search Challenge**

- **Team Name**: Algo Lover
- **Team Members**: Alvin Saw, Daeren Kim, Ewen Cheung

---

## Quick Start

```bash
cd submission && python3 scripts/evaluation/evaluate.py
```

---

## Executive Summary

**BayesPilot** is a deterministic, offline, probabilistic multi-turn shopping agent that locates a hidden target product in a frozen 50,000-item Amazon catalog within 10 turns.

The evaluated BayesPilot runtime is built purely on **NumPy and the Python standard library**. It operates with **zero LLM calls**, **zero neural network weights**, **zero token costs**, and an average inference latency of **7.8–16.9 ms per session**. Optuna is used only to reproduce the offline hyperparameter-fitting process.

```text
TechnicalScore = 0.50 × Hit@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency     = clip((11 − MTTC) / 10, 0, 1)      # MTTC counts a miss as turn 11
```

---

## Benchmark Results

Evaluated with the official unmodified evaluation harness:

| Dataset | Sessions | Hit@10 | MRR | MTTC | **TechnicalScore** | Total Time | Latency / Session | LLM Calls | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `public_set` | 200 | 1.0000 | 0.9942 | 2.19 | **0.9744** | 3.4s | 16.9 ms | 0 | \$0.00 |
| `generated_template_set` | 2,800 | 0.9911 | 0.9783 | 2.64 | **0.9562** | 21.7s | 7.8 ms | 0 | \$0.00 |
| `freeform_set` | 800 | 0.9912 | 0.9801 | 2.62 | **0.9572** | 10.1s | 12.7 ms | 0 | \$0.00 |

- The complete output from running the agent on the public set, including per-session results, is available in [`submission/runs/results.json`](submission/runs/results.json).
- **Official Baseline Comparison**: Official starter agent = `0.1067` · Popularity baseline = `0.7133` · **BayesPilot = 0.9744**

---

## High-Level Architecture

BayesPilot replaces opaque neural architectures with a mathematically grounded, two-level probabilistic discovery pipeline:

```mermaid
---
config:
  layout: fixed
---
flowchart LR
    U["Customer message"] --> P["Cascaded parser<br/>(Templates → Ontology)"]
    P --> S["Session state<br/>(Constraints, decay, overrides)"]
    S --> C["Level 1<br/>Category posterior"]
    C --> I["Level 2<br/>Item log-posterior"]
    I --> D["Expected-utility<br/>depth policy"]
    D --> O["Ranked ASINs<br/>+ Next question"]

    U:::input
    P:::input
    S:::state
    C:::inference
    I:::inference
    D:::inference
    O:::output

    classDef input fill:#dbeafe,stroke:#2563eb,color:#0f172a
    classDef state fill:#ffedd5,stroke:#f97316,color:#0f172a
    classDef inference fill:#ede9fe,stroke:#7c3aed,color:#0f172a
    classDef output fill:#dcfce7,stroke:#16a34a,color:#0f172a
```

---

## Detailed Architecture

```mermaid
flowchart LR
    subgraph S1["1. Deterministic NLP & State Tracking Tier"]
        T{"Exact regex<br/>template match?"}
        U["Customer utterance at turn t"]
        SS["Session State Tracker<br/>• Slot constraints C_t<br/>• Age decay γ = 0.9<br/>• Override demotion factor = 0.35"]
        ON["Ontology Normalizer<br/>(Fuzzy attribute-value extraction:<br/>brand, color, size, specs)"]
    end

    subgraph S2["2. Level 1: Bayesian Category Belief (1,115 Categories)"]
        C1["Category scoring:<br/>s_c(x) = W_c(x) · coverage_c(x)<br/>+ 3.0 · 1[quoted] · W_c(x)"]
        C2["Softmax with prior (T = 2.0, catalog share π_c):<br/>P(c|x) = softmax(s_c(x)/2.0 + 0.25 · log π_c)"]
        C3["Prefix mass pruning (τ = 0.85):<br/>Retain the smallest set where ΣP(c|x) ≥ 0.85<br/>(50,000 items → median 182 candidates)"]
    end

    subgraph S3["3. Level 2: Bounded Item Likelihood Fusion"]
        L1["Multi-source evidence accumulator:<br/>• Exact card match (g_exact = 3.2)<br/>• Soft-card Jaccard (J ≥ 0.34, g_soft = 1.5)<br/>• Lexical token overlap"]
        L2["Bounded log-likelihood floor:<br/>log L_r = log(max(0.02, exp(g_r(s−1))))"]
        L3["Temporal item log-posterior:<br/>log P_t(i) ∼ Σ 0.9^(t−turn)<br/>[log L_main + log L_soft]"]
        L4["Hard rejection masking:<br/>Proven-wrong shipped ASINs → log P(i) = −∞"]
    end

    subgraph S4["4. Decision-Theoretic Recommendation Depth Policy"]
        K1["Dynamic expected-utility maximizer:<br/>k* = argmax [Σ(p_j/j) + (1 − Σp_j) · V]"]
        K2["Continuation value:<br/>V = max(0, 0.75 · d^s − 0.0667)<br/>d ∈ {0.8 understood, 0.2 unreadable}"]
        OUT["Emit top k* ASIN recommendations or ask for evidence<br/>(k* ∈ 0..10, dynamic turn by turn)"]
    end

    U --> T
    T -- No --> ON
    ON --> SS
    SS --> C1
    C1 --> C2
    C2 --> C3
    C3 --> L1
    L1 --> L2
    L2 --> L3
    L3 --> L4
    L4 --> K1
    K1 --> K2
    K2 --> OUT
    T -- "Yes (deterministic fast path)" --> SS

    T:::stage1
    U:::stage1
    SS:::stage1
    ON:::stage1
    C1:::stage2
    C2:::stage2
    C3:::stage2
    L1:::stage3
    L2:::stage3
    L3:::stage3
    L4:::stage3
    K1:::stage4
    K2:::stage4
    OUT:::stage4

    classDef stage1 fill:#dbeafe,stroke:#2563eb,color:#0f172a
    classDef stage2 fill:#ede9fe,stroke:#7c3aed,color:#0f172a
    classDef stage3 fill:#fef3c7,stroke:#d97706,color:#0f172a
    classDef stage4 fill:#dcfce7,stroke:#16a34a,color:#0f172a
```

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
  $$U(k) = \sum_{i=1}^k \frac{p_i}{i} + \left(1 - \sum_{i=1}^k p_i\right) \left(V_{\text{continue}} \cdot \text{hope} - \text{cost}_{\text{turn}}\right)$$
  The agent derives list length $k$ dynamically by choosing the largest $k$ where marginal value $1/k > V$.

### 4. Hyperparameter Tuning via TPE (Tree-structured Parzen Estimator)
* Rather than manual trial-and-error or blind grid search, all 8 hyperparameter constants (evidence gains, category temperature, depth policy thresholds) were fitted offline using **Optuna's Tree-structured Parzen Estimator (TPE)** on the training split with noise-gated bootstrap confirmation.

### 5. Pruned / Rejected Components (Empirical Negative Results)
* **Dense / Semantic Embeddings (BLaIR, SVD)**: Evaluated extensively and deleted. Catalog intent matching is exact and keyword-grounded; semantic embeddings introduced noise and reduced Hit@10.
* **Heavy LLM Tier / LLM Router**: Removed. Evaluator messages follow structured patterns; deterministic ontology extraction achieves higher accuracy at $0$ token cost and $100\times$ lower latency.
* **GBDT / LightGBM Rerankers**: Overhead in runtime and complexity without statistically significant gains over bounded Bayesian fusion.

---

## Limitations

- **Distribution dependence**: The deterministic parser is strongest on the published evaluator's structured customer-message patterns. Novel phrasing, misspellings, or implicit constraints outside the catalog ontology can reduce extraction and ranking quality.
- **No semantic-model fallback in the submitted configuration**: The optional LLM path is disabled, so the agent deliberately trades open-ended language coverage for zero network, credential, quota, and cost risk.
- **Catalog dependence**: Rankings and category statistics are built from the frozen 50,000-product catalog. A materially changed catalog requires restarting the agent so its in-memory indexes are rebuilt.
- **Metadata ambiguity**: Products with sparse or near-identical catalog metadata may remain difficult to distinguish; the depth policy can return several candidates or spend an additional turn clarifying.
- **Evaluation scope**: The reported public and generated-set scores demonstrate performance on the supplied simulator and derived stress sets. They do not guarantee the same performance on unreleased final sessions or unconstrained real-world conversations.
- **Runtime scope**: Measurements use the official sequential evaluator. Concurrent throughput, peak memory, and behavior on substantially larger catalogs were not benchmarked.

---

## Project Structure

```
README.md                               # Project documentation & architecture report
submission/                             # Standalone submission directory
  agent.py                              # Entry point exporting Agent
  requirements.txt                      # NumPy runtime dependency
  results.json                          # Public-set output with per-session results
  data/
    catalog.jsonl                       # Frozen 50,000-product catalog
    public_set.jsonl                    # 200 official public evaluation sessions
    freeform_set/                       # Free-form natural-language dataset
    generated_template_set/             # ASIN-disjoint 60/20/20 template dataset
  demo/
    index.html                          # Interactive multi-turn replay visualizer
  participation_kit/                    # Official competition kit
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
- **Python**: 3.11.9 used for the reported public-set result; Python 3.11+ supported
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
    --offline \
    --output results.json

# Run full evaluation across all benchmark datasets
python3 scripts/evaluation/evaluate.py --all --ci --scenarios --output runs/all_results.json
```

### 3. Reproduce Hyperparameter Tuning

The production agent has no runtime dependency beyond NumPy. Install the pinned Optuna version only
when reproducing the offline TPE fitting process:

```bash
python3 -m pip install optuna==4.9.0
```

#### Quick Smoke Test

Use this small run to verify that dataset loading, evaluation, Optuna, checkpointing, and result
writing all work. With only 200 sessions and 3 trials, it is a pipeline check—not a statistically
meaningful tuning result:

```bash
python3 scripts/training/hyperparameter_tuning.py \
    --dataset data/generated_template_set/train.jsonl \
    --catalog data/catalog.jsonl \
    --n 200 \
    --levels 0,2,3 \
    --trials 3 \
    --seed 0 \
    --resume runs/tuning_smoke.db \
    --output runs/refit_smoke.json
```

#### Full Reproduction Run

```bash
python3 scripts/training/hyperparameter_tuning.py \
    --dataset data/generated_template_set/train.jsonl \
    --catalog data/catalog.jsonl \
    --n 3000 \
    --levels 0,2,3 \
    --trials 60 \
    --seed 0 \
    --resume runs/tuning.db \
    --output runs/refit.json
```

The search jointly fits eight constants, stores resumable trials in `runs/tuning.db`, applies a
paired-bootstrap noise gate, and writes the reproducible result to `runs/refit.json`. It is a
long-running, CPU-only experiment and does not call an LLM or modify the shipped defaults.

---

## Cost, Latency & Resource Disclosures

| Metric | Measured Value |
|---|---|
| **Average Inference Latency** | **7.8 – 16.9 ms** per multi-turn session |
| **Prompt Tokens** | **0** |
| **Completion Tokens** | **0** |
| **Model Cost** | **\$0.00** |
| **GPU / MPS Requirements** | None (Runs purely on standard CPU) |
| **External Network APIs** | None (100% offline & reproducible) |
| **Runtime Fallback** | Safe popularity-ordered fallback on any unexpected exception |
| **Measured Environment** | Python 3.11.9 · Darwin 25.5.0 · arm64 CPU; exact CPU model and RAM were not captured |

---

## Safe Submission Packaging

Commit the frozen submission files first, then build the archive from Git-tracked content only:

```bash
git archive --format=zip --output bayespilot-submission.zip HEAD:submission
```

This excludes ignored local files such as `submission/.env`, `.venv`, caches, and editor metadata.
Never ZIP the working directory directly, and never include real credential values in the archive.

For the frozen final run, first commit the solution and confirm the worktree is clean. Run the
released evaluator without changing the Agent or configuration, retain its per-session
`submission/results.json`, and verify that its provenance reports the submitted commit,
`"dirty": false`, and `"kit_pristine": true` before packaging.

---

## Interactive Demo

An interactive multi-turn session visualizer is provided in `submission/demo/index.html`. Open it in any web browser to explore turn-by-turn belief updates, candidate rankings, category posterior masses, and depth policy decisions.

---

## References & Academic Citations

The mathematical foundations, Bayesian belief models, and decision-theoretic rules in **BayesPilot** are grounded in the following academic research:

### 1. Conversational Decision Policy & Expected Utility
- **Ahsan-Ul-Haque, A. S. M., & Wang, H. (2022)**. *Rethinking Conversational Recommendations: Is Decision Tree All You Need?* In *Proceedings of CIKM '22* (pp. 686–695). (Core motivation for lightweight information-gain decision structures, asking strategies, and early stopping rules in conversational recommendation).
- **Fuhr, N. (2008)**. *A probability ranking principle for interactive information retrieval*. *Information Retrieval*, 11(3), 251–265. (Decision-theoretic basis for ranking interactive actions using their probability of success and associated conversational turn costs).
- **Chapelle, O., Metlzer, D., Zhang, Y., & Grinspan, P. (2009)**. *Expected reciprocal rank for graded relevance*. In *Proceedings of CIKM '09* (pp. 621–630). (Inspiration for rank-sensitive expected utility, where discovery at higher ranks receives substantially greater reward).

### 2. Multi-Evidence Probabilistic Retrieval & Negative Feedback
- **Turtle, H., & Croft, W. B. (1991)**. *Evaluation of an inference network-based retrieval model*. *ACM Transactions on Information Systems (TOIS)*, 9(3), 187–222. (Probabilistic foundation for combining heterogeneous retrieval evidence—exact match, normalized attributes, lexical overlap, and SoftCard Jaccard—into a unified relevance belief).
- **Bi, K., Ai, Q., Zhang, Y., & Croft, W. B. (2019)**. *Conversational Product Search Based on Negative Feedback*. In *Proceedings of CIKM '19* (pp. 359–368). (Theoretical precedent for incorporating implicit negative feedback on unselected products directly into subsequent conversational product search).

### 3. Hyperparameter Optimization & Baseline Discipline
- **Bergstra, J., Bardenet, R., Bengio, Y., & Kégl, B. (2011)**. *Algorithms for hyper-parameter optimization*. In *Advances in Neural Information Processing Systems (NeurIPS 24)*. (Core formulation of the Tree-structured Parzen Estimator (TPE) algorithm used for joint offline constant tuning).
- **Akiba, T., Sano, S., Yanase, T., Ohta, T., & Koyama, M. (2019)**. *Optuna: A next-generation hyperparameter optimization framework*. In *Proceedings of KDD '19* (pp. 2623–2631). (Practical framework utilized for executing the offline Bayesian tuning pipeline).
- **Dacrema, M. F., Cremonesi, P., & Jannach, D. (2019)**. *Are we really making much progress? A worrying analysis of recent neural recommendation approaches*. In *Proceedings of RecSys '19* (pp. 101–109). (Empirical motivation for rigorous evaluation of simple, well-tuned non-neural baselines before introducing unnecessary neural complexity).

---

## License

Competition submission for TikTok TechJam 2026, Track 4.
