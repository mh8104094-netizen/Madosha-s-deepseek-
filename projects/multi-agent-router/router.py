from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class AgentProfile:
    name: str
    capabilities: FrozenSet[str]
    reliability: float
    cost_per_task: float
    latency_ms: int


@dataclass(frozen=True)
class Task:
    name: str
    required: FrozenSet[str]
    max_cost: float | None = None
    max_latency_ms: int | None = None


@dataclass(frozen=True)
class RouteDecision:
    agent: str
    score: float
    explanation: tuple[str, ...]


class AgentRouter:
    def __init__(self, agents: list[AgentProfile]) -> None:
        if not agents:
            raise ValueError("at least one agent is required")
        self.agents = agents

    def route(self, task: Task) -> RouteDecision:
        candidates: list[tuple[float, AgentProfile, tuple[str, ...]]] = []

        for agent in self.agents:
            if not task.required.issubset(agent.capabilities):
                continue
            if task.max_cost is not None and agent.cost_per_task > task.max_cost:
                continue
            if task.max_latency_ms is not None and agent.latency_ms > task.max_latency_ms:
                continue

            reliability_component = agent.reliability * 70
            cost_component = max(0.0, 20 - agent.cost_per_task * 10)
            latency_component = max(0.0, 10 - agent.latency_ms / 200)
            score = reliability_component + cost_component + latency_component
            explanation = (
                f"reliability={agent.reliability:.2f}",
                f"cost={agent.cost_per_task:.2f}",
                f"latency_ms={agent.latency_ms}",
            )
            candidates.append((score, agent, explanation))

        if not candidates:
            raise LookupError(f"no agent satisfies task: {task.name}")

        score, agent, explanation = max(candidates, key=lambda item: (item[0], item[1].reliability))
        return RouteDecision(agent.name, round(score, 3), explanation)


if __name__ == "__main__":
    agents = [
        AgentProfile("fast-generalist", frozenset({"text", "tools"}), 0.92, 0.20, 250),
        AgentProfile("careful-researcher", frozenset({"text", "tools", "research"}), 0.98, 0.55, 900),
    ]
    print(AgentRouter(agents).route(Task("research", frozenset({"research"}))))
