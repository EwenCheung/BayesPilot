# R5 — decision log

## D16

**Free-form text costs R4 only 0.043, because the pool never depended on the parse.**

📊 Validation: `resplit` (templated) R4 **0.9540**; `freeform` R4 **0.9110**.

On free-form openers R4 parses `state.category` from **0.0%** and leaves route at its `"browsing"`
default in **100%** of sessions — and still scores 0.911. The level-1 category belief reads the **raw
opener string**, so the candidate pool is selected correctly from unparsed text. The ontology tier
independently recovers ≥1 constraint from **91.8%** of openers.

**Decision:** the deterministic path already handles this corpus. Do not rebuild parsing for it.

---

## D17

**Category and route recovery: built, measured, both worthless.**

📊 freeform train (1,200), later turns templated:

| | later=L0 | later=L2 |
|---|---|---|
| R4 baseline | 0.9153 | 0.7769 |
| + `freetext_route` | 0.9146 | 0.7767 |
| + `freetext_category` | 0.9153 | 0.7769 |
| + both | 0.9146 | 0.7767 |

`freetext_category` is **exactly zero to four decimals** — it fills a field no downstream decision
reads. `freetext_route` is slightly negative: a cue-word router that mislabels an ordinary session as
`override` triggers R4's override-silence branch and throws away turns 1–2 for nothing.

🔑 **Generalisable: recovering a value is worthless unless something consumes it.** The category
looked like the obvious gap because it was measurably absent (0.0%); absence was not the same as
cost.

**Decision:** both ship **off**. Code retained so the negative reproduces.

---

## D18 ⚠️ CORRECTED

**The escalation gate is off-by-one: it fires on the turn AFTER the unreadable one.**

⚠️ **An earlier version of this entry claimed the LLM "never fires on the free-form corpus". That was
wrong**, and it was wrong because it was reasoned from the code rather than measured. Corrected below;
the original claim is left described rather than deleted, because the reasoning error is the
transferable part.

📊 Measured, offline, by evaluating the gate exactly where `src/r4/agent.py` evaluates it:

| corpus | sessions where the gate opens | turns |
|---|---|---|
| `freeform` validation | **362 / 400 (90.5%)** | `{turn 2: 362}` — exactly once each |
| `resplit` validation (templated) | 0 / 400 (0.0%) | none |

**The gate does open — always on turn 2, exactly once per session.** The mistaken reasoning assumed
`template_hits` was incremented before the gate was read within the same turn. It is not: the gate is
evaluated at the *start* of turn `t` using hits accumulated through turn `t-1`. At turn 2 the
free-form opener has contributed nothing, so `template_hits == 0` and the gate opens.

🔑 **The real defect is worse than the one I claimed.** Here is the message the model is handed on
turn 2:

```
For that, what matters is: nylon; 89% Nylon, 11% Spandex.
For that, what matters is: leather; 100% Synthetic.
```

Those are **perfectly templated replies** — `REPLY_RE` parses them exactly. So:

* the free-form **opener**, which genuinely needs the model, is blocked by `turn >= 2`;
* the templated **reply**, which needs nothing, is the one message the model gets.

**The LLM fires on the wrong message: blocked where it is needed, invoked where it is not.** This has
been masking the tier's true value in every road that inherited the gate — a call spent on a message
the regex already handles is indistinguishable from a model that does not help (IMPORTANT.md §13.1.3).

