# Webhook Reliability Gateway

A compact event-processing reliability layer with features that show up in real integrations:

- HMAC-SHA256 signature verification
- idempotency / duplicate suppression
- bounded retries
- exponential backoff calculation
- dead-letter handling

```bash
python projects/webhook-reliability-gateway/gateway.py
python projects/webhook-reliability-gateway/test_gateway.py
```
