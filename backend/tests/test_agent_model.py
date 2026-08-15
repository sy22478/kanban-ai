"""The OpenRouter client: what it sends, and what it makes of what comes back.

The reply parser is reading a third party's JSON, so it is treated as untrusted
input like any other. The transport is stubbed rather than reached.
"""

import json

import httpx
import pytest

from app.agent import model as model_module
from app.agent.model import (
    ModelError,
    OpenRouterClient,
    parse_reply,
)
from app.config import OPENROUTER_MODEL

KEY = "sk-or-not-a-real-key"


class StubResponse:
    def __init__(self, status_code=200, payload=None, text_body=None):
        self.status_code = status_code
        self._payload = payload
        self._text_body = text_body

    def json(self):
        if self._text_body is not None:
            raise json.JSONDecodeError("not json", self._text_body, 0)
        return self._payload


class StubAsyncClient:
    """Stands in for httpx.AsyncClient for one call."""

    sent = {}

    def __init__(self, response=None, error=None, **kwargs):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json, headers):
        type(self).sent = {"url": url, "json": json, "headers": headers}
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture
def stub_transport(monkeypatch):
    def install(response=None, error=None):
        StubAsyncClient.sent = {}

        def factory(**kwargs):
            return StubAsyncClient(response=response, error=error, **kwargs)

        monkeypatch.setattr(model_module.httpx, "AsyncClient", factory)
        return StubAsyncClient

    return install


class TestParseReply:
    def test_a_plain_answer(self):
        reply = parse_reply(
            {"choices": [{"message": {"role": "assistant", "content": "Hello"}}]}
        )
        assert reply.content == "Hello"
        assert reply.tool_calls == []

    def test_a_tool_call(self):
        reply = parse_reply(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-9",
                                    "type": "function",
                                    "function": {
                                        "name": "create_card",
                                        "arguments": '{"title": "x"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        )
        [call] = reply.tool_calls
        assert call.id == "call-9"
        assert call.name == "create_card"
        assert call.arguments_json == '{"title": "x"}'

    def test_the_raw_message_is_kept_verbatim(self):
        """It is appended to the conversation as-is.

        Rebuilding it by hand is how a tool_call_id stops matching and the next
        request is rejected by the provider.
        """
        message = {"role": "assistant", "content": "hi", "reasoning": "ignored"}
        reply = parse_reply({"choices": [{"message": message}]})
        assert reply.raw_message == message

    def test_no_choices_is_an_error(self):
        with pytest.raises(ModelError):
            parse_reply({"choices": []})

    def test_a_missing_choices_key_is_an_error(self):
        with pytest.raises(ModelError):
            parse_reply({})

    def test_a_tool_call_with_no_name_is_skipped(self):
        """Rather than becoming a call to a tool named None."""
        reply = parse_reply(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "1", "function": {"arguments": "{}"}},
                                {
                                    "id": "2",
                                    "function": {"name": "list_board", "arguments": "{}"},
                                },
                            ]
                        }
                    }
                ]
            }
        )
        assert [call.name for call in reply.tool_calls] == ["list_board"]

    def test_absent_arguments_become_an_empty_object(self):
        reply = parse_reply(
            {
                "choices": [
                    {"message": {"tool_calls": [{"id": "1", "function": {"name": "list_board"}}]}}
                ]
            }
        )
        assert reply.tool_calls[0].arguments_json == "{}"

    def test_a_missing_message_is_an_empty_reply(self):
        reply = parse_reply({"choices": [{}]})
        assert reply.content is None
        assert reply.tool_calls == []


class TestWhatIsSent:
    async def test_the_pinned_slug_is_the_one_requested(self, stub_transport):
        """CLAUDE.md: do not substitute another slug, ask.

        This is the tripwire for that rule. A slug was picked silently on the
        previous project and this makes the same mistake here go red instead of
        shipping.
        """
        stub = stub_transport(
            StubResponse(payload={"choices": [{"message": {"content": "ok"}}]})
        )
        await OpenRouterClient(KEY).complete([{"role": "user", "content": "hi"}], [])

        assert stub.sent["json"]["model"] == "deepseek/deepseek-v4-flash-0731"
        assert stub.sent["json"]["model"] == OPENROUTER_MODEL

    async def test_the_key_travels_as_a_bearer_token(self, stub_transport):
        stub = stub_transport(
            StubResponse(payload={"choices": [{"message": {"content": "ok"}}]})
        )
        await OpenRouterClient(KEY).complete([], [])

        assert stub.sent["headers"]["Authorization"] == f"Bearer {KEY}"


class TestUpstreamFailures:
    async def test_a_non_200_does_not_relay_the_upstream_body(self, stub_transport):
        """The upstream body can echo the request, and with it the board.

        It is also written for a developer reading provider logs rather than for
        this application's users, so the message here is fixed.
        """
        stub_transport(
            StubResponse(status_code=429, payload={"error": "rate limited, key sk-or-abc"})
        )

        with pytest.raises(ModelError) as raised:
            await OpenRouterClient(KEY).complete([], [])

        message = str(raised.value)
        assert "429" in message
        assert "sk-or-abc" not in message
        assert "rate limited" not in message

    async def test_a_timeout_is_a_model_error(self, stub_transport):
        stub_transport(error=httpx.TimeoutException("too slow"))

        with pytest.raises(ModelError) as raised:
            await OpenRouterClient(KEY).complete([], [])

        assert "too long" in str(raised.value)

    async def test_a_transport_failure_is_a_model_error(self, stub_transport):
        stub_transport(error=httpx.ConnectError("no route"))

        with pytest.raises(ModelError) as raised:
            await OpenRouterClient(KEY).complete([], [])

        assert "could not be reached" in str(raised.value)

    async def test_an_unreadable_body_is_a_model_error(self, stub_transport):
        stub_transport(StubResponse(status_code=200, text_body="<html>oops</html>"))

        with pytest.raises(ModelError) as raised:
            await OpenRouterClient(KEY).complete([], [])

        assert "unreadable" in str(raised.value)

    async def test_the_key_never_appears_in_an_error(self, stub_transport):
        """Whatever went wrong, the message shown to a user is not the key."""
        for error in (
            httpx.TimeoutException("boom"),
            httpx.ConnectError("boom"),
        ):
            stub_transport(error=error)
            with pytest.raises(ModelError) as raised:
                await OpenRouterClient(KEY).complete([], [])
            assert KEY not in str(raised.value)
