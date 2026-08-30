# TechJam Track 4 — the three roads

[IDEA.md](IDEA.md) §0.3 splits this problem into three **roads** — three incompatible answers to *"what
kind of problem is this?"* — built separately and raced on one harness.

| Road | The agent is… | Core structure | Status |
|---|---|---|---|
| 🔵 **R1** Constraint Satisfaction | a **filter** | a shrinking candidate *set* | built, measured — [handover](docs/r1-exploration/SUMMARY.md) |
| 🟢 **R2** Retrieve & Rank | a **ranker** | a scored *list* | built, measured — [handover](docs/r2-exploration/SUMMARY.md) |
| 🟣 **R3** Bayesian Fusion | a **posterior** | belief over categories, then items | **built, measured; leads every held-out condition** — [handover](docs/r3-exploration/SUMMARY.md) |

**The result** ([docs/R3-RESULTS.md](docs/R3-RESULTS.md)) — one harness, one rewriter, one ablation
vocabulary, offline path enforced with `R3_OFFLINE=1`:

| Condition | R1 | R2 | **R3** | |
|---|---|---|---|---|
| clean (all 200) | 0.9597 | 0.9707 | **0.9731** | ⚠️ 60% in-sample |
| paraphrase L2 (all 200) | 0.7887 | 0.7872 | **0.8857** | ⚠️ 60% in-sample |
| paraphrase L3 (all 200) | 0.7241 | 0.6630 | **0.8299** | ⚠️ 60% in-sample |
| **held-out 80, clean** | 0.9597 | 0.9722 | **0.9730** | +0.001, noise |
| **held-out 80, L2** | 0.7752 | 0.7878 | **0.8756** | **+0.088** |
| **held-out 80, L3** | 0.6749 | 0.6584 | **0.8177** | **+0.143** |

**The honest one-liner: R3 leads every held-out condition; the clean margin is noise, the robustness
margin is large.**
The clean scores are saturated (theoretical max 0.9922, noise floor ~0.02) and the paraphrase columns are
what estimate the private 800.

⚠️ **Leakage audit: [03-decisions.md D22](docs/r3-exploration/03-decisions.md).** Fitted parameters used
the 140 only; the all-200 rows above are partly in-sample; two structural decisions made on all-200 were
re-tested per half.

⚠️ **R1's and R2's originally published stress and ablation numbers were never comparable** — different
rewriters, different `no_spec_phrase` definitions (R1 defect 2, R2 defect A8). Everything above is on
one harness; the corrected side-by-side is in
[docs/r3-exploration/04-merge-plan.md](docs/r3-exploration/04-merge-plan.md) §7.

**Start here:** [IMPORTANT.md](IMPORTANT.md) is authoritative on facts about the problem.
[docs/r3-exploration/](docs/r3-exploration/) is authoritative on what is being built now.
