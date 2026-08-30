# R4 — results

All numbers from the **official evaluator**, kit verified byte-identical to upstream, one paraphrase
rewriter, one runner (`src/eval/race.py`). 95% bootstrap CI, 1,000 resamples, `PYTHONHASHSEED=0`.

**Deterministic paths only — no network calls, no LLM tier**, enforced under `R3_OFFLINE=1`.

```bash
R3_OFFLINE=1 PYTHONHASHSEED=0 R4_FLAGS=exclude_shipped \
  python3 -m src.eval.race --dataset dev --roads r3,r4 --ci --scenarios
```

**Fitted on `train.jsonl` (12,000).** `dev.jsonl` (2,000) and the official 200 are read for reporting
only; their target ASINs are disjoint from train and from each other
([src/eval/datasets.py](../src/eval/datasets.py)).

> ⚠️ **Read [§6](#6-the-conflict-the-official-200-disagrees) before quoting anything from the official
> 200.** Train and dev agree with each other and both disagree with the 200 under paraphrase. That
> conflict is the most important thing in this document.

---

## 1. The race — R3 vs R4, every dataset, every stress level

| | | 🟣 R3 | 🟠 **R4** | Δ |
|---|---|---|---|---|
| **train** 12,000 | L0 clean | 0.9235 | **0.9520** | **+0.0285** |
| | L1 scaffold | 0.6443 | **0.7897** | **+0.1454** |
| | L2 + payloads | 0.5171 | **0.7763** | **+0.2592** |
| | L3 + category | 0.4344 | **0.7253** | **+0.2909** |
| **dev** 2,000 | L0 clean | 0.9188 | **0.9499** | **+0.0311** |
| | L1 scaffold | 0.6421 | **0.7854** | **+0.1433** |
| | L2 + payloads | 0.5065 | **0.7680** | **+0.2615** |
| | L3 + category | 0.4250 | **0.7131** | **+0.2881** |
| **public** 200 | L0 clean | 0.9731 | 0.9740 | +0.0009 |
| | L1 scaffold | 0.8684 | 0.8397 | 🔴 **−0.0287** |
| | L2 + payloads | 0.8857 | 0.8457 | 🔴 **−0.0400** |
| | L3 + category | 0.8299 | 0.8061 | 🔴 **−0.0238** |

🔑 **Train and dev agree to within 0.013 at every level** — two disjoint sets, 12,000 and 2,000
sessions. **The official 200 points the other way under stress.** §6.

⚠️ Train stress rows are the first **4,000** sessions, not all 12,000 (L3 on the full set is ~7 min
per road). The L0 row is the full 12,000.

---

## 2. Clean scores, with confidence intervals

| dataset | n | road | Hit@10 | MRR | MTTC | **Score** | 95% CI |
|---|---|---|---|---|---|---|---|
| train | 12,000 | R3 | 0.9733 | 0.9223 | 2.99 | 0.9235 | (0.9203, 0.9264) |
| train | 12,000 | **R4** | **0.9892** | **0.9730** | **2.73** | **0.9520** | (0.9501, 0.9539) |
| dev | 2,000 | R3 | 0.9695 | 0.9167 | 3.05 | 0.9188 | (0.9108, 0.9268) |
| dev | 2,000 | **R4** | **0.9865** | **0.9713** | **2.74** | **0.9499** | (0.9442, 0.9546) |
| public | 200 | R3 | 1.0000 | 0.9829 | 2.09 | 0.9731 | (0.9651, 0.9795) |
| public | 200 | **R4** | 1.0000 | **0.9942** | 2.21 | 0.9740 | (0.9689, 0.9787) |

**Non-overlapping CIs on train and dev.** On the official 200 the intervals overlap almost entirely —
that set is saturated (both roads at Hit@10 1.0000) and can no longer discriminate.

### Per scenario, R4

| dataset | scenario | n | Hit@10 | MRR | MTTC |
|---|---|---|---|---|---|
| **train** | buying | 4800 | 0.9883 | 0.9710 | 2.24 |
| | browsing | 4800 | 0.9898 | 0.9722 | 2.70 |
| | intent_override | 1800 | **0.9911** | 0.9788 | 3.79 |
| | boundary | 600 | 0.9867 | 0.9773 | 3.61 |
| **dev** | buying | 800 | 0.9900 | 0.9765 | 2.21 |
| | browsing | 800 | 0.9825 | 0.9660 | 2.73 |
| | intent_override | 300 | **0.9933** | 0.9735 | 3.81 |
| | boundary | 100 | 0.9700 | 0.9650 | 3.74 |
| **public** | all four | 200 | 1.0000 | 0.9833–1.0000 | 1.69–3.73 |

🔑 **`intent_override` is now the strongest scenario on Hit@10** (0.9911 train, 0.9933 dev), having
been the weakest for every previous road. Those sessions get turns 1–2 free — the evaluator discards
any list shipped before the override lands — and R4 is the first road to spend them: it ships, learns
those items are wrong, and excludes them. Its structural MTTC floor of ~3.5 is unchanged.

---

## 3. The re-fit — R3's constants were fitted on a set that is now saturated

`scripts/fit_r4.py`, staged, train only, R3's identical objective (mean of L0/L2/L3).

| constant | R3 (fitted on 120 of the official 200) | **train fit** | |
|---|---|---|---|
| **`prior_weight`** | 0.18 | **0.00** | 🔑 the whole story |
| `v_continue` | 0.90 | 0.75 | +0.0008 |
| `tau_mass` | 0.90 | 0.85 | +0.0013 |
| `stall_decay` | 0.20 | 0.20 | unchanged |
| `stall_decay_clean` | 0.80 | 0.80 | unchanged |
| `exact_gain` | 3.20 | 3.20 | unchanged |

Objective 0.7236 → 0.7639 on the swept range, then → **0.8157** once the range was extended.

### The `prior_weight` sweep, including the boundary extension

⚠️ 0.10 won at the **low edge** of the initial range `(0.10, 0.18, 0.26, 0.40)`. A boundary optimum is
not an optimum, so the sweep was extended downward — and the conclusion changed.

| `prior_weight` | L0 | L2 | L3 | objective |
|---|---|---|---|---|
| **0.00** | 0.9499 | **0.7759** | **0.7214** | **0.8157** |
| 0.02 | 0.9508 | 0.7762 | 0.7032 | 0.8101 |
| 0.05 | 0.9508 | 0.7595 | 0.6755 | 0.7953 |
| 0.08 | 0.9503 | 0.7347 | 0.6435 | 0.7762 |
| 0.10 | 0.9502 | 0.7172 | 0.6244 | 0.7639 |
| 0.18 *(R3's)* | 0.9483 | 0.6632 | 0.5593 | 0.7236 |
| 0.26 | — | — | — | 0.6878 |
| 0.40 | — | — | — | 0.6437 |

**L0 is flat across the entire range** (0.9483 → 0.9508). Deleting the popularity prior costs nothing
on clean text and gains ~0.09 under paraphrase. See [D14](r4-exploration/03-decisions.md#d14) for why
this does not contradict IMPORTANT.md §5 so much as bound it.

---

## 4. Ablations on the shipped configuration

| ablation | train | dev | public |
|---|---|---|---|
| **shipped R4** | **0.9520** | **0.9499** | **0.9740** |
| `no_spec_phrase` | 0.9070 | 0.9076 | 0.9556 |
| `no_popularity` | 0.9520 | 0.9499 | 0.9740 |

🔑 **`no_popularity` is now a no-op, exactly and on all three datasets** — because `prior_weight = 0`
means the shipped configuration *is* the popularity ablation. That identity is an internal consistency
check on §3: if these rows differed, the re-fit had not actually taken effect.

**`no_spec_phrase` is the private-set insurance number** — the score with template inversion switched
off entirely. At **0.907 on train and dev** it is far above the project's long-standing 0.826
paraphrase-proof floor, and unlike that floor it does not depend on the popularity prior.

---

## 5. Where the remaining loss is, and what a perfect stopping rule is worth

`scripts/earlyhit.py`, train, `exclude_shipped` on. `EarlyHit@k(T)` is the share of sessions whose
**internal** ranking held the target by turn T; `shipped` is what MTTC records.

| by turn | 1 | 2 | 3 | 4 | 6 | 10 |
|---|---|---|---|---|---|---|
| EarlyHit@1 | 0.207 | 0.675 | 0.890 | 0.932 | 0.957 | 0.964 |
| EarlyHit@3 | 0.285 | 0.783 | 0.940 | 0.960 | 0.968 | 0.980 |
| EarlyHit@10 | 0.416 | 0.874 | 0.970 | 0.979 | 0.982 | 0.986 |
| **shipped** | 0.115 | 0.541 | 0.886 | 0.931 | 0.961 | 0.986 |

The turn-2 gap is 0.241, but most of it is **justified patience**: holding a rank-3 list one turn to
ship it at rank 1 gains 0.20 of MRR for 0.02 of Efficiency. By turn 3, shipped (0.886) has already
caught EarlyHit@1 (0.890).

An oracle that ships the instant the target reaches internal rank 1 cannot improve MRR or Hit, so
everything it gains is pure stopping efficiency:

| | |
|---|---|
| MTTC now | 2.704 |
| MTTC under oracle stopping | 2.538 |
| **ceiling on any stopping rule** | **+0.0033** |

🔴 **This killed Phase C** (calibrated confidence). A calibrated posterior cannot beat an oracle, so
+0.0033 caps the entire phase — below the CI width.

### Phase S — the diagnosis held, the mechanism did not

Probing the *full* internal ranking (train, 3,000): the target is in the level-1 category pool in
**3,000 of 3,000** sessions. **There is no recall failure.** The 45 misses sit at median internal rank
69 of a ~335 pool — pure ranking.

`flatness` (pool fraction matched by the most selective constraint) separates outcomes ~2.8×:

| outcome | n | median flatness |
|---|---|---|
| rank 1 | 2404 | **0.190** |
| hit rank 2+ | 62 | 0.475 |
| miss | 34 | **0.527** |

So the gate is real. But every adaptive configuration loses to simply deleting the prior:

| config | objective |
|---|---|
| **prior 0.00, damp 0** | **0.8157** |
| prior 0.10, damp 1.0 | 0.7692 |
| prior 0.10, damp 0 | 0.7639 |
| prior 0.18, damp 1.0 | 0.7325 |
| prior 0.30, damp 1.0 | 0.6877 |

🔴 `prior_damp` **ships off**. Damping helps at any fixed prior weight (+0.005 at 0.10, +0.009 at
0.18) — the diagnosis was right — but the limit case of the idea beats every partial version of it.

---

## 6. 🔴 The conflict: the official 200 disagrees

This is the one result that should stop a reader.

| | train 12,000 | dev 2,000 | public 200 |
|---|---|---|---|
| L1 | **+0.1454** | **+0.1433** | 🔴 −0.0287 |
| L2 | **+0.2592** | **+0.2615** | 🔴 −0.0400 |
| L3 | **+0.2909** | **+0.2881** | 🔴 −0.0238 |

Two disjoint datasets totalling 14,000 sessions agree with each other to within 0.013 and say R4 is
massively more robust. One saturated 200-session set says it is slightly worse. Both cannot be
describing the same property.

**Three reasons to weight train and dev over the 200, all of them stated as reasoning rather than
proof:**

1. **The 200 is where R3's constants were fitted.** R3 is at home there and R4 is not — the re-fit
   moved three constants away from values chosen on that exact set.
2. **The 200 is saturated.** Both roads score Hit@10 1.0000. The only variation left is MRR and MTTC
   against a structural floor, and its CIs overlap almost completely.
3. **The stress rewriter may itself be tuned to the 200.** R3 scores 0.8299 at L3 on the 200 and
   0.4250 on dev — a gap of 0.41 that no property of the agent explains
   ([D10](r4-exploration/03-decisions.md#d10)). If the rewriter's substitution vocabulary was built
   against the 200's categories and payload strings, its *absolute* levels there are not comparable
   to anywhere else.

⚠️ **None of that is confirmed, and the honest position is that this is unresolved.** The private set
is generated by the same pipeline as all three, so if the 200 is representative and train/dev are not,
R4's robustness claim is wrong. **Re-deriving the stress harness against a dataset it was not built on
is the single highest-value next measurement in this road.**

---

## 7. Cost and latency

| dataset | n | R4 clean | ms/session | at L3 |
|---|---|---|---|---|
| train | 12,000 | 50 s | **4.1** | 94 s |
| dev | 2,000 | 13 s | **6.4** | 51 s |
| public | 200 | 3 s | 17.0 | 8 s |

- **Zero network calls. Zero tokens. Zero USD.** numpy only; no LLM on any path measured here.
- Per-session cost falls as the dataset grows because the one-off index build (~25–30 s: 50k-product
  item index, category belief, popularity table) amortises — the evaluator constructs **one** `Agent`
  for every session.
- Paraphrase roughly doubles cost, because sessions run about twice as many turns.

This is the latency disclosure `submission_rules.md` requires.

---

## 8. What is not measured here

- **Train L1–L3 are the first 4,000 sessions**, not all 12,000. The clean row is the full set.
- **L4 (model-written paraphrase)** needs the endpoint. L1–L3 are deterministic.
- **The LLM extraction tier** is untouched by R4 and contributes to none of these numbers.
- **Calibration — ECE, reliability curves.** Phase C was killed on ceiling (§5), so the posterior is
  still *used* as a probability without ever being *shown* to be one. "Confidently wrong" remains the
  named failure mode and remains unevidenced either way.
- **Stress levels across datasets.** Agent-vs-agent deltas under one rewriter are valid; absolute L1–L3
  levels are not comparable between datasets (§6).
- **`prior_weight = 0` has not been independently reproduced.** It reverses a project-level finding on
  a single re-fit. The risk profile is favourable in both directions — L0 is flat, so it costs nothing
  if the private set is un-paraphrased — but §6 is the reason to treat it as provisional.
- **Boundary is 600 / 100 / 10 sessions.** Never read it alone.
