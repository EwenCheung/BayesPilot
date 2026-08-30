"""Leakage-safe free-form language adapter for the unchanged official evaluator.

The competition JSONL rows describe sessions; they do not contain the messages heard by the agent.
``evaluator.local_evaluator`` creates those messages dynamically.  This module therefore wraps the
agent and rewrites only its input.  Labels, turns, override timing, hit checks, and score arithmetic
remain owned by the evaluator.
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Iterable

from src.eval.stress import KEY_REQ, NO_PREF, NULL_ASK, OPENER, OVERRIDE, REPLY, _reword_category


VERSION = "freeform-v1"
STYLES = (
    "chatty_slang",
    "terse_shorthand",
    "emoji_casual",
    "polite_ramble",
    "fragmented",
    "self_correcting",
    "lowercase_typo",
    "punctuation_light",
)

_BOUNDARY = re.compile(
    r"^I don't have a preference for (?P<attribute>[a-z_]+); please use your judgment\.?$", re.I
)
_OFFICIAL = (
    re.compile(r"^I'm looking for .+?(?:, but I'm still exploring\.|\. A key requirement is:)", re.S),
    re.compile(r"^For that, what matters is:", re.S),
    re.compile(r"^Actually, ignore my earlier preference\. What I need is:", re.S),
    re.compile(r"^I don't have (?:an additional preference|a preference) for", re.S),
    re.compile(r"^Those options are not quite right yet", re.S),
)


def stable_seed(*parts: object) -> int:
    raw = "\0".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], 16)


def is_official_grammar(message: str) -> bool:
    return any(pattern.search(message.strip()) for pattern in _OFFICIAL)


def _natural_payload(payload: str, rng: random.Random, style_index: int) -> str:
    """Reorder attribute labels without inventing or deleting catalog values."""
    rendered: list[str] = []
    for raw in payload.rstrip(".").split("; "):
        chunk = raw.strip()
        key, separator, value = chunk.partition(":")
        if separator and key.strip() and value.strip():
            key = key.strip().lower().replace("type", "kind")
            value = value.strip()
            forms = (
                f"{value} for {key}",
                f"{key} needs to be {value}",
                f"{value} ({key})",
                f"on {key}, {value}",
            )
            chunk = forms[(style_index + len(rendered)) % len(forms)]
        rendered.append(chunk)
    if len(rendered) == 1:
        return rendered[0]
    rng.shuffle(rendered)
    joins = (" + ", ", and ", " / ", "; also ")
    return joins[style_index % len(joins)].join(rendered)


def _decorate(message: str, style_index: int, rng: random.Random) -> str:
    if style_index == 0:
        replacements = (("right now", "rn"), ("something", "smth"), ("please", "pls"))
    elif style_index == 1:
        replacements = (("about", "abt"), ("with", "w/"), ("because", "cuz"))
    elif style_index == 2:
        replacements = ()
        message = f"{message} {rng.choice(('🙂', '🙏', '✨', '👀', '🛍️'))}"
    elif style_index == 4:
        message = message.replace(", ", " ... ").replace("; ", " / ")
        replacements = ()
    elif style_index == 6:
        replacements = (("looking", "lookin"), ("really", "rlly"), ("please", "plz"))
    elif style_index == 7:
        message = message.replace("—", " ").replace(",", "")
        replacements = ()
    else:
        replacements = ()
    for old, new in replacements:
        message = re.sub(rf"\b{re.escape(old)}\b", new, message, flags=re.I)
    return re.sub(r"\s+", " ", message).strip()


def rewrite_message(message: str, *, seed: int, turn: int = 1, style: str | None = None) -> str:
    """Rewrite one evaluator message while retaining its complete semantic payload.

    The function is deterministic for ``(message, seed, turn, style)``.  Typos affect only filler
    words, never categories or constraint values.
    """
    style_index = STYLES.index(style) if style in STYLES else stable_seed(seed, "style") % len(STYLES)
    rng = random.Random(stable_seed(seed, turn, message, style_index))
    stripped = message.strip()

    opener = OPENER.match(stripped)
    if opener:
        category = _reword_category(opener.group("category").strip(), rng)
        tail = (opener.group("tail") or "").strip()
        key = KEY_REQ.match(tail)
        if not tail or "still exploring" in tail:
            forms = (
                f"hey, just checking out {category} rn; no must-haves yet",
                f"any decent {category} around? still figuring out the details tbh",
                f"show me some {category} vibes, i'm open for now",
                f"could you help me browse {category}? I have not settled on specifics yet",
                f"{category} maybe ... haven't decided what matters yet",
                f"wait—yeah, {category}; just exploring at this point",
                f"lookin for {category}, not sure on the extras yet",
                f"browsing {category} no fixed preferences yet",
            )
        elif key:
            payload = _natural_payload(key.group("payload"), rng, style_index)
            forms = (
                f"yo, need {category}; biggest thing is {payload}",
                f"{category} pls — must have {payload}",
                f"shopping for {category}, and {payload} is non-negotiable",
                f"could you find {category} for me? The important part would be {payload}",
                f"need {category} ... {payload} matters most",
                f"actually, make it {category}; priority is {payload}",
                f"lookin for {category}, rlly need {payload}",
                f"after {category} must have {payload}",
            )
        else:
            payload = _natural_payload(tail.lstrip(". "), rng, style_index)
            forms = (
                f"hey, i'm after {category}; also {payload}",
                f"need {category} w/ {payload}",
                f"{category} would work, especially {payload}",
                f"could we look at {category}? I would prefer {payload}",
                f"{category} ... and {payload}",
                f"actually {category}; keep {payload} in mind",
                f"lookin for {category}, ideally {payload}",
                f"after {category} preferably {payload}",
            )
        output = forms[style_index]
    else:
        override = OVERRIDE.match(stripped)
        reply = REPLY.match(stripped)
        no_preference = NO_PREF.match(stripped)
        boundary = _BOUNDARY.match(stripped)
        if override:
            payload = _natural_payload(override.group("payload"), rng, style_index)
            forms = (
                f"nah scratch my old preference—what i need now is {payload}",
                f"change of plan: drop the earlier thing, go w/ {payload}",
                f"oops, replacing my previous choice; {payload} is the new requirement",
                f"please disregard what I said earlier and use {payload} instead",
                f"wait ... old preference is out / new need is {payload}",
                f"actually no—forget before; switch it to {payload}",
                f"sry changed my mind, remove the old one n use {payload}",
                f"ignore earlier preference use {payload} now",
            )
            output = forms[style_index]
        elif reply:
            payload = _natural_payload(reply.group("payload"), rng, style_index)
            forms = (
                f"yeah, what matters to me is {payload}",
                f"for that? {payload} pls",
                f"i'd go with {payload}, that's the key bit",
                f"The preference I would add is {payload}",
                f"hmm ... mainly {payload}",
                f"actually, the answer is {payload}",
                f"mostly {payload} tbh",
                f"for me its {payload}",
            )
            output = forms[style_index]
        elif boundary or no_preference:
            attribute = (boundary or no_preference).group("attribute")
            forms = (
                f"no preference on {attribute} tbh, you pick",
                f"{attribute}? idc, use your judgement",
                f"i'm flexible about {attribute} 🙂",
                f"I do not have a particular view on {attribute}; please decide",
                f"{attribute} ... whatever works",
                f"actually, no opinion on {attribute}",
                f"not fussed abt {attribute}, ur call",
                f"no preference for {attribute} you decide",
            )
            output = forms[style_index]
        elif NULL_ASK.match(stripped):
            forms = (
                "nah, none of those—ask me one concrete thing",
                "not quite; pls ask abt one detail",
                "those miss the mark 👀 ask me something specific",
                "Could you narrow this by asking me about one particular attribute?",
                "nope ... ask one specific thing",
                "wait, those are off; ask me a clearer question",
                "not right yet, ask smth specific plz",
                "those dont work ask one specific attribute",
            )
            output = forms[style_index]
        else:
            output = f"btw, {stripped.rstrip('.')}"  # defensive path; still breaks official grammar

    output = _decorate(output, style_index, rng)
    if output == stripped or is_official_grammar(output):
        output = f"hey—{output}"
    return output


class FreeFormDatasetAgent:
    """Assign each sequential evaluator session its row-specific language profile."""

    def __init__(self, agent, rows: Iterable[dict]) -> None:
        self._agent = agent
        self._rows = list(rows)
        self._next_row = 0
        self._by_session: dict[str, dict] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        if self._next_row >= len(self._rows):
            raise RuntimeError("free-form row/session alignment exhausted")
        self._by_session[session_id] = self._rows[self._next_row]
        self._next_row += 1
        self._agent.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        row = self._by_session[session_id]
        variant = row["free_form"]
        if turn == 1:
            expected = hashlib.sha256(user_message.encode("utf-8")).hexdigest()
            if expected != variant["canonical_initial_sha256"]:
                raise RuntimeError(f"free-form initial-message mismatch for {row['sample_id']}")
            rewritten = variant["initial_message"]
        else:
            rewritten = rewrite_message(
                user_message,
                seed=int(variant["seed"]),
                turn=turn,
                style=str(variant["style"]),
            )
        return self._agent.respond(session_id, rewritten, turn, top_k)

    def __getattr__(self, name: str):
        return getattr(self._agent, name)

