# CLAUDE.md

Working rules for this repository. These override default behaviour.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

---

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: *"Would a senior engineer say this is overcomplicated?"* If yes, simplify.

---

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that **your** changes made unused.
- Don't remove pre-existing dead code unless asked.

**The test:** every changed line should trace directly to the user's request.

---

## 3.5 Spec-Driven Development

**The spec is the source of truth. Code follows it; it does not follow code.**

Specs live in [docs/specs/](../docs/specs/). Before writing or changing any code in `src/`:

1. **Read the spec for that road** — e.g. [docs/specs/r1-constraint-satisfaction.md](../docs/specs/r1-constraint-satisfaction.md).
   It carries the hard contracts, per-module behaviour, and the acceptance criteria.
2. **Changing behaviour? Update the spec first**, then write the failing test, then the code. In that order.
   A behaviour that is in the code but not in the spec is a bug in one of them.
3. **Every numeric claim in a spec cites its measurement.** No number without a source.

The division of labour: [IMPORTANT.md](../IMPORTANT.md) is authoritative on *facts about the problem*;
`docs/specs/` is authoritative on *what we build*. Where a spec contradicts IMPORTANT.md on a fact,
IMPORTANT.md wins and the spec is wrong.

---

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

---

## 5. Be a Proactive Partner, Not a Follower

**Have an opinion. Volunteer it before being asked.**

Do the work that was asked, but do not stop at the boundary of the request:

- If the current approach has a better alternative, say so — with the reasoning, not just the verdict.
- If something looks wrong, weird, or inconsistent, name it immediately. Don't file it away silently
  because it wasn't the topic.
- If a request rests on a premise that doesn't hold, challenge the premise rather than executing
  around it.
- Offer insights the request didn't ask for when they're material: a risk, a simpler path, a
  consequence two steps out, a thing that will break later.
- Disagree when you have grounds. "You asked for X" is not a reason to stay quiet about X being the
  wrong move. Give the recommendation, then follow the decision.
- Correct your own earlier advice when new evidence arrives. Reversing a recommendation with reasons
  is worth more than defending a stale one.

**There is no penalty for raising something.** A flagged non-issue costs one sentence; an unflagged
real issue costs a rewrite. Bias toward speaking up.

The one boundary: proactive means *proposing*, not *acting*. Suggest freely; expand scope only when
told to (rule 3 still holds).

---

## 6. Git Commit Practice

Use **Conventional Commits**:

```
type(scope): imperative subject, lower case, no trailing period

Why this was needed. What changed only where the diff doesn't already say it.
```

| type | use for |
|---|---|
| `feat` | new capability |
| `fix` | bug fix |
| `docs` | documentation only |
| `test` | tests only |
| `refactor` | behaviour-preserving restructure |
| `perf` | performance |
| `style` | formatting only, no logic |
| `build` | dependencies, packaging |
| `ci` | CI configuration |
| `chore` | anything else — tooling, config, vendored files |

Breaking changes: `type(scope)!: subject`, with a `BREAKING CHANGE:` footer.

Write **what** changed and **why** it was needed. The *why* is the part that carries value — a
reader six months from now needs the reasoning, not a restatement of the diff.

- Concise. No filler, no ceremony, no restating what the diff already shows.
- Subject line: imperative mood, under ~72 chars including the type prefix.
- Body: the reasoning. Skip it only when the subject genuinely says everything.
- One logical change per commit. If two types apply, it's two commits.
- Commit or push only when asked. Never commit to `main` without being asked.

---

## Project context

**TikTok TechJam 2026, Track 4 — Shopping Copilot.** Build a multi-turn conversational shopping agent that finds
a hidden target product in a frozen 50,000-item Amazon clothing catalog within **10 turns**.

```
TechnicalScore = 0.50·HitRate@10 + 0.30·MRR + 0.20·Efficiency
Efficiency     = clip((11 − MTTC) / 10, 0, 1)
```
Scored on 800 private sessions. ⚠️ TechnicalScore is only *an input to* the 35% Technical Execution criterion —
the other 65% is Innovation, Impact, Feasibility and Presentation.

