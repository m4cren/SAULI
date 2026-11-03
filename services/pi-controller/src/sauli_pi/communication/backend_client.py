"""Minimal authenticated transport for the trusted Pi process."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DeviceApiError(Exception):
    pass


def request_json(origin: str, path: str, payload: dict, credential: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["Authorization"] = f"Device {credential}"
    request = Request(origin + path, data=json.dumps(payload).encode("utf-8"), headers=headers,
                      method="POST")
    try:
        with urlopen(request, timeout=8) as response:
            result = json.load(response)
            if not isinstance(result, dict):
                raise DeviceApiError("Invalid backend response")
            return result
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        # Do not log provider bodies, credentials, or bootstrap codes.
        raise DeviceApiError("Device API request failed") from exc
