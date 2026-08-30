# R5 — results

Official evaluator, kit verified byte-identical (`79a5ea06…`), `R3_OFFLINE=1`, `PYTHONHASHSEED=0`,
no network unless stated. 95% bootstrap CI, 1,000 resamples.

```bash
R3_OFFLINE=1 PYTHONHASHSEED=0 R4_FLAGS=exclude_shipped \
  python3 -m src.eval.race --dataset public --roads r3,r4,r5 --ci --scenarios
```

---

## 1. 🎯 Final evaluation — four datasets

R5 shipped configuration (= R4: `exclude_shipped`, `soft_card_gain 1.5`, `prior_weight 0.0`,
train-fitted constants). **LLM fallback enabled on `freeform_v1/test` only**; every other set is the
fully offline path.

| dataset | n | LLM | Hit@10 | MRR | MTTC | **TechnicalScore** | 95% CI |
|---|---|---|---|---|---|---|---|
| `freeform_v1/test` | 800 | ✅ fallback | 0.9738 | 0.9573 | 3.00 | **0.9341** | (0.9292, 0.9471) |
| `resplit_60_20_20/test` | 2,800 | offline | 0.9911 | 0.9783 | 2.64 | **0.9562** | (0.9526, 0.9599) |
| **`public_set.jsonl`** | 200 | offline | **1.0000** | 0.9942 | 2.19 | **0.9744** | (0.9692, 0.9789) |
| `dev.jsonl` | 2,000 | offline | 0.9865 | 0.9721 | 2.71 | **0.9506** | (0.9449, 0.9554) |

Reference rows: starter `0.1067` · popularity-only `0.7133` · public trick `0.7504` · paraphrase-proof
floor `0.826` · prior prototype `0.9607` · **theoretical max `0.9922`**.

⚠️ **The freeform row moved 0.9351 → 0.9341 (−0.0010) with the D21 gate repair**, and only that row.
`resplit/test`, `public_set` and `dev` reproduce to four decimals against the pre-repair run, which is
the check that the harness is stable and the repair touched only the free-form path. Re-measured by
`scripts/final_r5.py` → `runs/final_r5.json`.

⚠️ **`llm_calls` was 0 on all three templated datasets** and 800 on freeform — direct confirmation
that the escalation tier fires per unreadable message and nowhere else.

🔑 **Free-form language costs ~0.021.** `freeform_v1/test` (0.9351) and `resplit/test` (0.9562) are
drawn from the *same* source split, so the difference is language style alone and nothing else.

⚠️ **`freeform_v1/test.jsonl` was sealed and is now spent.** No further tuning against the free-form
corpus can be trusted.

⚠️ **`public_set.jsonl` is saturated** — Hit@10 1.0000, MRR 0.9942, and the only remaining variation
is MTTC against a structural floor of 1.39 driven by the 30 `intent_override` sessions. It can no
longer distinguish configurations. `resplit/test` (2,800) and `dev` (2,000) are the discriminating
sets.

### Cost of the LLM path

| dataset | wall | LLM calls | failures |
|---|---|---|---|
| freeform test (800) | **932.3 s** | 800 | **19 (2.4%)** |
| resplit test (2,800) | 23.7 s | 0 | — |
| public (200) | 3.9 s | 0 | — |
| dev (2,000) | 19.0 s | 0 | — |

**~1.2 s/session with the LLM against 8.5 ms offline — roughly 140×**, all of it one sequential call
per session. Against the +0.0014 the fallback measured on freeform train, that is a large latency and
availability cost for no measurable return, which is why it ships off. The 19 failures fell back to
the deterministic path silently — designed behaviour, but it means 19 of the 800 were not actually
LLM-assisted.

## 2. The corpora under `data/`

| corpus | split | R3 | **R4 = R5** |
|---|---|---|---|
| `resplit_60_20_20` (templated) | validation (400) | 0.9261 | **0.9540** |
| `freeform_v1` (free-form turn 1) | validation (400) | 0.8923 | **0.9110** |
| `public_set` | 200 | 0.9731 | **0.9744** |

**Free-form costs 0.043**, far less than expected — see [D16](r5-exploration/03-decisions.md).

Harder variant, free-form opener **plus** stressed later turns (a reconstruction of the generator's
stated policy, not the shipped data):

| later turns | soft-card off | **soft-card 1.5** |
|---|---|---|
| templated | 0.9088 | 0.9110 |
| stressed L2 | 0.7402 | **0.7951** |
| stressed L3 | 0.7402 | **0.7951** |

## 3. What R5 added, and what each part was worth

| mechanism | flag | freeform train | verdict |
|---|---|---|---|
| category recovery, closed 1,115-name vocabulary | `freetext_category` | 0.9153 → 0.9153 | 🔴 exactly zero |
| route recovery from speech-act cues | `freetext_route` | 0.9153 → 0.9146 | 🔴 negative |
| LLM fallback on the turn-1 opener | `llm_fallback` | 0.9131 → 0.9145, 400 calls, 6 failures | 🔴 noise |

**All three ship off.** R4's inherited `soft_card_gain = 1.5` is the only mechanism that moves hard
text (+0.018 at L2, +0.055 at L3, +0.080 at L4).

## 4. Cost and latency

| dataset | n | inference | ms/session |
|---|---|---|---|
| public_set | 200 | 4.0 s | 19.8 |
| dev | 2,000 | 12.8 s | 6.4 |
| train | 12,000 | 50 s | 4.1 |

Zero network calls, zero tokens, zero USD on the shipped path — numpy only. Per-session cost falls as
the set grows because the ~25–30 s index build amortises across one `Agent` instance.

## 5. What is not measured here

- **`freeform_v1/test.jsonl` (800) is sealed and was not opened.** Every freeform number above is
  train or validation.
- **Only turn 1 of the freeform corpus is free-form.** The manifest claims the generator restyled
  every turn; the rows carry one message. The stressed-later-turns rows are a reconstruction and are
  labelled as such.
- **`combine/` was not separately evaluated** — it is the union of the two corpora above, and both
  components are reported individually.
- **The LLM path is off in every headline number.** `llm_fallback` and `aligned_extract` are
  implemented and measured but not shipped.
