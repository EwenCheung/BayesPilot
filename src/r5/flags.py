"""R5 flags — R4's, plus BM25. Every new mechanism defaults OFF, so a default R5 is a default R4.

⚠️ `freetext_category`, `freetext_route`, `llm_fallback` and `fuzzy_expand` were removed after all four
measured **exactly 0.0000** (D17, D21, D22). Their measurements survive in `03-decisions.md`; the code
does not, because a default-off flag that can never be turned on is not an experiment, it is clutter.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.r4.flags import Flags as R4Flags


@dataclass
class Flags(R4Flags):
    # BM25 as an evidence term (D24). The IDF lexical route over the SAME surface measured harmful
    # (D23); this isolates what term saturation and length normalisation add on top.
    bm25_gain: float = 0.0
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    @classmethod
    def from_env(cls) -> "Flags":
        flags = cls()
        for var in ("R3_FLAGS", "R4_FLAGS", "R5_FLAGS"):
            for token in (os.environ.get(var) or "").split(","):
                token = token.strip()
                if not token:
                    continue
                if "=" in token:
                    name, _, value = token.partition("=")
                    current = getattr(flags, name)
                    setattr(flags, name, type(current)(value))
                elif token.startswith("no_"):
                    setattr(flags, token[3:], False)
                else:
                    setattr(flags, token, True)
        return flags
