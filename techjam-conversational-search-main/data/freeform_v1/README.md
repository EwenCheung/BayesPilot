# Free-form language corpus v1

This corpus contains `1,200` train, `400` validation, and `800` sealed-test **sessions**. Scenario
ratios match the released data: 40% buying, 40% browsing, 15% intent override, and 5% boundary.
Targets remain disjoint because every derived split samples only from its corresponding leakage-safe
`resplit_60_20_20` source split.

The 800-session test contains 800 unique target products across 298 coarse catalog categories. Train
contains 1,200 unique targets across 348 categories; validation contains 400 across 212 categories.

Every row stores a non-template first-turn message and a deterministic language profile. During a
score run, `src.eval.freeform.FreeFormDatasetAgent` applies that profile to every later dynamically
generated customer reply too. Slang, shorthand, casual punctuation, filler-word typos, reordered
attribute phrases, and occasional emoji are included. Constraint values are never randomly deleted
or invented.

The dataset does not replace or modify the official evaluator. Run:

```bash
# Development
python scripts/evaluate_freeform.py --mode offline --splits validation

# Final use only
python scripts/evaluate_freeform.py --mode always-router --splits test \
  --acknowledge-sealed-test --output runs/freeform_test_final.json
```

Both commands import and execute the unchanged `evaluator/local_evaluator.py`. The runner rejects the
score unless that file's SHA-256 remains
`79a5ea06f9a1b8c5036f30efa85dc1f36b8f6b06eb8feb8f545dfa767bc45564`.
