# R3 — contracts

Frozen seams. Changing anything here means amending this file first
([00-r3-spec.md](00-r3-spec.md) §9).

---

## 1. The kit boundary — unchanged, non-negotiable

```python
class Agent:
    def __init__(self, catalog_path="data/catalog.jsonl"): ...   # ⚠️ POSITIONAL, undocumented
    def respond(self, message: str, session_state: dict) -> dict: ...
```

⚠️ The evaluator constructs `Agent(catalog_path)` positionally. The README, `agent_api_contract.json`
and `submission_rules.md` all omit `__init__` entirely. Getting this wrong is a hard crash at startup,
not a low score.

⚠️ `usage` is **summed by the evaluator across turns**. Return per-turn deltas, never running totals —
running totals over-count quadratically and token usage is a disclosed submission figure.

---

## 2. R3 owns one index and one parser

R3 is one system, not a shim over two others. `src/r3/` contains:

| Module | Owns |
|---|---|
| `index.py` | the single `Index` — products, coarse categories, popularity, spec phrases, normalised attribute pairs, content tokens, embeddings |
| `evidence.py` | `parse(message, state) -> Evidence` — the three-tier parser (template → ontology → LLM escalation) |
| `likelihood.py` | the evidence terms of [00-r3-spec.md](00-r3-spec.md) §3.1 and their calibrators |
| `belief.py` | the posterior: prior, update, entropy, mass, pool widening |
| `policy.py` | ask / ship-depth / convert, all driven by `H(P)` and cumulative mass |
| `question.py` | expected information gain over the posterior |
| `agent.py` | the `Agent` the evaluator constructs |
| `flags.py` | every term and stage behind an ablation switch |

### 2.1 🔒 R3 imports nothing from R1 or R2

**No `from src.r1…` or `from src.r2…` anywhere under `src/r3/`.** Enforced by an AST-level test
(`tests/test_r3_isolation.py`), the same pattern R1 already uses for the evaluator-import trap.

Code may be **lifted** from either road where it is good — that is the point of going last, and
IDEA.md §0.3 is explicit that nothing built in the first two worktrees is thrown away. What is
forbidden is R3 *calling into* them at runtime, because then R3 is glue and not an architecture, and
the race compares a system against two of its own components.

R1 and R2 stay frozen as the baselines whose published numbers must reproduce. Their duplication with
R3 is temporary and is deleted at Phase 2 (converge).

---

## 3. Internal seams

```python
@dataclass
class Evidence:
    """One utterance, parsed. Never mutated after construction."""
    turn: int
    category: str | None            # coarse category if the utterance named one
    constraints: list[Constraint]   # raw text + normalised (attribute, value) + provenance
    is_override: bool
    template_matched: bool          # False ⇒ the wording is unfamiliar ⇒ paraphrase mode

@dataclass
class Constraint:
    text: str                       # the raw string, deduped on exact match
    attribute: str | None
    value: str | None
    provenance: str                 # initial_hard | initial_soft | reply | override
    turn: int

class Term(Protocol):
    """One evidence term. Returns an UNCALIBRATED score per candidate."""
    name: str
    def score(self, evidence: Evidence, candidates: list[str]) -> dict[str, float]: ...

class Calibrator(Protocol):
    """Monotone map from a term's raw score to a likelihood in [ℓ_min, 1]."""
    def __call__(self, raw: float) -> float: ...

class Belief:
    log_p: dict[str, float]         # unnormalised log posterior over the live pool
    def update(self, evidence: Evidence) -> None: ...
    def entropy(self) -> float: ...
    def mass(self, k: int) -> float:      # cumulative normalised mass of the top k
    def top(self, k: int) -> list[str]: ...
```

**A term that abstains returns `{}`**, not zeros — the belief must be able to tell "no opinion" from
"scored zero", exactly as R2's routes do. An abstaining term contributes a flat factor and cancels in
the normalisation ([00-r3-spec.md](00-r3-spec.md) §3.1).

**Every likelihood factor is bounded below by `ℓ_min > 0`.** No single piece of evidence may drive an
item's posterior to zero. This is R1's relaxation rule — *"an intersection that would empty S is
discarded"* — expressed as arithmetic rather than as a special case, and R1 measured what happens
without it: letting soft matches delete candidates dropped Hit@10 to 0.79 under stress, **below the
do-nothing baseline of 0.815.** The agent was filtering out the target on the strength of a guess.

---

## 4. Session state semantics — inherited, measured, not up for re-derivation

- **Accumulation.** Every reply appends constraints, deduped on exact raw string.
- **Override demotes, it does not delete.** The overridden preference is `soft_preferences[1]` — still a
  true constraint of the same target, because the target never changes. Deleting it cost R1 **0.05 MRR
  on override sessions**. In R3 this is native: evidence with a lower weight, not evidence retracted.
- **Decay.** Older evidence contributes less. R1 used `0.9 ** age`, R2 `1/(1+0.15·age)`. In R3 this is a
  calibrator parameter fitted on synthetic sessions, not a constant.
- **Paraphrase detection.** If no template has matched by turn 2 the session is in paraphrase mode. R3
  does **not** switch strategy on this flag — that is the point of §3.1 — but it is recorded, reported,
  and used to gate the LLM extraction tier.

---

## 5. Shared, unchanged

- `src/common/simulator.py` — ⚠️ **verbatim copies** of the evaluator's `intent_card`,
  `coarse_category`, `classify_constraint`, `searchable_text`. Copied, never imported, parity-tested
  against the kit on every run.
- `src/eval/` — the unified harness, rewriter, ablation vocabulary and registry
  ([04-merge-plan.md](04-merge-plan.md) §3). All three roads use it identically or the race means
  nothing.
- The held-out manifest ([04-merge-plan.md](04-merge-plan.md) §6).

---

## 6. Traps that are already paid for — do not rediscover them

1. **Never import `evaluator.local_evaluator` from agent code.** It does `from starter.agent import
   Agent` at module scope → circular import → hard crash. Harness scripts and tests are outside the
   cycle and may.
2. **`Agent.__init__` is positional.** §1.
3. **Never iterate a `set` where order matters.** Python salts string hashing per process; `list(s)[:64]`
   picks a different subset each run. This silently drifted reported scores in *both* roads.
4. **Every LLM call must assert on a parsed non-empty result and count failures.** Some models return
   `content: None` while burning the full token budget. This project has already scored 60
   silently-failed calls as "the model doesn't help".
5. **Pin explicit model IDs.** `default`, `test`, `ornith1.0:35b` are aliases that can be repointed.
6. **The endpoint rate-limits hard and is shared.** 12-way parallel embedding lost 548 of 1,042 batches;
   4-way lost none. A concurrent session on another road contaminated a reranker measurement (318 of
   386 calls failed). Content-hash caching makes retries free.
7. **Anything writing relative paths runs with `cwd=<kit>`.** A cache once materialised *inside* the kit
   we promise to keep pristine. Use absolute paths; `git status` on the kit is the check.
8. **`ask_attribute: "other"` is the simulator's wildcard**; `null` reveals nothing.
