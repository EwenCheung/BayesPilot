# Train/dev resplit and LLM interpretation results

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

## Rejected LLM question-selection scope

An earlier online experiment used the LLM only to select the next `ask_attribute`. Its input was the
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

## Retained gated intent-operation interpreter

The first experiment used an always-review LLM. The retained `template-llm` path applies the fixed
evaluator grammar first and makes zero model calls when it matches. For unknown wording, one
context-aware model call proposes the message kind, the shopper's category phrase, and typed
add/remove/replace operations. Deterministic code retrieves and verifies those meanings against the
real catalog, applies one atomic state transaction, and renders a fixed template only when the
interpretation is verified. A vague phrase can preserve multiple category hypotheses.

An ambiguous value is not forced into one label. For example, `poly` can remain a single probability
mixture over `polyester`, `polyurethane`, `polycarbonate`, and `polymer`. These hypotheses receive
soft attribute evidence and can never receive the exact-match gain. This costs some pilot score
relative to unsafe forced canonicalization, but prevents silent semantic corruption.

The clean-path control was rerun over all 2,800 validation sessions after the implementation and
remained exactly **0.927023 with zero LLM calls**. On identical stratified 20-session validation
pilots:

| language condition | mode | score | Hit@10 | MRR | model interactions | live tokens | elapsed |
|---|---|---:|---:|---:|---:|---:|---:|
| clean | deterministic | **0.940500** | 1.000 | 0.941667 | 0 | 0 | 1.27 s |
| clean | always-review LLM | **0.940500** | 1.000 | 0.941667 | 71 (25 cached) | 21,360 | 59.88 s |
| clean | gated template restoration | **0.940500** | 1.000 | 0.941667 | 0 | 0 | 1.33 s |
| strong paraphrase | deterministic | **0.436750** | 0.500 | 0.372500 | 0 | 0 | 5.69 s |
| strong paraphrase | always-review LLM | **0.520143** | 0.600 | 0.437143 | 145 (53 cached) | 47,620 | 118.52 s |
| strong paraphrase | **retained one-call ambiguity-safe interpreter** | **0.565750** | 0.600 | 0.562500 | 56 live + 59 cache hits | 59,202 | 81.65 s |
| strong paraphrase | unsafe forced-canonical prototype (removed) | **0.605875** | 0.650 | 0.606250 | 137 (10 cached) | 67,967 | 138.48 s |

The retained path gained `+0.129000` over deterministic and `+0.045607` over always-review under
strong paraphrasing, while clean templates remained identical with zero calls. Its bootstrap interval
(`0.3575–0.7700`) remains wide, so this is a promising robustness result rather than proof of a
population-wide gain. It deliberately gives up `0.040125` versus the removed forced-canonical
prototype because that prototype could turn an underspecified phrase such as `poly` into a wrong hard
constraint. The current path needs at most one intent call per unknown customer message; no LLM
reranker or question selector is used. Test and public were not read or evaluated during this
experiment.

The complete flow and the retained/changed/removed components are documented in
[FINAL-ARCHITECTURE.md](FINAL-ARCHITECTURE.md).

## Always-on one-call router experiment

Checkpoint `c816bfd` freezes the ambiguity-safe gated interpreter and all results above. The current
working experiment removes the R3 LLM feature toggle: every customer message attempts one model call
that returns `route=deterministic|hybrid`, lossless normalized text, message kind, category surface,
and typed operations. A deterministic route ignores proposed operations and runs the fixed parser. A
hybrid route reuses the same response for catalog verification and the atomic state transaction.

The first 8-session clean validation execution after this change reported `0.938750`, but all 25
router attempts failed because `SOCLAAS_BASE_URL` and `SOCLAAS_API_KEY` were absent. The score therefore
measures deterministic failure fallback, **not** the always-on LLM design, and is not eligible for
architecture selection. A valid online clean/paraphrase comparison remains pending. Test and public
were subsequently evaluated only at the user's explicit request with the locked offline evaluator:
test reproduced `0.933979` and public reproduced `0.973075`, both with zero tokens. Those holdout
numbers validate deterministic fallback only and must not be used to tune the router.

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
