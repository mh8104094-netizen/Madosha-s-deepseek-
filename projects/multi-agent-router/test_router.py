from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from router import AgentProfile, AgentRouter, Task  # noqa: E402


AGENTS = [
    AgentProfile("fast", frozenset({"text", "tools"}), 0.91, 0.10, 180),
    AgentProfile("research", frozenset({"text", "tools", "research"}), 0.98, 0.50, 800),
    AgentProfile("cheap-research", frozenset({"research"}), 0.88, 0.08, 400),
]


def test_capability_filtering():
    decision = AgentRouter(AGENTS).route(Task("deep research", frozenset({"research", "tools"})))
    assert decision.agent == "research"


def test_budget_constraint_changes_route():
    decision = AgentRouter(AGENTS).route(Task("cheap research", frozenset({"research"}), max_cost=0.10))
    assert decision.agent == "cheap-research"


def test_impossible_constraints_fail_explicitly():
    try:
        AgentRouter(AGENTS).route(Task("impossible", frozenset({"vision"})))
    except LookupError:
        return
    raise AssertionError("expected LookupError")


if __name__ == "__main__":
    test_capability_filtering()
    test_budget_constraint_changes_route()
    test_impossible_constraints_fail_explicitly()
    print("multi-agent-router: ok")
