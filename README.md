# AI Engineering Portfolio

> AI-native builder focused on automation, agentic workflows, retrieval systems, and reliable shipping.

I use AI as an engineering multiplier: to move faster from idea to working software while keeping the result inspectable, testable, and maintainable.

## What I build

- AI-assisted workflow automation
- Agent orchestration with explicit approvals and audit-friendly behavior
- Retrieval / knowledge search systems
- Evaluation harnesses for structured AI outputs
- API and operations tooling

## Featured projects

| Project | What it demonstrates | Stack |
|---|---|---|
| [AI Workflow Orchestrator](projects/ai-workflow-orchestrator) | Dependency-aware workflow execution, retries, human approval gates, deterministic state | Python stdlib |
| [Mini RAG Engine](projects/mini-rag-engine) | Chunking, TF-IDF retrieval, cosine ranking, explainable search results | Python stdlib |
| [Agent Eval Harness](projects/agent-eval-harness) | Repeatable evaluation of structured agent outputs and tool-selection behavior | Python stdlib |

## Engineering principles

1. **AI is a tool, not a black box.** Generated code still needs understandable architecture and tests.
2. **Make failure visible.** Workflows should fail explicitly and expose useful state.
3. **Prefer simple systems first.** These demos intentionally avoid heavy frameworks so the core ideas are easy to inspect.
4. **Design for humans in the loop.** Sensitive or irreversible actions should have explicit approval boundaries.
5. **Evaluate behavior, not vibes.** Agent outputs should be checked against concrete requirements.

## Run the portfolio tests

```bash
for test in projects/*/test_*.py; do python "$test"; done
```

Each project also includes its own README and runnable example.

## About this repository

This repository is now used as my public AI engineering portfolio workspace. Historical DeepSeek reference files remain in the git history / repository for attribution and are **not presented as my original work**. The portfolio projects under `projects/` are original demonstration projects created to show how I approach AI-enabled engineering.

---

**Current focus:** building practical AI systems that connect models to real workflows, data, APIs, validation, and human decision points.
