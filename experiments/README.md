# experiments/

Throwaway prototypes and measurement scripts backing the numbers in [../IDEA.md](../IDEA.md) and
[../REPORT.md](../REPORT.md). **Not the submission** — the real system goes in `src/` when we start building.

| File | What it does | Result |
|---|---|---|
| `agent_inversion_0.9074.py` | Simulator inversion, recommends every turn | TechnicalScore **0.9074** |
| `agent_best_0.9607.py` | Same + confidence gate + turn-3 deadline | TechnicalScore **0.9607** |
| `embed_catalog.py` | Embeds catalog pools with `bge-m3` (12-way parallel) | 22,458 items in ~6 min |
| `floor_test.py` | Paraphrase-proof floor: popularity vs dense vs RRF vs blend | blend hit@10 **0.905** |
| `blend_sweep.py` | Sweeps the dense/popularity weight × information state | optimum **w≈0.02–0.03** with full card, **pure popularity** at turn 1 |
| `rerank_model_test.py` | Listwise rerank quality across chat models | `qwen3.6:35b` **+0.19 MRR**, `llama3.1:8b` +0.005 |

## Running them

```bash
cd ..                                  # repo root
set -a && . ./.env && set +a           # SOCLAAS_API_KEY / SOCLAAS_BASE_URL
python3 experiments/embed_catalog.py   # writes experiments/emb.npy (gitignored)
python3 experiments/floor_test.py
python3 experiments/blend_sweep.py
```

To score an agent, copy it over the starter and run the official evaluator:
```bash
cp experiments/agent_best_0.9607.py techjam-conversational-search-main/starter/agent.py
cd techjam-conversational-search-main && python3 -m evaluator.local_evaluator
```
⚠️ **Then restore the pristine starter** — the kit must stay byte-identical to upstream so local scores are
verifiable:
```bash
curl -s https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/starter/agent.py \
  -o techjam-conversational-search-main/starter/agent.py
```

`embed_catalog.py` needs `experiments/pool_asins.json` (the ASIN list to embed); regenerate it by taking the
union of products whose `coarse_category` matches any public-set target's.
