"""One interface, two vendors, plain REST.

Both providers do the same thing here: take a system prompt, a user prompt and a JSON
schema, and return a parsed dict. That is the entire surface the AI features need, and it
is one HTTP call in each case — so this speaks REST rather than carrying two vendor SDKs
whose abstractions would then have to be reconciled. It also keeps the request payload
visible in the source, which matters when the thing being generated is SQL that a reviewer
is invited to audit.

**Structured output is the whole design.** BUILD_PLAN section 6 says to prefill the
assistant turn to force clean JSON, which is an Anthropic technique. Gemini has no prefill;
`responseSchema` is its replacement and is strictly stronger — it constrains decoding
rather than nudging it, so the response parses with no cleanup step and no "strip the
```json fence" helper. Anthropic's equivalent is a single forced tool call, used below for
the same reason.

**Failure is a value, not a crash.** Everything here raises `AiUnavailableError`, which callers
turn into `{available: false, reason: ...}` with HTTP 200. A demo cannot show a stack
trace, and an AI panel that 500s takes the page down with it.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings

log = logging.getLogger(__name__)

#: Generous on purpose. Gemini 3.x reasons before answering and the thinking tokens come
#: out of this budget, so a tight ceiling returns HTTP 200 with an empty candidate rather
#: than an error — which reads as "the model had nothing to say" and is very hard to debug.
MAX_OUTPUT_TOKENS = 8192

#: Long enough for a reasoning model, short enough that a hung call does not hold a request
#: worker for the length of a demo.
TIMEOUT_SECONDS = 60.0

#: One retry only. A second failure is a real outage, and the caller has a cached or
#: degraded path that is better than making the user wait through another backoff.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_BACKOFF_SECONDS = 2.0


class AiUnavailableError(RuntimeError):
    """The provider could not answer. The message is written to be shown to a user."""


@dataclass(frozen=True, slots=True)
class Completion:
    """A parsed structured response plus what it cost, for the API to echo."""

    data: dict[str, Any]
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AiProvider(Protocol):
    """What the AI features depend on. Deliberately one method wide."""

    name: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
    ) -> Completion: ...


def _post_with_retry(url: str, *, headers: dict[str, str], payload: dict[str, Any]) -> Any:
    last_status: int | None = None
    for attempt in (1, 2):
        try:
            response = httpx.post(
                url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS
            )
        except httpx.TimeoutException as exc:
            raise AiUnavailableError(
                f"The model did not respond within {TIMEOUT_SECONDS:.0f}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise AiUnavailableError(f"Could not reach the model: {exc}") from exc

        if response.status_code == 200:
            return response.json()

        last_status = response.status_code
        if response.status_code in RETRY_STATUSES and attempt == 1:
            log.warning("AI call got %s, retrying once", response.status_code)
            time.sleep(RETRY_BACKOFF_SECONDS)
            continue
        break

    raise AiUnavailableError(_explain_status(last_status or 0, _detail(response)))


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("message", ""))[:300]
    except ValueError:
        pass
    return response.text[:300]


def _explain_status(status: int, detail: str) -> str:
    """Turn a status code into something a user can act on.

    404 and 429 are not hypothetical here: probing this key found `gemini-2.5-flash`
    returning 404 "no longer available to new users" and every `pro` model returning 429,
    so both messages name the likely cause rather than echoing the code.
    """
    if status == 401 or status == 403:
        return "The AI API key was rejected. Check GOOGLE_API_KEY / ANTHROPIC_API_KEY."
    if status == 404:
        return (
            "That model is not available to this API key. Set MODEL_REASONING / MODEL_BULK "
            f"to a model the key can call. ({detail})"
        )
    if status == 429:
        return (
            "The AI provider's rate limit or free-tier quota is exhausted. Cached answers "
            "still work; new ones will not until it resets."
        )
    if status >= 500:
        return "The AI provider is having problems. This is their side, not yours."
    return f"The AI provider refused the request ({status}). {detail}"


class GeminiProvider:
    """Google Generative Language REST API.

    `responseMimeType` + `responseSchema` together are what make the output parseable
    without a cleanup step: the decoder is constrained to the schema rather than asked
    politely to follow it.
    """

    name = "gemini"
    _base = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
    ) -> Completion:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
                "responseSchema": _to_gemini_schema(schema),
            },
        }
        body = _post_with_retry(
            f"{self._base}/{model}:generateContent",
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            payload=payload,
        )

        text = _first_gemini_text(body)
        usage = body.get("usageMetadata", {}) or {}
        return Completion(
            data=_parse_json(text),
            model=model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )


def _first_gemini_text(body: dict[str, Any]) -> str:
    """Extract the response text, treating "200 with nothing in it" as a failure.

    A reasoning model that exhausts `maxOutputTokens` on thinking returns a candidate with
    no parts and `finishReason: MAX_TOKENS`. Returning "" here would surface as an empty
    answer instead of a problem, so it is raised.
    """
    candidates = body.get("candidates") or []
    if not candidates:
        block = (body.get("promptFeedback") or {}).get("blockReason")
        raise AiUnavailableError(
            f"The model returned no answer (blocked: {block})."
            if block
            else "The model returned no answer."
        )

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts)
    if not text.strip():
        reason = candidate.get("finishReason", "unknown")
        if reason == "MAX_TOKENS":
            raise AiUnavailableError(
                "The model spent its whole output budget reasoning and returned nothing. "
                "Raise MAX_OUTPUT_TOKENS or simplify the question."
            )
        raise AiUnavailableError(f"The model returned an empty answer (finishReason: {reason}).")
    return text


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip JSON Schema keywords the Gemini schema dialect rejects.

    It accepts a subset — `type`, `properties`, `items`, `required`, `enum`, `description`,
    `nullable`. Passing `additionalProperties` or `$schema` is a 400, so unknown keys are
    dropped here rather than every call site having to remember.
    """
    allowed = {"type", "properties", "items", "required", "enum", "description", "nullable"}
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in allowed:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _to_gemini_schema(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = _to_gemini_schema(value)
        else:
            out[key] = value
    return out


class AnthropicProvider:
    """Claude Messages API, using a single forced tool call as the structured-output path.

    A tool with the response schema as its input schema, plus `tool_choice` naming it, is
    Anthropic's equivalent of Gemini's `responseSchema`: the model must emit an input
    object matching the schema, so the result is parsed rather than scraped.
    """

    name = "anthropic"
    _url = "https://api.anthropic.com/v1/messages"
    _version = "2023-06-01"
    _tool_name = "respond"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
    ) -> Completion:
        payload = {
            "model": model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": self._tool_name,
                    "description": "Return the answer in this exact shape.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": self._tool_name},
        }
        body = _post_with_retry(
            self._url,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._version,
                "Content-Type": "application/json",
            },
            payload=payload,
        )

        for block in body.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == self._tool_name:
                usage = body.get("usage", {}) or {}
                return Completion(
                    data=dict(block.get("input") or {}),
                    model=model,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
        raise AiUnavailableError("The model did not return a structured answer.")


def _parse_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AiUnavailableError(f"The model's answer was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiUnavailableError("The model's answer was not a JSON object.")
    return parsed


def get_provider() -> AiProvider | None:
    """The configured provider, or None when the AI layer is switched off.

    None is a supported state, not an error: the whole product works without a key, and
    every AI route reports `available: false` rather than failing.
    """
    key = settings.ai_api_key
    if not key:
        return None
    provider = settings.resolved_ai_provider
    if provider == "gemini":
        return GeminiProvider(key)
    if provider == "anthropic":
        return AnthropicProvider(key)
    return None
