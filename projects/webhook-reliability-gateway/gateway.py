from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Callable


@dataclass
class Delivery:
    event_id: str
    attempts: int = 0
    status: str = "pending"
    last_error: str | None = None


class WebhookGateway:
    """Tiny reliability layer for authenticated, idempotent webhook processing."""

    def __init__(self, secret: str, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.secret = secret.encode()
        self.max_attempts = max_attempts
        self.processed: set[str] = set()
        self.dead_letter: list[Delivery] = []

    def sign(self, body: bytes) -> str:
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def verify(self, body: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(body), signature)

    def handle(
        self,
        event_id: str,
        body: bytes,
        signature: str,
        handler: Callable[[bytes], None],
    ) -> Delivery:
        if not self.verify(body, signature):
            return Delivery(event_id, status="rejected", last_error="invalid signature")

        if event_id in self.processed:
            return Delivery(event_id, status="duplicate")

        delivery = Delivery(event_id)
        for attempt in range(1, self.max_attempts + 1):
            delivery.attempts = attempt
            try:
                handler(body)
                delivery.status = "processed"
                delivery.last_error = None
                self.processed.add(event_id)
                return delivery
            except Exception as exc:  # gateway records handler failures; caller owns observability
                delivery.last_error = str(exc)

        delivery.status = "dead_letter"
        self.dead_letter.append(delivery)
        return delivery

    @staticmethod
    def backoff_seconds(attempt: int) -> int:
        if attempt < 1:
            raise ValueError("attempt must be positive")
        return min(2 ** (attempt - 1), 60)


if __name__ == "__main__":
    gateway = WebhookGateway("demo-secret")
    body = b'{"type":"ticket.created"}'
    print(gateway.handle("evt_1", body, gateway.sign(body), lambda payload: print(payload.decode())))
