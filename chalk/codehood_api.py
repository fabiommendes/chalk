"""
Minimal client of the Codehood REST API, on the standard library.

Every course lives under `/api/course/<discipline>/<instructor>_<edition>/`
and every request carries the key as a bearer token.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["ApiError", "CodehoodClient"]

#: Seconds before a request gives up.
TIMEOUT = 30


class ApiError(RuntimeError):
    """
    The server refused a request or could not be reached.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CodehoodClient:
    """
    Requests to one course of a Codehood server.

    The key is sent only in the Authorization header and never shows up in
    error messages.
    """

    def __init__(self, url: str, discipline: str, course: str, key: str) -> None:
        self.base = f"{url.rstrip('/')}/api/course/{discipline}/{course}/"
        self._key = key

    def get(self, path: str, **query: str | bool | Sequence[str] | None) -> Any:
        return self.request("GET", path, query=query)

    def put(self, path: str, body: Mapping[str, Any]) -> Any:
        return self.request("PUT", path, body=body)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | bool | Sequence[str] | None] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        """
        Send a request and return the decoded JSON of the answer.

        Raises:
            ApiError: the server answered with an error status or is unreachable.
        """
        url = self.base + path.lstrip("/")
        if params := _query(query or {}):
            url += "?" + urllib.parse.urlencode(params)
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self._key}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                text = response.read().decode()
        except urllib.error.HTTPError as e:
            raise ApiError(f"{method} {path}: {_reason(e)}", e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"{method} {path}: cannot reach {self.base}: {e}") from None
        return json.loads(text) if text else None


def _query(query: Mapping[str, str | bool | Sequence[str] | None]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    for name, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            params.append((name, "true" if value else "false"))
        elif isinstance(value, str):
            params.append((name, value))
        else:
            params.extend((name, item) for item in value)
    return params


def _reason(error: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(error.read().decode())
        return f"{error.code} {data.get('message') or data.get('code')}"
    except (ValueError, AttributeError):
        return f"{error.code} {error.reason}"
