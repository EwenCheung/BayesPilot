# Frozen contracts

These are the seams [IDEA.md §0.4](../../IDEA.md) freezes across R1/R2/R3. Everything else is private to a
road. ⚠️ Do not impose a common internal pipeline — R3 has no retrieval stage, and forcing
`recall/rerank/decide` on it would flatten the difference the race exists to measure.

## `SessionState` — [src/common/state.py](../../src/common/state.py)

```python
@dataclass
class SessionState:
    turn: int
    category: str | None            # coarse category, once known
    slots: dict[str, list[str]]     # attribute -> confirmed values
    slot_age: dict[str, int]        # turns since confirmed (slot decay, PROBLEM.md §4.3)
    disclosed: set[str]             # raw constraint strings already revealed
    history: list[str]              # customer utterances, in order
    profile: dict                   # anonymized user_profile
    long_term: dict                 # distilled cross-session preferences (Pillar III)
    asked: list[str]                # ask_attribute values already spent this session
    barren: set[str]                # attributes that returned "no additional preference"
    shown: list[str]                # asins already recommended (implicit negative feedback)
```

`parse(message, state) -> SessionState` mutates and returns state. All three roads call the same parser so
they see identical input; only what they *do* with it differs.

**Override semantics (Pillar II).** On an override utterance the parser must *erase*, not stack: the
superseded value leaves `slots`, and the new value enters with `slot_age = 0`.

## `CatalogIndex` — [src/common/catalog.py](../../src/common/catalog.py)

Built once, shared by every session (the evaluator constructs one `Agent` for all 200 sessions, so index
cost amortizes to zero).

```python
index.products      # asin -> raw catalog row
index.coarse        # asin -> coarse_category(row["categories"])
index.by_cat        # coarse category -> [asin]
index.pop           # asin -> rating_number (0 when null)
index.log_pop       # asin -> log1p(rating_number)
index.phrases       # asin -> frozenset of intent_card strings  (the inversion surface)
index.tokens        # asin -> frozenset of content tokens from those strings
```

## `Route` — [src/r2/routes.py](../../src/r2/routes.py)

```python
def score(self, query: Query, candidates: list[str]) -> dict[str, float]
```

Scores are **route-local and unnormalized**; fusion owns comparability. A route that cannot answer returns
`{}` rather than zeros, so fusion can tell "no opinion" from "scored zero".

## Registry row — `runs/registry.jsonl`

Appended by [src/eval/compare.py](../../src/eval/compare.py). Per [IDEA.md Part IV](../../IDEA.md),
**a run counts only if** it carries all four scenario breakdowns, a paraphrase-stressed score, the
`no_spec_phrase` ablation, `llm_call_failures`, and a git SHA.

```json
{"variant":"r2-full","git_sha":"...","timestamp":"...",
 "hit_rate_at_10":0.0,"mrr":0.0,"mttc":0.0,"efficiency":0.0,"technical_score":0.0,
 "scenario":{"buying":{},"browsing":{},"intent_override":{},"boundary":{}},
 "paraphrase":{"clean":0.0,"scaffold":0.0,"full":0.0},
 "ablations":{"no_spec_phrase":0.0,"no_dense":0.0,"no_popularity":0.0,"no_lexical":0.0},
 "bootstrap":{"lo":0.0,"hi":0.0},
 "models":{"embed":"...","rerank":"..."},"llm_call_failures":0,
 "latency":{"total_s":0.0}}
```

## Agent boundary

The kit's contract, unchanged: `reset(session_id, user_profile)` then
`respond(session_id, user_message, turn, top_k) -> {message, ask_attribute, recommendations, usage}`.
`ask_attribute` ∈ `{category, material, color, size, style, brand, budget, feature, use_case, other, null}`.
Only list **order** is scored; the optional `score` field is parsed and ignored.
