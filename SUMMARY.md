# TechJam Track 4 — the three roads

[IDEA.md](IDEA.md) §0.3 splits this problem into three **roads** — three incompatible answers to *"what
kind of problem is this?"* — built separately and raced on one harness.

| Road | The agent is… | Core structure | Status |
|---|---|---|---|
| 🔵 **R1** Constraint Satisfaction | a **filter** | a shrinking candidate *set* | built, measured — [handover](docs/r1-exploration/SUMMARY.md) |
| 🟢 **R2** Retrieve & Rank | a **ranker** | a scored *list* | built, measured — [handover](docs/r2-exploration/SUMMARY.md) |
| 🟣 **R3** Bayesian Fusion | a **posterior** | belief over categories, then items | [spec](docs/r3-exploration/00-r3-spec.md) · in progress |

⚠️ **R1's and R2's published stress and ablation numbers are not comparable to each other.** They were
produced by different paraphrase rewriters and different `no_spec_phrase` definitions (R1 defect 2, R2
defect A8). The merge onto one harness is what fixes that; the corrected side-by-side lives in
[docs/r3-exploration/04-merge-plan.md](docs/r3-exploration/04-merge-plan.md) §7.

**Start here:** [IMPORTANT.md](IMPORTANT.md) is authoritative on facts about the problem.
[docs/r3-exploration/](docs/r3-exploration/) is authoritative on what is being built now.
