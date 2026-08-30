"""Spec 3.3 — one clean ontology over the catalog's filthy `details` strings.

This is what makes matching survive rewording: the exact-phrase index needs the customer to
repeat a catalog string verbatim, this only needs them to mean the same thing.
Deterministic and offline — no model, no network.
"""
from __future__ import annotations

import re

from src.simulator import COLOR_RE, MATERIAL_RE, classify_constraint

# details keys are wildly inconsistent ("Sleeve type", "Outer Material", "Item Weight"),
# so map on keywords in the key rather than on the key itself.
KEY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("material", ("material", "fabric", "composition")),
    ("color", ("color", "colour", "shade")),
    ("size", ("size", "width", "length", "measurement", "fit type", "dimensions")),
    ("brand", ("brand", "manufacturer", "store", "label")),
    ("budget", ("price", "budget", "cost")),
    ("style", ("style", "department", "sleeve", "neck", "closure", "pattern", "shape", "cut", "fit")),
    ("use_case", ("occasion", "season", "activity", "sport", "use", "care", "wash")),
)
_SPLIT = re.compile(r"\s*[:=]\s*")
_JUNK = re.compile(r"[^a-z0-9%$. /&-]+")
_PRICE = re.compile(r"\$\s*([\d.]+)")
# lead-in phrases a paraphrase uses where the catalog would have written "Material: alloy".
# Only the cues that actually recover an attribute a customer might restate — not a grammar.
CUES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bmade (?:of|from|with|out of) ([\w -]{2,30})", re.I), "material"),
    (re.compile(r"\b([\w -]{2,25}?) (?:material|fabric)\b", re.I), "material"),
    (re.compile(r"\bsize ([\w.]{1,12})\b", re.I), "size"),
    (re.compile(r"\b(?:for|good for|great for) ([\w -]{3,25}?)(?: use| wear)?\b", re.I), "use_case"),
)
MAX_VALUE_CHARS = 60  # longer than this is marketing prose, not an attribute value


def _clean(text: str) -> str:
    text = _JUNK.sub(" ", text.lower())
    return re.sub(r"\s+", " ", text).strip(" .-/")


def _attribute_for_key(key: str) -> str | None:
    lowered = key.lower()
    for attribute, hints in KEY_HINTS:
        if any(hint in lowered for hint in hints):
            return attribute
    return None


def normalise(text: str) -> list[tuple[str, str]]:
    """Return every (attribute, value) pair a constraint string implies. Never raises."""
    pairs: list[tuple[str, str]] = []
    text = (text or "").strip()
    if not text:
        return pairs

    key, _, rest = text.partition(":") if ":" in text else ("", "", "")
    if rest.strip() and len(key) <= 40:
        attribute = _attribute_for_key(key)
        value = _clean(rest)
        if attribute and value:
            pairs.append((attribute, value[:MAX_VALUE_CHARS]))

    # free-text signals, which is how a paraphrase still lands on the right pair
    material = MATERIAL_RE.search(text)
    if material:
        pairs.append(("material", material.group(1).lower()))
    color = COLOR_RE.search(text)
    if color:
        pairs.append(("color", color.group(1).lower()))
    price = _PRICE.search(text)
    if price:
        pairs.append(("budget", price.group(1)))
    for pattern, attribute in CUES:
        cue = pattern.search(text)
        if cue:
            value = _clean(cue.group(1))
            if value:
                pairs.append((attribute, value[:MAX_VALUE_CHARS]))

    if not pairs:
        value = _clean(text)
        if value:
            pairs.append((classify_constraint(text), value[:MAX_VALUE_CHARS]))
    return list(dict.fromkeys(pairs))


STOPWORDS = frozenset(
    """a an and are as at be but by for from i in is it me my of on or please some that the this to want
    with would you looking need am so very just really about all our your their his her its will can more
    most other than then there these those they we us if not no yes have has had do does did""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> frozenset[str]:
    """Content tokens, for the low-precision fallback matcher (spec 3.6)."""
    return frozenset(
        token for token in _TOKEN.findall(text.lower())
        if len(token) > 2 and token not in STOPWORDS
    )
