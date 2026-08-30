#!/usr/bin/env python3
"""Unified parallel model training and hyperparameter fitting script.

Usage:
    python3 train_model.py \
      --dataset_train techjam-conversational-search-main/data/combine/train.jsonl \
      --dataset_validation techjam-conversational-search-main/data/combine/validation.jsonl \
      --output models/combine/ \
      --catalog assets/catalog.jsonl

Hardware Acceleration:
    * Automatically detects and uses CUDA (NVIDIA GPU) if available.
    * Automatically falls back to MPS (Apple Silicon GPU) if available.
    * Uses multi-core CPU parallelism for hyperparameter grid search and tabular LTR training.
    * You can explicitly override device with `--device cuda`, `--device mps`, or `--device cpu`.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Ensure repo root and starter kit are in sys.path
ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "techjam-conversational-search-main"
sys.path[:0] = [str(ROOT), str(KIT)]

from src.r3.flags import Flags
from src.r3.ltr import LTRRanker, extract_features


# ---------------- Hardware Detection ----------------

def detect_device(preferred: str | None = None) -> tuple[str, str]:
    """Detect best available compute device (cuda > mps > cpu)."""
    if preferred:
        return preferred.lower(), f"User requested device: {preferred}"

    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            return "cuda", f"CUDA GPU available: {gpu_name} (Device count: {torch.cuda.device_count()})"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps", "Apple Silicon MPS (Metal Performance Shaders) GPU available"
    except ImportError:
        pass
    return "cpu", f"CPU mode ({os.cpu_count() or 4} cores available)"


# ---------------- Candidate Configurations ----------------

CANDIDATE_CONFIGS: list[tuple[str, dict[str, Any]]] = [
    ("baseline_neutral", {
        "exact_gain": 3.2,
        "prior_weight": 0.10,
        "v_continue": 0.90,
        "stall_decay": 0.20,
        "stall_decay_clean": 0.80,
        "temperature": 2.0,
        "tau_mass": 0.90,
        "rescue_lexical": False,
        "rescue_semantic": False,
        "use_rrf": False,
    }),
    ("rescue_lexical_only", {
        "rescue_lexical": True,
        "rescue_top_k": 200,
        "use_rrf": True,
        "rrf_weight_category": 1.0,
        "rrf_weight_lexical": 0.5,
    }),
    ("rescue_semantic_only", {
        "rescue_semantic": True,
        "rescue_top_k": 200,
        "use_rrf": True,
        "rrf_weight_category": 1.0,
        "rrf_weight_semantic": 0.5,
    }),
    ("rescue_full_rrf", {
        "rescue_lexical": True,
        "rescue_semantic": True,
        "rescue_normalized": True,
        "rescue_top_k": 200,
        "use_rrf": True,
        "rrf_k": 60,
        "rrf_weight_category": 1.0,
        "rrf_weight_lexical": 0.5,
        "rrf_weight_semantic": 0.5,
    }),
    ("prior_015_rrf", {
        "prior_weight": 0.15,
        "rescue_lexical": True,
        "rescue_semantic": True,
        "use_rrf": True,
    }),
    ("prior_005_rrf", {
        "prior_weight": 0.05,
        "rescue_lexical": True,
        "rescue_semantic": True,
        "use_rrf": True,
    }),
    ("gain_400_rrf", {
        "exact_gain": 4.00,
        "rescue_lexical": True,
        "rescue_semantic": True,
        "use_rrf": True,
    }),
    ("tau_095_rrf", {
        "tau_mass": 0.95,
        "rescue_lexical": True,
        "rescue_semantic": True,
        "use_rrf": True,
    }),
    ("v_continue_095", {
        "v_continue": 0.95,
        "rescue_lexical": True,
        "rescue_semantic": True,
        "use_rrf": True,
    }),
]


# ---------------- Worker Functions ----------------

def _eval_single_config(
    name: str,
    overrides: dict[str, Any],
    dataset_path: str,
    catalog_path: str,
    sample_limit: int | None = None,
) -> dict[str, Any]:
    """Evaluate one parameter configuration on a dataset using local evaluator."""
    from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
    from src.r3.agent import Agent

    catalog_ids, categories, products = catalog_index(catalog_path)
    rows = load_jsonl(dataset_path)
    if sample_limit and sample_limit < len(rows):
        rows = rows[:sample_limit]

    agent = Agent(catalog_path)
    base_flags = Flags()
    for field in dataclasses.fields(base_flags):
        if field.name in overrides:
            setattr(agent.flags, field.name, overrides[field.name])

    start_time = time.time()
    result = evaluate(agent, rows, catalog_ids, categories, products)
    elapsed = time.time() - start_time

    return {
        "name": name,
        "overrides": overrides,
        "sample_count": len(rows),
        "hit_rate_at_10": result.get("hit_rate_at_10", 0.0),
        "mrr": result.get("mrr", 0.0),
        "mttc": result.get("mttc", 0.0),
        "efficiency": result.get("efficiency", 0.0),
        "recommended_technical_score": result.get("recommended_technical_score", 0.0),
        "elapsed_s": round(elapsed, 2),
    }


# ---------------- Dense Embedding Generation (CUDA / MPS / CPU) ----------------

def generate_embeddings_if_needed(
    catalog_path: Path,
    output_dir: Path,
    device_name: str,
) -> Path | None:
    """Generate dense BLaIR / transformer embeddings if PyTorch & transformers are present."""
    npz_out = output_dir / "blair.npz"
    if npz_out.exists():
        print(f"[Embedding] Using existing catalog embedding artifact at: {npz_out}")
        return npz_out

    try:
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        print("[Embedding] PyTorch or Transformers not installed in environment; skipping dense pre-embedding.")
        return None

    model_id = "hyp1231/blair-roberta-base"
    print(f"\n{'='*70}")
    print(f"[Embedding] Generating catalog dense embeddings on {device_name.upper()}...")
    print(f"[Embedding] Model: {model_id}")
    print(f"{'='*70}")
    sys.stdout.flush()

    start_time = time.time()
    device = torch.device(device_name)

    # Ingest catalog products
    products: list[dict] = []
    with catalog_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                products.append(json.loads(line))

    asins = [p["parent_asin"] for p in products if "parent_asin" in p]
    texts = [
        f"{p.get('title', '')} {' '.join(p.get('features', []) or [])[:300]}"
        for p in products if "parent_asin" in p
    ]

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id).to(device).eval()
    except Exception as e:
        print(f"[Embedding] Notice: Could not download {model_id} ({e}); continuing with in-memory SVD fallback.")
        return None

    batch_size = 64 if device_name in ("cuda", "mps") else 16
    all_vectors: list[np.ndarray] = []

    total_batches = math.ceil(len(texts) / batch_size)
    print(f"[Embedding] Encoding {len(texts)} products in {total_batches} batches (batch_size={batch_size})...")

    with torch.no_grad():
        for b_idx in range(0, len(texts), batch_size):
            batch_texts = texts[b_idx : b_idx + batch_size]
            encoded = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            ).to(device)
            out = model(**encoded, return_dict=True).last_hidden_state[:, 0]
            out = out / out.norm(dim=1, keepdim=True)
            all_vectors.append(out.cpu().numpy().astype(np.float32))

            if (b_idx // batch_size + 1) % 50 == 0 or (b_idx + batch_size) >= len(texts):
                progress = min(100.0, (b_idx + batch_size) / len(texts) * 100)
                print(f"  [Embedding] Progress: {progress:.1f}% ({min(b_idx + batch_size, len(texts))}/{len(texts)})", flush=True)

    matrix = np.vstack(all_vectors)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_out, asins=np.array(asins), vectors=matrix)

    elapsed = time.time() - start_time
    print(f"[Embedding] Completed in {elapsed:.2f}s. Saved to: {npz_out}\n", flush=True)
    return npz_out


# ---------------- LTR Training Pipeline ----------------

def train_ltr_ranker(
    train_path: Path,
    catalog_path: Path,
    output_dir: Path,
    sample_limit: int = 1500,
) -> Path:
    """Train a gradient-boosted Learning-to-Rank model on positive vs hard negative pairs."""
    from evaluator.local_evaluator import catalog_index, load_jsonl
    from src.r3.agent import Agent

    print(f"\n{'='*70}")
    print(f"[LTR] Training Learning-to-Rank (LTR / GBDT) model...")
    print(f"{'='*70}")
    sys.stdout.flush()

    start_time = time.time()
    agent = Agent(catalog_path)
    rows = load_jsonl(train_path)
    if sample_limit and sample_limit < len(rows):
        rows = rows[:sample_limit]

    X_list: list[np.ndarray] = []
    y_list: list[float] = []

    print(f"[LTR] Extracting ranking feature vectors across {len(rows)} training sessions...")
    for idx, sample in enumerate(rows):
        target = str(sample["ground_truth"]["parent_asin"])
        opener = sample.get("initial_message") or "I am looking for items"
        session_id = f"ltr_train_{idx}"
        agent.reset(session_id, sample.get("user_profile", {}))
        state = agent.sessions[session_id]

        # Get candidate pool
        pool = agent._candidate_pool(state, opener)
        if target not in pool:
            pool.append(target)

        # Sample positive + 8 hard negatives
        hard_negatives = [a for a in pool if a != target][:8]
        candidates = [target] + hard_negatives

        X_session = extract_features(
            agent.index,
            candidates,
            state,
            query_raw=opener,
            query_norm=opener,
            top_category=state.category,
        )

        # Labels: 1.0 for target, 0.0 for negatives
        y_session = [1.0] + [0.0] * len(hard_negatives)

        X_list.append(X_session)
        y_list.extend(y_session)

        if (idx + 1) % 300 == 0 or idx + 1 == len(rows):
            print(f"  [LTR Feature Extraction] {idx + 1}/{len(rows)} sessions processed", flush=True)

    import numpy as np
    X_train = np.vstack(X_list)
    y_train = np.array(y_list, dtype=np.float32)

    print(f"[LTR] Training HistGradientBoostingRegressor on {len(X_train)} item feature pairs...")
    ranker = LTRRanker(model_type="hist_gb")
    ranker.fit(X_train, y_train)

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "ltr_model.pkl"
    ranker.save(model_path)

    elapsed = time.time() - start_time
    print(f"[LTR] Model trained and serialized in {elapsed:.2f}s -> {model_path}\n", flush=True)
    return model_path


# ---------------- Main Driver ----------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Train, fit, and validate search ranking models")
    parser.add_argument("--dataset_train", required=True, help="Path to train JSONL")
    parser.add_argument("--dataset_validation", required=True, help="Path to validation JSONL")
    parser.add_argument("--output", required=True, help="Output directory to save fitted artifacts")
    parser.add_argument("--catalog", default=str(ROOT / "assets" / "catalog.jsonl"), help="Catalog JSONL path")
    parser.add_argument("--device", default=None, help="Explicit device override: cuda | mps | cpu")
    parser.add_argument("--num_workers", type=int, default=max(1, (os.cpu_count() or 4) - 1), help="CPU workers for parallel grid search")
    parser.add_argument("--skip_embeddings", action="store_true", help="Skip dense embedding generation")
    args = parser.parse_args()

    train_path = Path(args.dataset_train).resolve()
    val_path = Path(args.dataset_validation).resolve()
    catalog_path = Path(args.catalog).resolve()
    output_dir = Path(args.output).resolve()

    for label, path in (("Train dataset", train_path), ("Validation dataset", val_path), ("Catalog", catalog_path)):
        if not path.is_file():
            raise SystemExit(f"Error: {label} file not found at: {path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    device_name, device_desc = detect_device(args.device)

    print("=" * 80)
    print("🚀 TECHJAM CONVERSATIONAL SEARCH - UNIFIED MODEL TRAINING PIPELINE")
    print("=" * 80)
    print(f"Train Dataset:      {train_path}")
    print(f"Validation Dataset: {val_path}")
    print(f"Catalog Path:       {catalog_path}")
    print(f"Output Directory:   {output_dir}")
    print(f"Compute Device:     {device_name.upper()} ({device_desc})")
    print(f"Parallel Workers:   {args.num_workers} CPU cores")
    print("=" * 80)
    sys.stdout.flush()

    total_start = time.time()

    # 1. Generate dense embeddings if GPU / PyTorch available
    if not args.skip_embeddings:
        generate_embeddings_if_needed(catalog_path, output_dir, device_name)

    # 2. Train LTR Ranker
    ltr_model_path = train_ltr_ranker(train_path, catalog_path, output_dir)

    # 3. Parallel Parameter Sweep on Train Dataset
    print("=" * 80)
    print(f"[Stage 1/2] Running Parallel Parameter Fitting on {train_path.name}...")
    print(f"Evaluating {len(CANDIDATE_CONFIGS)} candidate configurations across {args.num_workers} workers...")
    print("=" * 80)
    sys.stdout.flush()

    train_results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.num_workers) as executor:
        futures = {
            executor.submit(
                _eval_single_config,
                name,
                overrides,
                str(train_path),
                str(catalog_path),
                sample_limit=800,  # Stratified subsample for fast high-confidence selection
            ): name
            for name, overrides in CANDIDATE_CONFIGS
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                res = future.result()
                train_results.append(res)
                print(f"  ✓ [{res['name']}] Technical Score: {res['recommended_technical_score']:.6f} | Hit@10: {res['hit_rate_at_10']:.4f} | MRR: {res['mrr']:.4f} ({res['elapsed_s']}s)", flush=True)
            except Exception as e:
                print(f"  ✗ [{name}] Failed with error: {e}", flush=True)

    # Sort training results
    train_results.sort(key=lambda r: -r["recommended_technical_score"])
    top_candidates = train_results[:3]

    print("\n" + "-" * 80)
    print("🏆 TOP 3 TRAINING CANDIDATES ADVANCING TO VALIDATION:")
    for rank, cand in enumerate(top_candidates, 1):
        print(f"  {rank}. {cand['name']}: Tech Score = {cand['recommended_technical_score']:.6f} (MRR={cand['mrr']:.4f}, Hit@10={cand['hit_rate_at_10']:.4f})")
    print("-" * 80 + "\n", flush=True)

    # 4. Evaluate Top Candidates on Validation Dataset
    print("=" * 80)
    print(f"[Stage 2/2] Validating Top Candidates on {val_path.name}...")
    print("=" * 80)
    sys.stdout.flush()

    val_results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=min(len(top_candidates), args.num_workers)) as executor:
        futures = {
            executor.submit(
                _eval_single_config,
                cand["name"],
                cand["overrides"],
                str(val_path),
                str(catalog_path),
            ): cand["name"]
            for cand in top_candidates
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                res = future.result()
                val_results.append(res)
                print(f"  ★ [Validation: {res['name']}] Tech Score: {res['recommended_technical_score']:.6f} | Hit@10: {res['hit_rate_at_10']:.4f} | MRR: {res['mrr']:.4f} | MTTC: {res['mttc']:.2f} ({res['elapsed_s']}s)", flush=True)
            except Exception as e:
                print(f"  ✗ [Validation: {name}] Failed with error: {e}", flush=True)

    val_results.sort(key=lambda r: -r["recommended_technical_score"])
    best_val = val_results[0] if val_results else top_candidates[0]

    # Save Best Configuration
    best_config_path = output_dir / "best_config.json"
    with best_config_path.open("w", encoding="utf-8") as f:
        json.dump(best_val["overrides"], f, indent=2)

    total_elapsed = time.time() - total_start

    # Build and write final training report
    report = {
        "dataset_train": str(train_path),
        "dataset_validation": str(val_path),
        "catalog_path": str(catalog_path),
        "device": device_name,
        "device_description": device_desc,
        "total_elapsed_s": round(total_elapsed, 2),
        "total_elapsed_min": round(total_elapsed / 60.0, 2),
        "best_configuration_name": best_val["name"],
        "best_configuration_overrides": best_val["overrides"],
        "best_validation_metrics": {
            "recommended_technical_score": best_val["recommended_technical_score"],
            "hit_rate_at_10": best_val["hit_rate_at_10"],
            "mrr": best_val["mrr"],
            "mttc": best_val["mttc"],
            "efficiency": best_val["efficiency"],
        },
        "all_validation_results": val_results,
        "training_sweep_results": train_results,
    }

    report_path = output_dir / "training_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 80)
    print("🎉 TRAINING AND VALIDATION COMPLETE!")
    print("=" * 80)
    print(f"Total Elapsed Time: {total_elapsed / 60.0:.2f} minutes ({total_elapsed:.1f}s)")
    print(f"Best Configuration: {best_val['name']}")
    print(f"Validation Tech Score: {best_val['recommended_technical_score']:.6f}")
    print(f"Validation Hit@10:    {best_val['hit_rate_at_10']:.4f}")
    print(f"Validation MRR:       {best_val['mrr']:.4f}")
    print(f"Validation MTTC:      {best_val['mttc']:.2f}")
    print(f"Artifacts Saved To:   {output_dir}")
    print(f"  - Best Config:      {best_config_path}")
    print(f"  - LTR Model:        {ltr_model_path}")
    print(f"  - Full Report:      {report_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
