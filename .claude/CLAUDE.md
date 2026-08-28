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

**TikTok TechJam 2026, Track 4 — Shopping Copilot.** Build a multi-turn conversational shopping agent that
finds a hidden target product in a frozen 50,000-item Amazon clothing catalog within 10 turns. Scored by
`TechnicalScore = 0.50·HitRate@10 + 0.30·MRR + 0.20·Efficiency` on 800 private sessions.

- Official kit (read-only, keep byte-identical to upstream): `techjam-conversational-search-main/`
- Problem statement: [docs/PROBLEM.md](../docs/PROBLEM.md)
- Baselines: BM25 starter `0.1067` · paraphrase-proof floor `0.826` · our prototype `0.9607` · max `0.9922`
- ⚠️ Judge new ideas against **0.826**, never against 0.1067.

### Reference docs (update these when a measurement changes a recommendation)

- **[IMPORTANT.md](../IMPORTANT.md)** — verified facts, exact numbers, traps, measurements (§12), errors &
  learnings (§13), PROBLEM.md requirement audit (§14). **Authoritative — read before writing code or quoting
  a number.** Where it disagrees with anything else, it wins.
- **[REPORT.md](../REPORT.md)** — the narrative: why the task works the way it does and what we found.
  Read when deciding *direction*, not for every small task.
- **[IDEA.md](../IDEA.md)** — proposals only: the 40-idea index, the four competing tracks (§0.3), and the
  frozen interface contract (§0.4). Read before starting a track.
- [experiments/](../experiments/) — runnable scripts behind every number in IMPORTANT.md §12.

### Non-obvious traps (full list in IMPORTANT.md §13)

- `Agent.__init__(self, catalog_path=...)` is positional and undocumented — the evaluator calls it that way.
- **Never import from `evaluator.local_evaluator`** — it imports `starter.agent`, so it is a circular import.
- Restore the pristine starter after testing; the kit must stay byte-identical to upstream.
- Every LLM call must assert on a parsed non-empty result — some models fail silently with `content: None`.