The cause is scope: `paraphrased()` is a **session-level** detector (*"nothing we know how to read has
matched by the second turn"*), which was correct against its design threat — an organizer rewriting
every turn. `freeform_v1` is a **per-turn** phenomenon: opener restyled, replies templated. A
session-level gate cannot see it.

**Decision:** fix the aim. `llm_fallback` escalates on the **current message** — when no template
matches it *and* the ontology tier recovers nothing from it — instead of on session history. That is
"read it deterministically if you can, else escalate", per turn.

📊 Value of the fix on freeform train[:400], agent online:

| | score | Hit@10 | LLM calls | failures |
|---|---|---|---|---|
| offline baseline | 0.9131 | 0.9525 | 0 | — |
| turn-1 fallback (first version) | 0.9145 | 0.9550 | 400 | 6 |

**+0.0014 — inside noise.** The gate bug is real and worth fixing, but on *this* corpus the ontology
tier already recovers >=1 constraint from 91.8% of free-form openers, so little is left to win. Ships
**off**: it buys a network dependency on every session for no measurable return.

⚠️ **Generalisable, and the reason this entry exists:** a detector whose scope is coarser than the
phenomenon fails silently and looks like a component that does not help. And a claim reasoned from
control flow is not a measurement — the "never fires" version survived a full write-up before a
four-line probe disproved it.

---

## D19

**The one mechanism that does work on hard text is R4's, not R5's.**

📊 freeform train, later turns stressed at L2: soft-card takes **0.7769 → 0.7951 (+0.018)**, while
every R5 mechanism moves nothing. Consistent with R4 D15: soft-card pays in proportion to how badly
the exact matcher is broken, and a free-form *opener* with templated *replies* barely breaks it.

**Implication for the sealed test and for any future corpus:** if later turns are also restyled — as
`manifest.json`'s policy line says the generator intended — the deterministic recoveries will still
be worthless and soft-card will carry the result.


---

## D20

**The fix to the escalation gate, and the second wrong predicate it took to get there.**

[D18](#d18-corrected) established that the gate fires on the wrong message. The fix replaces a
session-level test with a per-message one: `reads_deterministically(message, turn)`.

**The first version of that predicate was also wrong**, and only a spot-check caught it:

```
turn 1  escalate=False  <- yo, need & utility shoes; biggest thing is leather
```

It asked *"did any template match, or did the ontology tier find a pair?"* — and `normalise()` finds
`material=leather` in that opener, so it reported "readable". But the **category** was lost, and the
category is carried by turn 1 alone; no later turn ever repeats it. **"Recovered something" is not
"read it."**

The shipped predicate is message-type aware, because different turns carry different things:

| turn | carries | readable when |
|---|---|---|
| 1 | **category** (+ maybe a constraint) | `OPENER_RE` matches — nothing else recovers a category |
| 2+ | constraints only | a template matches, or the ontology finds a pair |

Verified:

```
turn 1  escalate=True   <- yo, need & utility shoes; biggest thing is leather
turn 1  escalate=True   <- browsing shoes oxfords no fixed preferences yet
turn 1  escalate=False  <- I'm looking for Jewelry Necklaces. A key requirement is: ...
turn 2  escalate=False  <- For that, what matters is: nylon; 89% Nylon, 11% Spandex.
turn 3  escalate=False  <- I don't have a preference for other; please use your judgment.
```

The two "recognised but empty" templates count as readable: `NULL_ASK_RE` and `NO_PREF_RE` are the
simulator saying it has nothing to add, and escalating there spends a call to rediscover that.

**Decision:** shipped **off** regardless. §1 of [R5-RESULTS.md](../R5-RESULTS.md) prices the LLM path
at ~1.2 s/session against 8.5 ms offline — about 140x — for a measured +0.0014 on this corpus. The
gate is now correct; the economics still do not justify enabling it by default.

⚠️ **Twice in one road a predicate looked right and was not**, and both times the error was invisible
to the end-to-end score: the first would have reported "escalation buys nothing" and the second
"escalation never triggers". Neither is distinguishable from a component that does not help.

---

## D21 ⚠️ REPAIR

**The escalation gate was repaired, R5's parallel path deleted, and the LLM still buys nothing.**

D20 shipped R5's turn-1 fallback as a *second* escalation path because the inherited gate at
`src/r4/agent.py:51` could not fire on a free-form opener. That was routing around a bug rather than
fixing it, and it left the bug live for R1–R4. Both are now resolved.

**The repair.** One line:

```python
- llm = self.llm if (self.flags.llm_extract and state.paraphrased()) else None
+ llm = self.llm if self.flags.llm_extract else None
```

`parse()` already gates per message — it escalates only when `not handled`, which is exactly the
right question. `paraphrased()` is a **session**-level test (`turn >= 2 and template_hits == 0`)
AND-ed on top, and on a corpus whose unreadable turn is the **opener** the two can never both hold:
turn 1 fails `turn >= 2`, and from turn 2 the templated replies are `handled`. Note `src/r1/agent.py`
never had the extra conjunct — R3 introduced it and R4 inherited it.

**Measured, freeform validation (400), before and after:**

| gate | extract() calls | score |
|---|---:|---:|
| broken (D20 measurement) | **0** | 0.9110 |
| repaired | **400** (1/session, the opener) | 0.9104 |

The calls are real now — 400, one per unreadable opener, where the broken gate made zero. The score
does not move: **−0.0006, with hit and MRR bit-identical** (0.9475 / 0.9329) and only MTTC drifting
3.13 → 3.16. 10 of 400 calls failed and fell back cleanly.

**This confirms D16 rather than contradicting it.** The candidate pool is selected from the level-1
category belief reading the **raw opener string**; nothing downstream consumes the parsed
`state.category` for ranking. So a correctly-parsed opener changes what the state *records* and not
what the agent *retrieves*. Escalation was never the missing piece.

**Decision:** the repair ships (it is a correctness fix, and it restores the LLM tier for every road
on any opener-restyled corpus); `llm_extract` still ships **off** by default. Cost is 580s vs 21s on
400 sessions — **28×** — for −0.0006.

**R5's parallel path is deleted.** With the gate repaired it would double-call every unreadable turn.
`llm_fallback` survives as a no-op flag name for one release so existing `runs/registry.jsonl` rows
stay interpretable; `reads_deterministically` stays in `freetext.py` because it documents the
predicate and its two wrong versions. Net: R5 has less code than before the bug was found.

⚠️ **R3's published extraction-tier gains (+0.055 L2, +0.063 L3) were measured under the broken
gate.** They are not wrong — on those corpora the unreadable turns are turns 2+, where the gate does
fire — but they are a floor, not a ceiling, and any restatement should say which gate produced them.

⚠️ **A gate *opening* is not a call being made.** This bug was mis-called twice from code reading in
both directions before anyone counted actual `extract()` invocations. Instrument the call, not the
condition.

---

## D22 🟥

**Fuzzy spelling correction: built, measured exactly 0.0000, and the reason is that this corpus does
not misspell the words that matter.**

The proposal was to run fuzzy canonicalisation *before* the deterministic-vs-LLM branch, so a typo'd
word gets a chance to become a real category word and the message becomes readable without a model
call. Built as `src/r5/fuzzy.py` behind `fuzzy_expand` (default off).

### Two measurements that shaped the design before it was written

**1. "Out of vocabulary" is not "misspelled."** Against a vocabulary from catalog *titles* only
(1,901 words, df >= 30), 49.6% of content tokens in `freeform_v1/train` are OOV. Against the **full**
catalog text (6,071 words) that drops to 14.9%, and what remains is ordinary conversational English:

    lookin(142) matters(122) wait(81) yeah(81) exploring(81) extras(72) haves(67)
    figuring(67) tbh(67) browse(62) settled(62) specifics(62) haven(61) decided(61)

Genuine shorthand is ~18% of the OOV set — **2.7% of all content tokens**.

**2. Correcting against the whole catalog vocabulary fabricates evidence.** With
`difflib.get_close_matches(w, VOCAB, cutoff=0.75)`:

| word | "correction" | ratio | why it is harmful |
|---|---|---:|---|
| `browsing` | `brown` | 0.77 | invents a **colour** from a route cue |
| `wait` | `waist` | 0.89 | invents a **size** |
| `haves` | `hanes` | 0.80 | invents a **brand** |
| `browse` | `rows` / `rose` | 0.80 | noise |

So the shipped design restricts the correction **target** to the 764 tokens of the coarse-category
names plus `MATERIALS` and `COLORS`, and **expands rather than replaces** — `sirt` ties `shirt` and
`skirt` at 0.889 and `difflib` breaks that tie *alphabetically*, so keeping the original plus the
top-`k` lets the posterior decide on evidence. Both guards are tested in `tests/test_fuzzy.py`.

### The measurement

Fitted with `scripts/fit_fuzzy.py` on `freeform_v1/train` (1,200), staged over
`fuzzy_cutoff × fuzzy_k × fuzzy_min_len`:

| | train (1,200) | validation (400) |
|---|---:|---:|
| fuzzy off | 0.9153 | 0.9110 |
| **every one of 10 configurations** | **0.9153** | 0.9108 |

⚠️ Ten configurations spanning cutoff 0.75→0.90 and k 1→5 returning a score **identical to four
decimals** is not a result, it is a symptom — the same signature as D17. So the firings were counted
rather than the score trusted:

```
200 openers -> 37 expanded (18.5%)
  'wait—yeah, Bras Everyday; just exploring...'        -> + waist
  'could you help me browse & Tees Tanks & Camis?...'  -> + specific
  'browsing Sandals Heeled Sandals no fixed pref...'   -> + bowling
category argmax on the 37 expanded openers: unchanged 37, changed 0
```

**The mechanism runs, fires on 18.5% of openers, and is wrong essentially every time it fires.** It
is harmless only because the appended tokens are too weak to move the level-1 posterior — a no-op
that becomes a liability the moment it carries any weight.

### Why there was nothing to find

The premise does not hold for this corpus. Measured on `freeform_v1/train`, the **target's coarse
category tokens appear verbatim in the opener**:

| | share |
|---|---:|
| all tokens present | **64.9%** |
| some present | 34.6% |
| none present | **0.5%** |

...and the `lowercase_typo` style is **84.7%** mean token coverage against 83.5–88.6% for every other
style — statistically indistinguishable. **The generator restyles the conversational scaffolding, not
the product nouns.** The category name survives intact in every style, which is exactly why D16 found
the level-1 pool already contains the target ~100% of the time from raw unparsed text.

**Decision:** ships **off**. Kept behind `fuzzy_expand` with its tests so the negative reproduces.

⚠️ **This is a corpus property, not a property of fuzzy matching.** On text that genuinely misspells
category words — a real search box — the module works: `snekers -> sneakers`, `bracelt -> bracelets`,
`dres -> dress`, `sirt -> shirt`. Nothing here argues it would fail there. It argues that
`freeform_v1` never asks the question.

⚠️ **One residual leak is pinned rather than fixed** (`tests/test_fuzzy.py`): `wait -> waist` scores
0.889, the *same* ratio as `sirt -> shirt`. No cutoff separates them. A trigram index or a phonetic
key (`sirt` and `shirt` collide under Soundex; `skirt` does not) would break exactly the ties
`difflib` cannot — worth doing only if a corpus arrives where fuzzy matching has something to fix.

### D22 addendum — where the effect actually came from, and the "only when it's a typo" gate

**The +0.0016 on `freeform_v1/test` was the LLM prompt, not the deterministic path.** Paired,
same-session comparison of `fuzzy_expand` on/off:

| split | n | LLM | sessions whose outcome changed | delta |
|---|---:|---|---:|---:|
| train | 1,200 | off | **1 (0.1%)** | +0.0000 |
| validation | 400 | off | **1 (0.2%)** | −0.0001 |
| test | 800 | off | **3 (0.4%)** | +0.0000 |
| test | 800 | **on** | **28 (3.5%)** | **+0.0016** |

Offline the module is inert — it moves 0.1–0.4% of sessions and nothing measurable. The only
configuration where it does anything is the one where the expanded string is also what gets sent to
`extract()`, so its whole measured effect is **perturbing the model's prompt with words the shopper
never said**. A paired bootstrap on that row gives CI (+0.0007, +0.0027), which is a real difference —
but a real difference produced by feeding noise to an LLM is not a mechanism, and it is not
reproducible reasoning about the shopper's text.

**The "only fuzzy when there is actually a typo" gate, measured.** The natural implementation is an
English dictionary: a word that is real English is not a misspelling, however absent it is from a
*product* catalog. Against `/usr/share/dict/words` (234,456 entries) on `freeform_v1/train`:

| | occurrences | share |
|---|---:|---:|
| words that currently trigger a correction | 222 | — |
| ...real English, so **suppressed** by the gate | 145 | **65.3%** |
| ...not English, so still corrected | 77 | 34.7% |

**The gate works.** It kills the two dominant false corrections outright — `wait → waist` (81
occurrences) and `browsing → bowling` (59) — which are 140 of the 145 it suppresses.

**And it leaves almost nothing behind.** Of the 77 survivors, `specifics → specific` (62) is an
ordinary word the dictionary simply lacks an inflection for, and most of the rest map to *themselves*
(`dryers → dryers`, `knits → knits`, `bustiers → bustiers`) — real catalog category words that fall
below the `df >= 30` threshold of the `known` set, so the "correction" is a duplicate token and a
no-op. The genuine misspellings are **`consteruction → construction` and `funn → fun`: two
occurrences in 1,200 openers, 0.17%.**

**Decision:** the gate is correct and not worth building. It raises precision on a mechanism whose
entire recall target is two sessions in twelve hundred, and it would add a dependency on a system
word list that is not guaranteed on the grading machine. `fuzzy_expand` stays off.

⚠️ Two cheap defects are recorded rather than fixed, since the module ships off: a candidate equal to
the input word should be skipped (it can only add a duplicate token), and `known` at `df >= 30` is
tight enough to treat real catalog words like `bustiers` as unknown.
