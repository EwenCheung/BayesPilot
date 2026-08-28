"""Paraphrase stress harness — the referee for the private-set risk.

Two levels, both deterministic and seeded so the number never drifts between runs (decision D5):

  scaffold — rewrite the CARRIER sentences, leave constraint strings verbatim.
             Answers: "does the agent depend on the template wording?"
  full     — scaffold, plus rewriting INSIDE the constraint strings: synonyms, token reordering,
             punctuation and casing. Answers: "does the agent depend on exact catalog strings?"

`full` is deliberately harsher than anything the organizer is likely to ship. It is a lower bound on
robustness, not a prediction. A team that only reports `clean` has measured nothing about the private set.
"""
from __future__ import annotations

import random
import re

from .harness import Rewriter

SCAFFOLDS_BROWSING = [
    "Hey — I'm after {cat}, though I haven't made up my mind yet.",
    "So I need something in {cat}. Still figuring out what exactly.",
    "Shopping for {cat} today, just having a look around.",
    "Can you show me {cat}? I'm open to suggestions.",
]
SCAFFOLDS_BUYING = [
    "Hey — I'm after {cat}. One thing that matters: {c}",
    "Shopping for {cat} today. It really needs to be {c}",
    "I need {cat}, and {c} is non-negotiable.",
    "Looking at {cat}. Must-have: {c}",
]
SCAFFOLDS_SOFT = [
    "Hey — I'm after {cat}. {c}",
    "Shopping for {cat} today. {c}",
    "I need {cat}. {c}",
]
SCAFFOLDS_REPLY = [
    "Sure — {c}",
    "What counts for me: {c}",
    "Well, {c} is what I care about.",
    "I'd say {c}",
]
SCAFFOLDS_OVERRIDE = [
    "Actually, forget what I said before — what I need is {c}",
    "Hold on, scratch that. {c} is what I'm after instead.",
    "Change of plan: ignore my earlier preference, I want {c}",
]
SCAFFOLDS_NOPREF = [
    "No strong feelings on {attr}, your call.",
    "I don't really mind about {attr} — you pick.",
    "{attr}? No preference, use your judgment.",
]

# Substitutions applied INSIDE constraint strings at the `full` level. Every one preserves meaning while
# destroying an exact string match.
SYNONYMS = [
    (r"\b100% (\w+)", r"pure \1"), (r"\bMaterial\s*:\s*", "made of "),
    (r"\bDepartment\s*:\s*", "for "), (r"\bcolor\s*:\s*", "in "),
    (r"\bclosure\b", "fastening"), (r"\bLightweight\b", "light"),
    (r"\bComfortable\b", "comfy"), (r"\bImported\b", "shipped in"),
    (r"\bwomens\b", "women's"), (r"\bmens\b", "men's"),
    (r"\bSleeve\s*:\s*", "sleeves are "), (r"\bFit\s*Type\s*:\s*", "fit is "),
    (r"\bpolyester\b", "poly"), (r"\bcotton\b", "cotton fabric"),
    (r"\bgray\b", "grey"), (r"\bMade in USA\b", "US-made"),
]

CATEGORY_RE = re.compile(r"looking for (.+?)(?:,? but I'm still exploring\.?|\.|$)", re.I)
KEYREQ_RE = re.compile(r"A key requirement is:\s*(.*?)\.?$", re.I)
REPLY_RE = re.compile(r"^For that, what matters is:\s*(.*?)\.?$", re.I)
OVERRIDE_RE = re.compile(r"What I need is:\s*(.*?)\.?$", re.I)
NOPREF_RE = re.compile(r"preference for (\w+)", re.I)


def _mangle(text: str, rng: random.Random) -> str:
    """Rewrite inside a constraint string. Meaning survives; the exact bytes do not."""
    out = text
    for pattern, repl in SYNONYMS:
        out = re.sub(pattern, repl, out, flags=re.I)
    if ":" in out and rng.random() < 0.7:
        head, _, tail = out.partition(":")
        out = f"{tail.strip()} {head.strip().lower()}".strip()
    if rng.random() < 0.35:
        words = out.split()
        if len(words) > 3:
            cut = rng.randrange(1, len(words) - 1)
            out = " ".join(words[cut:] + words[:cut])
    if rng.random() < 0.4:
        out = out.lower()
    return re.sub(r"\s+", " ", out).strip()


class ParaphraseRewriter(Rewriter):
    """Deterministic per (session-position, turn) so repeated runs give an identical score."""

    def __init__(self, level: str = "scaffold", seed: int = 7) -> None:
        assert level in ("scaffold", "full"), level
        self.name = level
        self.level = level
        self.seed = seed
        self._n = 0

    def __call__(self, message: str, turn: int) -> str:
        if turn == 1:
            self._n += 1
        rng = random.Random(f"{self.seed}:{self._n}:{turn}")
        mangle = (lambda s: _mangle(s, rng)) if self.level == "full" else (lambda s: s)

        nopref = NOPREF_RE.search(message)
        if nopref and "don't have" in message.lower():
            return rng.choice(SCAFFOLDS_NOPREF).format(attr=nopref.group(1))

        override = OVERRIDE_RE.search(message)
        if override and "ignore my earlier" in message.lower():
            return rng.choice(SCAFFOLDS_OVERRIDE).format(c=mangle(override.group(1)))

        reply = REPLY_RE.match(message.strip())
        if reply:
            parts = [mangle(p.strip()) for p in reply.group(1).split(";")]
            return rng.choice(SCAFFOLDS_REPLY).format(c="; ".join(parts))

        cat = CATEGORY_RE.search(message)
        if cat:
            category = cat.group(1).strip()
            key = KEYREQ_RE.search(message)
            if key:
                return rng.choice(SCAFFOLDS_BUYING).format(cat=category, c=mangle(key.group(1)))
            if "still exploring" in message.lower():
                return rng.choice(SCAFFOLDS_BROWSING).format(cat=category)
            trailing = message.split(".", 1)[1].strip() if "." in message else ""
            if trailing:
                return rng.choice(SCAFFOLDS_SOFT).format(cat=category, c=mangle(trailing))
            return rng.choice(SCAFFOLDS_BROWSING).format(cat=category)

        if "one specific attribute" in message.lower():
            return "Those aren't right yet — ask me about something specific."
        return message
