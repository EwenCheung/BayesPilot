"""Ablation switches (spec 3.10). Every route is behind one, so the honesty table is a run, not an argument."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Flags:
    spec_phrase: bool = True     # exact card-string matching — the inversion route
    attribute: bool = True       # normalised ontology matching
    token: bool = True           # token-overlap fallback
    popularity: bool = True      # the paraphrase insurance prior
    infogain: bool = True        # expected-information-gain question selection
    llm_extract: bool = True     # LLM constraint extraction (escalation only; 0 calls on clean text)
    llm_rerank: bool = True      # the brief's named LLM Semantic Ranking stage (adaptive, see below)
    adaptive: bool = True        # fire the reranker only when the wording stopped matching templates
    hedge: bool = True           # search the union of plausible categories when the wording is fuzzy
    llm_message: bool = False    # LLM-written prose for the human judges
    dense: bool = False          # bge-m3 cosine as a tie-break
    profile: bool = False        # long-term user profile (§14.6) — built, measured, off by default
    truncate: bool = False       # dynamic truncation (§14.3) — measured, off by default
    deadline: int = 3            # convert unconditionally from this turn (IMPORTANT.md §12.1)
    erase: str = "demote"        # intent-override slot handling: demote | delete | keep (Pillar II)
    shrink_min: float = 1.0      # minimum match strength allowed to shrink S (1.0 = exact only)

    @classmethod
    def from_env(cls) -> "Flags":
        """R1_FLAGS=no_spec_phrase,llm_rerank,deadline=4"""
        flags = cls()
        for token in (os.environ.get("R1_FLAGS") or "").split(","):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                name, _, value = token.partition("=")
                current = getattr(flags, name)
                cast = type(current) if not isinstance(current, bool) else int
                setattr(flags, name, cast(value))
            elif token.startswith("no_"):
                setattr(flags, token[3:], False)
            else:
                setattr(flags, token, True)
        return flags
