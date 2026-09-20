# Prompt Injection Firewall

A small, explainable screening layer for untrusted text entering an LLM workflow.

It normalizes input, applies weighted defensive rules, and returns both a verdict and the signals that caused it. This is intentionally not presented as a complete security product; it demonstrates defense-in-depth and inspectable guardrail design.

## Verdicts

- `allow` — no meaningful risk signals
- `review` — suspicious input that should receive extra controls
- `block` — multiple strong injection / exfiltration signals

```bash
python projects/prompt-injection-firewall/firewall.py
python projects/prompt-injection-firewall/test_firewall.py
```
