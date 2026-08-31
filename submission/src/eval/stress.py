"""Spec 3.10 — the paraphrase stress harness.

⚠️ It wraps the **agent**, never the evaluator: the kit stays byte-identical, and the agent simply
never sees the simulator's literal templates. That is the whole question the private set asks
: what is left when the customer says the same thing in different words?

Levels
  0  clean          — the simulator's own text
  1  scaffold       — templates reworded, constraint payloads verbatim   (tests the parser)
  2  full           — scaffold + payloads reworded                       (tests the matcher)
  3  category       — full + the CATEGORY NAME reworded                  (tests pool resolution)
  4  llm            — a model rewrites the whole utterance, cached       (tests everything, realistically)

⚠️ L3 exists because L1 and L2 have a hole: their scaffolds interpolate `{category}` verbatim, so
`best_category` — which checks for a quoted category name first — resolved 100% of openers correctly at
every level. `scripts/category_probe.py` measured exactly that, which made paraphrase look like a pure
ranking problem. It is not: R1 measured 85% category accuracy under model-written paraphrase. L3 closes
the hole without needing the network, so the number is reproducible and free.

⚠️ **This is the ONE rewriter, for all three roads.** R1 and R2 each shipped their own, which is why
R1's L2 = 0.8594 and R2's "heavy" = 0.7961 said nothing about which agent is more robust: different
programs, different aggression (R1 defect 2, R2 defect A8). `ParaphraseRewriter` below is R2's
interface over this ladder, not a second implementation.
"""
from __future__ import annotations

import hashlib
import random
import re

SCAFFOLDS: dict[str, tuple[str, ...]] = {
    "buying": (
        "Hi — after {category}. Must have: {payload}",
        "need {category}. the important bit is {payload}",
        "shopping for {category} and it really has to be {payload}",
    ),
    "browsing": (
        "just browsing {category} at the moment, nothing fixed yet",
        "having a look around {category}, still open on specifics",
        "not sure yet, somewhere in {category}",
    ),
    "override_open": (
        "after some {category}. {payload}",
        "looking at {category} — {payload}",
    ),
    "reply": (
        "what counts for me: {payload}",
        "mainly {payload}",
        "the things that matter are {payload}",
    ),
    "override": (
        "scratch that, forget what I said before — what I actually need is {payload}",
        "change of plan: {payload} is the real requirement",
    ),
    "no_pref": (
        "no strong feelings on {attribute} honestly",
        "{attribute} is up to you",
    ),
    "null_ask": ("those aren't right — ask me something specific",),
}

# Category rewording for L3. A shopper says "t-shirts"; the catalog says "Shirts T-Shirts".
# Every rule keeps at least one content word, so the category stays recognisable — a rewrite that
# destroys it is not paraphrase, it is a customer who changed their mind (tested).
CATEGORY_RULES = (
    (r"\bT-Shirts\b", "tees"), (r"\bShirts\b", "shirts"), (r"\bSweaters\b", "knitwear"),
    (r"\bActivewear\b", "workout wear"), (r"\bSwimwear\b", "swim stuff"),
    (r"\bAccessories\b", "accessories bits"), (r"\bNovelty\b", "novelty"),
    (r"\bClothing\b", "clothes"), (r"\bJewelry\b", "jewellery"),
    (r"\bWomen'?s?\b", "womens"), (r"\bMen'?s?\b", "mens"),
    (r"\bGirls'?\b", "girls"), (r"\bBoys'?\b", "boys"),
)


def _reword_category(category: str, rng: random.Random) -> str:
    """Reword a category name, keeping it recognisable. Drops a leading qualifier ~40% of the time,
    which is the realistic failure: a shopper rarely says the full taxonomy path."""
    out = category
    for pattern, replacement in CATEGORY_RULES:
        out = re.sub(pattern, replacement, out, flags=re.I)
    words = out.split()
    if len(words) > 2 and rng.random() < 0.4:
        words = words[1:] if rng.random() < 0.5 else words[:-1]
    if rng.random() < 0.5:
        out = " ".join(words).lower()
    else:
        out = " ".join(words)
    return out if out.strip() else category


SYNONYMS = (
    (r"\bcolor\b", "colour"), (r"\bmaterial\b", "made of"), (r"\bfit type\b", "fit"),
    (r"\bdepartment\b", "for"), (r"\bsleeve type\b", "sleeves"), (r"\bclosure type\b", "closure"),
    (r"\b100%\s*", "pure "), (r"\bimported\b", "imported goods"),
)

