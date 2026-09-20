import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("orchestrator.py")
spec = importlib.util.spec_from_file_location("orchestrator", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

Orchestrator = module.Orchestrator
Step = module.Step
WorkflowError = module.WorkflowError


class OrchestratorTests(unittest.TestCase):
    def test_dependency_and_context_flow(self):
        engine = Orchestrator()
        engine.register("seed", lambda inputs, context: inputs["value"])
        engine.register("double", lambda inputs, context: context[inputs["source"]] * 2)

        results = engine.run([
            Step(name="first", action="seed", inputs={"value": 21}),
            Step(name="second", action="double", inputs={"source": "first"}, depends_on=("first",)),
        ])

        self.assertEqual(results["second"].output, 42)
        self.assertEqual(results["second"].status, "succeeded")

    def test_approval_gate(self):
        engine = Orchestrator()
        engine.register("side_effect", lambda inputs, context: "executed")
        results = engine.run([
            Step(name="send", action="side_effect", requires_approval=True)
        ])
        self.assertEqual(results["send"].status, "awaiting_approval")

    def test_retry(self):
        engine = Orchestrator()
        attempts = {"count": 0}

        def flaky(inputs, context):
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise RuntimeError("temporary")
            return "ok"

        engine.register("flaky", flaky)
        results = engine.run([Step(name="job", action="flaky", retries=1)])
        self.assertEqual(results["job"].status, "succeeded")
        self.assertEqual(results["job"].attempts, 2)

    def test_cycle_is_detected(self):
        engine = Orchestrator()
        engine.register("noop", lambda inputs, context: None)
        with self.assertRaises(WorkflowError):
            engine.run([
                Step(name="a", action="noop", depends_on=("b",)),
                Step(name="b", action="noop", depends_on=("a",)),
            ])


if __name__ == "__main__":
    unittest.main()
