# Agent Eval Harness

A tiny evaluation framework for structured AI-agent outputs.

The goal is to turn "this response looks good" into repeatable checks that can run in CI.

## Checks included

- Required output keys
- Allowed tool selection
- Required tool selection
- Forbidden phrases
- Exact-field expectations
- Aggregate pass rate

## Run

```bash
python projects/agent-eval-harness/eval_harness.py
python projects/agent-eval-harness/test_eval_harness.py
```

This is intentionally model-provider agnostic: feed it captured JSON outputs from any agent or LLM stack.