OPENER = re.compile(r"^I'm looking for (?P<category>.+?)(?P<tail>, but I'm still exploring\.|\. .*)?$", re.S)
KEY_REQ = re.compile(r"^\. A key requirement is: (?P<payload>.+?)\.?$", re.S)
REPLY = re.compile(r"^For that, what matters is: (?P<payload>.+?)\.?$", re.S)
OVERRIDE = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (?P<payload>.+?)\.?$", re.S)
NO_PREF = re.compile(r"^I don't have (?:an additional preference|a preference) for (?P<attribute>[a-z_]+)")
NULL_ASK = re.compile(r"^Those options are not quite right yet")


def _rng(text: str) -> random.Random:
    return random.Random(int(hashlib.sha256(text.encode()).hexdigest()[:8], 16))


def _reword_payload(payload: str, rng: random.Random) -> str:
    """`Material: alloy` → `alloy material`. Kills exact-phrase matching, which is the point."""
    parts = []
    for chunk in payload.split("; "):
        key, sep, value = chunk.partition(":")
        if sep and value.strip() and len(key) < 40:
            chunk = f"{value.strip()} {key.strip().lower()}" if rng.random() < 0.7 else value.strip()
        for pattern, replacement in SYNONYMS:
            chunk = re.sub(pattern, replacement, chunk, flags=re.I)
        parts.append(chunk)
    rng.shuffle(parts)
    return (" and " if rng.random() < 0.5 else ", ").join(parts)


def paraphrase(message: str, level: int, llm=None) -> str:
    """Rewrite one customer utterance at the requested stress level. Never raises."""
    if level <= 0 or not message:
        return message
    try:
        if level >= 4 and llm is not None:
            written = llm.chat(
                [{"role": "system", "content": "Rewrite the shopper's message casually in your own words. "
                                               "Keep every requirement, change the wording. Reply with the "
                                               "rewritten message only."},
                 {"role": "user", "content": message}],
                max_tokens=160,
            )
            if written:
                return written.strip().strip('"')
            # fall through to the deterministic rewrite when the endpoint is unavailable (C8)
        rng = _rng(message)
        payload_level = max(level, 2) if level >= 3 else level

        def payload_of(text: str) -> str:
            return _reword_payload(text, rng) if payload_level >= 2 else text

        def category_of(name: str) -> str:
            return _reword_category(name, rng) if level >= 3 else name

        opener = OPENER.match(message.strip())
        if opener:
            category = opener.group("category").strip()
            tail = (opener.group("tail") or "").strip()
            if not tail or "still exploring" in tail:
                return rng.choice(SCAFFOLDS["browsing"]).format(category=category_of(category))
            key = KEY_REQ.match(opener.group("tail"))
            if key:
                return rng.choice(SCAFFOLDS["buying"]).format(
                    category=category_of(category), payload=payload_of(key.group("payload")))
            return rng.choice(SCAFFOLDS["override_open"]).format(
                category=category_of(category), payload=payload_of(tail.lstrip(". ")))
        override = OVERRIDE.match(message.strip())
        if override:
            return rng.choice(SCAFFOLDS["override"]).format(payload=payload_of(override.group("payload")))
        reply = REPLY.match(message.strip())
        if reply:
            return rng.choice(SCAFFOLDS["reply"]).format(payload=payload_of(reply.group("payload")))
        no_pref = NO_PREF.match(message.strip())
        if no_pref:
            return rng.choice(SCAFFOLDS["no_pref"]).format(attribute=no_pref.group("attribute"))
        if NULL_ASK.match(message.strip()):
            return SCAFFOLDS["null_ask"][0]
        return message
    except Exception:
        return message


# --- R2's Rewriter interface over the same ladder --------------------------------------------------
# R2's harness passes a callable object; R1 calls a function. One rewriting program, two call shapes.
LEVELS = {"clean": 0, "scaffold": 1, "full": 2, "category": 3, "llm": 4}


class ParaphraseRewriter:
    """Deterministic per utterance: `paraphrase` seeds its RNG from the message text itself.

    ⚠️ Behaviour change at the merge: R2's own rewriter was a different program. Its published stress
    numbers (light 0.8343, heavy 0.7961) were produced by that one and do NOT carry over — re-measuring
    both roads on this ladder is the point of the merge (04-merge-plan.md §3.2).
    """

    def __init__(self, level: str | int = "scaffold", llm=None) -> None:
        self.level = LEVELS[level] if isinstance(level, str) else int(level)
        assert 0 <= self.level <= 4, level
        self.name = next(k for k, v in LEVELS.items() if v == self.level)
        self.llm = llm

    def __call__(self, message: str, turn: int) -> str:
        return paraphrase(message, self.level, self.llm)
