"""Spec 3.5 — the single LLM client: chat, extraction, listwise rerank, embeddings.

Three rules the whole file exists to enforce:
  * every call asserts on a parsed non-empty result and counts failures (C7, IMPORTANT.md §13.1.3)
  * every call has an offline fallback the caller can act on — `None`/`[]`, never an exception (C8)
  * model IDs are pinned, never aliases (C9, IMPORTANT.md §13.1.4)
Responses are cached by content hash, so a repeat run is free and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

# Set to "1" to force EVERY road offline, disk cache included. The harness sets it for all reported
# runs. It lives here rather than in an agent because gating it per-agent let R1 and R2 keep reading a
# warm .cache/llm while R3 was offline (D24).
OFFLINE_ENV = "COPILOT_OFFLINE"

# absolute: runs execute with cwd=<kit>, and a cache written in there would both contaminate the
# kit we promise to keep pristine and be invisible to the next run
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "llm"

CHAT_MODEL = "qwen3.6:35b"     # 0.86 s/call, +0.191 rerank MRR (IMPORTANT.md §12.3)
EMBED_MODEL = "bge-m3"         # 1024-d, ~$0.10 for the catalog
PRICE_PER_MTOK = 0.0           # free on this endpoint; disclosure requires we say so explicitly

INTENT_SYSTEM = """Route and interpret one shopping message. Return JSON only:
{"route":"deterministic|hybrid","normalized_text":"lossless clear rewrite",
"kind":"buying|browsing|override_open|reply|override|no_preference|null_ask|unknown",
"category":"exact category phrase from the message or null","attribute":"requested field or null",
"operations":[{"op":"add|remove|replace|confirm|no_preference",
"attribute":"material|color|size|style|brand|budget|feature|use_case",
"value":"short literal or normalized value","polarity":"require|avoid",
"strength":"hard|soft","evidence":"exact supporting phrase","confidence":0.0,
"group":"shared ambiguity id or null"}]}

Rules:
1. Always choose one route. Choose deterministic only when the message already follows one of the fixed
   simulator templates exactly and needs no spelling, slang, abbreviation, negation, or context repair.
   Choose hybrid for every paraphrase, free-form sentence, typo, slang term, abbreviation, correction,
   implicit reference, or uncertain meaning.
2. normalized_text must preserve every category, constraint, negation, correction, uncertainty and number.
   Fix spelling/slang and make the meaning explicit, but never add information. For deterministic route,
   copy the original message exactly.
3. Classify the message by meaning, not its wording. Use unknown when no fixed-template meaning fits.
4. Read the entire current state and message together. Resolve pronouns and corrections against prior turns.
5. Understand common misspellings, slang and abbreviations (tee/t-shirt, kicks/shoes, cotten/cotton,
   polyster/polyester, XL/extra large), but never pretend an ambiguous abbreviation is certain.
6. Category must be copied from an exact phrase present in this message; never infer a longer taxonomy leaf.
   Category means the product type, never the requirement text. In "I want tees. Requirement: poly",
   category is "tees", while "poly" is an ambiguous constraint.
7. For an ambiguous span, emit 2-4 plausible operations with the same non-null group id and calibrated
   confidences. Example: "poly" may mean polyester material, polyurethane, polycarbonate, or another
   polymer feature depending on context. Do not choose one merely because it is common.
8. Preserve negation. "not dressy" is add style=dressy polarity=avoid.
9. Explicit cancellation such as "forget blue" is remove color=blue.
10. A correction such as "actually size XL, not L" replaces the previous size.
11. Extract every explicit usable fact. "My dad wears XL" includes size=XL even if recipient is vague.
12. Do not invent specificity: "from abroad" does not mean Europe.
13. Evidence must be an exact phrase present in the original message. Use no operation when unsupported.
14. If the current state already captures the message correctly, return confirm for that value rather
   than adding or replacing it again.
"""
CANONICAL_SYSTEM = """Resolve a shopper phrase to one real catalog label. Return JSON only:
{"choice":<1-based number or null>,"generated_query":"short query or null"}

