"""Experiment runner: score R2 variants side by side, clean and stressed, and register the results.

    python3 -m src.eval.compare quick     # floors + full R2, offline dense, no registry write
    python3 -m src.eval.compare full      # every variant + stress + ablations, writes runs/registry.jsonl

Heavy objects (catalog index, lexical index, dense backends) are built once and injected into every
variant, so comparing a dozen configurations costs one build rather than a dozen.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.catalog import CatalogIndex  # noqa: E402
from src.eval import harness  # noqa: E402
from src.eval.stress import ParaphraseRewriter  # noqa: E402
from src.r2.agent import Agent  # noqa: E402
from src.r2.routes import BgeBackend, LexicalRoute, SvdBackend  # noqa: E402

_SHARED: dict = {}


def shared(dense: str = "svd"):
    """Build (and cache) the expensive pieces once per process."""
    if "index" not in _SHARED:
        t0 = time.time()
        _SHARED["index"] = CatalogIndex(ROOT / "assets" / "catalog.jsonl")
        _SHARED["lexical"] = LexicalRoute(_SHARED["index"])
        print(f"  [index + lexical built in {time.time() - t0:.0f}s]", flush=True)
    index = _SHARED["index"]
    if dense == "none":
        backend = None
    elif dense not in _SHARED:
        t0 = time.time()
        _SHARED[dense] = SvdBackend(index) if dense == "svd" else BgeBackend(index)
        print(f"  [{dense} backend built in {time.time() - t0:.0f}s]", flush=True)
        backend = _SHARED[dense]
    else:
        backend = _SHARED[dense]
    return index, _SHARED["lexical"], backend


def build(dense: str = "svd", **kwargs) -> Agent:
    index, lexical, backend = shared(dense)
    return Agent(index=index, lexical=lexical, dense_backend=backend,
                 dense="none" if backend is None else dense, **kwargs)


def row(label: str, result: dict) -> str:
    return (f"{label:<34s} {result['hit_rate_at_10']:.3f}  {result['mrr']:.4f}  "
            f"{result['mttc']:.2f}  {harness.score(result):.4f}")


HEADER = f"{'variant':<34s} {'hit@10':>6s}  {'MRR':>6s}  {'MTTC':>5s}  {'SCORE':>6s}"


def evaluate(label: str, dense: str = "svd", stress: bool = False, **kwargs) -> dict:
    agent = build(dense, **kwargs)
    clean = harness.run(agent)
    print(row(label, clean), flush=True)
    out = {"clean": clean}
    if stress:
        for level in ("scaffold", "full"):
            agent = build(dense, **kwargs)  # fresh state, same indices
            stressed = harness.run(agent, ParaphraseRewriter(level))
            print(row(f"  └ paraphrase:{level}", stressed), flush=True)
            out[level] = stressed
    return out


def main(mode: str = "quick") -> None:
    print(HEADER)
    print("-" * len(HEADER))

    if mode == "quick":
        evaluate("R2 popularity only (floor)", dense="none",
                 ablations=("no_spec_phrase", "no_lexical", "no_dense"))
        evaluate("R2 no_spec_phrase (insurance)", dense="svd", ablations=("no_spec_phrase",))
        evaluate("R2 full (svd dense)", dense="svd")
        return

    results: dict[str, dict] = {}
    print("\n== floors ==")
    results["popularity_only"] = evaluate(
        "popularity only", dense="none",
        ablations=("no_spec_phrase", "no_lexical", "no_dense"))
    print("\n== ablations (svd dense) ==")
    for ablation in ("no_spec_phrase", "no_dense", "no_popularity", "no_lexical"):
        results[ablation] = evaluate(ablation, dense="svd", ablations=(ablation,))
    print("\n== fusion ==")
    results["rrf"] = evaluate("RRF baseline", dense="svd", fuse="rrf")
    print("\n== full ==")
    results["svd"] = evaluate("R2 full (svd dense)", dense="svd", stress=True)
    if (ROOT / "artifacts" / "emb.npy").exists():
        results["bge"] = evaluate("R2 full (bge-m3 dense)", dense="bge", stress=True)
        results["bge_no_spec"] = evaluate("R2 no_spec_phrase (bge-m3)", dense="bge",
                                          ablations=("no_spec_phrase",), stress=True)
    return results


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "quick")
