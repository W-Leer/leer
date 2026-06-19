"""Step 2 normalization tests:

  - Fix #3: cached_tokens canonical field across both providers + both
    OpenAI API styles.
  - Fix #4: malformed ``usage`` payload tolerance (list/string/None) in
    all three normalizers.

These tests live in their own module so the Step 2 hardening rules are
discoverable as a unit. They share the broader fixtures in
``test_normalize.py`` only by reusing identical request/response shapes
locally, to keep this file self-contained.
"""

from __future__ import annotations

from leer.integrations.normalize import (
    LLMUsage,
    NormalizedLLMCall,
    normalize_anthropic,
    normalize_openai,
)


# ---------------------------------------------------------------------------
# Fix #3 — cached_tokens canonical field
# ---------------------------------------------------------------------------

class TestCachedTokensOpenAIChat:

    def _request(self) -> dict:
        return {
            "model": "gpt-4.1",
            "messages": [
                {"role": "user", "content": "hi"},
            ],
        }

    def _response(self, *, cached: int | None) -> dict:
        usage: dict = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        }
        if cached is not None:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
        return {
            "id": "chatcmpl-cached-1",
            "model": "gpt-4.1",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hi back"},
                "finish_reason": "stop",
            }],
            "usage": usage,
        }

    def test_cached_tokens_extracted_when_reported(self):
        n = normalize_openai(self._request(), self._response(cached=42))
        assert n.usage.cached_tokens == 42
        assert n.usage.prompt_tokens == 100
        assert n.usage.completion_tokens == 20
        assert n.usage.total_tokens == 120

    def test_cached_tokens_absent_when_not_reported(self):
        n = normalize_openai(self._request(), self._response(cached=None))
        assert n.usage.cached_tokens is None

    def test_cached_tokens_zero_is_real_value(self):
        # Zero cached tokens means the provider reported the field but no
        # cache hit occurred. Distinguishable from ``None`` (not reported).
        n = normalize_openai(self._request(), self._response(cached=0))
        assert n.usage.cached_tokens == 0


class TestCachedTokensOpenAIResponses:

    def _request(self) -> dict:
        return {
            "model": "gpt-4.1",
            "instructions": "You are helpful.",
            "input": [{"role": "user", "content": "hi"}],
        }

    def _response(self, *, cached: int | None) -> dict:
        usage: dict = {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }
        if cached is not None:
            usage["input_tokens_details"] = {"cached_tokens": cached}
        return {
            "id": "resp-cached-1",
            "object": "response",
            "model": "gpt-4.1",
            "status": "completed",
            "output": [{
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi back"}],
            }],
            "usage": usage,
        }

    def test_cached_tokens_extracted_from_input_tokens_details(self):
        n = normalize_openai(self._request(), self._response(cached=33))
        assert n.usage.cached_tokens == 33

    def test_cached_tokens_absent_when_no_details_block(self):
        n = normalize_openai(self._request(), self._response(cached=None))
        assert n.usage.cached_tokens is None


class TestCachedTokensAnthropic:

    def _request(self) -> dict:
        return {
            "model": "claude-sonnet-4-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 200,
        }

    def _response(self, *, cache_read: int | None, cache_create: int | None = None) -> dict:
        usage: dict = {"input_tokens": 100, "output_tokens": 20}
        if cache_read is not None:
            usage["cache_read_input_tokens"] = cache_read
        if cache_create is not None:
            # Cache creation tokens are intentionally NOT mapped into the
            # canonical ``cached_tokens`` field. Test below asserts this.
            usage["cache_creation_input_tokens"] = cache_create
        return {
            "id": "msg-cached-1",
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "hi back"}],
            "stop_reason": "end_turn",
            "usage": usage,
        }

    def test_cache_read_input_tokens_maps_to_cached_tokens(self):
        n = normalize_anthropic(self._request(), self._response(cache_read=77))
        assert n.usage.cached_tokens == 77

    def test_cache_creation_input_tokens_not_mapped_to_cached(self):
        # Cache *creation* (write cost) is a different concept and stays
        # off the canonical field for cross-provider parity.
        n = normalize_anthropic(self._request(), self._response(cache_read=None, cache_create=500))
        assert n.usage.cached_tokens is None

    def test_cached_tokens_absent_when_not_reported(self):
        n = normalize_anthropic(self._request(), self._response(cache_read=None))
        assert n.usage.cached_tokens is None


