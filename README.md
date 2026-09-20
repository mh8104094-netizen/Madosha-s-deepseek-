# Mohamed Hassan Shehata — AI-Native Builder

> I build practical AI systems, automation, agents, retrieval tools, and reliable backend workflows.

I work **AI-first**: I use modern AI tools as an engineering multiplier to move quickly from an idea to working software, while keeping the result understandable, testable, and reviewable.

## Engineering portfolio

| Project | What it demonstrates | Core ideas |
|---|---|---|
| [AI Workflow Orchestrator](projects/ai-workflow-orchestrator) | Reliable multi-step automation | DAG execution, retries, approvals, state |
| [Mini RAG Engine](projects/mini-rag-engine) | Retrieval without framework magic | Chunking, TF-IDF, cosine ranking |
| [Agent Eval Harness](projects/agent-eval-harness) | Repeatable AI behavior testing | Assertions, structured outputs, tool checks |
| [AI Ops Copilot](projects/ai-ops-copilot) | Safe AI-to-action workflows | Risk scoring, policy gates, approvals, audit log |
| [Prompt Injection Firewall](projects/prompt-injection-firewall) | Defensive input screening | Normalization, heuristics, risk signals, explainability |
| [Multi-Agent Router](projects/multi-agent-router) | Intelligent task routing | Capability matching, reliability, cost, latency |
| [Webhook Reliability Gateway](projects/webhook-reliability-gateway) | Production-style event handling | HMAC verification, idempotency, retries, DLQ |

## What a reviewer can verify

- Every portfolio project contains runnable code.
- Every project includes tests.
- GitHub Actions runs the complete portfolio test suite.
- The projects intentionally minimize dependencies so the important logic is easy to inspect.
- Safety-sensitive actions use explicit policy and human-approval boundaries instead of blindly executing model output.

## How I build with AI

I do not hide the fact that AI is part of my workflow. I treat it the same way strong engineering teams treat compilers, frameworks, code search, and automation: as leverage.

My focus is on the parts that still require engineering judgment:

1. Breaking problems into clear systems and interfaces.
2. Defining constraints, failure modes, and approval boundaries.
3. Connecting AI to APIs, workflows, data, and business operations.
4. Testing behavior instead of trusting a generated answer.
5. Keeping implementations simple enough to understand and maintain.

## Run everything

```bash
for test in projects/*/test_*.py; do python "$test"; done
```

No API keys are required for the portfolio examples.

## Current interests

AI agents · workflow automation · RAG · API integrations · operations tooling · evaluation · guardrails · event-driven systems

---

### About this repository

This repository is used as my public AI engineering portfolio workspace. Historical DeepSeek reference material from the repository's earlier state is **not presented as my original work**. The projects under `projects/` are portfolio implementations created to demonstrate my engineering approach.
