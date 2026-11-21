"""A small async client for ptashka's REST API, authenticated with a personal API token.

The MCP server talks to ptashka exactly like any other client: over HTTP, with a token. It never
imports backend code, so an agent gets precisely the permissions of its token and board role, and
the backend stays the single place where rules are enforced.
"""

from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

TIMEOUT = httpx.Timeout(15.0)


def _message(detail: Any, fallback: str) -> str:
    """The API's `detail` comes as a string, an object with `message`, or a list of 422 field errors."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"]
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):
        first = detail[0]
        where = ".".join(str(p) for p in first.get("loc", [])[1:])
        return f"{where}: {first.get('msg')}" if where else str(first.get("msg"))
    return fallback


def _explain(status: int, message: str) -> str:
    """Turn an API error into something an agent can act on: what happened, and what to do next.

    Only ToolError messages reach the model (any other exception becomes a bare "Error executing
    tool"), so every API failure is converted here.
    """
    if status == 401:
        return f"Authentication failed ({message}). The API token is invalid, expired or revoked; ask the user for a new one."
    if status == 403 and message == "This API token is read-only":
        return "This API token is read-only: it can look but not change anything."
    if status == 403:
        return f"Not allowed: {message}. Your role on this board doesn't permit it."
    if status == 404:
        return f"{message}. It doesn't exist, or it's on a board you aren't a member of."
    if status == 409:
        return f"{message}. Someone changed it since you read it: call get_card for the latest version, then retry."
    if status == 422:
        return f"Invalid request: {message}"
    return f"ptashka API error {status}: {message}"


class PtashkaApi:
    def __init__(self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
            transport=transport,
        )

    async def request(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = await self._client.request(method, path, json=json, params=query)
        except httpx.HTTPError as e:
            raise ToolError(f"Could not reach ptashka at {self._client.base_url}: {e}") from e
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = None
            raise ToolError(_explain(response.status_code, _message(detail, response.reason_phrase)))
        return None if response.status_code == 204 else response.json()

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Any = None) -> Any:
        return await self.request("POST", path, json=body)

    async def patch(self, path: str, body: Any) -> Any:
        return await self.request("PATCH", path, json=body)

    async def put(self, path: str) -> Any:
        return await self.request("PUT", path)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def aclose(self) -> None:
        await self._client.aclose()
