# Shopping Copilot — TikTok TechJam 2026, Track 4

A multi-turn conversational agent that finds one hidden product in a frozen 50,000-item Amazon
catalog within 10 turns. It runs offline, on numpy, with no trained model files.

```
TechnicalScore = 0.50·Hit@10 + 0.30·MRR + 0.20·Efficiency
Efficiency     = clip((11 − MTTC) / 10, 0, 1)      MTTC counts a miss as turn 11
```

| dataset | n | Hit@10 | MRR | MTTC | **TechnicalScore** |
|---|---|---|---|---|---|
| `public_set.jsonl` | 200 | 1.0000 | 0.9942 | 2.19 | **0.9744** |
| `resplit_60_20_20/test` | 2,800 | 0.9911 | 0.9783 | 2.64 | **0.9562** |
| `dev.jsonl` | 2,000 | 0.9865 | 0.9721 | 2.71 | **0.9506** |
| `freeform_v1/test` | 800 | 0.9725 | 0.9604 | 2.98 | **0.9348** |

Reference points: official starter `0.1067` · popularity-only `0.7133` · theoretical max `0.9922`.
Zero network calls, zero tokens, ~4–20 ms/session. Every number is one run of the organizer's own
`evaluate()` with our agent passed in — see [SUMMARY.md](SUMMARY.md) for how each was obtained.

## Setup

```bash
# the catalog is 60 MB and gitignored; restore it from the official release
cp /path/to/catalog.jsonl data/catalog.jsonl
shasum -a 256 data/catalog.jsonl     # da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67

python3 -m pytest tests/ -q                                  # 91 tests
COPILOT_OFFLINE=1 PYTHONHASHSEED=0 python3 scripts/evaluate.py   # the table above
```

No dependencies beyond numpy and the standard library. `.env` is needed only for the optional
language tier, which never fires on templated input.

## Reproducing

| command | what it does |
|---|---|
| `python3 scripts/evaluate.py` | the four-dataset table above → `runs/final_r5.json` |
| `python3 -m src.eval.measure --dataset dev --ci --scenarios` | one dataset, with CI and per-scenario breakdown |
| `python3 -m src.eval.measure --dataset public --stress 3` | the same under L3 paraphrase |
| `python3 -m src.eval.measure --dataset dev --ablate no_spec_phrase` | an ablation from the shared vocabulary |
| `python3 scripts/fit.py` | re-fit the policy constants on `data/train.jsonl` |
| `python3 scripts/fit_bm25.py` | the BM25 gain sweep and the tokenizer isolation |
| `python3 scripts/earlyhit.py` | the EarlyHit curve — what a perfect stopping rule would be worth |

⚠️ **Fit on `data/train.jsonl` only.** `dev.jsonl`, `public_set.jsonl` and the `*/test` splits are
read for reporting. `freeform_v1/test` is sealed and spent.

## Layout

```
agent.py              submission entry point — `from agent import Agent`
src/
  copilot/            the turn loop and the flag defaults that ARE the submission
  understand/         parse cascade: templates -> ontology -> verified model tier
  retrieve/           the item index, the level-1 category posterior, BM25
  rank/               the item log-posterior, its evidence terms, the depth policy
  state/              what the customer told us, and what we still believe about it
  eval/               the harness around the organizer's evaluator; never imported by the agent
  simulator.py        a mirror of the evaluator's own shopper, for generating sessions
scripts/              evaluate · fit · fit_bm25 · earlyhit · llm_tier
tests/                91 tests
techjam-conversational-search-main/   the official kit — never edited, hash-verified before every run
```

## How it works, in six steps

1. **Parse, cheapest tier first.** The simulator's five literal templates, then keyword/regex
   ontology extraction, then a model — stopping at the first that works. On templated input the
   templates handle everything, so the agent makes **zero** model calls.
2. **Verify before believing.** A model-proposed value is not evidence until it resolves to a string
   the catalog actually contains. An ambiguous span is carried as a probability **mixture** over real
   catalog strings rather than resolved to a guess.
3. **Choose a pool with a distribution.** `P(category | opener)` over 1,115 shelves, widened until it
   covers 85% of the mass. 50,000 items become ~335, and the target is in that pool ~100% of the time.
4. **Score with one log-posterior.** Exact card strings, normalised attribute pairs, token overlap and
   soft-card Jaccard, every factor bounded. A term with no opinion cancels; no term may zero an item.
5. **Use survival as evidence.** The evaluator stops on the first hit, so a session that is still
   alive proves every item already shipped is wrong.
6. **Price waiting, and let list length fall out.** `V = 0.75·hope − 0.0667`; ship the largest `k`
   with `1/k > V`. Nobody tuned "how many items to show".

## Limitations

- **The pool is chosen from the raw opener**, so the model tier cannot rescue a mis-resolved category.
  Real gap, not exercised by the current corpora, which spell category words correctly 99.5% of the time.
- **Depth reads only the stall counter**, not the shape of the belief — a razor-sharp posterior and a
  flat one produce the same list length. A belief-aware `V` is the honest next experiment.
- **The paraphrased branch is a cliff**: one barren turn takes depth from 1 to 10 with nothing between.
- **`freeform_v1/test` is spent** and `public_set.jsonl` is saturated (Hit@10 1.0000). `resplit/test`
  and `dev` are the only sets that still discriminate.

[SUMMARY.md](SUMMARY.md) is authoritative on results and rejected ideas; [MERGE.md](MERGE.md) records
what was taken from the two sibling branches and what was left behind.
