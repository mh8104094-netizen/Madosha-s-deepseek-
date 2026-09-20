# AI Ops Copilot

A deterministic safety layer for AI-generated operational actions.

Instead of letting a model directly mutate external systems, the copilot evaluates each requested action, assigns risk, requires human approval for sensitive operations, blocks forbidden actions, and records an audit event.

## Demonstrates

- policy-as-code
- risk scoring
- human approval gates
- explicit separation between planning and execution
- audit-friendly event records

```bash
python projects/ai-ops-copilot/copilot.py
python projects/ai-ops-copilot/test_copilot.py
```
