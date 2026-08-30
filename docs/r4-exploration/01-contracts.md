# R4 — contracts

Frozen seams. Changing anything here means amending this file first
([00-r4-spec.md](00-r4-spec.md) §9).

---

## 1. The kit boundary — unchanged, non-negotiable

```python
class Agent:
    def __init__(self, catalog_path="data/catalog.jsonl"): ...   # ⚠️ POSITIONAL, undocumented
    def respond(self, session_id, user_message, turn, top_k) -> dict: ...
    def reset(self, session_id, user_profile) -> None: ...
```

⚠️ The evaluator constructs `Agent(catalog_path)` positionally. Getting this wrong is a hard crash at
startup, not a low score.

⚠️ `usage` is summed by the evaluator **across turns**. Return per-turn deltas, never running totals.

---

## 2. 🔒 R4 inherits from R3, and that is the one exception to the isolation rule

R1, R2 and R3 are isolated from each other by two AST tests, because a road that calls into another
road is not an independent measurement. **R4 is different by construction:** it is R3's posterior with
a calibrated head, and its central acceptance test ([R4-A1](02-acceptance.md)) is that it reproduces
R3 exactly when the new parts are disabled.

So:

```python
# ALLOWED, and required
from src.r3.belief     import Belief
from src.r3.index      import Index
from src.r3.likelihood import terms
from src.r3.category   import CategoryBelief

# FORBIDDEN — the isolation rule still binds for R1 and R2
from src.r1 import *      # ✗
from src.r2 import *      # ✗
```

`tests/test_imports.py` is extended with an R4 case rather than relaxed: **`src/r4/` may import
`src/r3/`, and nothing else under `src/r*/`.** If R4 needs an R1 or R2 mechanism, it is lifted through
R3 the way D23 lifted the others, or it is copied with its provenance recorded in
[03-decisions.md](03-decisions.md).

R4 owns exactly three new modules:

| Module | Owns |
|---|---|
| `src/r4/features.py` | the runtime feature vector of [00-r4-spec.md §4](00-r4-spec.md), incl. the selectivity table |
| `src/r4/calibrate.py` | isotonic fit, `p̂ = g(features)`, reliability curve, ECE |
| `src/r4/agent.py` | the `Agent` the evaluator constructs — R3's loop with the calibrated head and exhaustion rule |
| `src/r4/flags.py` | every new mechanism behind a switch, R3's flags passed through |

---

## 3. 🔒 The offline/runtime barrier

This is the contract that makes the road's headline metric trustworthy, and it is enforced by a test
rather than by care.

```python
# src/r4/instrument.py — OFFLINE ONLY
@dataclass
class TurnTrace:
    turn: int
    internal_ranking: list[str]   # the agent's full internal order, BEFORE the ship/hold decision
    shipped: list[str] | None     # what actually went to the evaluator, None if it held
    features: dict[str, float]    # the calibrator's inputs, for the reliability curve
```

**Rules:**

1. `TurnTrace` is written by the harness, never read by the agent. `src/r4/agent.py` must not import
   `instrument`.
2. `FirstHit@k` and `EarlyHit@k(T)` are computed from `internal_ranking`, **never from `shipped`**.
   Computed from shipped lists they are definitionally MTTC and carry no new information
   ([00-r4-spec.md §2.1](00-r4-spec.md) — the evaluator breaks on first hit, so a shipped target's
   rank never evolves).
3. No ground-truth ASIN may enter the agent's process. `tests/test_no_leakage.py` asserts the target
   ASIN is absent from every argument reaching `Agent.respond`, and that `src/r4/` contains no import
   of `holdout`, `instrument`, or the dataset path.

⚠️ The internal ranking must be captured **before** the ship/hold decision, not after. Capturing it
after means a held turn records nothing and the EarlyHit curve silently degenerates into MTTC again.

---

## 4. 🔒 Fit on `train.jsonl`. Report on `dev` and `public`. Never the reverse.

```
train.jsonl   12,000 sessions   ← FIT HERE. Constants, thresholds, calibrators, everything.
dev.jsonl      2,000 sessions   ← test only. Read to report, never to choose.
public_set       200 sessions   ← test only. The official set; read least of all.
```

Target ASINs are **mutually disjoint across all three** and all three carry the identical 40/40/15/5
scenario mix, so a number moves between them only because the agent generalised.
`src/eval/datasets.py` owns the paths; `tests/test_datasets.py` enforces the contract, including an
AST check that no fitting code so much as *names* an evaluation set.

⚠️ **`devsplit.py` is deleted.** It carved `dev.jsonl` into 1200 train / 800 test and fitted on the
first half. Splitting an evaluation set does not make it a training set — it spends it either way.

⚠️ **A parameter chosen while looking at `dev` or `public` is contaminated even if it is never
committed**, because the choice was informed. Two such values were caught and re-derived on train;
see [03-decisions.md D11](03-decisions.md#d11).

---

## 5. 🔒 Recommendation depth

The agent **always returns 10 recommendations**, except where it deliberately holds and returns an
empty list.

Truncation is measured-negative ([03-decisions.md D4](03-decisions.md#d4)) and exists solely because
PROBLEM.md §4.3 names *"custom dynamic truncation"* as in scope. It ships **behind a default-off flag**
(`truncate=0`) so the negative result reproduces, and the write-up reports the cost rather than
omitting the requirement.

```python
flags.truncate: int = 0    # 0 = always 10.  >0 = cap depth. DEFAULT OFF, measured negative.
```

---

## 6. 🔒 Reproducibility

Every reported R4 number is produced under:

```bash
R3_OFFLINE=1 PYTHONHASHSEED=0 python3 -m src.eval.race --roads r4
```

- `R3_OFFLINE=1` — a warm `.cache/llm` silently turns the offline path into the LLM path with zero
  network calls. This bug was caught once already (D22) and every headline number since is measured
  under the flag.
- `PYTHONHASHSEED=0` — set iteration order drifted scores in both earlier roads.
- Kit byte-identical before and after, asserted by `harness.kit_is_pristine()`.
- A registry row in `runs/registry.jsonl` pinned to a git SHA. No SHA, no row.
