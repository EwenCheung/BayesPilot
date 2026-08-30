"""Does R3 improve by absorbing R1/R2 mechanisms? Measured on resplit train only.

Each candidate is a mechanism the other roads have and R3 did not. Kept only if it earns its place;
the alternative is a system with more parts and no more score.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["R3_OFFLINE"] = "1"          # headline numbers are the offline path (D22)

from scripts.fit_policy import score_on  # noqa: E402

CANDIDATES = {
    "R3 as-is (baseline)": {},
    # pool-normalising divides log_pop by its pool max (~11), so the SAME prior_weight is a ~11x
    # weaker prior. Judging it at the raw-scale weight would be the units error of D16 all over
    # again — it gets its own sweep.
    "pool-norm prior, w=0.5": {"pool_normalised_prior": True, "prior_weight": 0.5},
    "pool-norm prior, w=1.5": {"pool_normalised_prior": True, "prior_weight": 1.5},
    "pool-norm prior, w=3.0": {"pool_normalised_prior": True, "prior_weight": 3.0},
    "pool-norm prior, w=6.0": {"pool_normalised_prior": True, "prior_weight": 6.0},
    "+ IDF lexical, gain 0.5": {"idf_gain": 0.5},
    "+ IDF lexical, gain 1.5": {"idf_gain": 1.5},
    "+ IDF lexical, gain 4.0": {"idf_gain": 4.0},
}

if __name__ == "__main__":
    train = "train"
    print(f"{'variant':<30s} {'clean':>7s} {'L2':>7s} {'L3':>7s} {'mean':>7s}")
    for label, kw in CANDIDATES.items():
        row = [score_on(train, lvl, **kw) for lvl in (0, 2, 3)]
        print(f"{label:<30s} {row[0]:>7.4f} {row[1]:>7.4f} {row[2]:>7.4f} "
              f"{sum(row)/3:>7.4f}", flush=True)
