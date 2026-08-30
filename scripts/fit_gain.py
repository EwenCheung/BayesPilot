"""Fit the two evidence gains on the resplit train data only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fit_policy import score_on  # noqa: E402

if __name__ == "__main__":
    train = "train"
    base = json.loads((ROOT / "runs" / "r3_fitted.json").read_text())
    best = None
    print(f"{'clean gain':>10s} {'para gain':>10s} | {'clean':>7s} {'L3':>7s} | {'obj':>7s}")
    for clean_gain in (3.2, 6.0, 10.0, 16.0):
        for para_gain in (2.0, 3.2, 5.0):
            kw = dict(base, exact_gain=clean_gain, paraphrased_gain=para_gain)
            c, l = score_on(train, 0, **kw), score_on(train, 3, **kw)
            obj = 0.5 * c + 0.5 * l
            print(f"{clean_gain:>10.1f} {para_gain:>10.1f} | {c:>7.4f} {l:>7.4f} | {obj:>7.4f}", flush=True)
            if best is None or obj > best[0]:
                best = (obj, clean_gain, para_gain, c, l)
    base.update(exact_gain=best[1], paraphrased_gain=best[2])
    (ROOT / "runs" / "r3_fitted.json").write_text(json.dumps(base, indent=1))
    print(f"\nchosen: exact_gain={best[1]} paraphrased_gain={best[2]} "
          f"(train clean {best[3]:.4f}, L3 {best[4]:.4f})")
