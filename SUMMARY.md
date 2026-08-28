# R1 — Constraint Satisfaction: handover

**Branch:** `r1-exploration` · **Worktree:** `../r1-constraint` · **Status:** built, measured, not merged

If you read one thing, read [§2 How good it is](#2-how-good-it-is-and-how-bad) and
[§7 Known defects](#7-known-defects-read-before-you-trust-a-number). R1 does **not** improve the clean
score — it was never going to — and two of its numbers are not comparable to R2's even though they look
like they are.

---

## 1. What R1 is

TechJam Track 4 asks for a multi-turn shopping agent that finds a hidden target product in a frozen
50,000-item Amazon clothing catalog within 10 turns. [IDEA.md](IDEA.md) §0.3 splits the work into three
**roads** — three incompatible answers to "what kind of problem is this?" — to be built separately and
raced:

| Road | The agent is… | Core structure |
|---|---|---|
| 🔵 **R1 (this one)** | a **filter** | a shrinking candidate *set* — intersect, convert when it collapses |
| 🟢 R2 | a **ranker** | a scored *list* — fuse routes, order, take 10 |
| 🟣 R3 | a **posterior** | `P(item) ∝ prior × Π likelihoods` — fuses R1 and R2, starts after both |

**R1's bet: this is a database query wearing a conversational costume.** The customer states hard facts;
each one eliminates products. Ranking exists only to break ties among whatever survives. Where R2 asks
*"how well does each product explain this?"* and sorts, R1 asks *"which products satisfy this?"* and
deletes the rest.

That bet buys **precision and speed** — a set that collapses to one item converts immediately, with no
weight tuning anywhere — and it carries an obvious structural risk: **a set intersection that misses
returns nothing.** Reword one constraint and the exact match is gone. R2 degrades down a slope; R1
degrades off a cliff.

The whole point of building it was to find out how tall the cliff is, because the competition spec
reserves the right to paraphrase the private 800 sessions: *"If natural-language paraphrasing is added
by the organizer, it cannot decide correctness."* See [IMPORTANT.md](IMPORTANT.md) §3.

**The answer: the cliff is real, R1 has a ledge partway down, and the ledge is held up by two things
that are not the filter** — the popularity prior and an LLM extraction tier.

---

## 2. How good it is, and how bad

All numbers from the official evaluator on the 200 public sessions, kit verified byte-identical to
upstream before *and* after every run. Rows: `runs/registry.jsonl`. Generated table:
[docs/R1-RESULTS.md](docs/R1-RESULTS.md).

### The scoreboard

| Configuration | Hit@10 | MRR | MTTC | **Score** | 95% CI |
|---|---|---|---|---|---|
| **R1 shipping default, clean** | 1.000 | 0.9692 | 2.55 | **0.9597** | 0.9529–0.9658 |
| R1 deterministic only, no network | 1.000 | 0.9692 | 2.55 | 0.9597 | 0.9529–0.9658 |
| R1 with the reranker always on | 1.000 | 0.9515 | 2.55 | 0.9545 | 0.9459–0.9623 |
| **R1 stressed L2** (payloads reworded) | 0.945 | 0.7464 | 2.85 | **0.8594** | 0.8273–0.8881 |
| R1 stressed L2, deterministic only | 0.890 | 0.6437 | 3.47 | 0.7887 | 0.7479–0.8278 |
| **R1 stressed L3** (model-written) | 0.820 | 0.5753 | 3.90 | **0.7246** | 0.6783–0.7726 |
| R1 with inversion removed (`no_spec_phrase`) | 0.995 | 0.8784 | 2.75 | 0.9260 | 0.9109–0.9390 |
| R1 with popularity removed | 0.985 | 0.8699 | 2.67 | 0.9200 | 0.8988–0.9377 |
| — seed prototype `agent_best_0.9607.py` | 1.000 | 0.9750 | 2.59 | 0.9607 | — |
| — paraphrase-proof floor ⚠️ **the bar** | 0.905 | 0.6860 | ~2.6 | 0.8260 | — |
| — popularity + category only | 0.815 | 0.4981 | 3.18 | 0.7133 | — |
| — public PR#1 trick | 0.875 | 0.5400 | 3.46 | 0.7504 | — |
| — shipped BM25 starter | 0.125 | 0.0680 | 9.81 | 0.1067 | — |
| — theoretical maximum | 1.000 | 1.000 | 1.39 | 0.9922 | — |

### The good

- **Clean 0.9597, and the LLM costs nothing to get it.** `r1_extract` (extraction enabled) scores
  *identically* to `r1_clean` in the same 9 s, because on clean text every template matches and the
  model is never called. **Zero network calls on the clean set** — verified by a test, not by hope.
- **0.8594 under paraphrase stress**, clearing the road's own kill criterion of 0.826. Deterministic
  alone it is 0.7887, so the LLM extraction tier is what carries it across; that tier only exists
  because the templates stopped matching, which is exactly when insurance should pay.
- **Hit@10 = 1.000 on every clean scenario**, and intent_override MTTC of **3.60 — the structural
  floor.** Those 30 sessions cannot convert before turn 3 or 4 (the evaluator discards earlier lists),
  so R1 stops selling and spends the discarded turns extracting.
- **Robust to a failing endpoint.** With **167 of 760 model calls rate-limited (22%)**, the stressed
  score fell only 0.8594 → 0.8474. Every LLM path has a deterministic fallback and the failures are
  counted, not swallowed.
- **`R1_OFFLINE=1` scores 0.9597** — bit-identical to the networked run. The no-network path is not a
  retrofit, it is the default.

### The bad — and this is the part that matters

**1. R1 does not beat the incumbent.** 0.9597 against the seed prototype's 0.9607, inside a CI spanning
0.013. It is the same number. Clean headroom was only +0.031 with Hit@10 already at 1.000, so this was
never where the road could win — but do not let anyone quote R1 as an improvement on the clean set.

**2. R1 dies at L3.** Under model-written paraphrase it scores **0.7246**, below the 0.826 bar and
barely above the 0.7133 popularity-only baseline. What each route is worth once the wording changes
(all measured at L2, the deepest stress level with a full ablation sweep):

| removed from the stressed run | Δ score |
|---|---|
| exact spec-phrase matching — the filter's whole thesis | **0.0000** — it is already dead here |
| popularity prior | **−0.2422** |
| normalised attribute matching | −0.0652 |
| token-overlap matching | −0.0041 |

So under free-form rewording, **the filter contributes nothing and the popularity prior is doing the
work.** R1 is, at that point, an expensive way to run the do-nothing baseline. That is the road's
predicted failure mode arriving on schedule, and it is a genuine result: the filter thesis is false
under paraphrase, and the fix is a scored blend, i.e. R2.

**3. Its two headline robustness numbers are not comparable to R2's.** See §7 defects 1 and 2. Do not
put R1's `no_spec_phrase` = 0.9260 next to R2's 0.8315 in a table — they ablate different amounts of
the same signal, and R1's is the weaker ablation.

**Honest summary: R1 matched the incumbent, proved the filter thesis survives mechanical rewording and
fails free-form rewording, and produced the measurement that tells R2 what to build.**

---

## 3. The algorithm

```
user message
    │
    ├─ parse (3 tiers) ────► SessionState
    │    template            the simulator's four literal sentences — exact, free, verbatim strings
    │    ontology            attribute/value extraction from arbitrary prose
    │    llm                 escalation, fires only when NO template matched
    │
    ├─ resolve the pool ───► coarse category, or a hedged union when the wording is fuzzy
    │
    ├─ FILTER ─────────────► S ← S ∩ matches(constraint), once per live constraint
    │                        an intersection that would empty S is DISCARDED (relaxation)
    │                        only exact matches may shrink; weaker matchers only score
    │
    ├─ tie-break ──────────► weighted match count → log-popularity → [dense] → [LLM listwise]
    │
    └─ judge ──────────────► converged / NQC / deadline → convert, else ask the highest-EIG attribute
```

### 3.1 The filter — three matchers, one privilege

`matches(constraint, product)` returns a strength, and only the sharpest one is allowed to delete:

| matcher | strength | may shrink `S` | survives rewording |
|---|---|---|---|
| exact spec-phrase — the constraint string is verbatim in the product's own intent card | 1.0 | ✅ | no |
| normalised attribute — `("material","alloy")` from `Material: alloy` *or* from `made of alloy` | 0.6 | ❌ | mostly |
| token overlap ≥ 0.6 of the constraint's content tokens | 0.3 | ❌ | yes |

🔑 **Only exact matches may shrink the set, and that rule is worth a lot.** Letting attribute-level
matches filter dropped Hit@10 to **0.79 under stress — below the popularity-only baseline of 0.815.**
The agent was deleting the target on the strength of a guess. The generalisable form: **a filter should
only remove on evidence it would bet the session on; everything softer belongs in the ranking.**

`S` is never empty. If a constraint's match set is empty, the constraint is recorded as unmatched and
`S` is kept as it was.

### 3.2 Category resolution and hedging

`S` starts as the target's coarse category (1,115 of them, median pool 181). On clean text the template
hands over the category verbatim. When it does not:

1. the longest category name quoted verbatim in the message wins;
2. otherwise `hits² / |category tokens|` over the 1,115 names — scoring by coverage alone let
   "Shirts T-Shirts" outscore the "Shirts Tanks Tops" the shopper actually said, and cost **21 sessions**;
3. if several categories score within 40% of the best, **search the union of them** (capped at 4,000
   products) rather than betting on one.

Hedging is worth **+0.0464 at L3** and exactly **0.0000** on clean and L2 — it only fires when the
wording is genuinely ambiguous. Wrong pool = guaranteed miss, and 15% of model-paraphrased openers
resolve to the wrong category, so hedging buys recall at a ranking cost R1 can afford because it
relaxes rather than shrinks.

### 3.3 Question selection — expected information gain

Every turn, for each askable attribute, partition `S` by the answer the simulator *would* give if each
candidate were the target, and score `H(S) − E[H(S | a)]` with the prior `∝ popularity`. `O(|S|)` per
attribute because items producing the same answer form one group.

This re-derives `"other"` as the usual winner rather than hardcoding it — `"other"` bypasses the
simulator's crude classifier and returns the next two undisclosed constraints, while asking the
semantically "right" attribute is measurably worse ([IMPORTANT.md](IMPORTANT.md) §4).

⚠️ **It is worth −0.0010.** Hardcoding `"other"` scores 0.9607, information gain scores 0.9597. That is
inside the noise, and it never wins. It is kept because "the expected value of this question exceeded
the others" is a defensible mechanism where a magic string is not, and 65% of judging is not the score
— but if you want the incumbent's number back, `R1_FLAGS=no_infogain` is it.

Attributes that answer *"I don't have an additional preference"* are recorded and never asked again —
Pillar III's *"iteratively refines its own guidance logic"*, concretely.

### 3.4 The policy — patience, then a deadline

```
override session and the override has not landed and turn < 4  → recommend NOTHING (extract instead)
strict unique leader  (top score > runner-up)                  → convert
NQC = stdev(top-10)/mean ≥ 0.35                                → convert
turn ≥ 3                                                       → convert regardless
```

A hit **ends** the session and locks in that reciprocal rank, so converting early is a trap: holding one
turn for a rank-1 hit gains +0.225 MRR against −0.02 efficiency. Measured: deadline 3 beats deadline 2
by 0.0053 and deadline 4 by 0.0014.

The override rule is worth stating plainly: the evaluator will not count a hit until the override
message arrives on turn 3 or 4, so every list shipped before it is discarded **even at rank 1**. R1
detects the override scenario from the opening sentence and stays silent, which is why its override
MTTC is exactly the 3.60 floor.

**Dynamic truncation** (§14.3 of the requirement audit) is implemented and measured at **±0.0000** — when
the filter has converged the leader is always right, so cutting the list to 1 costs nothing. It is off by
default because it can only ever lose a hit, never win one.

### 3.5 State semantics

`SessionState` holds `turn, category, slots, slot_age, disclosed, history, profile, long_term,
constraints, asked, route, override_seen, template_hits`.

- **Accumulation** — every reply appends constraints, deduped on the exact raw string.
- **Override demotes, it does not delete.** ⚠️ The simulator's "overridden" preference is
  `soft_preferences[1]` — *still a true constraint of the same target*, because the target never
  changes. Deleting it cost **0.05 MRR on override sessions** (0.909 → 0.967 when switched to
  demotion). The shipped behaviour retires the named slot to weight 0.35: it honours the dialog act
  without throwing away a discriminator. Modes: `demote` (default) · `delete` · `keep`.
- **Slot decay** — `weight = 0.9 ** age`, named in PROBLEM.md §4.3.
- **Runtime paraphrase detection** — `template_hits` counts utterances a known template matched. If
  nothing has matched by turn 2, the session is *in paraphrase mode* and the strategy changes (below).

### 3.6 Adaptive orchestration (Pillar III), concretely

The LLM reranker measured **−0.0053 on clean text** and **+0.0018 under paraphrase**. Rather than pick
one, the agent gates it on the runtime signal that distinguishes them: fire the reranker only once
`state.paraphrased()` is true. Clean sessions never pay for it; reworded ones get it automatically. Same
for extraction, which escalates only when no template matched.

That is the brief's *"runtime workflow re-orchestration"* with a number attached, and it is the reason
the shipping default is 0.9597/9 s on clean **and** 0.8594 under stress with the same flags.

---

## 4. Repository map

```
docs/specs/
  r1-constraint-satisfaction.md   THE SPEC — hard contracts, per-module behaviour, acceptance criteria
  r1-implementation-plan.md       step → the test that proves it, plus the defect log
docs/R1-RESULTS.md                generated from runs/registry.jsonl — never hand-copied
src/
  common/                         Track 0 foundation, shared by all three roads (IDEA.md §0.4)
    simulator.py   ⚠️ VERBATIM COPY of the evaluator's intent_card / coarse_category /
                      classify_constraint / searchable_text. Copied, never imported — §6 trap 1
    contracts.py   SessionState + Constraint (decay, demotion, paraphrase detection)
    catalog.py     CatalogIndex — pools, popularity, card strings, lazy per-pool features, hedging
    attributes.py  the normalised ontology + paraphrase cue patterns
    parse.py       the three-tier parser — template → ontology → LLM
    llm.py         one client: chat, embeddings, disk cache, failure counter, offline mode
  r1/
    filter.py      the shrinking candidate set — the road's thesis, 60 lines
    question.py    expected-information-gain question selection
    rank.py        tie-break cascade + the adaptive LLM rerank gate
    policy.py      convergence, NQC, deadline, override silence, dynamic truncation
    agent.py       the Agent the evaluator constructs
    dense.py       bge-m3 cosine tie-break (measured and rejected — §7)
    flags.py       every route behind an ablation switch
  eval/
    run.py         swap shim in → official evaluator → restore → re-verify kit SHA-256
    stress.py      the paraphrase rewriter — wraps the AGENT, never the evaluator (4 levels)
    ablate.py      the measurement matrix (35 named runs)
    compare.py     registry rows + seeded bootstrap CI + scenario breakdown
    report.py      regenerates docs/R1-RESULTS.md from the registry
    embed.py       one-off: all 50,000 products through bge-m3 (~$0.10)
    entry.py       the graded object: R1 + the stress wrapper + the disclosure dump
tests/             59 tests, pytest
runs/              registry.jsonl (committed) — raw run dumps gitignored
.cache/            gitignored: llm/ response cache, embeddings.npz (50000 × 1024, float16)
```

---

## 5. How to run it

```bash
# one-time: the catalog is gitignored, symlink it into the kit
ln -sf /path/to/assets/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl

python3 -m pip install pytest          # the only dev dependency; numpy is the only runtime one
python3 -m pytest tests/ -q            # 59 tests, ~10 s

python3 -m src.eval.run --name r1      # one run of the official evaluator (~10 s)
python3 -m src.eval.ablate             # the whole 35-run matrix
python3 -m src.eval.ablate r1_ship r1_ship_stress2     # or just the headline rows
python3 -m src.eval.report             # regenerate docs/R1-RESULTS.md

R1_OFFLINE=1 python3 -m src.eval.run --name r1_offline # the no-network path
```

Optional, for the LLM tiers and the dense route only:
```bash
set -a && . ./.env && set +a           # SOCLAAS_API_KEY / SOCLAAS_BASE_URL
python3 -m src.eval.embed              # ~50k vectors, 4-way parallel, ~$0.10
R1_LLM_NOCACHE=1 python3 -m src.eval.ablate disclosure_stress2   # real latency/token figures
```

**Flags** — `R1_FLAGS=no_spec_phrase,erase=delete,deadline=4`; `no_<flag>` disables, `flag` enables,
`name=value` sets. `R1_STRESS=0..3` picks the paraphrase level. Everything in `src/r1/flags.py`.

### How the harness treats the kit

Each run writes a three-line shim into `starter/agent.py`, runs the **unmodified** official evaluator as
a subprocess, restores the starter from a stored pristine copy, and re-verifies the SHA-256 of every kit
file a score depends on. A run whose SHA check fails is refused, not recorded. `PYTHONHASHSEED=0` is
pinned so repeated runs are bit-identical.

⚠️ **R2's harness is better and you should probably adopt it.** It imports the evaluator's `evaluate()`
and hands it an agent instance, never touching `starter/agent.py` at all — which means no shim, no
restore, and no 9-second index rebuild per variant. R1 pays ~10 s per run for a guarantee R2 gets for
free.

---

## 6. Traps that will cost you an hour each

1. **Never import `evaluator.local_evaluator` from agent code.** The evaluator does
   `from starter.agent import Agent` at module scope, so importing it back is a circular import and a
   hard crash at startup. The functions are copied into `src/common/simulator.py` and parity-tested over
   2,000 catalog rows. An AST-level test asserts no module under `src/` imports it. *Tests and harness
   scripts may — they sit outside the cycle.*
2. **`Agent.__init__(self, catalog_path=...)` is positional and undocumented.** The evaluator constructs
   it that way; the README, the API contract and `submission_rules.md` all omit `__init__` entirely.
3. **Never iterate a `set` where order matters.** `card_strings` was a `set`, and the information-gain
   model read "the first two undisclosed constraints" out of it — so the score drifted between identical
   runs (0.9584 vs 0.9594) because CPython salts string hashing per process. It is now a tuple in the
   simulator's own order, which also made the model *correct*, not merely deterministic.
4. **`usage` is summed by the evaluator across turns.** Returning the client's running totals
   over-counts quadratically, and token usage is a disclosed submission figure. Return per-turn deltas;
   there is a regression test.
5. **Every LLM call must assert on a parsed non-empty result and count failures.** A silent model failure
   is indistinguishable from a model that is not helping. This project has already scored 60
   silently-failed calls as "the model doesn't help".
6. **The endpoint rate-limits hard.** 12-way parallel embedding lost **548 of 1,042 batches**; 4-way lost
   none. A content-hash cache made the retry free. During a live scored run, 22% of calls failed.
7. **Anything writing relative paths runs with `cwd=<kit>`.** The LLM cache silently materialised
   *inside* the kit we promise to keep pristine. Use absolute paths; `git status` on the kit is the check.
8. **Pin explicit model IDs.** `default`, `test` and `ornith1.0:35b` are aliases that can be repointed.

---

## 7. Known defects — read before you trust a number

1. ⚠️ **`no_spec_phrase` = 0.9260 is a weaker ablation than R2's 0.8315 and the two are NOT
   comparable.** R1's switch disables only the *exact* matcher; the attribute and token matchers still
   read the same template-literal text and recover most of it. R2's removes its whole inversion route
   including partial credit. Quoting them side by side would overstate R1 by roughly 0.09. **Fixing this
   — one shared ablation definition across roads — is the single highest-value cleanup on this list.**
2. ⚠️ **The stress numbers are not comparable across roads either.** R1's rewriter and R2's are different
   programs with different aggression. R1 L2 = 0.8594 and R2 heavy = 0.7961 say nothing about which
   agent is more robust. Race them on **one** harness before anyone writes a comparison table.
3. **No held-out evaluation.** Every threshold (shrink 1.0, demote 0.35, decay 0.9, NQC 0.35, deadline 3,
   hedge 0.6) was chosen on all 200 public sessions. The bootstrap CI is not a substitute for a split.
   A teammate's immutable 140/60 partition with disjoint sample IDs *and* target ASINs is the model.
4. **L3 (model-written) stress is measured on `qwen3.6:35b` rewrites of the simulator's sentences.** It
   is the most honest proxy available and it is still a proxy — the organizer's paraphrase, if any, will
   differ.
5. **The dense route is implemented and rejected, not tuned.** As a lexicographic tie-break placed above
   popularity it costs −0.0270 clean and −0.0530 stressed, because it displaces the prior that is
   actually carrying the stressed score. This is evidence *for* R2's blended form, not against dense —
   nobody has tried `dense + w·log(popularity)` inside R1.
6. **Information gain loses to a hardcoded `"other"` by 0.0010.** Kept for the mechanism, not the score
   (§3.3). If the submission is judged only on the number, flip it.
7. **The long-term profile layer is built, measured at −0.0469, and shipped off.** That is the correct
   call for this dataset (the supplied `user_profile` is near information-free) but it means Pillar III's
   *"long-term user profiles"* is present as a measured negative, not a working feature.
8. **Boundary is 10 sessions.** Its MRR moves 0.10 when one session changes rank. Never read it alone.

---

## 8. How to pick this up

**Highest value first.**

1. **Unify the ablation and stress definitions across R1 and R2** (defects 1 and 2), then re-run both.
   Until that exists there is no race, only two scoreboards. This is cheap and it unblocks every
   comparison anyone will want to make.
2. **Try the blend inside R1.** The L3 failure is *entirely* "constraints stopped discriminating and
   only popularity was left". R2 has already measured that `dense + w·log(pop)` beats both parts alone.
   Wiring it into `rank.order` as a score, not a tie-break, is the obvious next experiment — and if it
   works, R1 and R2 have converged and R3 should start.
3. **Build a held-out split** before tuning anything else (defect 3).
4. **Attack L3 recall, not L3 ranking.** At L3, Hit@10 is 0.820 and MRR-given-hit is decent; the losses
   are pools that never contained the target. Category resolution is 85% accurate there — embedding the
   1,115 category names once and resolving by cosine is a ~20-line change with a plausible +0.03.
5. **Re-measure the LLM reranker on an uncontended endpoint.** Its +0.0018 under stress was taken while
   22% of calls were failing.
6. **Port the harness to R2's in-process design** (§5) and the whole matrix gets ~3× faster.

**Do not repeat these — they were measured and rejected:**

- Dense similarity as a tie-break above popularity (−0.027 clean, −0.053 stressed).
- Deleting the overridden slot instead of demoting it (−0.0036 overall, −0.05 MRR on override sessions).
- Letting attribute-level matches shrink the candidate set (Hit@10 0.89 → 0.79 under stress).
- The supplied `user_profile` as a ranking signal (−0.0469).
- Converting at turn 2 (−0.0053) or waiting until turn 4 (−0.0014). Turn 3 is the optimum.
- Scoring category candidates by coverage alone (21 wrong pools under stress).

### What R1 contributes to the race, whatever wins

- **The filter thesis is false under free-form paraphrase and true under mechanical rewording.** That is
  a real finding with a number on each side: 0.8594 at L2, 0.7246 at L3.
- **The popularity prior is the entire insurance policy** (−0.2422 under stress) — larger than anything
  the filter contributes.
- **An LLM tier that fires only when the deterministic path stops working costs nothing when it is not
  needed.** Identical score and identical wall-clock on clean text, +0.07 under stress.
- **Six defects the process caught** are logged with their symptoms in
  [docs/specs/r1-implementation-plan.md](docs/specs/r1-implementation-plan.md). Three of them (hash-order
  drift, the usage over-count, the cache writing into the kit) would have silently corrupted numbers
  rather than crashing.

---

## 9. Working rules for this branch

Spec-driven and test-driven, in this order, no steps skipped — `.claude/CLAUDE.md` §3.5 makes it binding:

1. **Spec first** — amend [docs/specs/r1-constraint-satisfaction.md](docs/specs/r1-constraint-satisfaction.md).
   Behaviour that is in the code but not the spec is a bug in one of them.
2. **Test second** — write it, watch it fail *for the right reason*, then implement.
3. **Implement third** — the minimum that makes the test pass.
4. **Measure fourth** — the real evaluator, appending a row to `runs/registry.jsonl`.
5. **Record** — when a measurement changes a decision, including reversing one, put the number in the
   spec next to the behaviour it justifies. Every threshold in §3 carries the measurement that chose it.

**A run counts only if** it carries all four scenario breakdowns, a paraphrase-stressed score beside the
clean one, the `no_spec_phrase` ablation, `llm_call_failures`, a git SHA and a pristine kit.

---

## 10. Where the rest of the context lives

| Document | What it is |
|---|---|
| [IMPORTANT.md](IMPORTANT.md) | **Authoritative on facts** — evaluator mechanics, the simulator-inversion finding, the popularity leak, §12 measurements, §13 errors, §14 requirement audit |
| [REPORT.md](REPORT.md) | The narrative: what the problem is and what was found |
| [IDEA.md](IDEA.md) | Proposals: the 40-component index, the three roads, the shared contract |
| [docs/PROBLEM.md](docs/PROBLEM.md) | The official brief — four pillars, scope, judging |
| [docs/specs/](docs/specs/) | This road's spec and its implementation/verification log |
| [docs/R1-RESULTS.md](docs/R1-RESULTS.md) | Every measurement, regenerated from the registry |

⚠️ **TechnicalScore is only an input to the 35% "Technical Execution" criterion**, not the score. The
other 65% is Innovation, Impact, Feasibility and Presentation. A naked lookup table that scores 0.95
loses to a real agent at 0.75. R1's most defensible contribution is not 0.9597 — it is the ablation
table, the honest statement that the filter contributes **zero** once wording changes, and the fact that
the popularity prior, not the clever part, is what keeps the score up.
