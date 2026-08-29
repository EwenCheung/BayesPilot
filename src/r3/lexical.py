"""IDF-weighted lexical evidence — ported from R2's `LexicalRoute` (src/r2/routes.py).

R3's per-constraint token term is a plain overlap ratio with a floor. R2's is IDF-weighted over a
**different surface** (title + store + categories + features rather than features + details), scored
against the whole accumulated query at once. It is the one part of R2's cascade that R3 did not have an
equivalent of, and R2's clean MRR was the better of the two.

⚠️ Never truncate a `set` — `list(tokens)[:cap]` picks a different subset per process because string
hashing is salted, and the score then drifts between identical runs. Keep the `cap` RAREST tokens:
deterministic, and it drops the high-frequency tokens that discriminate least anyway.
"""
from __future__ import annotations

import math

from src.common.attributes import tokens


class IdfLexical:
    FIELD_CAP = 64

    def __init__(self, index) -> None:
        self.index = index
        raw: dict[str, frozenset[str]] = {}
        df: dict[str, int] = {}
        for asin, text in index.lexical_text.items():
            got = tokens(text)
            raw[asin] = got
            for token in got:
                df[token] = df.get(token, 0) + 1
        n = len(raw) or 1
        self.idf = {t: math.log(1.0 + n / (1.0 + c)) for t, c in df.items()}
        self.doc_tokens = {
            asin: frozenset(sorted(got, key=lambda t: (-self.idf[t], t))[:self.FIELD_CAP])
            for asin, got in raw.items()
        }

    def scores(self, query: str, candidates: list[str]) -> dict[str, float]:
        wanted = tokens(query)
        if not wanted:
            return {}
        ceiling = sum(self.idf.get(t, 0.0) for t in wanted) or 1.0
        out: dict[str, float] = {}
        for asin in candidates:
            hit = wanted & self.doc_tokens.get(asin, frozenset())
            if hit:
                out[asin] = sum(self.idf.get(t, 0.0) for t in hit) / ceiling
        return out