### Where everything lives

| What | Path | Notes |
|---|---|---|
| **Problem statement** | [docs/PROBLEM.md](../docs/PROBLEM.md) | Official brief: four pillars, scope, limits, deliverables, judging |
| **Official kit** | [techjam-conversational-search-main/](../techjam-conversational-search-main/) | ⚠️ **Read-only.** Keep byte-identical to upstream or local scores are unverifiable |
| ├ evaluator + simulator | `…/evaluator/local_evaluator.py` | 312 lines. **This is both the referee and the simulated customer** |
| ├ weak starter | `…/starter/agent.py` | BM25/FTS5, scores 0.1067. Restore after every test |
| ├ 200 dev sessions | `…/data/public_set.jsonl` | 80 buying / 80 browsing / 30 override / 10 boundary |
| ├ rules | `…/docs/competition_specification.md`, `…/docs/submission_rules.md` | |
| └ contracts | `…/docs/agent_api_contract.json`, `…/docs/evaluation_config.json` | |
| **Catalog** | `assets/catalog.jsonl` | 50,000 products, 58 MB, **gitignored** — re-download from the release, verify with `assets/SHA256SUMS` |
| **Dataset docs** | [docs/AmazonReviews2023.md](../docs/AmazonReviews2023.md) | Field dictionary for Amazon Reviews 2023 |
| **Academic toolkit** | [AmazonReviews2023/](../AmazonReviews2023/) | Upstream McAuley Lab repo (MIT): BLaIR, Amazon-C4, ESCI. Reference only |
| **Experiments** | [experiments/](../experiments/) | Runnable scripts behind every number in IMPORTANT.md §12 |

**Setup before anything runs:** `cp assets/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl`
Models: `set -a && . ./.env && set +a` (`SOCLAAS_API_KEY`, `SOCLAAS_BASE_URL`; `.env` is gitignored — never commit it).

### Reference docs — read before writing code

- **[IMPORTANT.md](../IMPORTANT.md)** — **authoritative on facts.** Evaluator mechanics, the simulator-inversion
  finding, the popularity leak, **§12 measurements**, **§13 errors & learnings**, **§14 PROBLEM.md requirement
  audit**. Where any doc disagrees with it on a number or a rule, it wins.
- **[REPORT.md](../REPORT.md)** — the narrative: what the problem is and what we found. Read for *direction*.
- **[IDEA.md](../IDEA.md)** — proposals only: the 40-component index, the three exploration roads (§0.3), the
  shared contract (§0.4). Read before starting a road.

### Baselines — judge every idea against these

| | Score | |
|---|---|---|
| Shipped BM25 starter | `0.1067` | never compare against this |
| Popularity + category only | `0.7133` | ignores everything the customer says |
| **Paraphrase-proof floor** | **`0.826`** | ⚠️ **this is the bar** — blended dense + popularity, no template matching |
| Our prototype | `0.9607` | `experiments/agent_best_0.9607.py`, incumbent to beat |
| Theoretical maximum | `0.9922` | MTTC floors at 1.39 because override sessions cannot convert before turn 3 |

All remaining headroom is **MRR** (+0.075 available vs +0.012 from speed). Hit@10 is already 1.000.

---

## The three exploration roads

The agent can be conceived three ways. Each is one worktree. Full detail in [IDEA.md](../IDEA.md) §0.3.

| Road | The agent is… | Core structure | Fails on |
|---|---|---|---|
| 🔵 **R1** Constraint Satisfaction | a **filter** | shrinking candidate *set* — intersect, convert when it collapses | Browsing; paraphrase |
| 🟢 **R2** Retrieve & Rank | a **ranker** | scored *list* — fuse routes, order, take 10 | precision; never fully commits |
| 🟣 **R3** Bayesian Fusion = R1 + R2 | a **posterior** | `P(item) ∝ prior × Π likelihoods` — R1's matches and R2's scores as evidence terms | calibration; confidently wrong |

