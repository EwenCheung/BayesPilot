# R5 — acceptance criteria

Status: `⬜ open` · `🟩 passed` · `🟥 failed` · `⬛ explained`.
Fit on **train** splits; validation reports; `freeform_v1/test.jsonl` stays **sealed**.

| ID | Criterion | Test | Status |
|---|---|---|---|
| **R5-A1** 🟩 | With every new flag off, R5 reproduces R4 bit-for-bit (rank **and** turn) | `tests/test_r5_reduces_to_r4.py` | 🟩 |
| **R5-A2** 🟩 | R5 inherits R4's fitted constants unchanged | `tests/test_r5_reduces_to_r4.py` | 🟩 |
| **R5-A3** 🟩 | Corpus integrity: freeform test hashes to `a60dfacc…`, evaluator to `79a5ea06…` | manual, §1 of the spec | 🟩 |
| **R5-A4** 🟩 | The free-form runner wraps the **agent**, never the evaluator | `src/eval/freeform.py` | 🟩 |
| **R5-A5** 🟥 | `freetext_category` beats R4 on freeform validation by > CI width | 0.9153 → 0.9153, **exactly zero** | 🟥 |
| **R5-A6** 🟥 | `freetext_route` beats R4 | 0.9153 → 0.9146, **negative** | 🟥 |
| **R5-A7** 🟥 | `llm_fallback` beats R4 by > CI width | 0.9131 → 0.9145 on 400 calls — noise | 🟥 |
| **R5-A8** 🟩 | No mechanism regresses the templated corpus — all ship **off** | defaults asserted | 🟩 |
| **R5-A9** 🟩 | Final report on `public_set.jsonl` with CI and scenario breakdowns | §1 of `R5-RESULTS.md` | 🟩 |
| **R5-A10** 🟩 | Four-dataset evaluation: freeform test **0.9351**, resplit test **0.9562**, public **0.9744**, dev **0.9506** | `R5-RESULTS.md` §1 | 🟩 |
| **R5-A11** 🟩 | The escalation gate is fixed to test the **current message**, per turn, not session history | `src/r5/freetext.py::reads_deterministically` | 🟩 |
| **R5-A12** 🟩 | Fuzzy canonicalisation repairs a misspelled category word by **expansion**, keeping the original | `tests/test_fuzzy.py` | 🟩 |
| **R5-A13** 🟩 | Fuzzy canonicalisation does **not** invent constraints from ordinary English (`browsing`↛`brown`) | `tests/test_fuzzy.py` | 🟩 |
| **R5-A14** 🟥 | `fuzzy_expand` beats R4 on freeform validation by > CI width | 0.9110 → 0.9108; **all 10 train configs identical at 0.9153** — [D22](03-decisions.md) | 🟥 |

⚠️ **`freeform_v1/test.jsonl` was opened for R5-A10 and is now spent.** It was the sealed 800-session
split; no later tuning against the free-form corpus can be trusted.

🔴 **R5-A5/A6/A7 all fired.** The mechanisms are kept behind default-off flags so the negatives
reproduce; see [03-decisions.md](03-decisions.md).
