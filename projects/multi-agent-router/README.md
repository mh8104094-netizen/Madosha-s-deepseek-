# Multi-Agent Router

A deterministic router that selects an agent based on required capabilities, reliability, cost, and latency constraints.

The point is not to pretend routing needs an LLM. The router keeps model selection explainable and testable while allowing an AI system to use different specialist workers.

## Demonstrates

- capability-based dispatch
- budget and latency constraints
- reliability-weighted scoring
- explicit failure when no worker can satisfy a task

```bash
python projects/multi-agent-router/router.py
python projects/multi-agent-router/test_router.py
```
