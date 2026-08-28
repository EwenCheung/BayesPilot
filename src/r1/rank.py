"""Spec 3.8 — order the survivors. Ranking is a tie-break here, not the main event.

Cascade: weighted match count → log-popularity → dense cosine (flag) → LLM listwise (flag).
Popularity is never ablated by default: it is the one signal no rewording can touch
(IMPORTANT.md §5).
"""
from __future__ import annotations

from src.common.catalog import CatalogIndex
from src.common.contracts import SessionState
from src.r1.flags import Flags

RERANK_DEPTH = 10


def order(
    index: CatalogIndex,
    state: SessionState,
    candidates: list[str],
    scores: dict[str, float],
    flags: Flags,
    llm=None,
    dense=None,
) -> list[str]:
    popularity = index.popularity if flags.popularity else {}

    def key(asin: str) -> tuple:
        similarity = dense.similarity(asin) if (flags.dense and dense) else 0.0
        return (-scores.get(asin, 0.0), -similarity, -popularity.get(asin, 0.0), asin)

    ranked = sorted(candidates, key=key)

    # LLM Semantic Ranking (PROBLEM.md Pillar I, IMPORTANT.md §14.1) — escalation only:
    # if the deterministic path already has a strict unique leader there is nothing to fix,
    # and a call we skip is a call that cannot time out during official scoring.
    # Adaptive orchestration (Pillar III): reranking measured -0.005 on clean text and +0.009 under
    # paraphrase, so gate it on the runtime signal that tells the two apart — whether any template
    # has matched this session. Clean sessions never pay for it; reworded ones get it automatically.
    if flags.llm_rerank and llm is not None and len(ranked) > 1:
        if flags.adaptive and not state.paraphrased():
            return ranked
        leader_is_strict = scores.get(ranked[0], 0.0) > scores.get(ranked[1], 0.0)
        if not leader_is_strict:
            head = ranked[:RERANK_DEPTH]
            query = "; ".join(c.text for c in state.live()) or (state.category or "")
            labels = [f"{index.title.get(asin, '')} | {' | '.join(index.spec_strings.get(asin, [])[:3])}"
                      for asin in head]
            permuted = llm.rerank(query, head, labels=labels)
            if permuted:
                ranked = permuted + ranked[RERANK_DEPTH:]
    return ranked
