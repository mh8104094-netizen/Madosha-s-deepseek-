from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


Action = Callable[[dict[str, Any], dict[str, Any]], Any]


@dataclass(frozen=True)
class Step:
    name: str
    action: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    requires_approval: bool = False


@dataclass
class StepResult:
    status: str
    output: Any = None
    attempts: int = 0
    error: str | None = None


class WorkflowError(RuntimeError):
    pass


class Orchestrator:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    def register(self, name: str, action: Action) -> None:
        if not name or not callable(action):
            raise ValueError("Action name and callable are required")
        self._actions[name] = action

    def run(
        self,
        steps: list[Step],
        context: dict[str, Any] | None = None,
        approvals: set[str] | None = None,
    ) -> dict[str, StepResult]:
        context = dict(context or {})
        approvals = set(approvals or set())
        results: dict[str, StepResult] = {}
        pending = {step.name: step for step in steps}

        if len(pending) != len(steps):
            raise WorkflowError("Step names must be unique")

        while pending:
            progressed = False

            for name, step in list(pending.items()):
                missing = [dep for dep in step.depends_on if dep not in results]
                if missing:
                    continue

                failed_deps = [
                    dep for dep in step.depends_on if results[dep].status != "succeeded"
                ]
                if failed_deps:
                    results[name] = StepResult(
                        status="blocked",
                        error=f"Failed dependencies: {', '.join(failed_deps)}",
                    )
                    del pending[name]
                    progressed = True
                    continue

                if step.requires_approval and name not in approvals:
                    results[name] = StepResult(
                        status="awaiting_approval",
                        error="Explicit approval required",
                    )
                    del pending[name]
                    progressed = True
                    continue

                action = self._actions.get(step.action)
                if action is None:
                    results[name] = StepResult(
                        status="failed", error=f"Unknown action: {step.action}"
                    )
                    del pending[name]
                    progressed = True
                    continue

                result = StepResult(status="failed")
                for attempt in range(1, step.retries + 2):
                    result.attempts = attempt
                    try:
                        output = action(dict(step.inputs), context)
                        result.status = "succeeded"
                        result.output = output
                        result.error = None
                        context[name] = output
                        break
                    except Exception as exc:  # control layer records failure explicitly
                        result.error = f"{type(exc).__name__}: {exc}"

                results[name] = result
                del pending[name]
                progressed = True

            if not progressed:
                unresolved = ", ".join(sorted(pending))
                raise WorkflowError(
                    f"Workflow cannot progress. Check cyclic or missing dependencies: {unresolved}"
                )

        return results


def render_message(inputs: dict[str, Any], context: dict[str, Any]) -> str:
    template = str(inputs.get("template", ""))
    values = {**context, **inputs.get("values", {})}
    return template.format_map(values)


def uppercase(inputs: dict[str, Any], context: dict[str, Any]) -> str:
    source_step = str(inputs["source_step"])
    return str(context[source_step]).upper()


if __name__ == "__main__":
    engine = Orchestrator()
    engine.register("render_message", render_message)
    engine.register("uppercase", uppercase)

    workflow = [
        Step(
            name="draft",
            action="render_message",
            inputs={"template": "AI workflow ready for {team}", "values": {"team": "ops"}},
        ),
        Step(
            name="publish_preview",
            action="uppercase",
            inputs={"source_step": "draft"},
            depends_on=("draft",),
            requires_approval=True,
        ),
    ]

    for step_name, result in engine.run(workflow, approvals={"publish_preview"}).items():
        print(f"{step_name}: {result.status} -> {result.output}")
