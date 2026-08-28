# Merge plan — R1 + R2 → `r3-exploration`

**Blocks R3.** Nothing in `src/r3/` may be written until every gate below is green.

The merge lands on **`r3-exploration` only**. `main` stays untouched (CLAUDE.md §6: never commit to
`main` without being asked).

---

## 1. Why this is a deliverable, not plumbing

R1 defect #1, R1 defect #2 and R2's open `A8` are all the same problem: **the two roads' robustness
numbers are not comparable, so there is currently no race, only two scoreboards.**

| Quoted as if comparable | R1 | R2 | Actually |
|---|---|---|---|
| `no_spec_phrase` | 0.9260 | 0.8315 | R1's switch disables only the *exact* matcher; its attribute and token matchers still read the same template text and recover most of it. R2's removes the whole inversion route. **R1's is the weaker ablation and overstates it by ~0.09.** |
| paraphrase stress | 0.8594 (L2) | 0.7961 (heavy) | Two different rewriter programs with different aggression. The comparison says nothing. |

**Fixing this is the single highest-value item on both roads' own "how to pick this up" lists.** It is
worth doing whether or not R3 is ever built, which is why it comes first and why it has its own gates.

---

## 2. Conflicts — the real list

`git merge-tree --write-tree r1-exploration r2-exploration` reports **exactly six**;
`.claude/CLAUDE.md` auto-merges.

| File | Resolution | Risk |
|---|---|---|
| `.gitignore` | union, **minus** the `runs/registry.jsonl` ignore — see §4 | none |
| `SUMMARY.md` | split → `docs/r1-exploration/SUMMARY.md`, `docs/r2-exploration/SUMMARY.md`; new root `SUMMARY.md` indexes the three roads | docs only |
| `src/common/simulator.py` | **one file**, union of functions. Both are verbatim copies of the same evaluator code; both roads' kit-parity tests are kept and both must pass against the merged file | low, and tested |
| `src/common/catalog.py` | **split**, not unified → `src/r1/catalog.py`, `src/r2/catalog.py`; mechanical `sed` on the import lines | none if §3 passes |
| `src/eval/compare.py` | **unify** — the work of this merge, §3 | this is where care goes |
| `src/eval/stress.py` | **unify** — one rewriter, §3 | same |

### Why `catalog.py` is split rather than unified

The two `CatalogIndex` classes have genuinely different APIs (R1: `pool` / `best_category` /
`ranked_categories` / `hedge` / `pool_features`; R2: `candidates` / `resolve_category`). Unifying them
would silently rewrite the data both roads' published numbers were produced from, and any drift would
be impossible to attribute.

R1 and R2 are **frozen baselines** after this merge. They exist to be raced, not extended. The
duplication is temporary and is deleted at Phase 2 (converge). **R3 does not inherit it** — R3 builds
its own single index (see [01-contracts.md](01-contracts.md) §2), which is where the unification
actually belongs.

---

## 3. The unified harness — the substance

### 3.1 One runner

Adopt **R2's in-process harness** (`src/eval/harness.py`), which imports the evaluator's own
`evaluate()` and hands it an agent instance. R1's SUMMARY §5 explicitly recommends this: no shim into
`starter/agent.py`, no restore step, no 9-second index rebuild per variant, and ablation flags reach
the constructor.

Keep **R1's SHA-256 kit manifest** (`src/eval/kit_manifest.json`) on top: verify every kit file a score
depends on before and after each run, and refuse to record a run whose check fails. R2's approach is
faster; R1's is more paranoid; there is no reason not to have both.

`PYTHONHASHSEED=0` stays pinned (R1 trap 3 — set iteration order silently drifted scores by 0.001).

### 3.2 One paraphrase rewriter

R1 ships 4 levels, R2 ships 3, and they are different programs. Take **R1's ladder** (L0–L3) because L3
is model-written and is the harshest honest proxy available, and fold in any R2 rewrite rule L1–L2 does
not already cover. One rewriter, one level vocabulary, applied identically to all three roads.

It wraps the **agent**, never the evaluator. The evaluator, the labels and the exact-code hit check are
untouched; the agent simply hears a reworded version of the same sentence. That is the only
rules-compliant way to ask *"what if the organizer paraphrases the private set?"*

### 3.3 One ablation vocabulary

`no_spec_phrase` must mean **the same removal** in every road: *remove all credit derived from the
simulator's inverted spec strings, including partial credit* — R2's definition, which is the strict one.
R1's flag is strengthened to match, so R1's 0.9260 will move down. **That is the correction, not a
regression.**

Same for `no_popularity`, `no_dense`, `no_lexical`, `no_llm`. One definition, defined here, applied by
one flag parser.

---

## 4. The registry

`runs/registry.jsonl` is **gitignored on both branches**, which silently breaks CLAUDE.md's *"every
worktree appends to `runs/registry.jsonl`"* — the race has no shared record. Un-ignore the registry;
keep raw per-run dumps and `.cache/` ignored.

Row schema is IDEA.md Part IV, plus one new required field:

```
"holdout": {"train_140": 0.0, "test_60": 0.0}
```

---

## 5. Gates — the merge is not done until all of these are green

| ID | Gate | Why |
|---|---|---|
| **M1** | Both test suites pass as one suite: R1's 59 pytest + R2's 38 unittest | the merge broke nothing |
| **M2** | Calibration: the unified harness reproduces the official starter at **0.106710** and the seed prototype at **0.9607**, exactly | R2's `A0` — a harness that cannot reproduce known numbers cannot report new ones. It has already caught one real bug |
| **M3** | R1 clean reproduces **0.9597**; R2 clean reproduces **0.9707** | the merge is score-neutral where it must be |
| **M4** | Kit byte-identical to upstream, verified before and after | a score from a mutated kit is unverifiable |
| **M5** | No module under `src/` imports `evaluator.local_evaluator` (AST test; harness and tests exempt) | R1 trap 1 — circular import, hard crash at startup |
| **M6** | Two subprocess index builds produce identical output | R1 trap 3 / R2 trap 3 — hash-order drift |

**Expected to change, and this is the deliverable:** every stress and ablation number for both roads.
Publish the corrected side-by-side table in `docs/r3-exploration/04-merge-plan.md` §7 and correct both
roads' SUMMARY files in the same commit. Numbers moving here is the merge working.

---

## 6. Held-out split — lands with the merge, blocks all R3 tuning

R1 defect #3 and R2 defect #1 are both this. R3 adds calibration parameters, so it is the road most able
to overfit 200 sessions invisibly — a bootstrap CI resamples the very sessions the parameters were
tuned on and cannot detect it.

- **140 / 60**, scenario-stratified (buying / browsing / intent_override / boundary).
- **Disjoint on sample ID *and* target ASIN** — the same product appearing in both halves leaks.
- Committed as an immutable manifest with a content hash; a test asserts disjointness on both keys and
  that the hash has not moved.
- Every R3 threshold is tuned on the 140 and **reported on the 60**, plus the full 200 for
  comparability with R1 and R2's published numbers.

⚠️ Boundary is 10 sessions total; a 7/3 split of it is noise on both sides. Report it, never read it
alone.

---

## 7. Corrected comparison table

*(filled in when the merge gates are green — this section is the merge's output)*

| Road | Clean | L2 | L3 | `no_spec_phrase` | Hit@10 clean | Hit@10 L3 | 95% CI |
|---|---|---|---|---|---|---|---|
| R1 | | | | | | | |
| R2 | | | | | | | |
