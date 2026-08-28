"""R1 with the one-line defence it is missing, as a fairness control.

R1 scores exactly 0.0000 under paraphrase stress. Two different things cause that and they must not be
conflated:

  (a) its parser is a template literal — `CAT_RE` requires the exact string "I'm looking for", so a
      reworded opening leaves `cat = None`; and
  (b) it has no fallback — `by_cat.get(None, [])` is empty, so it ships an EMPTY list every turn of
      every session, forever.

(b) is a missing guard, not an architectural property, and beating it proves nothing about filters vs
rankers. This control fixes only (b): when the category cannot be parsed, fall back to the globally most
popular products — the same paraphrase-proof prior R2 uses. Whatever gap remains after that is the real
architectural difference: R1's set intersection returns zero on a reworded constraint where R2's scored
overlap returns a smaller number.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_r1():
    spec = importlib.util.spec_from_file_location(
        "r1_base", ROOT / "experiments" / "agent_best_0.9607.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Agent


def make(catalog_path: str):
    base = _load_r1()

    class HardenedR1(base):  # type: ignore[misc, valid-type]
        def __init__(self, path: str) -> None:
            super().__init__(path)
            self._global_top = sorted(self.meta, key=lambda a: -self.meta[a])[:10]

        def respond(self, session_id, user_message, turn, top_k):
            out = super().respond(session_id, user_message, turn, top_k)
            if not out["recommendations"]:
                out["recommendations"] = [{"parent_asin": a} for a in self._global_top[:top_k]]
            return out

    return HardenedR1(catalog_path)
