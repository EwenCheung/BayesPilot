# R3 — Bayesian Fusion: handover

**Branch:** `r3-exploration` · **Worktree:** `../r3-bayesian` · **Status:** built, measured, merged R1+R2

If you read one thing, read [§2](#2-how-good-it-is-and-how-bad) and [§7 What is missing](#7-what-is-missing-read-before-you-trust-this).
R3 wins every measured condition and the win generalises to a held-out split — but three of the four
things IDEA.md promised this road would do **did not survive measurement**, and the two largest
contributors are not the clever parts.

---

## 1. What R3 is

The agent as a **posterior**, at two levels:

```
level 1   P(category | evidence)      over 1,115 coarse categories -> the pool, by mass
level 2   P(item | pool, evidence)    over the items in it         -> order, depth, when to stop
```

R1's exact matching and R2's scored routes become **evidence terms** in one belief. Popularity is the
prior. The decision of what to ship is expected utility over that posterior, not a tuned gate.

**The claim, and it is tested rather than asserted:** set the likelihood hard 0/1 and you recover R1;
read the posterior as a score and you recover R2. R3 is the generalisation both are special cases of.

---

## 2. How good it is, and how bad

Official evaluator, 200 public sessions, kit byte-identical, one rewriter, one ablation vocabulary,
no network. Full table: [docs/R3-RESULTS.md](../R3-RESULTS.md).

| Condition | 🔵 R1 | 🟢 R2 | 🟣 **R3** | R3 − best |
|---|---|---|---|---|
| **clean** | 0.9597 | 0.9707 | **0.9720** | +0.0013 |
| L1 scaffold | 0.7737 | 0.8305 | **0.8705** | +0.040 |
| L2 payloads | 0.7887 | 0.7872 | **0.8845** | **+0.096** |
| L3 category | 0.7241 | 0.6630 | **0.8297** | **+0.106** |
| `no_spec_phrase` | 0.9128 | 0.8315 | **0.9339** | +0.021 |

**Held out — tuned on 140, read once on 60:**

| | test60 clean | **test60 L3** |
|---|---|---|
| R1 | 0.9604 | 0.6740 |
| R2 | 0.9728 | 0.6863 |
| **R3** | 0.9708 | **0.8381** |

🔑 R3's held-out L3 (0.8381) is **higher than its training L3** (0.8261). The gain transfers.

### The good

- **Wins every condition**, and the paraphrase margins (+0.096, +0.106) are 3–5× the CI width.
- **Keeps R1's recall and R2's precision instead of trading them.** L3 Hit@10 0.915 against R1's 0.820
  and R2's 0.700. That is what fusing them was supposed to buy.
- **6 fitted constants** replace R2's 32 fusion weights + depth ladder + regime threshold and R1's NQC,
  deadline and three hedge constants.
- **Zero network calls, numpy only.** R2 needs scipy and scikit-learn; R3 needs neither.
- **And when a network IS available, +0.055 at L2 and +0.063 at L3** from the escalation-gated LLM
  extraction tier — for **0 calls and a bit-identical score on clean text** (D21).
- **The first held-out number in this project.** R1 and R2 both list its absence as a top defect.

### The bad — and this is the part that matters

**1. The clean win is noise.** 0.9720 vs 0.9707, CIs overlapping almost entirely. Do not claim it.

**2. Three of IDEA.md's four promises for this road failed measurement.**

| IDEA.md §0.3 promised | Outcome |
|---|---|
| popularity as the prior | ✅ holds — and it is the largest contributor (−0.121 to remove) |
| R1 + R2 as likelihood terms | ✅ holds — L3 Hit@10 0.915 vs 0.820 / 0.700 |
| EIG question selection "now exact over a real distribution" | ❌ **worse at every level** (−0.021 clean, −0.040 L3). Shipped off (D18) |
| "entropy replaces the hand-tuned confidence gate" | ❌ entropy separates clean from stressed only 1.34×; the policy reads **expected utility**, not entropy (D15) |

**3. The two biggest wins are unglamorous.** The popularity prior's **units** (`log1p(rating)` spans
0–11 while one exact match is worth 3.2 — it was outvoting three exact matches) was worth **+0.066**.
Switching EIG off was worth **+0.040**. The category belief — the road's headline idea — is worth
**+0.054**, real but third.

