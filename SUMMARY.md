# TechJam Track 4 — the three roads

[IDEA.md](IDEA.md) §0.3 splits this problem into three **roads** — three incompatible answers to *"what
kind of problem is this?"* — built separately and raced on one harness.

| Road | The agent is… | Core structure | Status |
|---|---|---|---|
| 🔵 **R1** Constraint Satisfaction | a **filter** | a shrinking candidate *set* | built, measured — [handover](docs/r1-exploration/SUMMARY.md) |
| 🟢 **R2** Retrieve & Rank | a **ranker** | a scored *list* | built, measured — [handover](docs/r2-exploration/SUMMARY.md) |
| 🟣 **R3** Bayesian Fusion | a **posterior** | belief over categories, then items | **built, measured, wins every condition** — [handover](docs/r3-exploration/SUMMARY.md) |

**The result** ([docs/R3-RESULTS.md](docs/R3-RESULTS.md)) — one harness, one rewriter, one ablation
vocabulary, no network:

| Condition | R1 | R2 | **R3** |
|---|---|---|---|
| clean | 0.9597 | 0.9707 | **0.9720** |
| paraphrase L2 | 0.7887 | 0.7872 | **0.8845** |
| paraphrase L3 | 0.7241 | 0.6630 | **0.8297** |
| **held-out 60, L3** | 0.6740 | 0.6863 | **0.8381** |

⚠️ **R1's and R2's originally published stress and ablation numbers were never comparable** — different
rewriters, different `no_spec_phrase` definitions (R1 defect 2, R2 defect A8). Everything above is on
one harness; the corrected side-by-side is in
[docs/r3-exploration/04-merge-plan.md](docs/r3-exploration/04-merge-plan.md) §7.

**Start here:** [IMPORTANT.md](IMPORTANT.md) is authoritative on facts about the problem.
[docs/r3-exploration/](docs/r3-exploration/) is authoritative on what is being built now.
