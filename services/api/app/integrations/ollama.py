"""Structured, bounded local Ollama gateway."""

import json
import logging
import re
from typing import TypeVar

import httpx
from ollama import AsyncClient, ResponseError
from pydantic import BaseModel, ValidationError

from app.core.errors import ServiceError

Model = TypeVar("Model", bound=BaseModel)
logger = logging.getLogger("sauli.ollama")


def first_json_object(value: str) -> dict:
    if not isinstance(value, str):
        raise ValueError("Expected text")
    cleaned = re.sub(r"```(?:json)?", "", value, flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    leading = cleaned.lstrip()
    if leading.startswith("{"):
        try:
            parsed, _ = decoder.raw_decode(leading)
        except json.JSONDecodeError as exc:
            raise ValueError("Incomplete top-level object") from exc
        if isinstance(parsed, dict):
            return parsed
    if leading.startswith("["):
        raise ValueError("Expected an object")
    for index, character in enumerate(cleaned):
        if character == "{":
            try:
                parsed, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("No complete JSON object")


def response_payload(response) -> dict:
    message = response.get("message", {}) if isinstance(response, dict) else response.message
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    thinking = message.get("thinking", "") if isinstance(message, dict) else getattr(message, "thinking", "")
    if isinstance(content, str) and content.strip():
        return first_json_object(content)
    if isinstance(thinking, str) and thinking.strip():
        return first_json_object(thinking)
    raise ValueError("Empty model response")


class OllamaGateway:
    def __init__(self, host: str, timeout: float):
        self.client = AsyncClient(host=host, timeout=timeout)

    async def list_model_names(self) -> list[str]:
        response = await self.client.list()
        return [model.model for model in response.models if model.model]

    async def structured(self, model: str, prompt: str, schema: type[Model], images: list[bytes] | None = None) -> Model:
        repair = ""
        for attempt in range(2):
            try:
                response = await self.client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt + repair, "images": images or []}],
                    format=schema.model_json_schema(),
                    think=False,
                    stream=False,
                    options={"temperature": 0, "num_ctx": 12288, "num_predict": 3072},
                )
            except ResponseError as exc:
                if exc.status_code == 404:
                    raise ServiceError("OLLAMA_MODEL_MISSING", "The configured local analysis model is not installed.", 503) from exc
                raise ServiceError("OLLAMA_UNAVAILABLE", "The local item-analysis service is unavailable. Please try again.", 503) from exc
            except (httpx.TimeoutException, TimeoutError) as exc:
                raise ServiceError("OLLAMA_TIMEOUT", "The local item-analysis service timed out. Please try again.", 504) from exc
            except (httpx.RequestError, ConnectionError, OSError) as exc:
                raise ServiceError("OLLAMA_UNAVAILABLE", "The local item-analysis service is unavailable. Please try again.", 503) from exc
            try:
                result = schema.model_validate_json(json.dumps(response_payload(response)), strict=True)
                return result
            except (ValueError, TypeError, AttributeError, ValidationError):
                logger.warning("Invalid structured response model=%s attempt=%s", schema.__name__, attempt + 1)
                if attempt:
                    raise ServiceError("MALFORMED_AI_RESPONSE", "The analysis did not return usable item details. Please try again.", 502) from None
                repair = "\n\nThe previous answer did not match the required schema. Return a fresh complete JSON object with every required field and no extra keys. Return JSON only."
        raise AssertionError("Unreachable")

    async def close(self) -> None:
        await self.client.close()
