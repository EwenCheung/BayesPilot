"""Embed ALL 50,000 catalog products with bge-m3 -> artifacts/emb.npy (fp16) + emb_ids.json.

Why all 50k and not a pool: experiments/embed_catalog.py embedded only the 22,458 products whose
coarse_category matched a PUBLIC-SET target's. That pool is derived from the public labels, so a
private-set target in an unrepresented category would have no vector at all. R2's dense route has to
cover the whole catalog or it is not measurable on the private set.

Run:  set -a && . ./.env && set +a && python3 scripts/embed_all.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
BATCH = 48
WORKERS = 12
DIM = 1024

KEY = os.environ["SOCLAAS_API_KEY"]
API = os.environ["SOCLAAS_BASE_URL"]


def blob(product: dict) -> str:
    """Same shape as experiments/embed_catalog.py so earlier measurements stay comparable."""
    parts = [str(product.get("title") or "")]
    parts += [str(x) for x in (product.get("features") or [])][:8]
    parts += [f"{k}: {v}" for k, v in list((product.get("details") or {}).items())[:10]]
    parts.append(" > ".join(str(x) for x in (product.get("categories") or [])))
    return " | ".join(x for x in parts if x)[:2000]


def embed_chunk(start: int) -> tuple[int, list[list[float]]]:
    chunk = TEXTS[start:start + BATCH]
    for attempt in range(5):
        try:
            body = json.dumps({"model": "bge-m3", "input": chunk}).encode()
            req = urllib.request.Request(
                API + "/embeddings", body,
                {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
            )
            data = json.load(urllib.request.urlopen(req, timeout=180))
            vectors = [e["embedding"] for e in data["data"]]
            assert len(vectors) == len(chunk), f"got {len(vectors)} for {len(chunk)}"
            return start, vectors
        except Exception as exc:  # noqa: BLE001 - retry any transport/parse failure
            if attempt == 4:
                print(f"FAIL {start}: {exc}", flush=True)
                FAILURES.append(start)
                return start, [[0.0] * DIM] * len(chunk)
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    catalog = ROOT / "assets" / "catalog.jsonl"
    products = {}
    with catalog.open(encoding="utf-8") as handle:
        for line in handle:
            p = json.loads(line)
            products[str(p["parent_asin"])] = p

    IDS = sorted(products)
    TEXTS = [blob(products[a]) for a in IDS]
    FAILURES: list[int] = []
    print(f"{len(IDS)} products to embed", flush=True)

    starts = list(range(0, len(TEXTS), BATCH))
    out: dict[int, list[list[float]]] = {}
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        for n, (start, vectors) in enumerate(pool.map(embed_chunk, starts)):
            out[start] = vectors
            if n % 50 == 0:
                print(f"{n}/{len(starts)} {time.time() - t0:.0f}s", flush=True)

    matrix = np.zeros((len(IDS), DIM), dtype=np.float32)
    for start, vectors in out.items():
        matrix[start:start + len(vectors)] = np.asarray(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9

    zero_rows = int((np.abs(matrix).sum(axis=1) < 1e-6).sum())
    OUT.mkdir(exist_ok=True)
    np.save(OUT / "emb.npy", matrix.astype(np.float16))
    (OUT / "emb_ids.json").write_text(json.dumps(IDS))
    print(f"done {time.time() - t0:.0f}s shape={matrix.shape} "
          f"failed_batches={len(FAILURES)} zero_rows={zero_rows}", flush=True)
    if zero_rows:
        print("WARNING: zero rows present - dense route will be blind for those products", flush=True)
        sys.exit(1)
