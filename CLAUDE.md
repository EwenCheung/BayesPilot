# Checkpoints

| commit/state | method | score | status |
|---|---|---|---|
| `8260052` | Locked deterministic R3; train fit, validation select | validation `0.927023`; test `0.933979`; public `0.973075` | Protocol checkpoint; public historically contaminated |
| `c816bfd` | Gated ambiguity-safe LLM for unknown wording; deterministic ranker | clean validation `0.927023`; paraphrase-20 `0.565750` vs deterministic `0.436750` | Safe rollback; `152` tests |
| `05fb5c2` | Checkpoint documentation only | no new score | Documentation checkpoint |
| working tree | Always-on one-call LLM router: `deterministic` or `hybrid` | no valid online LLM score; deterministic fallback test `0.933979`, public `0.973075` | Credentials missing; `154` tests |

Fit on train only; select on validation only. Never tune on test or `public_set.jsonl`.
