import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("eval_harness.py")
spec = importlib.util.spec_from_file_location("eval_harness", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

EvalCase = module.EvalCase
evaluate = module.evaluate
pass_rate = module.pass_rate


class EvalHarnessTests(unittest.TestCase):
    def test_good_output_passes(self):
        result = evaluate(EvalCase(
            name="good",
            output={"tool": "answer", "status": "ok"},
            required_keys=("tool", "status"),
            allowed_tools=("answer",),
            expected_fields={"status": "ok"},
        ))
        self.assertTrue(result.passed)

    def test_unknown_tool_fails(self):
        result = evaluate(EvalCase(
            name="bad tool",
            output={"tool": "delete_everything"},
            allowed_tools=("answer", "create_ticket"),
        ))
        self.assertFalse(result.passed)
        self.assertTrue(any("not allowed" in item for item in result.failures))

    def test_pass_rate(self):
        good = evaluate(EvalCase(name="good", output={"x": 1}, required_keys=("x",)))
        bad = evaluate(EvalCase(name="bad", output={}, required_keys=("x",)))
        self.assertEqual(pass_rate([good, bad]), 0.5)


if __name__ == "__main__":
    unittest.main()
