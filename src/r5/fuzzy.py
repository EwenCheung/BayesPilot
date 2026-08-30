"""Fuzzy canonicalisation — repair misspelled *matching* words before the parse tiers see them.

The free-form corpus restyles the opener into slang, shorthand and typos. Two measurements decided
the shape of this module, and both killed the obvious implementation:

📊 **1. Most out-of-vocabulary words are not typos.** Against a vocabulary built from catalog
*titles* only (1,901 words, frequency >= 30), 49.6% of content tokens in `freeform_v1/train` are OOV.
Against the **full** catalog text (6,071 words) that falls to 14.9% — and what remains is dominated by
ordinary conversational English, not misspellings:

    lookin(142) matters(122) wait(81) yeah(81) exploring(81) extras(72) haves(67)
    figuring(67) tbh(67) browse(62) settled(62) specifics(62) haven(61) decided(61)

Genuine shorthand (`lookin`, `rlly`, `tbh`) is ~18% of the OOV set, i.e. **2.7% of all content
tokens**. A corrector that fires on "OOV" fires almost entirely on correctly-spelled words.

📊 **2. Correcting against the whole catalog vocabulary actively injects false constraints.** Measured
with `difflib.get_close_matches(w, VOCAB, cutoff=0.75)`:

    browsing -> brown(0.77)   ⚠️ a COLOR — invents a colour constraint out of a route cue
    browse   -> rows/rose/bros(0.80)
    wait     -> waist(0.89)   ⚠️ a SIZE word
    haves    -> hanes(0.80)   ⚠️ a BRAND

That is the failure `softcard.py` already records: *a confident wrong snap is worse than no snap*,
because it feeds the same channel as a genuine match.

🔑 **So the target vocabulary is restricted to words that can actually help matching** — the tokens of
the 1,115 coarse category names, plus the simulator's own material and colour vocabularies — rather
than every word in the catalog. Re-measured against that target, 15 of the 17 ordinary words above are
left untouched, while `sirt->shirt`, `snekers->sneakers`, `bracelt->bracelets` still resolve.

🔑 **And a correction EXPANDS the message rather than replacing a word.** `sirt` scores 0.889 against
both `shirt` and `skirt`; `difflib` breaks that tie alphabetically, which is not a linguistic judgment.
Appending the top-`k` candidates and keeping the original lets the level-1 category posterior and the
rest of the utterance decide on evidence. It also bounds the damage from a wrong candidate: the
original token is still there, and a term with no opinion cancels (`likelihood.py`).

⚠️ Ships **off** (`fuzzy_expand=False`), and even enabled it only fires on messages the deterministic
path cannot already read — so the templated corpora are untouched by construction.
"""
from __future__ import annotations

import difflib
import re

from src.common.attributes import tokens
from src.r4.extract import COLORS, MATERIALS

WORD_RE = re.compile(r"[a-z]{3,}")


class FuzzyCanon:
    """Correct misspelled category/material/colour words by expansion, not replacement."""

    def __init__(self, category_names, lexical_text, min_df: int = 30) -> None:
        # words the catalog genuinely uses — never "corrected", however odd they look
        counts: dict[str, int] = {}
        for text in lexical_text.values():
            for word in WORD_RE.findall(text.lower()):
                counts[word] = counts.get(word, 0) + 1
        self.known = frozenset(w for w, c in counts.items() if c >= min_df)

        # ...and the much smaller set a correction is allowed to land ON
        target = {t for name in category_names for t in tokens(name) if len(t) >= 3}
        target.update(MATERIALS)
        target.update(COLORS)
        self.target = sorted(target)
        self._cache: dict[tuple[str, int, float], tuple[str, ...]] = {}

    def candidates(self, word: str, k: int, cutoff: float) -> tuple[str, ...]:
        key = (word, k, cutoff)
        got = self._cache.get(key)
        if got is None:
            got = self._cache[key] = tuple(
                difflib.get_close_matches(word, self.target, n=k, cutoff=cutoff))
        return got

    def expand(self, message: str, k: int = 3, cutoff: float = 0.80, min_len: int = 4) -> str:
        """Return `message` with candidate corrections appended. Never removes anything."""
        if not message:
            return message
        added: list[str] = []
        seen: set[str] = set()
        for word in WORD_RE.findall(message.lower()):
            if len(word) < min_len or word in self.known or word in seen:
                continue
            seen.add(word)
            for candidate in self.candidates(word, k, cutoff):
                if candidate not in seen:
                    seen.add(candidate)
                    added.append(candidate)
        return f"{message} {' '.join(added)}" if added else message
