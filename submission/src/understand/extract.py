"""LLM extraction aimed at the deterministic pathway, not at fluent English.

The shared `EXTRACT_SYSTEM` in `src/common/llm.py` asks for `{"attribute", "value"}` with a "short
value", which optimises for a tidy summary. That is the wrong target here, and the reason is
mechanical:

* the exact term is `constraint.text in index.card[asin]` — a tuple membership test, so **equality**;
* the soft-card term is token-Jaccard against the item's own card strings;
* `src.understand.attributes.normalise()` and the simulator's own `classify_constraint()` both key off a
  **small fixed keyword vocabulary**.

So a value is useful in proportion to how many of the *original tokens* it preserves, not how well it
reads. "made from genuine leather" and "leather" are equally fluent; only the second is a card string.

⚠️ **This prompt lives in `src/r4/` on purpose.** `EXTRACT_SYSTEM` is shared by R1, R2 and R3, and
changing it would silently move their published numbers. R4 brings its own and leaves theirs alone.

The vocabularies below are copied from `evaluator/local_evaluator.py` — copied, never imported, because
the evaluator does `from starter.agent import Agent` at module scope and importing it from agent code
is a circular import and a hard crash (IMPORTANT.md §13.1.1).
"""
from __future__ import annotations

import json
import re

# --- copied verbatim from evaluator/local_evaluator.py (do not import — circular) ----------------
ALLOWED_ATTRIBUTES = ("category", "material", "color", "size", "style", "brand",
                      "budget", "feature", "use_case", "other")
MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
COLORS = ("black", "white", "blue", "red", "pink", "green", "brown", "gray", "grey",
          "purple", "yellow", "orange")
# `classify_constraint`'s own trigger words, so an extracted value lands in the same bucket the
# simulator would have put the original in.
SIZE_CUES = ("size", "sizing", "width", "wide", "narrow")
STYLE_CUES = ("department", "style", "fit", "sleeve", "neck")
USE_CASE_CUES = ("hiking", "running", "gym", "winter", "outdoor", "work")

SYSTEM = (
    "You convert a shopper's message into catalog constraints. The catalog stores short spec strings "
    "like 'leather', 'color: black', '100% Polyester', 'Buckle closure', "
    "'Product Dimensions: 3.54 x 3.54 x 0.39 inches'.\n"
    "Your job is to recover the ORIGINAL spec wording, not to paraphrase it.\n"
    "RULES:\n"
    "1. Copy distinctive words VERBATIM from the message: materials, colors, brand names, numbers, "
    "units, percentages, measurements. Never round, convert, spell out or re-order a number.\n"
    "2. Drop conversational filler ('I want', 'it has to be', 'I'm looking for', 'really').\n"
    f"3. When the message means one of these, use that exact word: {', '.join(MATERIALS)}; "
    f"{', '.join(COLORS)}.\n"
    "4. Keep each value short — the spec phrase itself, not a sentence.\n"
    f"5. attribute must be one of: {'|'.join(ALLOWED_ATTRIBUTES)}.\n"
    'Reply with JSON only: {"constraints":[{"attribute":"material","value":"leather"}]}. No prose.'
)


def _attribute_for(value: str) -> str:
    """Mirror of `classify_constraint`, used to repair a bad attribute rather than discard the row.

    The value is what the matcher uses, so a row with a good value and a wrong attribute is still
    worth keeping — it just needs re-filing.
    """
    lowered = value.lower()
    if "budget" in lowered or re.search(r"(?:\$|<=|under)\s*\d", lowered):
        return "budget"
    if any(m in lowered for m in MATERIALS):
        return "material"
    if any(w in lowered for w in ("color",) + COLORS):
        return "color"
    if any(w in lowered for w in SIZE_CUES):
        return "size"
    if any(w in lowered for w in STYLE_CUES):
        return "style"
    if any(w in lowered for w in USE_CASE_CUES):
        return "use_case"
    return "feature"


class AlignedExtractor:
    """Wraps an `LLMClient` and exposes the `.extract()` shape `src.understand.parse` expects.

    Every call asserts on a parsed non-empty result and counts failures: a model that returns
    `content: None` while burning the full token budget looks exactly like a model that is not
    helping, and that wrong conclusion has already been reached once here (IMPORTANT.md §13.1.3).
    """

    def __init__(self, client, max_values: int = 4) -> None:
        self.client = client
        self.max_values = max_values
        self.failures = 0
        self.calls = 0

    def __getattr__(self, item):
        """Delegate anything we do not override — `restore_template`, `totals`, the counters.

        `IntentPipeline.decide()` selects its path with `hasattr(llm, "restore_template")`, so a
        wrapper that swallowed it would silently downgrade the router to the older extract-only
        prompt and look exactly like a router that had nothing to say.
        """
        return getattr(self.client, item)

    def extract(self, message: str) -> list[tuple[str, str, str]]:
        if not message or not message.strip():
            return []
        self.calls += 1
        content = self.client.chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": message[:1500]}],
            max_tokens=300,
        )
        if not content:
            self.failures += 1
            return []
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            self.failures += 1
            return []
        try:
            rows = json.loads(match.group(0)).get("constraints") or []
        except Exception:
            self.failures += 1
            return []

        out: list[tuple[str, str, str]] = []
        for row in rows[: self.max_values]:
            value = str(row.get("value") or "").strip()
            if not value:
                continue
            attribute = str(row.get("attribute") or "").strip().lower()
            if attribute not in ALLOWED_ATTRIBUTES:
                attribute = _attribute_for(value)
            out.append((attribute, value, message))
        if not out:
            self.failures += 1
        return out

    def totals(self) -> tuple[int, int]:
        return getattr(self.client, "totals", lambda: (0, 0))()
