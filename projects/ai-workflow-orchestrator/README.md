# AI Workflow Orchestrator

A small, inspectable workflow engine for AI-enabled operations.

It demonstrates patterns that matter in production agent systems: dependency ordering, retries, approval gates, shared state, and explicit execution results.

## Why this exists

LLMs are useful at planning and generating structured actions, but execution should still happen inside a deterministic control layer. This project shows that separation.

## Features

- Register named actions instead of executing arbitrary model-generated code
- Declare step dependencies
- Retry transient failures
- Require explicit approval for selected steps
- Pass shared context between steps
- Return structured status for every step

## Run

```bash
python projects/ai-workflow-orchestrator/orchestrator.py
python projects/ai-workflow-orchestrator/test_orchestrator.py
```

## Example use cases

- AI-assisted operations workflows
- Ticket / request routing
- Multi-step API automations
- Agent plans that require human approval before side effects

The demo intentionally uses only the Python standard library.
