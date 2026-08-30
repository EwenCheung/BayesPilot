# R4 — Early Convergence: handover

**Branch:** `Daeren-branch` · **Status:** Phase F and Phase I complete, Phase C killed by its own gate,
Phase S measured and subsumed

If you read one thing, read [§2](#2-how-good-it-is-and-how-bad) and
[§7 What is missing](#7-what-is-missing-read-before-you-trust-this).

**In one line: one correctness fix and one re-fitted constant take dev from 0.9188 to 0.9499, and
both came from finding that the previous road was measuring itself on a saturated 200-session set.**
Nothing R4 shipped was in the plan it started from.

---

## 1. What R4 is

R3's Bayesian posterior, unchanged, plus **one rule and one re-fit**. It is not a new architecture,
and `tests/test_r4_reduces_to_r3.py` enforces that: with its new mechanisms off and its constants
reset to R3's, R4 reproduces R3 **bit-for-bit** — identical per-session rank *and* turn on 200 and on
12,000 sessions.

The road asks a different question from the first three. R1 (filter), R2 (ranker) and R3 (posterior)
all answer *"which item?"*. R4 asks *"is what I have good enough to ship **now**?"* — and the answer
turned out to be that the agent's stopping was already near-optimal, while two other things were
quietly broken.

```
utterance ─ parse (template → ontology → LLM escalation)          unchanged from R3
     ├─ LEVEL 1  P(category | evidence) → pool by mass            unchanged from R3
     ├─ LEVEL 2  P(item | pool, evidence)                         prior_weight now 0.0
     ├─ NEW      survival: P(item | survived a checked turn) = 0
     └─ POLICY   ship k maximising U(k) = Σ pᵢ/i + (1−Σpᵢ)·V      unchanged from R3
```

---

## 2. How good it is, and how bad

Official evaluator, kit byte-identical, `R3_OFFLINE=1`, `PYTHONHASHSEED=0`, no network.
Full table: [docs/R4-RESULTS.md](../R4-RESULTS.md).

**Fitted on `train.jsonl` (12,000). `dev.jsonl` and the official 200 are read for reporting only.**

| dev.jsonl, n=2000 | Hit@10 | MRR | MTTC | Score | 95% CI |
|---|---|---|---|---|---|
| R3 | 0.970 | 0.9167 | 3.05 | 0.9188 | (0.9108, 0.9268) |
| **R4** | **0.987** | **0.9713** | **2.73** | **0.9499** | (0.9442, 0.9546) |

Non-overlapping CIs. Per scenario, R4 on dev:

| scenario | n | Hit@10 | MRR | MTTC |
|---|---|---|---|---|
| buying | 800 | 0.9900 | 0.9765 | 2.21 |
| browsing | 800 | 0.9825 | 0.9660 | 2.73 |
| intent_override | 300 | 0.9933 | 0.9735 | 3.81 |
| boundary | 100 | 0.9700 | 0.9650 | 3.74 |

🔑 `intent_override` — the scenario with a *structural* floor at turn 3–4 and the worst scenario for
every previous road — is now the **best** on Hit@10 (0.9933). Those sessions get free turns 1–2 that
the evaluator discards, and R4 is the first road to use them: it ships, learns the items were wrong,
and excludes them.

### The good

- **+0.031 on dev, +0.027 on train, and the two agree to 0.003** — the signature of a change with no
  fitted parameters, which `exclude_shipped` is.
- **Robustness is where it pays.** On train, L2 +0.054 and L3 +0.065 from the re-fit alone, on top of
  L1/L2/L3 gains of +0.11 to +0.14 from `exclude_shipped`. Clean barely moves; that is the point.
- **Fewer constants, not more.** R4 ships one new boolean and three re-fitted numbers, one of which is
  now zero — so the system has *less* tuning surface than R3, not more.
- **6.4 ms/session, zero network calls, numpy only.** 2,000 dev sessions in 12.8 s.
- **Everything is fitted on `train.jsonl`**, enforced by an AST test that fails the build if fitting
  code so much as names an evaluation set.

### The bad — and this is the part that matters

**1. Two of the four planned phases were killed by their own gates, and that is most of R4's value.**

| Phase | Planned | Outcome |
|---|---|---|
| F — foundation | reproduce R3, split the data | ✅ and found the bug that carries the road |
| I — instrument | build `EarlyHit@k` | ✅ built, and it **killed Phase C** |
| C — calibration | calibrated top-k confidence | 🔴 **not built.** Ceiling measured at **+0.0033** |
| S — selectivity | adaptive prior | 🔴 **subsumed.** Every adaptive config loses to `prior_weight = 0` |

**2. The headline gain is a bug fix, not an idea.** `exclude_shipped` is arithmetic from reading the
evaluator: it breaks on first hit, so surviving a hit-checked turn *proves* every shipped item is not
the target. R3 threw that away and re-shipped identical lists — 43 of 43 sessions alive at turn 5
shipped a list turn 4 had already disproved.

**3. The second gain reverses a headline finding of the whole project.** `prior_weight` re-fits to
**zero**: deleting the popularity prior is worth +0.092 on the train objective. IMPORTANT.md §5 calls
that prior *"the biggest free win in the whole problem"*. Both are true — the prior was worth +0.24 to
R1 and is worth ≤ 0 to R4, because `exclude_shipped` removed the thing it was good for. See
[D14](03-decisions.md#d14).

**4. Almost nothing the road was designed to do survived.** Of the original proposal: the persistent
candidate pool was already R3's posterior (D2), better question selection is measured-worse *and*
unanswerable by the simulator (D3), dynamic truncation is measured-negative (D4), calibration was
capped at +0.0033 (D12), and the adaptive prior was subsumed (D14). **The two things that worked were
found by measuring, not by planning.**

---

## 3. The five things that actually changed

| # | Change | Worth | Where |
|---|---|---|---|
| 1 | `exclude_shipped` — survival is evidence | **+0.027 train, +0.028 dev** | [D8](03-decisions.md#d8) |
| 2 | `prior_weight` 0.18 → **0.00** | **+0.092 train objective** | [D14](03-decisions.md#d14) |
| 3 | `v_continue` 0.90 → 0.75, `tau_mass` 0.90 → 0.85 | +0.002 combined | [D14](03-decisions.md#d14) |
| 4 | `train.jsonl` as the only fitting set | correctness, not score | [D11](03-decisions.md#d11) |
| 5 | `runs/holdout.json` actually committed | correctness | [D5](03-decisions.md#d5) |

---

## 4. Repository map

```
docs/r4-exploration/
  00-r4-spec.md      the bet, the motivating measurements, kill criteria
  01-contracts.md    frozen seams: the R3 inheritance exception, the offline/runtime barrier,
                     and the fit-on-train rule
  02-acceptance.md   R4-A0..A29 across five phases, each with its number and its test
  03-decisions.md    D1-D14 — the negatives are the useful entries
docs/R4-RESULTS.md   every number, regenerable
src/r4/
  agent.py       R3's loop + survival evidence. `_respond` is COPIED, not called — see its docstring
  belief.py      Phase S: `flatness()` and `SelectiveBelief`. Ships OFF (D14), kept for the negative
  flags.py       the train-fitted constants + every mechanism behind a switch
  instrument.py  ⚠️ OFFLINE ONLY. TurnTrace / EarlyHit curves. The agent must never import it
src/eval/
  datasets.py    train / dev / public, and the rule about which one you may fit on
  race.py        ⭐ one runner — now with `--dataset`, `--limit`, `--ci`, `--scenarios`
scripts/
  fit_r4.py      the staged re-fit, train only
  earlyhit.py    R4-A7/A8 — the curve that killed Phase C
```

---

## 5. How to run it

```bash
ln -sf /path/to/catalog.jsonl assets/catalog.jsonl
ln -sf /path/to/catalog.jsonl techjam-conversational-search-main/data/catalog.jsonl

# the headline number
R3_OFFLINE=1 PYTHONHASHSEED=0 R4_FLAGS=exclude_shipped \
  python3 -m src.eval.race --dataset dev --roads r3,r4 --ci --scenarios

# under paraphrase (L1 scaffold · L2 payloads · L3 category)
... --dataset dev --roads r4 --stress 3

python3 -m pytest tests/ -q          # 140 tests
python3 scripts/earlyhit.py 4000     # the EarlyHit curve
python3 scripts/fit_r4.py 2500       # re-fit on train (~55 min)
```

⚠️ The env vars are not optional. `R3_OFFLINE=1` stops a warm `.cache/llm` turning the offline path
into the LLM path with zero network calls; `PYTHONHASHSEED=0` because set iteration order drifted
scores in two earlier roads.

---

## 6. Traps (each of these cost real time here)

1. **A default value is not a measurement.** `SessionState.route` defaults to `"browsing"`, so
   `route != "override"` is *also* what an unparsed opener looks like. Reading the default as proof
   turned 9 override sessions into misses at L3 ([D9](03-decisions.md#d9)).
2. **"Penalise what is probably wrong" is worse than ignoring it.** An unchecked turn's top item is
   the one *most* likely to be the target. Softening a hard exclusion into a penalty cost 0.068 on
   clean and halved override MRR ([D9](03-decisions.md#d9)).
3. **A tuning gain measured on top of a bug is a measurement of the bug.** `stall_decay_clean = 0.4`
   looked worth +0.0075 on dev; once the re-shipping bug was fixed the whole range 0.2–0.8 spanned
   0.002 ([D11](03-decisions.md#d11)).
4. **A boundary optimum is not an optimum.** `prior_weight` won at the low edge of its swept range;
   extending downward moved it to zero and changed the road's conclusion ([D14](03-decisions.md#d14)).
5. **`log(L_MIN)` is not the no-match value.** That floor never binds at `exact_gain = 3.2`, so a
   first `flatness()` called perfectly sharp evidence maximally flat. A unit test caught it; an
   end-to-end sweep would have reported "the mechanism buys nothing" and been believed
   ([D13](03-decisions.md#d13)).
6. **Setting an env var at test-module scope leaks into every module imported afterwards.** It
   silently broke three `tests/test_llm.py` cases that pass in isolation.
7. **A metric read off shipped lists is MTTC wearing a different name.** The evaluator breaks on first
   hit, so a shipped target's rank never evolves — `FirstHit@k` is only informative on the *internal*
   ranking, captured before the ship/hold decision ([D5](03-decisions.md#d5)).

---

## 7. What is missing — read before you trust this

0. ⚠️ **`prior_weight = 0` reverses a project-level finding on a single re-fit.** It is fitted on
   12,000 disjoint sessions with a favourable risk profile in both directions (L0 is flat across the
   whole range, so it costs nothing if the private set is un-paraphrased and gains ~0.09 if it is) —
   but it has not been independently reproduced and it contradicts IMPORTANT.md §5. **Re-derive it
   before relying on it.**
1. **Train stress numbers are on a 4,000-session subset**, not all 12,000 — L3 on the full set is
   ~7 minutes per road. Clean numbers are the full 12,000.
2. **The stress levels do not transfer between datasets.** R3 scores 0.8299 at L3 on the official 200
   and 0.4250 on dev — a gap of 0.41 that no property of the agent explains. The rewriter's vocabulary
   was probably built against the 200. Deltas between agents are safe; absolute levels are not
   ([D10](03-decisions.md#d10)).
3. **The official 200 is saturated and is no longer a discriminator.** R4 scores Hit 1.0000 and MRR
   1.0000 there. Use dev.
4. **No calibration, no reliability curve, no ECE.** Phase C was killed on ceiling, not attempted and
   failed — the posterior is still *used* as a probability without ever being *shown* to be one.
5. **No L4** (model-written paraphrase). Needs the endpoint.
6. **The LLM extraction tier is untouched by R4** and contributes to none of these numbers.
7. **Boundary is 100 sessions on dev, 10 on the official 200.** Never read it alone.

---

## 8. How to pick this up

1. **Reproduce D14 independently.** It is the largest and least-corroborated claim here. If it holds,
   IMPORTANT.md §5 and REPORT.md Discovery 2 need rewriting, and the "paraphrase-proof floor of 0.826"
   — which is *built on* the popularity prior — needs re-deriving.
2. **Re-baseline the remaining headroom.** D12's decomposition (recall vs ranking vs stopping) was
   measured before the re-fit, so its numbers are stale even though its method is sound.
3. **Reconcile the root docs.** IMPORTANT.md and REPORT.md still say all remaining headroom is MRR
   ([D1](03-decisions.md#d1)) and that popularity is the biggest free win ([D14](03-decisions.md#d14)).
   Both are now contradicted by larger samples. R4 did not edit them.
4. **Run the full 12,000 at L2/L3** on a machine with time to spare.

**Do not repeat these — measured and rejected here:**

- Calibrated top-k confidence for stopping (ceiling +0.0033 — [D12](03-decisions.md#d12)).
- Adaptive prior damping by evidence selectivity (loses to `prior_weight = 0` — [D14](03-decisions.md#d14)).
- Dynamic truncation (k=3 costs ~0.012; rank is the index in your own list — [D4](03-decisions.md#d4)).
- Better question selection (measured worse, and the simulator holds only four constraint strings —
  [D3](03-decisions.md#d3)).
- A soft penalty for unproven-wrong items (−0.068 clean — [D9](03-decisions.md#d9)).
- Splitting `dev.jsonl` into train/test halves ([D11](03-decisions.md#d11)).

⚠️ **TechnicalScore is an input to the 35% Technical Execution criterion, not the score.** R4's most
defensible contribution is not 0.9499 — it is that two of its four planned phases were killed by
gates it set for itself in advance, and that the two changes which did work were both found by
measuring the previous road rather than by building something new.
