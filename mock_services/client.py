from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import httpx


class MockBillingClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def preview_refund(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict:
        return await self._request(
            "POST",
            "/billing/refunds/preview",
            json={
                "payment_id": str(payment_id),
                "amount": str(amount),
                "idempotency_key": idempotency_key,
            },
        )

    async def execute_refund(
        self,
        *,
        payment_id: UUID,
        amount: Decimal,
        idempotency_key: str,
    ) -> dict:
        return await self._request(
            "POST",
            "/billing/refunds",
            json={
                "payment_id": str(payment_id),
                "amount": str(amount),
                "idempotency_key": idempotency_key,
            },
        )

    async def get_refund(self, idempotency_key: str) -> dict:
        return await self._request(
            "GET",
            f"/billing/refunds/{idempotency_key}",
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        client = self._client or httpx.AsyncClient()
        owns = self._client is None
        try:
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response.json()
        finally:
            if owns:
                await client.aclose()


__all__ = ["MockBillingClient"]
