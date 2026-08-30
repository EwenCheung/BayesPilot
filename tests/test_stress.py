"""Spec 3.10 — the stress harness must actually destroy the thing it claims to destroy."""
from src.eval.stress import paraphrase

BUY = "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton."
REPLY = "For that, what matters is: color: black; Closure type: Buckle."
OVERRIDE = "Actually, ignore my earlier preference. What I need is: Material: alloy."
BROWSE = "I'm looking for Dresses Casual, but I'm still exploring."


def test_level_zero_is_the_identity():
    for message in (BUY, REPLY, OVERRIDE, BROWSE):
        assert paraphrase(message, 0) == message


def test_level_one_removes_the_scaffold_but_keeps_the_payload_verbatim():
    stressed = paraphrase(BUY, 1)
    assert "A key requirement is" not in stressed
    assert "Material: cotton" in stressed, "level 1 tests the parser, not the matcher"


def test_level_two_also_rewrites_the_payload():
    stressed = paraphrase(BUY, 2)
    assert "Material: cotton" not in stressed
    assert "cotton" in stressed.lower(), "meaning must survive even though the string does not"


def test_paraphrase_is_deterministic():
    assert paraphrase(REPLY, 2) == paraphrase(REPLY, 2)


def test_every_template_is_covered():
    for message in (BUY, REPLY, OVERRIDE, BROWSE):
        assert paraphrase(message, 2) != message, message


def test_llm_level_falls_back_to_deterministic_when_offline():
    class DeadLLM:
        def chat(self, *_, **__):
            return None

    stressed = paraphrase(BUY, 3, llm=DeadLLM())
    assert stressed != BUY and "A key requirement is" not in stressed


def test_l3_rewords_the_category_itself():
    """The ladder's hole: L1 and L2 keep the category verbatim, so they never stress the earliest
    and least recoverable decision in the session.

    Measured consequence of the hole: `scripts/category_probe.py` reports 100% category accuracy at
    L2, which made paraphrase look like a pure ranking problem. It is not — R1 measured 85% category
    accuracy under model-written paraphrase. L3 closes the hole deterministically, without needing
    the network.
    """
    from src.eval.stress import paraphrase

    message = "I'm looking for Shirts T-Shirts. A key requirement is: Material: cotton."
    assert "Shirts T-Shirts" in paraphrase(message, 1), "L1 should keep the category verbatim"
    assert "Shirts T-Shirts" in paraphrase(message, 2), "L2 should keep the category verbatim"
    assert "Shirts T-Shirts" not in paraphrase(message, 3), "L3 must reword the category"


def test_l3_keeps_the_category_recognisable():
    """A rewrite that destroys the category is not paraphrase, it is a different question.

    Every L3 opener must still share at least one content word with the original category, or we are
    measuring the agent against a customer who changed their mind.
    """
    from src.understand.attributes import tokens
    from src.eval.stress import paraphrase

    for category in ("Shirts T-Shirts", "Novelty Clothing", "Girls Swimwear Sets", "Belts"):
        message = f"I'm looking for {category}, but I'm still exploring."
        out = paraphrase(message, 3)
        assert tokens(category) & tokens(out), f"{category!r} unrecognisable in {out!r}"
