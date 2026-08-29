# The race — three roads, one harness

All numbers from the **official evaluator** on the 200 public sessions, kit verified byte-identical to
upstream before and after every run. One paraphrase rewriter, one `no_spec_phrase` definition, one
runner (`src/eval/race.py`). 95% bootstrap CI, 1,000 resamples, `PYTHONHASHSEED=0`.

Deterministic paths only — **no network calls, no LLM tier**. Regenerate with `python3 scripts/final.py`.

---

## 1. The race

| Condition | 🔵 R1 filter | 🟢 R2 ranker | 🟣 **R3 posterior** | R3 − best |
|---|---|---|---|---|
| **clean** | 0.9597 | 0.9707 | **0.9731** | +0.0024 |
| L1 scaffold reworded | 0.7737 | 0.8305 | **0.8684** | **+0.038** |
| L2 + payloads reworded | 0.7887 | 0.7872 | **0.8857** | **+0.097** |
| L3 + category reworded | 0.7241 | 0.6630 | **0.8299** | **+0.106** |
| `no_spec_phrase` | 0.9128 | 0.8315 | **0.9277** | +0.015 |
| `no_popularity` | 0.9200 | 0.9318 | **0.9599** | +0.028 |

⚠️ **This table is scored on all 200 sessions, and 120 of them were used for tuning — so 60% of it is
in-sample.** It is reported this way because R1's and R2's published numbers are also all-200 and
this is the only like-for-like comparison. **§2 is the unbiased table**, and it now agrees: on the
held-out 80, R3 leads on clean (0.9730 vs 0.9722), L2 (+0.088) and L3 (+0.143). See D22 for the full
leakage audit.

**R3 wins every condition here.** The clean margin is still inside the noise floor and is not claimed as
a win; the paraphrase margins are three to five times the CI width and are what matter.

⚠️ **All figures are the OFFLINE path**, measured under `R3_OFFLINE=1`. That is enforced rather than
assumed: a warm `.cache/llm` otherwise lifts L3 to 0.8926 with **zero network calls**, which is
indistinguishable from an offline run unless you count cache hits (D22).

### Hit@10 — where the difference comes from

| Condition | R1 | R2 | **R3** |
|---|---|---|---|
| clean | 1.000 | 1.000 | 1.000 |
| L2 | 0.890 | 0.835 | **0.970** |
| L3 | 0.820 | 0.700 | **0.915** |
| `no_spec_phrase` | 0.995 | 0.890 | **0.990** |

R3 keeps R1's recall *and* R2's precision instead of trading one for the other — which is what fusing
them was supposed to buy, stated as a testable claim in [00-r3-spec.md](r3-exploration/00-r3-spec.md)
§1 and now measured.

### 1.1 With the LLM extraction tier (network available)

The headline table is the **offline** path, because *"organizer policy may disable network access"*.
When the endpoint does exist, the escalation-gated extraction tier adds:

| Condition | offline | + LLM tier | Δ | calls | failures |
|---|---|---|---|---|---|
| clean | 0.9720 | 0.9720 | **0.000** | **0** | 0 |
| L2 | 0.8845 | **0.9399** | **+0.055** | 188 | 51 (27%) |
| L3 | 0.8297 | **0.8926** | **+0.063** | 28 | 113 (80%) |

Zero calls on clean text — the tier fires only once no template has matched by turn 2. Both stressed
gains were measured while the shared endpoint was failing 27–80% of calls, so they are **lower bounds**;
every failure falls back to the deterministic path, which is why the score rises anyway.

---

## 2. Generalisation — tuned on 120, read once on 80

Every R3 constant was fitted on the 120-session train split. The held-out 80 (disjoint on sample ID
**and** target ASIN, manifest hash `30dc09816cff6b1c`) was read once, at the end.

⚠️ Widened from 70/30 to **60/40** after the leakage audit: with 60 held-out sessions the L3 CI spanned
~0.13, too wide to separate the roads. The tuning set was never the binding constraint — most fits are
flat — so buying a sharper verdict with unused tuning data was the right trade.

| Road | train120 clean | **test80 clean** | train120 L2 | **test80 L2** | train120 L3 | **test80 L3** |
|---|---|---|---|---|---|---|
| R1 | 0.9597 | 0.9597 | 0.7977 | 0.7752 | 0.7569 | 0.6749 |
| R2 | 0.9696 | 0.9722 | 0.7868 | 0.7878 | 0.6660 | 0.6584 |
| **R3** | 0.9731 | **0.9730** | 0.8925 | **0.8756** | 0.8381 | **0.8177** |

**On 80 sessions never used for tuning, R3 leads every condition:** clean +0.0008 (noise, not claimed),
L2 **+0.088**, L3 **+0.143** over the better baseline.

R3's train→test gap is small and in the expected direction — clean 0.9731→0.9730, L2 0.8925→0.8756,
L3 0.8381→0.8177. (On the previous 70/30 split R3's held-out L3 came out *above* its training score;
that was luck on 60 sessions, and a small positive gap is the healthier result.)

⚠️ 80 sessions still leaves the L3 CIs spanning ~0.13. The direction is trustworthy; the third decimal
is not.

---

## 3. Ablations — what each part is worth

