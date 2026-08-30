# Locked data and evaluation protocol

Effective 2026-08-30, all new R3 fitting follows this protocol:

1. `resplit_60_20_20/train.jsonl` is the only fitting dataset.
2. At most the three strongest declared training candidates plus the neutral baseline advance to
   `validation.jsonl` for selection.
3. `test.jsonl` is not addressable by the fitting program. It is evaluated only after the selected
   configuration is written to `runs/r3_resplit_locked.json`.
4. `public_set.jsonl` is not addressable by the fitting program. It is read by the final evaluator
   only with the explicit `--acknowledge-golden-final` flag.
5. Train, validation and test are disjoint by both sample ID and target ASIN. Dataset hashes are
   recorded in the split manifest and the locked configuration.
6. At the historical locked evaluation, LLM interpretation was disabled. The post-checkpoint
   always-on-router experiment changes runtime architecture only and must earn selection on validation
   before any new final holdout evaluation. LLM attribute selection remains removed from R3.

The scenario distribution is exactly preserved in every split:

| split | buying | browsing | intent override | boundary |
|---|---:|---:|---:|---:|
| train (8,400) | 3,360 (40%) | 3,360 (40%) | 1,260 (15%) | 420 (5%) |
| validation (2,800) | 1,120 (40%) | 1,120 (40%) | 420 (15%) | 140 (5%) |
| test (2,800) | 1,120 (40%) | 1,120 (40%) | 420 (15%) | 140 (5%) |

The shared development harness now defaults to resplit train. Legacy sweeps, category probes,
ablation scripts, LLM-tier experiments, and parameter-fitting scripts no longer inherit the public
dataset. Public remains reachable only through an explicit final-evaluation acknowledgement.

The selected clean-path change is `prior_weight=0.10`. It scored `0.924447` on train and `0.927023`
on validation, versus `0.920248` and `0.923199` for the legacy `0.18` value. The validation gain
(`+0.003824`) exceeded the predeclared minimum improvement of `0.002`.

## Locked final results

At configuration lock, after 129 passing tests, the final evaluator ran test first and public second.
The current regression suite contains 153 passing tests; the holdouts were not rerun for the later
intent-router work:

| split | rows | Hit@10 | MRR | MTTC | TechnicalScore | 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| test | 2,800 | 0.981429 | 0.935120 | 2.863571 | **0.933979** | 0.9284–0.9394 |
| public golden | 200 | 1.000000 | 0.982917 | 2.090000 | **0.973075** | 0.9657–0.9794 |

Both runs used zero LLM tokens. The locked test score improved by `0.003929` over the legacy
`prior_weight=0.18` test result (`0.930050`); the public score was exactly unchanged.

At the user's explicit request, the current always-on-router working tree was run again through this
locked offline evaluator. It reproduced test `0.933979` and public `0.973075` with zero tokens and was
written to `runs/r3_current_router_fallback_final.json`. This validates failure fallback, not live LLM
routing, and the repeated holdout results are not eligible for further tuning.

Historical limitation: the public 200 was used during earlier development, so it cannot be made
statistically pristine retroactively. It is frozen as a golden regression set from this protocol
forward; its score must not be used for further parameter or architecture selection.

Reproduce fitting and the one-way final evaluation with:

```bash
python scripts/fit_resplit.py
pytest -q
python scripts/evaluate_locked.py --acknowledge-golden-final
```