**4. No semantic term — and that is now a measured result, not a gap.** TF-IDF/SVD and BLaIR
(`hyp1231/blair-roberta-base`, pretrained on this exact corpus, all 50k embedded) were both built and
run as evidence terms. BLaIR at its best scores **0.8953 mean against 0.8954 without it**; the SVD
version is actively harmful. Kill gate R3-A23 fires and both are dropped (D19, D20). **The reason is
structural: the simulator draws its constraints verbatim from the catalog's own text, so there is no
vocabulary gap for a semantic model to close.**

**Honest summary: R3 wins, the win generalises, and the reasons are mostly not the ones predicted.**

---

## 3. The algorithm

```
utterance ─ parse (template → ontology → LLM escalation) ─► Evidence
     │
     ├─ LEVEL 1  log P(c) = idf-weighted stemmed name match / T
     │           pool = smallest set of categories with Σ P(c) ≥ τ_mass
     │
     ├─ LEVEL 2  log P(i) = prior_weight·log1p(rating) + Σ_t w_t · log L(e_t | i)
     │           terms: exact card string · normalised (attribute,value) · token overlap
     │           every factor bounded below — no evidence may zero an item
     │
     └─ POLICY   ship k maximising  U(k) = Σ_{i≤k} p_i/i + (1 − Σ_{i≤k} p_i)·V
                 V = v_continue · stall_decay^(consecutive barren turns) − 0.0667
```

**Three details carry most of the result:**

🔑 **A term with no evidence abstains and cancels.** R2 needed a hand-coded `spec_support < 0.60` regime
switch to stop popularity swamping the other routes under paraphrase. Here a term matching nothing
returns `{}` and contributes nothing. Tested by D17: adding a channel-conditioned gain on top bought
**zero**, because the abstention already did the job.

🔑 **`U(0) = V`, so "say nothing this turn" is the k=0 case,** not a special rule. `turn_cost = 0.0667`
is not a knob — one turn costs 0.2 × 0.1 of efficiency against MRR's weight of 0.3.

🔑 **`V` must not be constant.** With constant `V`, `U(1) − U(0) = p₁(1−V) > 0` and `U(2) − U(1) =
p₂(0.5−V) < 0` unconditionally, so the agent ships exactly one item forever. It scored 0.6216 at L3 and
sweeping `V` changed *nothing* — which is how the degeneracy was caught (D15).

---

## 4. Repository map

```
docs/r3-exploration/
  00-r3-spec.md      the bet, architecture, kill criteria
  01-contracts.md    frozen seams; the rule that R3 imports nothing from R1/R2
  02-acceptance.md   M1-M8 and R3-A1..A31, each with its number and its test
  03-decisions.md    D1-D18 — including four reversals, which are the useful entries
  04-merge-plan.md   the merge, its gates, and the corrected R1-vs-R2 table
docs/R3-RESULTS.md   every number above, regenerated by scripts/final.py
src/r3/
  category.py   level 1 — P(category | utterance), pool by mass
  index.py      one item index (R1 and R2 each had their own)
  likelihood.py the evidence terms; abstention and the lower bound
  belief.py     level 2 — the posterior, entropy, expected-utility depth
  question.py   EIG — built, measured, SHIPPED OFF (D18)
  agent.py      the Agent the evaluator constructs
  flags.py      6 fitted constants + 2 structural
src/eval/
  race.py       ⭐ one runner, roads by name
  ablations.py  ⭐ one vocabulary — `no_spec_phrase` means the same thing in every road
  stress.py     ⭐ one rewriter, L0-L4
  holdout.py    the immutable 140/60, hash a367f15873d772aa
scripts/
  final.py           the full race → runs/final.json
  fit_policy.py      staged fit on the 140
  category_probe.py  the probe that killed the original thesis (D13)
```

---

## 5. How to run it

