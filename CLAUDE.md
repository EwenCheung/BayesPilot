# Project checkpoints and operating rules

## Current rollback checkpoint

- Commit: `c816bfd` (`checkpoint: safe adaptive intent interpretation`)
- Verified at checkpoint: `152 passed`
- Clean validation: `0.927023` with the deterministic default.
- Strong-paraphrase 20-session validation pilot: `0.436750` deterministic and `0.565750`
  with the ambiguity-safe LLM interpreter.
- Restore or compare this checkpoint with `git show c816bfd` or a new branch based on `c816bfd`.
  Do not use destructive reset commands in a dirty worktree.

The earlier data-protocol checkpoint is `8260052` (`checkpoint: lock train validation evaluation
protocol`).

## Data boundary

- Fit on `resplit_60_20_20/train.jsonl` only.
- Select experiments on `validation.jsonl` only.
- Do not use `test.jsonl` or `public_set.jsonl` for fitting, prompt design, architecture selection,
  augmentation, or routine experiments.

## Active experiment after the checkpoint

Build one submitted R3 agent with an always-available LLM router. Every customer message receives one
LLM routing/interpretation call. The response chooses `deterministic` or `hybrid`; the hybrid path must
reuse that same response for normalized text and typed operations rather than making another intent
call. Deterministic validation remains authoritative for state changes, catalog values, candidate
generation, and ranking.

Implementation status: the router experiment is present in the working tree and its offline failure
fallback passes `154` tests. It does not yet have a valid online score. The first 8-session attempt had
25 failed router calls because `SOCLAAS_BASE_URL` and `SOCLAAS_API_KEY` were absent; its `0.938750`
score is deterministic fallback only and must not be treated as evidence for the experiment.