Choose a number only when the label is fully entailed by the phrase. Never add unsupported details
(for example, "abroad" does not entail "Europe"). If no label fits, provide a short meaning-preserving
query for a second retrieval pass. If even that would invent meaning, use null for both fields.
Typos may be corrected when the intended word is clear from context. Short ambiguous fragments such
as "poly" must abstain unless the surrounding message and state distinguish the meaning.
"""
RERANK_SYSTEM = (
    "You rank products against a shopper's requirements. Reply with a JSON array of the candidate "
    "numbers, best first, every number used exactly once. No prose."
)

# Domain importance is a tie-breaker. Candidate answer probability and information gain are stronger
# signals: size matters enormously for shoes but often not at all for jewellery.

EXTRACT_SYSTEM = (
    "You extract shopping constraints. Reply with JSON only: "
    '{"constraints":[{"attribute":"material|color|size|style|brand|budget|feature|use_case",'
    '"value":"<short value>"}]}. No prose.'
)
RERANK_SYSTEM = (
    "You rank products against a shopper's requirements. Reply with a JSON array of the candidate "
    "numbers, best first, every number used exactly once. No prose."
)


def _http(path: str, body: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        os.environ["SOCLAAS_BASE_URL"].rstrip("/") + path,
        json.dumps(body).encode(),
        {"Authorization": "Bearer " + os.environ["SOCLAAS_API_KEY"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class LLMClient:
    def __init__(
        self,
        chat_model: str = CHAT_MODEL,
        embed_model: str = EMBED_MODEL,
        cache_dir: str | Path | None = None,
        offline: bool | None = None,
        transport=_http,
        retries: int = 3,
    ) -> None:
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = os.environ.get("R1_OFFLINE") == "1" if offline is None else offline
        self.transport = transport
        self.retries = retries
        # R1_LLM_NOCACHE=1 forces real calls, so the disclosed latency and token figures are
        # measured rather than replayed
        self.nocache = os.environ.get("R1_LLM_NOCACHE") == "1"
        self.failures = 0
        self.calls = 0
        self.cache_hits = 0
        self.from_cache = False
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latencies: list[float] = []

    # --- plumbing ----------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _post(self, path: str, body: dict, timeout: float):
        key = hashlib.sha256((path + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:32]
        cached = self._cache_path(key)
        if cached.exists() and not self.nocache:
            self.cache_hits += 1
            self.from_cache = True
            return json.loads(cached.read_text())
        self.from_cache = False
        if self.offline:
            return None
        for attempt in range(self.retries):
            started = time.time()
            try:
                payload = self.transport(path, body, timeout)
                self.latencies.append(time.time() - started)
                self.calls += 1
                cached.write_text(json.dumps(payload))
                return payload
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503) and attempt + 1 < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                self.failures += 1
                return None
            except Exception:
                self.failures += 1
                return None
        self.failures += 1
        return None

    # --- primitives --------------------------------------------------------
    def chat(self, messages: list[dict], max_tokens: int = 400, temperature: float = 0.0) -> str | None:
        payload = self._post(
            "/chat/completions",
            {"model": self.chat_model, "messages": messages,
             "max_tokens": max_tokens, "temperature": temperature},
            timeout=60,
        )
        if not payload:
            return None
        try:
            choice = payload["choices"][0]
            content = choice["message"].get("content")
            usage = payload.get("usage") or {}
            if not self.from_cache:  # disclosure counts tokens actually spent, not replays
                self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.completion_tokens += int(usage.get("completion_tokens") or 0)
        except Exception:
            self.failures += 1
            return None
        if not content or not content.strip():
            # a model that answers with nothing looks exactly like a model that does not help
            self.failures += 1
            return None
        return content.strip()

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        payload = self._post("/embeddings", {"model": self.embed_model, "input": texts}, timeout=180)
        if not payload:
            return None
        try:
            vectors = [row["embedding"] for row in payload["data"]]
        except Exception:
            self.failures += 1
            return None
        if len(vectors) != len(texts):
            self.failures += 1
            return None
        return vectors

    # --- tasks -------------------------------------------------------------
    def restore_template(self, message: str, state: dict) -> dict:
        """Return an untrusted fixed-template classification plus typed operation proposals."""
        if self.offline or os.environ.get(OFFLINE_ENV) == "1":
            return {}
        user = f"Current state: {json.dumps(state, sort_keys=True)[:2500]}\nMessage: {message[:1500]}"
        content = self.chat(
            [{"role": "system", "content": INTENT_SYSTEM}, {"role": "user", "content": user}],
            max_tokens=700,
        )
        if not content:
            return {}
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            self.failures += 1
            return {}
        try:
            payload = json.loads(match.group(0))
        except Exception:
            self.failures += 1
            return {}
        if not isinstance(payload, dict):
            self.failures += 1
            return {}
        rows = payload.get("operations") or []
        payload["operations"] = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        route = str(payload.get("route") or "").strip().lower()
        payload["route"] = route if route in {"deterministic", "hybrid"} else ""
        payload["normalized_text"] = str(payload.get("normalized_text") or "").strip()[:1500]
        return payload

    def interpret_operations(self, message: str, state: dict) -> list[dict]:
        """Backward-compatible operation-only view over template restoration."""
        return list(self.restore_template(message, state).get("operations") or [])

    def extract(self, message: str) -> list[tuple[str, str, str]]:
        """Paraphrase insurance: read constraints out of prose no template will match."""
        # ⚠️ OFFLINE_ENV is checked HERE, not in an agent, so it holds for every road. Gating it
        # per-agent let R1 and R2 keep reading a warm `.cache/llm` while R3 was offline, which
        # silently lifted R1's L3 from 0.7241 to 0.7893 in a table headed "no network" (D22, D24).
        if os.environ.get(OFFLINE_ENV) == "1":
            return []
        # ⚠️ OFFLINE_ENV is checked HERE, not in an agent, so it holds for every road. Gating it
        # per-agent let R1 and R2 keep reading a warm `.cache/llm` while R3 was offline, which
        # silently lifted R1's L3 from 0.7241 to 0.7893 in a table headed "no network" (D22, D24).
        if os.environ.get(OFFLINE_ENV) == "1":
            return None
        content = self.chat(
            [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": message[:1500]}],
            max_tokens=300,
        )
        if not content:
            return []
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            self.failures += 1
            return []
        try:
            rows = json.loads(match.group(0)).get("constraints") or []
            pairs = [
                (str(row["attribute"]).strip().lower(), str(row["value"]).strip().lower(), message)
                for row in rows
                if row.get("attribute") and row.get("value")
            ]
        except Exception:
            self.failures += 1
            return []
        if not pairs:
            self.failures += 1
        return pairs

    def rerank(self, query: str, candidates: list[str], labels: list[str] | None = None) -> list[str] | None:
        """The brief's named 'LLM Semantic Ranking' stage. Returns None on any malformed answer."""
        # ⚠️ OFFLINE_ENV is checked HERE, not in an agent, so it holds for every road. Gating it
        # per-agent let R1 and R2 keep reading a warm `.cache/llm` while R3 was offline, which
        # silently lifted R1's L3 from 0.7241 to 0.7893 in a table headed "no network" (D22, D24).
        if os.environ.get(OFFLINE_ENV) == "1":
            return None
        shown = labels or candidates
        listing = "\n".join(f"{i + 1}. {text[:220]}" for i, text in enumerate(shown))
        content = self.chat(
            [{"role": "system", "content": RERANK_SYSTEM},
             {"role": "user", "content": f"Requirements: {query[:1200]}\n\nCandidates:\n{listing}"}],
            max_tokens=300,
        )
        if not content:
            return None
        match = re.search(r"\[[\d,\s]+\]", content)
        if not match:
            self.failures += 1
            return None
        try:
            order = json.loads(match.group(0))
        except Exception:
            self.failures += 1
            return None
        seen, ranked = set(), []
        for position in order:
            index = int(position) - 1
            if 0 <= index < len(candidates) and index not in seen:
                seen.add(index)
                ranked.append(candidates[index])
        if len(ranked) != len(candidates):
            self.failures += 1
            return None
        return ranked

    # --- disclosure --------------------------------------------------------
    def report(self) -> dict:
        latencies = sorted(self.latencies)
        percentile = lambda p: latencies[min(len(latencies) - 1, int(p * len(latencies)))] if latencies else 0.0
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "failures": self.failures,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "usd": round((self.prompt_tokens + self.completion_tokens) / 1e6 * PRICE_PER_MTOK, 4),
            "latency_p50_ms": round(percentile(0.50) * 1000, 1),
            "latency_p95_ms": round(percentile(0.95) * 1000, 1),
        }
