"""Embed the catalog with BLaIR — the one encoder pretrained on Amazon Reviews 2023 itself (D11).

⚠️ BUILD-TIME ONLY. This writes a float16 matrix; the agent needs numpy and nothing else at runtime,
so the shipped system still makes zero network calls (PROBLEM.md: "organizer policy may disable
network access").
"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODEL = "hyp1231/blair-roberta-base"        # ⚠️ explicit id, never an alias (trap 8)
OUT = ROOT / "artifacts" / "blair.npz"


def main(limit: int | None = None, batch: int = 128) -> None:
    import torch
    from transformers import AutoModel, AutoTokenizer

    from src.eval import harness
    from src.r3.index import ItemIndex

    index = ItemIndex(str(harness.CATALOG))
    asins = list(index.title)[:limit]
    texts = [f"{index.title[a]}. {' '.join(index.spec[a][:8])}"[:900] for a in asins]

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(device)
    print(f"{MODEL} on {device}, {len(texts)} items", flush=True)

    out = np.zeros((len(texts), model.config.hidden_size), dtype=np.float16)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            enc = tokenizer(chunk, padding=True, truncation=True, max_length=128,
                            return_tensors="pt").to(device)
            # BLaIR's own recipe: CLS token, L2-normalised (AmazonReviews2023/blair/README.md)
            emb = model(**enc, return_dict=True).last_hidden_state[:, 0]
            emb = emb / emb.norm(dim=1, keepdim=True)
            out[i:i + len(chunk)] = emb.cpu().numpy().astype(np.float16)
            if i % (batch * 20) == 0:
                rate = (i + len(chunk)) / max(time.time() - t0, 1e-9)
                print(f"  {i + len(chunk)}/{len(texts)}  {rate:.0f}/s  "
                      f"eta {(len(texts) - i) / max(rate, 1e-9) / 60:.1f} min", flush=True)

    OUT.parent.mkdir(exist_ok=True)
    np.savez_compressed(OUT, vectors=out, asins=np.array(asins))
    print(f"wrote {OUT}  {out.shape}  {OUT.stat().st_size / 1e6:.0f} MB  "
          f"in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
