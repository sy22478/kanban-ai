"""The call out to the model, and the shape of what comes back.

This module is the only thing in the application that talks to OpenRouter. It
knows nothing about boards, cards or users: it takes messages and tool
definitions, and returns what the model said. Keeping it that narrow is what
lets the whole tool-calling loop be tested against a fake without a network or a
bill.

The key is read from the backend environment and used here. It never appears in
a response body, and the `frontend` compose service is given no environment at
all, so there is no path from this process into the browser.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import (
    AGENT_TIMEOUT_SECONDS,
    OPENROUTER_MODEL,
    OPENROUTER_URL,
)


class ModelError(Exception):
    """The model could not be reached, or answered with something unusable.

    Carries a sentence fit to show a user. The underlying transport error is not
    folded into it: an upstream error body can contain anything, including the
    request that was sent.
    """


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    # The raw JSON string the model emitted, deliberately not parsed here. A
    # model can and does emit invalid JSON, and that is an ordinary event the
    # runner answers with a tool error the model can retry from, rather than an
    # exception that ends the turn.
    arguments_json: str


@dataclass(frozen=True)
class ModelReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # The assistant message exactly as it arrived, so the runner can append it to
    # the conversation verbatim. Reconstructing it by hand is how a tool_call_id
    # ends up not matching and the next request is rejected.
    raw_message: dict[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelReply: ...


def parse_reply(payload: dict[str, Any]) -> ModelReply:
    """Read an OpenAI-compatible chat completion.

    Tolerant about what is absent, strict about what it returns: every field is
    reached with .get so a provider that omits an optional key gives a reply with
    no tool calls rather than a KeyError five frames down.
    """
    choices = payload.get("choices") or []
    if not choices:
        raise ModelError("The model returned no response.")

    message = choices[0].get("message") or {}

    tool_calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        tool_calls.append(
            ToolCall(
                id=call.get("id") or "",
                name=name,
                arguments_json=function.get("arguments") or "{}",
            )
        )

    return ModelReply(
        content=message.get("content"),
        tool_calls=tool_calls,
        raw_message=message,
    )


class OpenRouterClient:
    def __init__(self, api_key: str, model: str = OPENROUTER_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelReply:
        body = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            # Let the model decide whether to call a tool. It has to be able to
            # answer "I cannot do that" in words, which "required" would forbid.
            "tool_choice": "auto",
        }

        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    OPENROUTER_URL,
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise ModelError("The model took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise ModelError("The model could not be reached.") from exc

        if response.status_code != 200:
            # The upstream body is deliberately not relayed. It can echo the
            # request, which contains the board's contents, and it is not written
            # for this application's users to read.
            raise ModelError(
                f"The model service answered {response.status_code}."
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ModelError("The model service answered with something unreadable.") from exc

        return parse_reply(payload)
