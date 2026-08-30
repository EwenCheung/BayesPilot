"""The four retrieval routes.

Each returns `{asin: score}` over the candidate pool, route-local and unnormalized — fusion owns
comparability. A route with no opinion returns `{}` so fusion can tell "abstained" from "scored zero".

    popularity   log(rating_number)           paraphrase-proof, and startlingly strong alone (0.7133)
    spec_phrase  soft phrase + token overlap  high precision, paraphrase-fragile — the ablation switch
    lexical      IDF-weighted overlap         keyword surface, Pillar I names it explicitly
    dense        SVD (offline) | bge-m3       semantic, the route that survives rewording
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..r2.catalog import CatalogIndex, content_tokens

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"


@dataclass
class Query:
    """What the customer has told us so far, in the shape the routes want it."""
    category: str | None = None
    resolved_category: str | None = None
    constraints: list[tuple[str, float]] = field(default_factory=list)  # (value, decayed weight)
    text: str = ""            # natural-language rewrite, for dense and lexical
    n_slots: int = 0

    @property
    def tokens(self) -> set[str]:
        return content_tokens(" ".join(v for v, _ in self.constraints))


class Route:
    name = "route"
    def score(self, query: Query, candidates: list[str]) -> dict[str, float]:
        raise NotImplementedError


class PopularityRoute(Route):
    """The 570x target skew (IMPORTANT.md §5) as a ranking signal.

    Normalized within the candidate pool: "well reviewed for a hoop earring" is the signal, not
    "well reviewed compared to a shoe". Ignores every word the customer says, which is exactly why it
    cannot be broken by paraphrasing.
    """
    name = "popularity"

    def __init__(self, index: CatalogIndex) -> None:
        self.index = index

    def score(self, query: Query, candidates: list[str]) -> dict[str, float]:
        if not candidates:
            return {}
        top = max(self.index.log_pop[a] for a in candidates) or 1.0
        return {a: self.index.log_pop[a] / top for a in candidates}


class SpecPhraseRoute(Route):
    """The inversion signal, as a SCORE rather than a filter (decision D4).

    R1 intersects frozensets: one reworded character and the match returns zero — the failure is a cliff.
    Here an exact phrase hit is worth full credit, a partial token overlap earns partial credit, and
    paraphrase becomes a gradient instead of a wall.

    This is the route the `no_spec_phrase` ablation switches off. That ablated score is our private-set
    insurance estimate, so this route must stay cleanly separable.
    """
    name = "spec_phrase"

    def __init__(self, index: CatalogIndex, partial_credit: float = 0.55) -> None:
        self.index = index
        self.partial_credit = partial_credit

    def score(self, query: Query, candidates: list[str]) -> dict[str, float]:
        if not query.constraints:
            return {}
        out: dict[str, float] = {}
        total = sum(w for _, w in query.constraints) or 1.0
        per_constraint = [(v, content_tokens(v), w) for v, w in query.constraints]
        for asin in candidates:
            phrases = self.index.phrases[asin]
            tokens = self.index.tokens[asin]
            earned = 0.0
            for value, value_tokens, weight in per_constraint:
                if value in phrases:
                    earned += weight                      # exact spec string: full credit
                elif value_tokens:
                    overlap = len(value_tokens & tokens) / len(value_tokens)
                    if overlap > 0:
                        earned += weight * self.partial_credit * overlap
            if earned:
                out[asin] = earned / total
        return out


class LexicalRoute(Route):
    """IDF-weighted token overlap over the product's own words.

    A BM25 simplification: no term-frequency saturation, because product docs here are short and of
    near-uniform length, and the postings-with-counts index that TF would need costs several hundred MB
    for no measurable gain. Surface is title + categories + store + features — deliberately DIFFERENT
    from the spec-phrase route, which reads features + details, so the two are not the same evidence
    counted twice.
    """
    name = "lexical"
    FIELDS = ("title", "categories", "store", "features")

    def __init__(self, index: CatalogIndex, cap: int = 64) -> None:
        self.index = index
        raw: dict[str, set[str]] = {}
        df: dict[str, int] = {}
        for asin, product in index.products.items():
            parts: list[str] = []
            for field_name in self.FIELDS:
                value = product.get(field_name)
                if isinstance(value, list):
                    parts.extend(str(x) for x in value)
                elif value is not None:
                    parts.append(str(value))
            tokens = content_tokens(" ".join(parts))
            raw[asin] = tokens
            for token in tokens:
                df[token] = df.get(token, 0) + 1

        n = len(raw) or 1
        self.idf = {t: math.log(1.0 + n / (1.0 + c)) for t, c in df.items()}
        # ⚠️ Truncating with list(set)[:cap] would pick a DIFFERENT subset every process, because
        # str hashing is salted per interpreter — the score then drifts run to run and the harness is
        # worthless. Keep the `cap` rarest tokens instead: deterministic, and it drops exactly the
        # high-frequency tokens that carry the least discrimination anyway.
        self.doc_tokens: dict[str, frozenset[str]] = {
            asin: frozenset(sorted(tokens, key=lambda t: (-self.idf[t], t))[:cap])
            for asin, tokens in raw.items()
        }

    def score(self, query: Query, candidates: list[str]) -> dict[str, float]:
        wanted = query.tokens | content_tokens(query.category or "")
        if not wanted:
            return {}
        ceiling = sum(self.idf.get(t, 0.0) for t in wanted) or 1.0
        out: dict[str, float] = {}
        for asin in candidates:
            hit = wanted & self.doc_tokens[asin]
            if hit:
                out[asin] = sum(self.idf.get(t, 0.0) for t in hit) / ceiling
        return out


class SvdBackend:
    """Offline dense backend: TF-IDF -> TruncatedSVD, built from the catalog at startup.

    No download, no network, no spend. This exists because the dense route is the ONE route that cannot
    be skipped when the network is disabled — unlike the reranker it must embed the live query every
    turn (decision D2). Weaker than bge-m3, and that gap is measured rather than assumed.
    """
    name = "svd"

    def __init__(self, index: CatalogIndex, dim: int = 256, seed: int = 0) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.asins = list(index.products)
        corpus = [_blob(index.products[a]) for a in self.asins]
        self.vectorizer = TfidfVectorizer(
            max_features=120_000, sublinear_tf=True, strip_accents="unicode",
            lowercase=True, stop_words="english", min_df=2,
        )
        matrix = self.vectorizer.fit_transform(corpus)
        self.svd = TruncatedSVD(n_components=dim, random_state=seed)
        reduced = self.svd.fit_transform(matrix).astype(np.float32)
        reduced /= np.linalg.norm(reduced, axis=1, keepdims=True) + 1e-9
        self.matrix = reduced
        self.pos = {a: i for i, a in enumerate(self.asins)}

    def encode(self, text: str) -> np.ndarray:
        vector = self.svd.transform(self.vectorizer.transform([text])).astype(np.float32)[0]
        return vector / (np.linalg.norm(vector) + 1e-9)


class BgeBackend:
    """API dense backend: precomputed bge-m3 vectors for all 50,000 products.

    Query embedding is one API call per turn, content-hash cached so repeated evaluation runs are free
    and deterministic. Requires network — that is the disclosure, and SvdBackend is the fallback.
    """
    name = "bge-m3"

    def __init__(self, index: CatalogIndex) -> None:
        ids = json.loads((ARTIFACTS / "emb_ids.json").read_text())
        self.matrix = np.load(ARTIFACTS / "emb.npy").astype(np.float32)
        assert len(ids) == self.matrix.shape[0], "emb_ids.json and emb.npy disagree"
        self.pos = {a: i for i, a in enumerate(ids)}
        missing = len(index.products) - len(self.pos)
        assert missing == 0, f"{missing} catalog products have no vector - dense route would be blind"
        self.api = os.environ.get("SOCLAAS_BASE_URL", "")
        self.key = os.environ.get("SOCLAAS_API_KEY", "")
        self.cache_path = ARTIFACTS / "query_cache.jsonl"
        self.cache: dict[str, list[float]] = {}
        if self.cache_path.exists():
            for line in self.cache_path.open(encoding="utf-8"):
                row = json.loads(line)
                self.cache[row["k"]] = row["v"]
        self.calls = 0
        self.failures = 0

    def encode(self, text: str) -> np.ndarray:
        key = hashlib.sha256(text.encode()).hexdigest()[:32]
        if key not in self.cache:
            body = json.dumps({"model": "bge-m3", "input": [text[:1500]]}).encode()
            request = urllib.request.Request(
                self.api + "/embeddings", body,
                {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
            )
            data = json.load(urllib.request.urlopen(request, timeout=60))
            vector = data["data"][0]["embedding"]
            # Never let a silent failure look like a model that is not helping (IMPORTANT.md §13.1.3).
            assert vector and len(vector) == self.matrix.shape[1], "empty bge-m3 embedding"
            self.calls += 1
            self.cache[key] = vector
            with self.cache_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"k": key, "v": vector}) + "\n")
        vector = np.asarray(self.cache[key], dtype=np.float32)
        return vector / (np.linalg.norm(vector) + 1e-9)


class DenseRoute(Route):
    """Semantic similarity between the rewritten query and the product blob."""
    name = "dense"

    def __init__(self, backend) -> None:
        self.backend = backend

    def score(self, query: Query, candidates: list[str]) -> dict[str, float]:
        if not query.text.strip() or not candidates:
            return {}
        known = [a for a in candidates if a in self.backend.pos]
        if not known:
            return {}
        try:
            vector = self.backend.encode(query.text)
        except Exception:
            return {}  # a dead endpoint costs the route, not the turn
        rows = np.fromiter((self.backend.pos[a] for a in known), dtype=np.int64, count=len(known))
        sims = self.backend.matrix[rows] @ vector
        return dict(zip(known, (sims + 1.0) / 2.0))  # cosine [-1,1] -> [0,1]


_WS = re.compile(r"\s+")


def _blob(product: dict) -> str:
    """Same text shape the bge-m3 embeddings were built from, so the backends stay comparable."""
    parts = [str(product.get("title") or "")]
    parts += [str(x) for x in (product.get("features") or [])][:8]
    parts += [f"{k}: {v}" for k, v in list((product.get("details") or {}).items())[:10]]
    parts.append(" > ".join(str(x) for x in (product.get("categories") or [])))
    return _WS.sub(" ", " | ".join(x for x in parts if x))[:2000]
