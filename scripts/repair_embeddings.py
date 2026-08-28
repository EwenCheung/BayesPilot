"""Re-embed any product whose vector came back all-zero (rate-limited batch), serially.

A zero row is not a harmless gap: cosine against it is 0 for every query, so that product is invisible
to the dense route forever. Silent partial failure is exactly the class of bug IMPORTANT.md §13.1.3
warns about, so embed_all.py exits non-zero when zero rows remain and this script closes the gap.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np

from embed_all import blob  # noqa: E402  (same directory)

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
KEY = os.environ["SOCLAAS_API_KEY"]
API = os.environ["SOCLAAS_BASE_URL"]


def embed(texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": "bge-m3", "input": texts}).encode()
    request = urllib.request.Request(
        API + "/embeddings", body,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(request, timeout=180))
    return [e["embedding"] for e in data["data"]]


if __name__ == "__main__":
    matrix = np.load(ART / "emb.npy").astype(np.float32)
    ids = json.loads((ART / "emb_ids.json").read_text())
    broken = np.where(np.abs(matrix).sum(axis=1) < 1e-6)[0]
    print(f"{len(broken)} zero rows to repair")
    if len(broken) == 0:
        raise SystemExit(0)

    products = {}
    wanted = {ids[i] for i in broken}
    with (ROOT / "assets" / "catalog.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            p = json.loads(line)
            if str(p["parent_asin"]) in wanted:
                products[str(p["parent_asin"])] = p

    for start in range(0, len(broken), 16):
        chunk = broken[start:start + 16]
        texts = [blob(products[ids[i]]) for i in chunk]
        for attempt in range(6):
            try:
                vectors = np.asarray(embed(texts), dtype=np.float32)
                assert vectors.shape[0] == len(chunk)
                vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
                matrix[chunk] = vectors
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 5:
                    raise
                print(f"  retry {start} ({exc})", flush=True)
                time.sleep(5 * (attempt + 1))
        time.sleep(1.5)  # stay under the rate limit that broke the parallel run
        print(f"  repaired {start + len(chunk)}/{len(broken)}", flush=True)

    remaining = int((np.abs(matrix).sum(axis=1) < 1e-6).sum())
    assert remaining == 0, f"{remaining} rows still zero"
    np.save(ART / "emb.npy", matrix.astype(np.float16))
    print(f"done, 0 zero rows, shape={matrix.shape}")