**Sequencing: R1 ∥ R2 in parallel, then R3 reuses both.** R3 is not a third guess — it is the principled merge:
popularity becomes the prior, R1's exact matching and R2's dense similarity become likelihood terms, and entropy
replaces the hand-tuned confidence gate. It cannot start until R1 and R2 have produced components to fuse.

### When to suggest a worktree

**Do suggest** splitting into a worktree when two approaches genuinely conflict — different data structure,
different loop, different failure mode — and we want both measured rather than argued about. Say which road it
belongs to and what would make it win or die.

**Do not** suggest one for a variation that will obviously be merged anyway (a different fusion weight, one extra
retrieval route, a prompt tweak). Those are flags and ablations inside an existing road, not new roads.

```bash
git worktree add ../r1-constraint idea/r1-constraint   # parallel
git worktree add ../r2-rank       idea/r2-rank         # parallel
git worktree add ../r3-bayesian   idea/r3-bayesian     # after R1 and R2
```
Every worktree runs the identical harness and appends to `runs/registry.jsonl` on `main`.
**A row without a paraphrase-stressed score and the four scenario breakdowns does not count** — a winner on the
clean set alone tells us nothing about the private set.

---

## Non-obvious traps (full list in [IMPORTANT.md](../IMPORTANT.md) §13)

1. `Agent.__init__(self, catalog_path=...)` is **positional and undocumented** — the evaluator calls it that way.
2. **Never import from `evaluator.local_evaluator`** — it imports `starter.agent`, so it is a circular import and
   crashes at startup. Copy the functions instead.
3. **Restore the pristine starter after testing.** Re-diff the kit against upstream before any reported score.
4. **Every LLM call must assert on a parsed non-empty result** — some models return `content: None` while burning
   the full token budget, and a silent failure looks exactly like a model that is not helping.
5. **Pin explicit model IDs**, never aliases (`default`, `test`, `ornith1.0:35b` are all aliases).
6. `ask_attribute: "other"` is the simulator's wildcard; `null` reveals nothing.
7. 200 sessions is small — **a 0.02 score gap is noise.** Bootstrap before declaring a winner.

---

## Spec-driven development — binding when working on a road

**Read the road's spec before writing code, and update it when a measurement changes a decision.**

| Road | Spec |
|---|---|
| 🟢 **R2** Retrieve & Rank | [docs/r2-exploration/](../docs/r2-exploration/) — [00-r2-spec.md](../docs/r2-exploration/00-r2-spec.md) (the bet, architecture, kill criteria) · [01-contracts.md](../docs/r2-exploration/01-contracts.md) (frozen seams, shared with R1/R3) · [02-acceptance.md](../docs/r2-exploration/02-acceptance.md) (`R2-A0..A10`) · [03-decisions.md](../docs/r2-exploration/03-decisions.md) (ADR log) |

The loop, in order, no steps skipped:

1. **Spec first.** Add or amend the entry in `00`/`01`, and give it an acceptance ID in `02` with the
   number it must hit and the test that proves it.
2. **Test second.** Write the test naming that ID in its docstring. Watch it fail *for the right reason*
   before writing any implementation.
3. **Implement third.** Minimum code that makes the test pass.
4. **Measure fourth.** Gates run the real evaluator; append a row to `runs/registry.jsonl`.
5. **Record.** When a measurement changes a decision — including reversing one — append to `03-decisions.md`.
   A rejected idea with its number is worth more than a silent deletion.

```bash
python3 -m unittest discover tests   # fast: parity, state, routes, contract (~60s)
python3 -m unittest tests.test_gates # slow: real evaluator runs
python3 -m src.eval.final            # the full comparison + registry rows
```

⚠️ **Do not tune on the clean public-set score.** It is 200 sessions and a 0.02 gap is noise. A change is
real only if it survives the bootstrap CI, and R2 is judged on its **stressed** and **`no_spec_phrase`**
numbers — the clean score is sanity, not the point.

⚠️ **The harness never writes to `starter/agent.py`.** It imports the evaluator's own `evaluate()` and
injects our agent. If you find yourself copying a file over the starter, you are using the wrong tool.
