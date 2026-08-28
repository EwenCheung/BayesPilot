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

---

### D6 — The lexical index must not iterate a set and truncate ⚠️ bug found by a test
**Symptom.** The same configuration scored 0.9578 in one process and 0.9566 in the next.

**Cause.** `LexicalRoute` built each document's token set and kept `list(tokens)[:64]`. Python salts
string hashing per interpreter, so set iteration order — and therefore *which* 64 tokens survived —
differed on every run.

**Fix.** Keep the `cap` rarest tokens by IDF: deterministic, and it drops the high-frequency tokens that
carry least discrimination anyway. `tests/test_routes.py` now runs the index build in two subprocesses
and asserts the output is identical.

**Why it matters beyond the bug.** A harness that reports a different number for the same code cannot
referee a race. This was found because a reference number failed to reproduce, which is the whole reason
R2-A0 pins the harness to two known values before trusting it.

---

### D7 — An "exactness step" for full constraint coverage: proposed, measured, REJECTED
**Hypothesis.** Satisfying every stated constraint exactly is qualitatively different from satisfying
most, and a purely additive score cannot express that. Adding a bonus when a candidate matched all
constraints exactly should fix the one session R2 missed.

**Result.** It lost in 8 of 8 configurations (0.9616 → 0.9589 at the then-current schedule) and did not
fix the missed session. Reverted; the code is gone, the finding stays here.

**What was actually wrong.** The missed session's target matched all four constraints exactly *and* was
rank 1 by popularity among the 20 products that did — so it was never a coverage problem. Twenty
candidates tied on spec, and the tie was being broken by the dense route, which is close to
uninformative between products that satisfy identical specs. See D8.

---

### D8 — 🔑 Popularity must stay STRONG even with a full constraint card
**The initial schedule was wrong in a way worth naming.** It decayed popularity from 1.00 to 0.32 as
slots accumulated, on the intuitive theory that hard evidence should take over from a prior. Measured
across 23 configurations, raising it back to 2.5 moved the score from **0.9616 to 0.9707**.

**Why.** Once every stated constraint is matched, dozens of catalog products tie exactly — the
constraints are low-entropy strings like `"Imported"` or `"100% Polyester"` that hundreds of products
share. At that point popularity is not a tiebreak of convenience, it is the only route still carrying
information about which of the tied candidates is the answer, because the targets are drawn from a
5-core split and are ~570x more reviewed than the catalog median (IMPORTANT.md §5).

The generalisable form: **a prior is most valuable exactly where the evidence stops discriminating**,
which is the opposite of the schedule intuition says to build.

The optimum is a broad plateau (0.969–0.971 across a 4x range of both weights), not a peak — evidence
that this is not a knife-edge fit to 200 sessions.
