# Decision log

Appended as we learn. Reversals are expected and are recorded, not edited away.

---

### D1 — The harness imports the evaluator; the agent never does
**Decision.** `src/eval/harness.py` does `from evaluator.local_evaluator import evaluate` and calls it with
our agent instance directly. The kit's `starter/agent.py` is never written to.

**Why.** The circular-import trap ([IMPORTANT.md §13.1.1](../../IMPORTANT.md)) only bites when the *agent
module* imports the evaluator, because the evaluator imports `starter.agent` at module scope. A harness
script sits outside that cycle. This buys three things the copy-over-the-starter workflow cannot: the kit
stays provably pristine, ablation flags can be passed to the constructor, and variants run in one process
without 17s of index rebuild each.

---

### D2 — Offline dense backend first, `bge-m3` second
**Decision.** The dense route is an interface with two backends: TF-IDF + TruncatedSVD built from the
catalog at startup (offline, no download, no spend), and `bge-m3` via API (higher quality). SVD was built
first.

**Why.** The reranker is escalation-only and can be skipped if the network is gone. The dense route cannot —
it has to embed the *live query* every turn. An API-only dense route means R2 has no semantic route at all
under the network restriction the submission rules reserve. Building the offline one first also unblocked
development without waiting on a 13-minute embedding run, and hands us the ablation for free.

---

### D3 — Embed all 50,000 products, not the 22,458-product pool
**Decision.** `scripts/embed_all.py` embeds the entire catalog.

**Why.** `experiments/embed_catalog.py` embedded only products whose `coarse_category` matched a
**public-set target's**. That pool is a function of the public labels. A private-set target in an
unrepresented category would have no vector, so any score measured on it overstates what transfers.
Cost of doing it properly: ~13 min, ~$0.10, 98 MB at fp16.

---

### D4 — Spec-phrase is a *score*, not a filter
**Decision.** The inversion signal enters R2 as one weighted route contributing a continuous score, with
token-level partial credit, not as a set intersection.

**Why.** This is the whole difference between R1 and R2. R1's `frozenset & frozenset` returns zero the
moment a constraint string is reworded by one character — the failure is a cliff. Scoring partial overlap
makes paraphrase a gradient. It also means the `no_spec_phrase` ablation is a clean switch: set the route
weight to zero and everything else still ranks.

---

### D5 — The paraphrase stress harness is rule-based and deterministic, not LLM-driven
**Decision.** Two levels, seeded, no model calls. `scaffold` rewrites the template carrier sentences while
leaving constraint strings verbatim. `full` additionally rewrites *inside* the constraint strings —
synonym substitution, token reordering, punctuation and casing changes.

**Why.** The stress harness is the referee, and a referee has to be reproducible and free to run on every
commit. An LLM rewriter would make the number drift between runs and cost minutes per evaluation. It wraps
the **agent**, never the evaluator, so the kit stays untouched and hits remain exact-code matches.

`full` is deliberately harsher than anything the organizer is likely to do — it is a lower bound, not a
prediction.