| Removed from R3 | Condition | Score | Δ |
|---|---|---|---|
| the popularity prior | L3 | 0.7093 | **−0.121** |
| generic lexical evidence | L3 | 0.7499 | −0.080 |
| **the level-1 category belief** | **L3** | **0.7764** | **−0.054** |
| the level-1 category belief | L2 | 0.8857 | **0.000** |
| exact + partial inversion (`no_spec_phrase`) | clean | 0.9277 | −0.045 |
| — *adding* EIG question selection | clean | 0.9645 | **−0.009** |
| — *adding* EIG question selection | L3 | 0.8039 | **−0.026** |
| — *adding* R2's pool-normalised prior | mean | 0.8975 | **−0.002** |
| — *adding* R2's IDF lexical route | mean | 0.8973 | **−0.003** |
| — *switching* to R2's override-delete | clean | 0.9705 | **−0.002** |

Three things worth reading twice:

1. **The popularity prior is still the largest single contributor under stress** (−0.121), replicating
   what R1 and R2 each found independently. R3's contribution is not discovering this — it is getting
   the prior's *units* right, which was worth +0.066 on its own (D16).
2. **The category belief is worth +0.054 at L3 and exactly 0.000 at L2.** That is the D13 prediction
   holding: it only pays where the category wording actually changes, so it buys robustness without
   spending anything elsewhere.
3. **Expected information gain makes things worse at every level** and is shipped off (D18). It was one
   of IDEA.md's two headline promises for this road.

---

## 4. Cost

| | R1 | R2 | **R3** |
|---|---|---|---|
| tuned constants | ~10 | 32 fusion weights + ladder + regime threshold | **7 fitted + 2 structural** |
| network calls, default path | 0 | 0 | **0** |
| runtime dependencies | numpy | numpy, scipy, scikit-learn | **numpy** |
| wall clock, 200 sessions | ~10 s | ~17 s | ~12 s |
| LLM calls on clean text | 0 | 0 | **0** |

R3's seven fitted constants — `exact_gain`, `prior_weight`, `temperature`, `tau_mass`, `v_continue`,
`stall_decay`, `stall_decay_clean` — replace R2's two 16-weight schedules, its four-rung depth ladder, its `spec_support <
0.60` regime switch, R1's `NQC 0.35`, its turn-3 deadline, and its `hedge(keep=0.6, top-3, cap=4000)`.
Every one was fitted on the 120, never on the 80.

---

## 5. Semantic retrieval: built, measured, dropped

Both backends were implemented and run as evidence terms. Neither ships. ⚠️ Measured before the D23
boundary fix, so the baseline row here is the then-current 0.8954 — the comparison within the table is
like-for-like, and re-running it after the fix moves every row equally.

| `semantic_gain` | backend | clean | L2 | L3 | mean |
|---|---|---|---|---|---|
| **0.0** | **none — shipped** | **0.9720** | **0.8845** | 0.8297 | **0.8954** |
| 1.0 | TF-IDF→SVD | 0.9691 | 0.8712 | 0.8219 | 0.8874 |
| 2.5 | TF-IDF→SVD | 0.9652 | 0.8554 | 0.8196 | 0.8801 |
| 1.0 | BLaIR | 0.9711 | 0.8773 | 0.8273 | 0.8919 |
| 2.5 | BLaIR | 0.9707 | 0.8802 | **0.8349** | 0.8953 |
| 4.0 | BLaIR | 0.9704 | 0.8704 | 0.8297 | 0.8902 |
| 6.0 | BLaIR | 0.9654 | 0.8590 | 0.8204 | 0.8816 |

`hyp1231/blair-roberta-base` is pretrained on **Amazon Reviews 2023 — this exact catalog's corpus** —
and all 50,000 products were embedded with it (CLS-pooled, L2-normalised, 71 MB float16, 4.6 min on
MPS). At its best it scores **0.8953 mean against 0.8954 without it**. Kill gate R3-A23 required ≥0.01
on the stressed number; it delivers +0.005 at L3 while losing 0.013 clean and 0.043 at L2. Dropped.

🔑 **This is the fourth independent negative on semantic retrieval for this benchmark** — after R2's
`bge-m3`, a teammate's separate codebase, and this road's own TF-IDF/SVD — and it is the one that
closes the loophole in the other three, all of which used *generic* encoders.

**The mechanism is worth naming.** The simulator draws its constraints **verbatim from the catalog's own
`features` and `details`**. The evidence that decides a session is string-level by construction, and the
exact/attribute/token terms read that surface directly. A semantic encoder adds a correlated but
blurrier view of the same text: redundancy plus noise, which is the shape of the measured harm.
**There is no vocabulary gap here for a semantic model to close, because the customer's vocabulary *is*
the catalog's vocabulary.**

`torch` and `transformers` are therefore **not runtime dependencies**. The code stays behind
`R3_FLAGS=semantic_gain=2.5,semantic_backend=blair` with `scripts/embed_blair.py` to reproduce it —
`tests/test_runtime_deps.py` asserts the shipped path never imports either.

---

## 6. What is not measured here

- **L4 (model-written paraphrase)** needs the LLM endpoint. L3 is deterministic and reproduces R1's
  published LLM-written L3 to within 0.0005 (0.7241 vs 0.7246), so it is a good free proxy — but it is
  a proxy.
- **The LLM extraction tier** is implemented and escalation-gated but contributes nothing to any number
  above, which are all offline. R1 measured that tier at ~+0.07 under stress.
- **A dense route.** R3 ships with no semantic term, and that is now a *measured* choice rather than an
  omission — see §6.
- **Calibration (ECE, reliability curves)** — Phase P3 is not built.