class TestCachedTokensCanonicalShape:
    """Cross-provider parity for the cached_tokens canonical field."""

    def test_llm_usage_default_is_none(self):
        u = LLMUsage()
        assert u.cached_tokens is None
        # to_dict round-trip exposes the field for downstream consumers.
        assert "cached_tokens" in u.__dict__

    def test_all_three_normalizers_produce_same_usage_keyset(self):
        # Step 1's parity guarantee: usage shape is identical across
        # OpenAI chat, OpenAI Responses, and Anthropic. Step 2 must
        # preserve this with the new ``cached_tokens`` field.
        chat = normalize_openai(
            {"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
            {
                "id": "x", "model": "gpt-4.1",
                "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
        resp = normalize_openai(
            {"model": "gpt-4.1", "input": [{"role": "user", "content": "hi"}]},
            {
                "id": "x", "object": "response", "model": "gpt-4.1", "status": "completed",
                "output": [{
                    "type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi"}],
                }],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
        )
        anth = normalize_anthropic(
            {"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
            {
                "id": "x", "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "hi"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
        assert set(chat.usage.__dict__.keys()) == set(resp.usage.__dict__.keys())
        assert set(chat.usage.__dict__.keys()) == set(anth.usage.__dict__.keys())
        assert "cached_tokens" in chat.usage.__dict__


# ---------------------------------------------------------------------------
# Fix #4 — Malformed ``usage`` payload tolerance
# ---------------------------------------------------------------------------

class TestMalformedUsageOpenAIChat:

    def _request(self) -> dict:
        return {"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]}

    def _response(self, usage) -> dict:
        return {
            "id": "x", "model": "gpt-4.1",
            "choices": [{
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }],
            "usage": usage,
        }

    def test_usage_as_list_does_not_crash(self):
        n = normalize_openai(self._request(), self._response(usage=[1, 2, 3]))
        assert n.usage.prompt_tokens is None
        assert n.usage.completion_tokens is None
        assert n.usage.total_tokens is None
        assert n.usage.cached_tokens is None

    def test_usage_as_string_does_not_crash(self):
        n = normalize_openai(self._request(), self._response(usage="garbage"))
        assert n.usage.prompt_tokens is None

    def test_usage_as_int_does_not_crash(self):
        n = normalize_openai(self._request(), self._response(usage=42))
        assert n.usage.prompt_tokens is None

    def test_usage_missing_field_still_works(self):
        resp = self._response(usage={})
        n = normalize_openai(self._request(), resp)
        assert n.usage.prompt_tokens is None
        assert n.usage.cached_tokens is None


class TestMalformedUsageOpenAIResponses:

    def _request(self) -> dict:
        return {"model": "gpt-4.1", "input": [{"role": "user", "content": "hi"}]}

    def _response(self, usage) -> dict:
        return {
            "id": "x", "object": "response", "model": "gpt-4.1", "status": "completed",
            "output": [{
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "hi"}],
            }],
            "usage": usage,
        }

    def test_usage_as_list_does_not_crash(self):
        n = normalize_openai(self._request(), self._response(usage=["bad"]))
        assert n.usage.prompt_tokens is None

    def test_usage_as_none_does_not_crash(self):
        n = normalize_openai(self._request(), self._response(usage=None))
        assert n.usage.prompt_tokens is None

    def test_malformed_input_tokens_details_does_not_crash(self):
        # Even when the top-level usage is a dict, inner details may be
        # malformed. Cached-token extraction must tolerate that.
        n = normalize_openai(self._request(), self._response(usage={
            "input_tokens": 5, "output_tokens": 5,
            "input_tokens_details": "not-a-dict",
        }))
        assert n.usage.cached_tokens is None
        assert n.usage.prompt_tokens == 5


class TestMalformedUsageAnthropic:

    def _request(self) -> dict:
        return {"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}

    def _response(self, usage) -> dict:
        return {
            "id": "x", "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": "end_turn",
            "usage": usage,
        }

    def test_usage_as_list_does_not_crash(self):
        n = normalize_anthropic(self._request(), self._response(usage=[1, 2]))
        assert n.usage.prompt_tokens is None
        assert n.usage.total_tokens is None

    def test_usage_as_string_does_not_crash(self):
        n = normalize_anthropic(self._request(), self._response(usage="x"))
        assert n.usage.prompt_tokens is None

    def test_usage_missing_does_not_crash(self):
        # Drop the usage field entirely.
        resp = self._response(usage={})
        del resp["usage"]
        n = normalize_anthropic(self._request(), resp)
        assert n.usage.prompt_tokens is None
        assert n.usage.total_tokens is None
