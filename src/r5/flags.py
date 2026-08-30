"""R5 flags. Every new mechanism defaults OFF, so a default R5 is a default R4."""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.r4.flags import Flags as R4Flags


@dataclass
class Flags(R4Flags):
    # Recover `state.category` from a free-form opener by matching the catalog's coarse-category
    # vocabulary. R4 parses it from 0% of free-form openers.
    freetext_category: bool = False
    category_floor: float = 0.34      # min share of the category name's tokens present in the opener
    # Recover buying/browsing/override from speech-act cues. R4 assigns the "browsing" DEFAULT to
    # 100% of free-form sessions, which also keeps exclude_shipped's guard permanently conservative.
    freetext_route: bool = False
    # Escalation: canonicalise with the LLM only when both deterministic recoveries fail.
    llm_fallback: bool = False
    # Fuzzy canonicalisation BEFORE the deterministic/LLM decision (D22). Fires only on messages
    # `reads_deterministically` rejects, so the templated corpora are untouched by construction.
    fuzzy_expand: bool = False
    fuzzy_k: int = 3            # keep the top-k candidates; n=1 loses shirt/skirt to an alphabetical tie
    fuzzy_cutoff: float = 0.80  # difflib SequenceMatcher ratio floor
    fuzzy_min_len: int = 4      # shorter words match too much of the vocabulary to be safe

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
