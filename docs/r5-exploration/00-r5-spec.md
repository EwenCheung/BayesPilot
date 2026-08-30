# R5 — Free-form language *(the agent stops assuming templates)*

> **Road 🔴 R5, the fifth.** R1 filter · R2 ranker · R3 posterior · R4 scheduler · **R5 reads text the
> simulator did not write.** Binding on `src/r5/`: no code lands without an entry here and a failing
> test naming its acceptance ID in [02-acceptance.md](02-acceptance.md).

## The bet, and why it mostly did not pay

Every road up to R4 was built against `local_evaluator.py`'s four literal templates. `data/freeform_v1/`
removes them: 2,400 sessions whose first turn is restyled into slang, shorthand, typos, emoji,
fragments and self-correction, across eight named styles. The bet was that R4 would collapse on text
it cannot pattern-match, and that recovering the stripped structure would be worth a lot.

**It collapsed far less than expected, and three of the four recoveries bought nothing.** That is the
result, and it is more useful than the number.

---

## 1. The corpus

| corpus | train | validation | test | first turn |
|---|---|---|---|---|
| `resplit_60_20_20/` | 8,400 | 2,800 | 2,800 | official templates |
| `freeform_v1/` | 1,200 | 400 | 800 (sealed) | **free-form, 8 styles** |
| `combine/` | 9,600 | 3,200 | — | both |

All scenario-stratified 40/40/15/5, disjoint on `sample_id` and target ASIN, derived from the
leakage-safe `resplit` splits. Verified: `freeform_v1/test.jsonl` hashes to the manifest's
`a60dfacc…`, and the kit evaluator hashes to `79a5ea06…` — byte-identical to upstream.

⚠️ **The README misattributes a hash.** It says the runner "rejects the score unless that file's
SHA-256 remains `79a5ea06…`", but `79a5ea06…` is the **evaluator's** hash; the test file's is
`a60dfacc…`. Both check out; the sentence does not.

⚠️ **Only turn 1 is free-form.** The manifest's policy line claims *"every agent-visible turn
rewritten"*, but each row carries exactly one message and the generator is not in this repository, so
later turns cannot be reproduced. `src/eval/freeform.py` therefore offers two modes and reports which
was used: `later="template"` (what the data supports, and an **understatement** of the intended
difficulty) and `later="stress"` (a reconstruction, never to be quoted as a freeform number).

## 2. What R4 actually loses on free-form text

📊 Validation splits, R4 as shipped, offline:

| corpus | R3 | **R4** |
|---|---|---|
| `resplit` validation (templated) | 0.9261 | **0.9540** |
| `freeform` validation | 0.8923 | **0.9110** |

**Free-form costs R4 only 0.043.** The reason is structural and was not obvious: `state.category` is
parsed from **0.0%** of free-form openers and route is the dataclass default in **100%** of sessions
— yet the score barely moves, because the level-1 category belief reads the **raw opener text**, not
the parsed field. The pool is chosen correctly even when nothing is parsed.

Constraint extraction survives too: the ontology tier recovers ≥1 constraint from **91.8%** of
free-form openers. Between the raw-text pool and the ontology tier, the deterministic path already
handles this corpus.

## 3. What was built, and what each part was worth

| mechanism | flag | measured on freeform train | verdict |
|---|---|---|---|
| Category recovery from a closed 1,115-name vocabulary | `freetext_category` | 0.9153 → 0.9153 | 🔴 **exactly zero** |
| Route recovery from speech-act cues | `freetext_route` | 0.9153 → 0.9146 | 🔴 **slightly negative** |
| LLM fallback on the turn-1 opener | `llm_fallback` | 0.9131 → 0.9145, **400 calls** | 🔴 noise |
| Soft-card matching *(inherited from R4)* | `soft_card_gain` | 0.7769 → **0.7951** under stressed later turns | ✅ the one that works |

**All three R5 mechanisms ship off.** The road's contribution is the measurement, not the code.

🔑 **Why the category recovery bought nothing** is the most transferable finding here: it fills a
field that no downstream decision reads. The pool comes from the raw text; `state.category` is used
only as R4's *positive evidence that the opener was understood* (R4 D9). Filling it correctly changes
one guard, and that guard was not the binding constraint.

🔑 **Why the LLM fallback bought nothing** is more specific, and it is a real bug worth keeping:
`SessionState.paraphrased()` is `turn >= 2 and template_hits == 0`, so on a free-form **opener** —
`template_hits` 0, turn 1 — the escalation gate is closed and the model never sees the one message
that needs it. R5 opens that gate. It then turns out there is little left to win, because the
ontology tier already parsed 91.8% of those openers.

## 4. Kill criteria (set before measuring)

R5 **dies** if its mechanisms do not beat R4 on freeform validation by more than the CI width, or if
any regresses the templated corpus. **Three of four fired.** They ship behind default-off flags so the
negative reproduces rather than being deleted.

## 5. Non-negotiables

1. `Agent.__init__(self, catalog_path=...)` — positional, defaulted.
2. Never import `evaluator.local_evaluator` from agent code.
3. Fit on **train** splits only; validation is for reporting, `freeform_v1/test.jsonl` stays sealed.
4. Every LLM call asserts on a parsed non-empty result and counts failures.
5. `src/r5/` may import `src/r4/`, and nothing else under `src/r*/`.
