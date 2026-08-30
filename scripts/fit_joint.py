"""SUMMARY defect 7: `temperature` and `tau_mass` were chosen on category COVERAGE, before level 2
existed. Coverage is not score — a wider pool is ranking cost. Re-fit them jointly on end-to-end
score, on the 140."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fit_policy import score_on  # noqa: E402

if __name__ == "__main__":
    train = "train"
    base = json.loads((ROOT / "runs" / "r3_fitted.json").read_text())
    base.pop("confidence_power", None)
    best = None
    print(f"{'T':>5s} {'tau':>6s} | {'clean':>7s} {'L2':>7s} {'L3':>7s} | {'obj':>7s}")
    for T in (0.8, 1.2, 2.0, 3.0):
        for tau in (0.85, 0.90, 0.95):
            kw = dict(base, temperature=T, tau_mass=tau)
            c = score_on(train, 0, **kw)
            l2 = score_on(train, 2, **kw)
            l3 = score_on(train, 3, **kw)
            obj = (c + l2 + l3) / 3
            print(f"{T:>5.1f} {tau:>6.2f} | {c:>7.4f} {l2:>7.4f} {l3:>7.4f} | {obj:>7.4f}", flush=True)
            if best is None or obj > best[0]:
                best = (obj, T, tau, c, l2, l3)
    print(f"\nchosen: temperature={best[1]} tau_mass={best[2]}  "
          f"(train clean {best[3]:.4f}, L2 {best[4]:.4f}, L3 {best[5]:.4f})")
    base.update(temperature=best[1], tau_mass=best[2])
    (ROOT / "runs" / "r3_fitted.json").write_text(json.dumps(base, indent=1))
