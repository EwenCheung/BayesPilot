"""One-off: embed the catalog with `bge-m3` so the dense tie-break has vectors to use.

~50,000 products ≈ 9.9M tokens ≈ $0.10 on this endpoint (IMPORTANT.md §12.3). Resumable, cached
to `.cache/embeddings.npz`, and stored as float16 (50k × 1024 = 102 MB) so it stays comfortably
in-memory as the rules require.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from src.common.llm import LLMClient
from src.common.simulator import _flatten_values

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "embeddings.npz"
BATCH = 48
# 12-way parallelism measured 548/1042 batches rate-limited on this endpoint;
# 4 is the level that completes. Override with R1_EMBED_WORKERS.
WORKERS = int(os.environ.get("R1_EMBED_WORKERS") or 4)


def product_text(product: dict) -> str:
    parts = [str(product.get("title") or ""), *(_flatten_values(product.get("features"))[:8]),
             *(_flatten_values(product.get("details"))[:8])]
    return " | ".join(part for part in parts if part)[:1500]


def main(catalog: str = "techjam-conversational-search-main/data/catalog.jsonl") -> None:
    rows = [json.loads(line) for line in (ROOT / catalog).open(encoding="utf-8")]
    asins = [str(row["parent_asin"]) for row in rows]
    texts = [product_text(row) for row in rows]
    client = LLMClient()
    batches = [(i, texts[i:i + BATCH]) for i in range(0, len(texts), BATCH)]
    vectors: dict[int, list[list[float]]] = {}

    def work(job):
        start, chunk = job
        result = client.embed(chunk)
        if result is None:
            return start, None
        return start, result

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, (start, result) in enumerate(pool.map(work, batches), start=1):
            if result is not None:
                vectors[start] = result
            if done % 50 == 0:
                print(f"{done}/{len(batches)} batches, failures={client.failures}", flush=True)

    missing = [start for start, _ in batches if start not in vectors]
    if missing:
        print(f"⚠️ {len(missing)} batches failed; embedding file will be partial", flush=True)
    keep_asins, matrix = [], []
    for start, chunk in batches:
        if start in vectors:
            keep_asins.extend(asins[start:start + len(chunk)])
            matrix.extend(vectors[start])
    array = np.asarray(matrix, dtype=np.float32)
    array /= np.linalg.norm(array, axis=1, keepdims=True) + 1e-9
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, asins=np.array(keep_asins), vectors=array.astype(np.float16))
    print(f"wrote {CACHE} — {array.shape} · llm report {client.report()}")


if __name__ == "__main__":
    main(*sys.argv[1:])
