"""M6 — identical inputs must give identical scores across processes.

Python salts string hashing per interpreter, so any place that iterates a `set` and truncates picks a
different subset each run. This has already bitten BOTH roads: R1's score drifted 0.9584 / 0.9594 and
R2's 0.9578 / 0.9566 from exactly this, and in R1's case the fix made the model *correct*, not merely
stable. A score that moves between identical runs cannot be compared to anything.

`tests/test_routes.py` covers R2's lexical index. This covers the end-to-end score for every road, in
fresh interpreters, with hash randomisation left ON so the bug can actually appear.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval import race  # noqa: E402

PROBE = (
    "import sys; sys.path.insert(0, {root!r});"
    "from src.eval import race;"
    "print('%.10f' % race.score_road({road!r}))"
)


class TestM6Determinism(unittest.TestCase):
    def _score_in_fresh_process(self, road: str, seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", PROBE.format(root=str(ROOT), road=road)],
                             capture_output=True, text=True, cwd=ROOT, env=env, timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return out.stdout.strip()

    def test_every_road_scores_identically_under_different_hash_seeds(self) -> None:
        """M6: different PYTHONHASHSEED must not change the score by even one digit."""
        for road in race.ROADS:
            with self.subTest(road=road):
                a = self._score_in_fresh_process(road, "1")
                b = self._score_in_fresh_process(road, "2")
                self.assertEqual(a, b, f"{road} drifted between hash seeds: {a} vs {b}")


if __name__ == "__main__":
    unittest.main()
