# Train/dev resplit and LLM question-writer result

## Data split

`data/train.jsonl` (12,000) and `data/dev.jsonl` (2,000) were merged and deterministically split
60/20/20 by `scripts/split_train_dev.py`. The original files were not modified.

| split | rows | buying | browsing | intent override | boundary |
|---|---:|---:|---:|---:|---:|
| train | 8,400 | 3,360 | 3,360 | 1,260 | 420 |
| validation | 2,800 | 1,120 | 1,120 | 420 | 140 |
| test | 2,800 | 1,120 | 1,120 | 420 | 140 |

The manifest verifies zero overlap by sample ID and target ASIN and locks every source/output SHA-256.

## Deterministic search result

| split | Hit@10 | MRR | MTTC | TechnicalScore | 95% CI |
|---|---:|---:|---:|---:|---:|
| train | 0.971190 | 0.918128 | 3.039286 | **0.920248** | 0.9166–0.9240 |
| validation | 0.972857 | 0.921948 | 2.990714 | **0.923199** | 0.9168–0.9296 |
| test | 0.977500 | 0.931071 | 2.901071 | **0.930050** | 0.9241–0.9362 |

These independent results supersede the contaminated public-200 `0.973075` as a generalisation
estimate.

### Locked refit

The clean-path constants were subsequently refit using train only and selected using validation only.
`prior_weight=0.10` was selected over the legacy `0.18` value. After configuration lock, the final
test score was **0.933979** (95% CI `0.9284–0.9394`) and the public golden regression score remained
**0.973075**. See [the locked protocol](DATA-PROTOCOL.md).

## LLM scope

The online architecture uses the LLM only to select the next `ask_attribute`. Its input is the
accumulated agent state: category, known slots, missing attributes, exhausted attributes, intent route,
override status, profile, turn, and previous question. It never sees products, candidates, BM25 or
semantic scores, or ranks. BM25/semantic/posterior retrieval and ranking remain authoritative, and a
deterministic template turns the selected attribute into matching customer-facing text.

On an eight-session stratified training pilot:

| mode | score | calls | tokens | elapsed |
|---|---:|---:|---:|---:|
| deterministic | **0.9575** | 0 | 0 | 0.24 s |
| LLM state-only attribute selector | **0.8975** | 36 | 18,306 | 57.84 s |

The selector asked sensible fields but lost score because a specific field often has no hidden answer
in the simulator, while wildcard `other` always reveals the next available evidence. Invalid, known,
or exhausted model choices fall back to the deterministic policy.

An earlier experiment allowing the LLM to choose `ask_attribute` scored `0.591875` on the same eight
rows. Specific attributes reveal only matching constraints and often return nothing, while the
simulator's wildcard `other` returns the next two available constraints regardless of type. LLM
attribute selection was therefore rejected.

A subsequent deterministic candidate-information policy was restricted to concrete questions
(`material`, `size`, `color`, `use_case`/season, `style`, `feature`). On the full validation split it
scored **0.889028**, down from **0.923199** with wildcard `other`; boundary performance was hit hardest.
It remains available through `R3_FLAGS=critical_questions` for real-UX evaluation, but is not the
competition-score default.

## Augmentation verdict

Do not downsample to equal scenario counts. Train, validation, and test intentionally share the same
40% buying / 40% browsing / 15% override / 5% boundary distribution.

Targeted training-only augmentation is justified for conversational robustness:

- paraphrases, colloquial wording, typos, negation, and multiple constraints in one message;
- boundary refusals, uncertainty, “use your judgment”, and no-preference variants;
- override timing and wording variants, partial replacements, and explicit contradictions;
- budget, fit, compatibility, occasion, and recipient phrasings from the critical-question guide.

Never augment validation or test. Preserve the natural evaluation distribution and report both the
overall score and the macro/worst-scenario score.
