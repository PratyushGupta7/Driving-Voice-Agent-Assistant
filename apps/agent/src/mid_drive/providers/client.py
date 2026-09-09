from __future__ import annotations

import asyncio

import httpx

USER_AGENT = "Mid-Drive/0.1 (DataForge prototype; voice mission agent)"


def headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-IN,en;q=0.9",
    }


def client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers=headers())


async def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float,
    params: dict | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(2):
        try:
            async with client(timeout) as http:
                response = await http.request(method, url, params=params, content=content)
            if response.status_code in {429, 502, 503, 504} and attempt == 0:
                await asyncio.sleep(0.35)
                continue
            response.raise_for_status()
            return response
        except Exception as exc:
            last = exc
            if attempt == 0:
                await asyncio.sleep(0.35)
                continue
            raise
    raise last or RuntimeError("request_failed")
