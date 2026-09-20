from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from gateway import WebhookGateway  # noqa: E402


def test_signature_and_idempotency():
    gateway = WebhookGateway("secret")
    body = b"hello"
    signature = gateway.sign(body)
    calls = []

    first = gateway.handle("evt-1", body, signature, lambda value: calls.append(value))
    second = gateway.handle("evt-1", body, signature, lambda value: calls.append(value))

    assert first.status == "processed"
    assert second.status == "duplicate"
    assert calls == [body]


def test_invalid_signature_is_rejected():
    gateway = WebhookGateway("secret")
    result = gateway.handle("evt-2", b"hello", "bad", lambda _: None)
    assert result.status == "rejected"
    assert result.attempts == 0


def test_retries_then_dead_letters():
    gateway = WebhookGateway("secret", max_attempts=3)
    body = b"event"

    def broken(_):
        raise RuntimeError("downstream unavailable")

    result = gateway.handle("evt-3", body, gateway.sign(body), broken)
    assert result.status == "dead_letter"
    assert result.attempts == 3
    assert len(gateway.dead_letter) == 1
    assert gateway.backoff_seconds(4) == 8


if __name__ == "__main__":
    test_signature_and_idempotency()
    test_invalid_signature_is_rejected()
    test_retries_then_dead_letters()
    print("webhook-reliability-gateway: ok")
