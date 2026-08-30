from types import SimpleNamespace

from src.common.contracts import SessionState
from src.r3.agent import Agent


class CatalogBackedCategories:
    """A tiny stand-in whose pools represent fresh global-category retrieval."""

    def __init__(self):
        self.calls = []
        self.pools = {
            "Shirts": [f"shirt-{index}" for index in range(500)],
            "Shoes": [f"shoe-{index}" for index in range(400)],
        }

    def pool(self, opener, tau):
        self.calls.append((opener, tau))
        return list(self.pools[opener])


def lightweight_agent():
    agent = Agent.__new__(Agent)
    agent.categories = CatalogBackedCategories()
    agent.flags = SimpleNamespace(belief_pool=True, tau_mass=0.9)
    agent._fallback = ["fallback"]
    return agent


def test_second_turn_restarts_from_full_category_pool_not_previous_shortlist():
    agent = lightweight_agent()
    state = SessionState(category="Shirts", history=["I want shirts"])

    first_universe = agent._candidate_pool(state, "I want shirts")
    previous_top_200 = first_universe[:200]

    # A changed constraint may completely reorder the results. Retrieval must start from all 500
    # category candidates, including products that the previous turn ranked below 200.
    second_universe = agent._candidate_pool(state, "Actually, replace cotton with leather")

    assert len(second_universe) == 500
    assert set(second_universe) - set(previous_top_200)
    assert agent.categories.calls == [("Shirts", 0.9), ("Shirts", 0.9)]


def test_category_change_retrieves_a_new_pool_from_the_global_category_index():
    agent = lightweight_agent()
    state = SessionState(category="Shirts", history=["I want shirts"])
    assert agent._candidate_pool(state, "I want shirts")[0].startswith("shirt-")

    state.category = "Shoes"
    state.category_surface = "shoes"
    refreshed = agent._candidate_pool(state, "Actually, I want shoes")

    assert len(refreshed) == 400
    assert all(item.startswith("shoe-") for item in refreshed)
    assert agent.categories.calls[-1] == ("Shoes", 0.9)
