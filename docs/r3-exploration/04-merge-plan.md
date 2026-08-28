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

One harness, one rewriter, one `no_spec_phrase`. Deterministic paths only — no LLM tier, no network —
so these are the offline numbers both roads ship by default. 95% bootstrap CI, 1,000 resamples.

| Road | Condition | Hit@10 | MRR | MTTC | Score | 95% CI |
|---|---|---|---|---|---|---|
| R1 | clean | 1.000 | 0.9692 | 2.55 | **0.9597** | 0.9529–0.9658 |
| R1 | L1 scaffold | 0.870 | 0.6382 | 3.64 | 0.7737 | 0.7296–0.8155 |
| R1 | **L2 full** | 0.890 | 0.6437 | 3.47 | **0.7887** | 0.7479–0.8278 |
| R1 | **no_spec_phrase** | **0.995** | 0.8399 | 2.83 | **0.9128** | 0.8967–0.9261 |
| R1 | no_popularity | 0.985 | 0.8699 | 2.67 | 0.9200 | 0.8988–0.9377 |
| R2 | clean | 1.000 | 0.9746 | 2.08 | **0.9707** | 0.9630–0.9774 |
| R2 | L1 scaffold | 0.865 | 0.8196 | 3.40 | 0.8305 | 0.7838–0.8764 |
| R2 | **L2 full** | 0.835 | 0.7500 | 3.77 | **0.7872** | 0.7375–0.8364 |
| R2 | **no_spec_phrase** | 0.890 | 0.7781 | 3.35 | **0.8315** | 0.7894–0.8735 |
| R2 | no_popularity | 0.985 | 0.9103 | 2.69 | 0.9318 | 0.9126–0.9482 |

### 7.1 What the correction changed

**① R1's `no_spec_phrase` was overstated — but far less than R1 itself estimated.** 0.9260 → **0.9128**,
a drop of 0.013. R1 defect 1 predicted *"roughly 0.09"*. R1 was wrong about its own weakness: even with
exact matching **and** normalised-pair matching removed, its token-overlap matcher plus the popularity
prior plus the category pool still reach **Hit@10 0.995**.

**② ⭐ R1 without inversion beats R2 without inversion by 0.081** — 0.9128 against 0.8315, on Hit@10
0.995 against 0.890, with the CIs barely touching. R2's handover concluded *"R2's paraphrase-proof
insurance number is beaten by an ordinary non-inversion pipeline"* and pointed at a teammate's
0.9044. **The better non-inversion pipeline was R1 all along**, and nobody could see it because the two
roads' flags meant different things. R1 also edges that teammate baseline (0.9128 vs 0.9044).

**③ Under real paraphrase the two roads are indistinguishable.** L2: R1 0.7887, R2 0.7872 — a gap of
0.0015 inside CIs spanning 0.08. The published comparison (R1 "0.8594 at L2" against R2 "0.7961 heavy")
was two different rewriter programs and said nothing whatsoever. R1's 0.7887 reproduces its own
published *deterministic-only* L2 to four decimals, which is the evidence that the unified rewriter is
faithful to R1's original.

**④ The recall failure is caused by paraphrase, not by losing inversion.** This is the finding that
matters for R3:

| Condition | R1 Hit@10 | R2 Hit@10 | |
|---|---|---|---|
| inversion removed, wording intact | **0.995** | 0.890 | recall is fine |
| wording changed (L2) | **0.890** | 0.835 | recall breaks |

Removing the inversion signal costs R1 nothing in recall. **Changing the wording costs it 10 points.**
That isolates the damage to the stages that read raw wording — and the earliest of those is category
resolution, which [00-r3-spec.md](00-r3-spec.md) §2.3 identifies as lexical word-counting in both
roads. The two-level belief (D10) is aimed at exactly this, and the gate moves accordingly: **R3-A3 is
now L2 Hit@10 ≥ 0.95 against a current best of 0.890**, not the 0.890→0.90 the earlier draft asked for.

⚠️ **L3 (model-written paraphrase) is not in this table** — it needs the LLM endpoint, and these are the
offline defaults. It runs in P6 with pinned model IDs.

⚠️ **R1's clean 0.9597 here is the deterministic path.** Its published 0.8594 at L2 came with the LLM
extraction tier on, which is worth ~+0.07 under stress and 0.0000 on clean. Both are true; they answer
different questions.
