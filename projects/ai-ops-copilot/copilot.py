from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class ActionRequest:
    action: str
    target: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    risk: int
    requires_approval: bool
    allowed: bool
    reasons: tuple[str, ...]


class ActionPolicy:
    """Small policy engine that keeps AI-generated plans behind deterministic gates."""

    HIGH_RISK_ACTIONS = {"delete", "terminate", "pay", "publish", "grant_admin"}
    MUTATING_ACTIONS = {"create", "update", "delete", "terminate", "pay", "publish", "grant_admin"}

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        risk = 0
        reasons: list[str] = []

        if request.action in self.MUTATING_ACTIONS:
            risk += 2
            reasons.append("action changes external state")

        if request.action in self.HIGH_RISK_ACTIONS:
            risk += 5
            reasons.append("high-risk action")

        if request.payload.get("contains_personal_data"):
            risk += 3
            reasons.append("payload contains personal data")

        if request.payload.get("bulk"):
            risk += 3
            reasons.append("bulk operation")

        allowed = request.action not in {"disable_audit", "bypass_policy"}
        if not allowed:
            reasons.append("action is explicitly blocked")

        return PolicyDecision(
            risk=risk,
            requires_approval=risk >= 5,
            allowed=allowed,
            reasons=tuple(reasons),
        )


class OpsCopilot:
    def __init__(self, policy: ActionPolicy | None = None) -> None:
        self.policy = policy or ActionPolicy()
        self.audit_log: list[dict[str, Any]] = []

    def run(
        self,
        request: ActionRequest,
        executor: Callable[[ActionRequest], Any],
        approved: bool = False,
    ) -> dict[str, Any]:
        decision = self.policy.evaluate(request)

        if not decision.allowed:
            return self._record(request, decision, "blocked", None)

        if decision.requires_approval and not approved:
            return self._record(request, decision, "approval_required", None)

        result = executor(request)
        return self._record(request, decision, "executed", result)

    def _record(
        self,
        request: ActionRequest,
        decision: PolicyDecision,
        status: str,
        result: Any,
    ) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": request.action,
            "target": request.target,
            "risk": decision.risk,
            "reasons": list(decision.reasons),
            "status": status,
            "result": result,
        }
        self.audit_log.append(event)
        return event


if __name__ == "__main__":
    copilot = OpsCopilot()
    request = ActionRequest("update", "crm/contact/42", {"field": "status"})
    print(copilot.run(request, lambda r: {"updated": r.target}))
