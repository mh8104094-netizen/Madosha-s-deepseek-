from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from copilot import ActionRequest, OpsCopilot  # noqa: E402


def test_low_risk_action_executes():
    copilot = OpsCopilot()
    event = copilot.run(ActionRequest("read", "tickets/7"), lambda _: "ok")
    assert event["status"] == "executed"
    assert event["result"] == "ok"


def test_high_risk_action_requires_approval():
    copilot = OpsCopilot()
    request = ActionRequest("pay", "invoice/99", {"amount": 1200})
    event = copilot.run(request, lambda _: "paid")
    assert event["status"] == "approval_required"

    approved = copilot.run(request, lambda _: "paid", approved=True)
    assert approved["status"] == "executed"
    assert approved["result"] == "paid"


def test_blocked_action_never_executes():
    called = False

    def executor(_):
        nonlocal called
        called = True

    event = OpsCopilot().run(ActionRequest("bypass_policy", "system"), executor, approved=True)
    assert event["status"] == "blocked"
    assert not called


if __name__ == "__main__":
    test_low_risk_action_executes()
    test_high_risk_action_requires_approval()
    test_blocked_action_never_executes()
    print("ai-ops-copilot: ok")
