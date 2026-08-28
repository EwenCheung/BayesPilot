"""LLM semantic ranking — the stage PROBLEM.md Pillar I names in the required pipeline.

⚠️ Two things are true at once and the write-up must say both. The brief specifies
"Multi-Route Retrieval -> LLM Semantic Ranking", so this stage is built. And on the clean public set the
blend already puts the target at rank 1 in the overwhelming majority of sessions, so there is very little
left for a reranker to fix. Omitting it looks like a missing pillar; shipping it without the caveat is an
unmeasured claim (IMPORTANT.md §14.1). We build it, measure it, and report what it actually did.

Called as an ESCALATION, never a default: if the deterministic path already has a confident leader the
model is skipped. The binding constraint is wall-clock and network reachability, not cost — the
evaluator loop is sequential, so one call per turn across the private 800 sessions is a real elapsed-time
bill and a bet that the endpoint is up during official scoring.

⚠️ Every call asserts on a parsed non-empty result and counts failures. `ornith1.5:35b` returns
content: None while consuming the full token budget, and a silent model failure is indistinguishable
from a model that is not helping — a wrong conclusion we already reached once (IMPORTANT.md §13.1.3).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

MODEL = "qwen3.6:35b"  # pinned explicitly: `default`, `test` and `ornith1.0:35b` are all ALIASES that
                       # can be repointed under us (IMPORTANT.md §13.1.4)
RANK_RE = re.compile(r"\[(\d+)\]")


class LlmReranker:
    def __init__(self, index, model: str = MODEL, timeout: int = 60,
                 retries: int = 5, backoff: float = 1.5) -> None:
        self.index = index
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.rate_limited = 0
        self.api = os.environ.get("SOCLAAS_BASE_URL", "")
        self.key = os.environ.get("SOCLAAS_API_KEY", "")
        self.calls = 0
        self.failures = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _describe(self, asin: str) -> str:
        product = self.index.products[asin]
        features = " ".join(str(x) for x in (product.get("features") or [])[:4])
        details = " ".join(f"{k}:{v}" for k, v in list((product.get("details") or {}).items())[:5])
        return f"{product.get('title') or ''} || {features} || {details}"[:420]

    def rerank(self, query, ranked: list[str], depth: int = 20) -> list[str]:
        """Permute the head of the list. On any failure the original order is returned unchanged."""
        head = ranked[:depth]
        if len(head) < 2 or not self.api or not self.key:
            return ranked
        items = "\n".join(f"[{i + 1}] {self._describe(a)}" for i, a in enumerate(head))
        wants = "; ".join(v for v, _ in query.constraints) or "no specific requirements yet"
        prompt = (
            f"A shopper wants: {query.resolved_category or query.category}. "
            f"Their stated requirements: {wants}\n\n"
            f"Rank these {len(head)} products best to worst.\n{items}\n\n"
            "Reply ONLY the ranking like [3] > [1] > [7]. No explanation."
        )
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400, "temperature": 0,
        }).encode()
        # Retry only on rate limiting. A shared endpoint returns 429 in bursts, and without backoff
        # the failure count measures contention rather than the reranker.
        order = None
        for attempt in range(self.retries):
            try:
                request = urllib.request.Request(
                    self.api + "/chat/completions", body,
                    {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
                )
                data = json.load(urllib.request.urlopen(request, timeout=self.timeout))
                choice = data["choices"][0]
                content = choice["message"].get("content")
                assert content, f"empty content (finish_reason={choice.get('finish_reason')})"
                order = [int(x) for x in RANK_RE.findall(content)]
                assert order, "no ranking parsed from a non-empty response"

                usage = data.get("usage") or {}
                self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.completion_tokens += int(usage.get("completion_tokens") or 0)
                self.calls += 1
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < self.retries - 1:
                    self.rate_limited += 1
                    time.sleep(self.backoff * (2 ** attempt))
                    continue
                self.failures += 1
                return ranked
            except Exception:
                self.failures += 1
                return ranked
        if order is None:
            self.failures += 1
            return ranked

        seen: set[int] = set()
        out: list[str] = []
        for i in order:
            if 1 <= i <= len(head) and i not in seen:
                seen.add(i)
                out.append(head[i - 1])
        out += [a for a in head if a not in out]
        return out + ranked[depth:]
