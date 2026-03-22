"""
AFMX Webhook Notifier

Fires HTTP POST requests to a configured URL when specific AFMX events occur.
Fully async, non-blocking — a webhook failure NEVER affects execution.

Configuration (environment variables):
  AFMX_WEBHOOK_URL            — target URL (required to enable webhooks)
  AFMX_WEBHOOK_EVENTS         — comma-separated list of event types to fire on
                                 default: execution.completed,execution.failed
  AFMX_WEBHOOK_SECRET         — optional HMAC-SHA256 signing secret
  AFMX_WEBHOOK_TIMEOUT_SECONDS— HTTP timeout per delivery (default: 10s)
  AFMX_WEBHOOK_RETRIES        — number of delivery retries (default: 3)

Payload format (JSON POST body):
  {
    "event": "execution.completed",
    "execution_id": "...",
    "matrix_id": "...",
    "matrix_name": "...",
    "status": "COMPLETED",
    "timestamp": 1712345678.0,
    "data": { ... }   // original AFMXEvent.data
  }

If AFMX_WEBHOOK_SECRET is set, a header X-AFMX-Signature is included:
  X-AFMX-Signature: sha256=<hex_digest>
  where the digest is HMAC-SHA256 of the raw JSON body using the secret.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """
    Subscribes to the AFMX EventBus and fires HTTP POST webhooks.

    Usage:
        notifier = WebhookNotifier(
            url="https://your-server/afmx-webhook",
            events=["execution.completed", "execution.failed"],
            secret="your-signing-secret",
        )
        notifier.attach_to_event_bus(event_bus)
    """

    def __init__(
        self,
        url: str,
        events: Optional[List[str]] = None,
        secret: Optional[str] = None,
        timeout_seconds: float = 10.0,
        retries: int = 3,
    ):
        self._url = url
        self._events: Set[str] = set(
            events or ["execution.completed", "execution.failed"]
        )
        self._secret = secret
        self._timeout = timeout_seconds
        self._retries = max(1, retries)
        self._client = None

    def attach_to_event_bus(self, bus) -> None:
        """Wire to the AFMX EventBus — called once at startup."""
        bus.subscribe_all(self._on_event)
        logger.info(
            f"[Webhook] Attached notifier → {self._url} "
            f"events={sorted(self._events)}"
        )

    async def _on_event(self, event) -> None:
        """EventBus callback — filters events and fires webhook."""
        if event.type.value not in self._events:
            return

        payload = {
            "event":        event.type.value,
            "execution_id": event.execution_id,
            "matrix_id":    event.matrix_id,
            "timestamp":    event.timestamp,
            "data":         event.data,
        }

        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent":   "AFMX-Webhook/1.0",
            "X-AFMX-Event": event.type.value,
        }

        if self._secret:
            sig = hmac.new(
                self._secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-AFMX-Signature"] = f"sha256={sig}"

        await self._deliver(body, headers, event.type.value)

    async def _deliver(self, body: bytes, headers: dict, event_name: str) -> None:
        """Attempt delivery with exponential backoff. Errors are logged, not raised."""
        try:
            import httpx
        except ImportError:
            logger.warning(
                "[Webhook] httpx not installed — webhooks disabled. "
                "Install: pip install httpx"
            )
            return

        client = await self._get_client()
        last_exc = None

        for attempt in range(1, self._retries + 1):
            try:
                resp = await client.post(
                    self._url,
                    content=body,
                    headers=headers,
                    timeout=self._timeout,
                )
                if resp.status_code < 300:
                    logger.debug(
                        f"[Webhook] ✅ {event_name} delivered "
                        f"(status={resp.status_code} attempt={attempt})"
                    )
                    return
                logger.warning(
                    f"[Webhook] ⚠️ {event_name} → {resp.status_code} "
                    f"(attempt {attempt}/{self._retries})"
                )
                last_exc = Exception(f"HTTP {resp.status_code}")
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"[Webhook] ⚠️ {event_name} delivery error "
                    f"(attempt {attempt}/{self._retries}): {exc}"
                )

            if attempt < self._retries:
                import asyncio
                await asyncio.sleep(2 ** (attempt - 1))

        logger.error(
            f"[Webhook] ❌ {event_name} delivery failed after "
            f"{self._retries} attempts: {last_exc}"
        )

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient()
        return self._client
