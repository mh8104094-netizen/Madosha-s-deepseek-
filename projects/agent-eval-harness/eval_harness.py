from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalCase:
    name: str
    output: dict[str, Any]
    required_keys: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    required_tool: str | None = None
    forbidden_phrases: tuple[str, ...] = ()
    expected_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalResult:
    name: str
    passed: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]


def evaluate(case: EvalCase) -> EvalResult:
    checks: list[str] = []
    failures: list[str] = []

    for key in case.required_keys:
        checks.append(f"required_key:{key}")
        if key not in case.output:
            failures.append(f"missing required key: {key}")

    tool = case.output.get("tool")
    if case.allowed_tools:
        checks.append("allowed_tool")
        if tool not in case.allowed_tools:
            failures.append(f"tool {tool!r} is not allowed")

    if case.required_tool is not None:
        checks.append("required_tool")
        if tool != case.required_tool:
            failures.append(
                f"expected tool {case.required_tool!r}, received {tool!r}"
            )

    serialized = str(case.output).lower()
    for phrase in case.forbidden_phrases:
        checks.append(f"forbidden_phrase:{phrase}")
        if phrase.lower() in serialized:
            failures.append(f"forbidden phrase found: {phrase}")

    for key, expected in case.expected_fields.items():
        checks.append(f"expected_field:{key}")
        if case.output.get(key) != expected:
            failures.append(
                f"field {key!r}: expected {expected!r}, got {case.output.get(key)!r}"
            )

    return EvalResult(
        name=case.name,
        passed=not failures,
        checks=tuple(checks),
        failures=tuple(failures),
    )


def pass_rate(results: list[EvalResult]) -> float:
    if not results:
        return 0.0
    return sum(result.passed for result in results) / len(results)


if __name__ == "__main__":
    cases = [
        EvalCase(
            name="routes support request",
            output={"tool": "create_ticket", "category": "support"},
            required_keys=("tool", "category"),
            allowed_tools=("create_ticket", "answer"),
            required_tool="create_ticket",
            expected_fields={"category": "support"},
        ),
        EvalCase(
            name="rejects unknown tool",
            output={"tool": "run_arbitrary_shell", "category": "support"},
            allowed_tools=("create_ticket", "answer"),
        ),
    ]

    results = [evaluate(case) for case in cases]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}: {', '.join(result.failures) or 'all checks passed'}")
    print(f"pass_rate={pass_rate(results):.0%}")
