"""Spec 3.8 — the dense tie-break.

R1 is a filter, so dense similarity is deliberately the *third* key: it only ever reorders items
the constraint matcher could not separate. (Dense retrieval as a primary route is R2's road.)
Returns zeros, never an error, when no embedding cache exists — offline stays a first-class path.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.common.contracts import SessionState

CACHE = Path(__file__).resolve().parents[2] / ".cache" / "embeddings.npz"


class DenseRoute:
    def __init__(self, asins, vectors, llm=None) -> None:
        self.position = {asin: i for i, asin in enumerate(asins)}
        self.vectors = vectors
        self.llm = llm
        self.scores: dict[str, float] = {}

    @classmethod
    def load(cls, llm=None) -> "DenseRoute | None":
        if not CACHE.exists():
            return None
        data = np.load(CACHE, allow_pickle=False)
        return cls(list(data["asins"]), data["vectors"].astype(np.float32), llm=llm)

    def prepare(self, state: SessionState, candidates: list[str]) -> None:
        self.scores = {}
        if self.llm is None:
            return
        query = f"{state.category or ''}. " + "; ".join(c.text for c in state.live())
        embedded = self.llm.embed([query[:1500]])
        if not embedded:
            return
        vector = np.asarray(embedded[0], dtype=np.float32)
        vector /= np.linalg.norm(vector) + 1e-9
        rows = [(asin, self.position[asin]) for asin in candidates if asin in self.position]
        if not rows:
            return
        indices = np.fromiter((index for _, index in rows), dtype=np.int64, count=len(rows))
        similarity = self.vectors[indices] @ vector
        self.scores = {asin: float(score) for (asin, _), score in zip(rows, similarity)}

    def similarity(self, asin: str) -> float:
        return self.scores.get(asin, 0.0)
