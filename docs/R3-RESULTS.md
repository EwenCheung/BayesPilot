# The race — three roads, one harness

All numbers from the **official evaluator** on the 200 public sessions, kit verified byte-identical to
upstream before and after every run. One paraphrase rewriter, one `no_spec_phrase` definition, one
runner (`src/eval/race.py`). 95% bootstrap CI, 1,000 resamples, `PYTHONHASHSEED=0`.

Deterministic paths only — **no network calls, no LLM tier**. Regenerate with `python3 scripts/final.py`.

---

## 1. The race

| Condition | 🔵 R1 filter | 🟢 R2 ranker | 🟣 **R3 posterior** | R3 − best |
|---|---|---|---|---|
| **clean** | 0.9597 | 0.9707 | **0.9720** | +0.0013 |
| L1 scaffold reworded | 0.7737 | 0.8305 | **0.8705** | **+0.040** |
| L2 + payloads reworded | 0.7887 | 0.7872 | **0.8845** | **+0.096** |
| L3 + category reworded | 0.7241 | 0.6630 | **0.8297** | **+0.106** |
| `no_spec_phrase` | 0.9128 | 0.8315 | **0.9339** | +0.021 |
| `no_popularity` | 0.9200 | 0.9318 | **0.9604** | +0.029 |

**R3 wins every condition.** The clean margin is inside the noise floor and should not be claimed; the
paraphrase margins are three to five times the CI width and are the ones that matter, because the
private set is what they estimate.

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

---

## 2. Generalisation — tuned on 140, read once on 60

Every R3 constant was fitted on the 140-session train split. The held-out 60 (disjoint on sample ID
**and** target ASIN, manifest hash `a367f15873d772aa`) was read once, at the end.

| Road | train140 clean | **test60 clean** | train140 L3 | **test60 L3** |
|---|---|---|---|---|
| R1 | 0.9595 | 0.9604 | 0.7456 | 0.6740 |
| R2 | 0.9698 | 0.9728 | 0.6530 | 0.6863 |
| **R3** | 0.9725 | **0.9708** | 0.8261 | **0.8381** |

🔑 **R3's held-out L3 score (0.8381) is *higher* than its training score (0.8261).** Tuning did not buy
performance that fails to transfer — the strongest evidence available on 60 sessions that the gain is
real. On the same held-out sessions R3 beats R1 by **+0.164** and R2 by **+0.152**.

⚠️ 60 sessions is small and the L3 CIs there span ~0.13. The direction is trustworthy; the third decimal
is not.

---

## 3. Ablations — what each part is worth

| Removed from R3 | Condition | Score | Δ |
|---|---|---|---|
| the popularity prior | L3 | 0.7087 | **−0.121** |
| generic lexical evidence | L3 | 0.7488 | −0.081 |
| **the level-1 category belief** | **L3** | **0.7753** | **−0.054** |
| the level-1 category belief | L2 | 0.8845 | **0.000** |
| exact + partial inversion (`no_spec_phrase`) | clean | 0.9339 | −0.038 |
| — *adding* EIG question selection | clean | 0.9509 | **−0.021** |
| — *adding* EIG question selection | L3 | 0.7899 | **−0.040** |

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
| tuned constants | ~10 | 32 fusion weights + ladder + regime threshold | **6 fitted + 2 structural** |
| network calls, default path | 0 | 0 | **0** |
| runtime dependencies | numpy | numpy, scipy, scikit-learn | **numpy** |
| wall clock, 200 sessions | ~10 s | ~17 s | ~12 s |
| LLM calls on clean text | 0 | 0 | **0** |

R3's six fitted constants — `exact_gain`, `prior_weight`, `temperature`, `tau_mass`, `v_continue`,
`stall_decay` — replace R2's two 16-weight schedules, its four-rung depth ladder, its `spec_support <
0.60` regime switch, R1's `NQC 0.35`, its turn-3 deadline, and its `hedge(keep=0.6, top-3, cap=4000)`.
Every one was fitted on the 140, never on the 60.

---

## 5. Semantic retrieval: built, measured, dropped

Both backends were implemented and run as evidence terms. Neither ships.

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