```bash
ln -sf /path/to/assets/catalog.jsonl assets/catalog.jsonl
ln -sf /path/to/assets/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl

python3 -m pytest tests/ -q                  # 111 tests, ~85 s
python3 -m unittest tests.test_gates         # calibration: starter 0.10671, seed 0.9607
python3 -m src.eval.race                     # all three roads, clean
python3 -m src.eval.race --stress 3          # ...under category paraphrase
python3 scripts/final.py                     # the full table + held-out → runs/final.json
```

`R3_FLAGS=no_belief_pool,infogain,prior_weight=0.5` — `no_<flag>` disables, `<flag>` enables,
`name=value` sets. **Dependencies: numpy.** No network on the default path.

---

## 6. Traps (all of these cost an hour here)

1. **Never import `evaluator.local_evaluator` from agent code** — it does `from starter.agent import
   Agent` at module scope. Two AST tests guard this; one of them caught a real mistake during the merge.
2. **`Agent.__init__(self, catalog_path=...)` is positional and undocumented.**
3. **Never iterate a `set` where order matters** — hash salting drifted scores in both roads.
4. **`usage` is summed across turns by the evaluator.** Return per-turn deltas.
5. **`log1p(rating_number)` is not a log-probability.** It spans 0–11 and will silently outvote your
   evidence. This cost 0.066 (D16).
6. **A constant in an expected-utility formula can make the formula degenerate** without ever looking
   wrong (D15).
7. **A stress harness that interpolates `{category}` verbatim does not test category resolution.** It
   reported 100% accuracy and hid the entire problem (D13).

---

## 7. What is missing — read before you trust this

1. **No calibration.** Phase P3 (isotonic on synthetic sessions), ECE and reliability curves are not
   built (R3-A7, R3-A15–A17). The posterior is *used* as a probability but has never been *shown* to be
   one, and "confidently wrong" is this road's named failure mode.
2. **No L4.** Model-written paraphrase needs the endpoint. L3 is a good free proxy — it reproduces R1's
   published LLM-written L3 to 0.0005 — but a proxy.
3. **The LLM tier's gain is a lower bound.** Measured at +0.055 / +0.063 (D21) while the shared endpoint
   failed 27–80% of calls. Not re-measured uncontended.
4. **The tagging/classification models from D12 are unbuilt.** They were promoted into P3 and P3 did not
   happen.
5. **Boundary is 10 sessions.** Its MRR moves 0.10 when one session changes rank. Never read it alone.
6. **`temperature` and `tau_mass` were fitted on category coverage.** Re-fitted jointly on end-to-end
   score afterwards: clean and L2 are completely insensitive to both, and L3 moves 0.006. Non-issue,
   but worth knowing they are flat rather than tuned.

## 8. How to pick this up

1. **Calibrate (P3)** and publish the reliability curve — the one claim R3 makes that is still
   unevidenced, and its named failure mode is "confidently wrong".
2. **Re-measure the LLM tier on an uncontended endpoint** — its +0.055/+0.063 was taken while 27–80% of
   calls were failing.
3. **Run L4** on a quiet endpoint with pinned model IDs.
4. **Attack the remaining L3 losses as ranking, not recall.** Category coverage is 0.967 and Hit@10 is
   0.915, so ~5% is the target sitting in the pool below rank 10.

**Do not repeat these — measured and rejected:**

- Per-category naive Bayes over product titles for category resolution (0.525 vs 0.825 — D14).
- **Semantic retrieval, four times over**: `bge-m3` (R2), a teammate's dense route, TF-IDF/SVD (D19),
  and **BLaIR pretrained on this exact corpus** (D20). The last one closes the "but it was a generic
  encoder" objection to the first three.
- EIG question selection (−0.021 clean, −0.040 L3 — D18).
- Entropy as the patience signal (1.34× separation vs p₁'s 2.4× — D15).
- Channel-conditioned `exact_gain` (bought exactly zero — D17).
- Raw `log1p(rating)` as a log-prior (−0.066 — D16).

⚠️ **TechnicalScore is an input to the 35% Technical Execution criterion, not the score.** R3's most
defensible contribution is not 0.9720 — it is the held-out table, the four recorded reversals, and the
fact that the merge proved R1's and R2's published robustness numbers were never comparable.
