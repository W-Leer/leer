"""Tests for multimodal content-part normalization and summary handling.

Covers:
- OpenAI chat completions: multimodal inputs preserved in summaries
- OpenAI responses API: image/file output items normalized as canonical parts
- Anthropic: image/document input+output blocks normalized correctly
- Fallback behavior for unknown block types
- Summaries reveal media presence instead of dropping it
- Text-only and tool_call behavior remains unchanged
"""

import base64

from leer.integrations.normalize import (
    materialize_media_artifacts,
    normalize_anthropic,
    normalize_openai,
    _summarize_content_for_user,
)


# ---------------------------------------------------------------------------
# Fixtures: OpenAI
# ---------------------------------------------------------------------------

def _oai_chat_req(messages=None, **kw):
    d = {"model": "gpt-4.1", "messages": messages or []}
    d.update(kw)
    return d


def _oai_chat_resp(content="Hi", tool_calls=None, usage=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-test",
        "model": "gpt-4.1",
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _oai_resp_req(input_msgs=None, **kw):
    d = {"model": "gpt-4.1", "input": input_msgs or []}
    d.update(kw)
    return d


def _oai_resp_resp(output=None, usage=None):
    return {
        "id": "resp-test",
        "object": "response",
        "status": "completed",
        "model": "gpt-4.1",
        "output": output or [],
        "usage": usage or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


# ---------------------------------------------------------------------------
# Fixtures: Anthropic
# ---------------------------------------------------------------------------

def _ant_req(messages=None, **kw):
    d = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "messages": messages or [],
    }
    d.update(kw)
    return d


def _ant_resp(content=None, usage=None):
    return {
        "id": "msg-test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-20250514",
        "content": content or [],
        "stop_reason": "end_turn",
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


# ===================================================================
# _summarize_content_for_user
# ===================================================================

class TestSummarizeContentForUser:

    def test_string_content(self):
        assert _summarize_content_for_user("hello world") == "hello world"

    def test_text_only_array(self):
        content = [{"type": "text", "text": "What is this?"}]
        assert _summarize_content_for_user(content) == "What is this?"

    def test_openai_image_url_block(self):
        content = [
            {"type": "text", "text": "Explain this chart"},
            {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        ]
        result = _summarize_content_for_user(content)
        assert "[image]" in result
        assert "Explain this chart" in result

    def test_openai_input_image_block(self):
        content = [
            {"type": "input_image", "image_url": "https://..."},
            {"type": "input_text", "text": "Describe"},
        ]
        result = _summarize_content_for_user(content)
        assert "[image]" in result
        assert "Describe" in result

    def test_anthropic_image_block(self):
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            {"type": "text", "text": "What's in this image?"},
        ]
        result = _summarize_content_for_user(content)
        assert "[image]" in result
        assert "What's in this image?" in result

    def test_anthropic_document_block(self):
        content = [
            {"type": "document", "source": {"type": "url", "url": "https://..."}},
            {"type": "text", "text": "Summarize this PDF"},
        ]
        result = _summarize_content_for_user(content)
        assert "[document]" in result
        assert "Summarize this PDF" in result

    def test_file_block_with_filename(self):
        content = [
            {"type": "file", "filename": "data.csv"},
            {"type": "text", "text": "Parse it"},
        ]
        result = _summarize_content_for_user(content)
        assert "[file: data.csv]" in result

    def test_document_block_with_filename(self):
        content = [
            {"type": "document", "filename": "report.pdf"},
            {"type": "text", "text": "Summarize"},
        ]
        result = _summarize_content_for_user(content)
        assert "[document: report.pdf]" in result

    def test_unknown_block_type_preserved(self):
        content = [
            {"type": "audio", "data": "..."},
            {"type": "text", "text": "Listen"},
        ]
        result = _summarize_content_for_user(content)
        assert "[audio]" in result

    def test_openai_input_file_block(self):
        content = [
            {"type": "input_file", "filename": "readme.txt"},
            {"type": "input_text", "text": "Read this"},
        ]
        result = _summarize_content_for_user(content)
        assert "[file: readme.txt]" in result

    def test_openai_input_pdf_block(self):
        content = [
            {"type": "input_pdf"},
            {"type": "input_text", "text": "Summarize"},
        ]
        result = _summarize_content_for_user(content)
        assert "[document: PDF]" in result


# ===================================================================
# OpenAI chat completions: text-only unchanged
# ===================================================================

class TestOpenAIChatTextOnly:

    def test_text_only_unchanged(self):
        req = _oai_chat_req(messages=[
            {"role": "user", "content": "Hello"},
        ])
        resp = _oai_chat_resp(content="Hi there")
        n = normalize_openai(req, resp)

        assert n.output.text == "Hi there"
        assert n.output.content_blocks == [{"type": "text", "text": "Hi there"}]
        assert n.output.tool_calls == []

    def test_tool_calls_unchanged(self):
        req = _oai_chat_req(messages=[{"role": "user", "content": "Weather?"}])
        resp = _oai_chat_resp(content=None, tool_calls=[
            {"id": "c1", "type": "function", "function": {"name": "weather", "arguments": '{"city":"NYC"}'}},
        ])
        n = normalize_openai(req, resp)

        assert n.output.text is None
        assert len(n.output.tool_calls) == 1
        assert n.output.tool_calls[0]["name"] == "weather"
        blocks = n.output.content_blocks
        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_call"


# ===================================================================
# OpenAI chat completions: multimodal INPUT in summaries
# ===================================================================

class TestOpenAIChatMultimodalInput:

    def test_image_input_shows_in_summary(self):
        req = _oai_chat_req(messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "Explain this chart"},
                {"type": "image_url", "image_url": {"url": "https://example.com/chart.png"}},
            ]},
        ])
        resp = _oai_chat_resp(content="This chart shows...")
        n = normalize_openai(req, resp)

        assert n.output.text == "This chart shows..."
        # The raw input messages are preserved
        assert isinstance(n.input.messages[0]["content"], list)


# ===================================================================
# OpenAI responses API: multimodal OUTPUT
# ===================================================================

class TestOpenAIResponsesMultimodalOutput:

    def test_image_output_block(self):
        output = [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Here is the image:"},
                    {"type": "output_image", "mime_type": "image/png", "file_id": "file-123"},
                ],
            },
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert n.output.text == "Here is the image:"
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "text", "text": "Here is the image:"}

        img = n.output.content_blocks[1]
        assert img["type"] == "image"
        assert img["mime_type"] == "image/png"
        assert img["provider"] == "openai"
        assert img["provider_part_type"] == "output_image"
        assert img["source"]["kind"] == "provider_file"
        assert img["source"]["value"] == "file-123"

    def test_image_generation_call_item(self):
        output = [
            {"type": "image_generation_call", "result": "base64-data-here"},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert len(n.output.content_blocks) == 1
        block = n.output.content_blocks[0]
        assert block["type"] == "image"
        assert block["provider_part_type"] == "image_generation_call"

    def test_unknown_output_item_not_dropped(self):
        output = [
            {"type": "some_future_type", "data": "opaque"},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert len(n.output.content_blocks) == 1
        block = n.output.content_blocks[0]
        assert block["type"] == "file"
        assert block["provider_part_type"] == "some_future_type"
        assert "raw_type" in block.get("metadata", {})

    def test_unknown_message_content_block_not_dropped(self):
        output = [
            {
                "type": "message",
                "content": [
                    {"type": "weird_block", "stuff": "data"},
                ],
            },
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert len(n.output.content_blocks) == 1
        block = n.output.content_blocks[0]
        assert block["type"] == "file"
        assert block["provider_part_type"] == "weird_block"

    def test_text_and_tool_calls_still_work(self):
        output = [
            {"type": "message", "content": [{"type": "output_text", "text": "Checking..."}]},
            {"type": "function_call", "call_id": "c1", "name": "search", "arguments": '{"q": "test"}'},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert n.output.text == "Checking..."
        assert len(n.output.tool_calls) == 1
        assert n.output.tool_calls[0]["name"] == "search"
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0]["type"] == "text"
        assert n.output.content_blocks[1]["type"] == "tool_call"

    def test_refusal_block_preserved(self):
        output = [
            {"type": "message", "content": [
                {"type": "refusal", "refusal": "I cannot help with that"},
            ]},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))

        assert len(n.output.content_blocks) == 1
        assert "[refusal]" in n.output.content_blocks[0]["text"]


# ===================================================================
# OpenAI responses API: multimodal INPUT in summaries
# ===================================================================

class TestOpenAIResponsesMultimodalInputSummary:

    def test_input_with_image(self):
        req = _oai_resp_req(input_msgs=[
            {"role": "user", "content": [
                {"type": "input_text", "text": "Describe this"},
                {"type": "input_image", "image_url": "https://img.png"},
            ]},
        ])
        n = normalize_openai(req, _oai_resp_resp(output=[
            {"type": "message", "content": [{"type": "output_text", "text": "A cat."}]},
        ]))

        assert isinstance(n.input.messages[0]["content"], list)
        assert n.output.text == "A cat."


# ===================================================================
# Anthropic: text-only unchanged
# ===================================================================

class TestAnthropicTextOnly:

    def test_text_only_unchanged(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Hello"}]),
            _ant_resp(content=[{"type": "text", "text": "Hi there!"}]),
        )
        assert n.output.text == "Hi there!"
        assert n.output.content_blocks == [{"type": "text", "text": "Hi there!"}]

    def test_tool_use_unchanged(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Weather?"}]),
            _ant_resp(content=[
                {"type": "text", "text": "Checking..."},
                {"type": "tool_use", "id": "t1", "name": "weather", "input": {"city": "NYC"}},
            ]),
        )
        assert n.output.text == "Checking..."
        assert len(n.output.tool_calls) == 1
        assert n.output.tool_calls[0]["name"] == "weather"
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0]["type"] == "text"
        assert n.output.content_blocks[1]["type"] == "tool_call"

    def test_thinking_blocks_unchanged(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Think hard"}]),
            _ant_resp(content=[
                {"type": "thinking", "thinking": "reasoning..."},
                {"type": "text", "text": "42"},
            ]),
        )
        assert n.output.content_blocks[0] == {"type": "thinking", "thinking": "reasoning..."}
        assert n.output.content_blocks[1] == {"type": "text", "text": "42"}


# ===================================================================
# Anthropic: multimodal OUTPUT
# ===================================================================

class TestAnthropicMultimodalOutput:

    def test_image_output_block(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Draw a cat"}]),
            _ant_resp(content=[
                {"type": "text", "text": "Here you go:"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBOR...",
                    },
                },
            ]),
        )
        assert n.output.text == "Here you go:"
        assert len(n.output.content_blocks) == 2

        img = n.output.content_blocks[1]
        assert img["type"] == "image"
        assert img["mime_type"] == "image/png"
        assert img["provider"] == "anthropic"
        assert img["provider_part_type"] == "image"
        assert img["source"]["kind"] == "inline"
        assert img["preview_text"] == "image output"

    def test_image_url_source(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Show me"}]),
            _ant_resp(content=[
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "media_type": "image/jpeg",
                        "url": "https://example.com/img.jpg",
                    },
                },
            ]),
        )
        img = n.output.content_blocks[0]
        assert img["type"] == "image"
        assert img["mime_type"] == "image/jpeg"
        assert img["source"]["kind"] == "url"
        assert img["source"]["value"] == "https://example.com/img.jpg"

    def test_document_output_block(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Generate PDF"}]),
            _ant_resp(content=[
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": "JVBERi...",
                    },
                    "title": "report.pdf",
                },
            ]),
        )
        doc = n.output.content_blocks[0]
        assert doc["type"] == "document"
        assert doc["mime_type"] == "application/pdf"
        assert doc["provider"] == "anthropic"
        assert doc["provider_part_type"] == "document"
        assert doc["filename"] == "report.pdf"
        assert doc["preview_text"] == "document output"

    def test_document_url_source(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Here's a doc"}]),
            _ant_resp(content=[
                {
                    "type": "document",
                    "source": {
                        "type": "url",
                        "media_type": "application/pdf",
                        "url": "https://example.com/doc.pdf",
                    },
                },
            ]),
        )
        doc = n.output.content_blocks[0]
        assert doc["source"]["kind"] == "url"
        assert doc["source"]["value"] == "https://example.com/doc.pdf"

    def test_unknown_block_not_dropped(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Future stuff"}]),
            _ant_resp(content=[
                {"type": "text", "text": "Ok"},
                {"type": "some_future_type", "data": "opaque"},
            ]),
        )
        assert len(n.output.content_blocks) == 2
        assert n.output.content_blocks[0] == {"type": "text", "text": "Ok"}
        fallback = n.output.content_blocks[1]
        assert fallback["type"] == "file"
        assert fallback["provider"] == "anthropic"
        assert fallback["provider_part_type"] == "some_future_type"
        assert "raw_type" in fallback.get("metadata", {})


# ===================================================================
# Anthropic: multimodal INPUT in summaries
# ===================================================================

class TestAnthropicMultimodalInput:

    def test_image_input_preserved_in_messages(self):
        req = _ant_req(messages=[
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
                {"type": "text", "text": "What is this?"},
            ]},
        ])
        n = normalize_anthropic(req, _ant_resp(content=[{"type": "text", "text": "A chart."}]))

        assert isinstance(n.input.messages[0]["content"], list)
        assert n.output.text == "A chart."

    def test_document_input_preserved_in_messages(self):
        req = _ant_req(messages=[
            {"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "..."}},
                {"type": "text", "text": "Summarize this PDF"},
            ]},
        ])
        n = normalize_anthropic(req, _ant_resp(content=[{"type": "text", "text": "The report shows..."}]))

        assert isinstance(n.input.messages[0]["content"], list)


# ===================================================================
# Summary behavior: OpenAI
# ===================================================================

class TestOpenAISummaries:

    def test_input_summary_text_only(self):
        from leer.integrations.openai import _input_summary
        req = _oai_chat_req(messages=[{"role": "user", "content": "Hello"}])
        resp = _oai_chat_resp(content="Hi")
        n = normalize_openai(req, resp)
        s = _input_summary(n)
        assert s["user"] == "Hello"

    def test_input_summary_with_image(self):
        from leer.integrations.openai import _input_summary
        req = _oai_chat_req(messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "Explain this"},
                {"type": "image_url", "image_url": {"url": "https://img.png"}},
            ]},
        ])
        n = normalize_openai(req, _oai_chat_resp())
        s = _input_summary(n)
        assert "[image]" in s["user"]
        assert "Explain this" in s["user"]

    def test_input_summary_with_document(self):
        from leer.integrations.openai import _input_summary
        req = _oai_chat_req(messages=[
            {"role": "user", "content": [
                {"type": "document", "filename": "report.pdf"},
                {"type": "text", "text": "Summarize"},
            ]},
        ])
        n = normalize_openai(req, _oai_chat_resp())
        s = _input_summary(n)
        assert "[document: report.pdf]" in s["user"]

    def test_output_summary_text_only(self):
        from leer.integrations.openai import _output_summary
        n = normalize_openai(
            _oai_chat_req(messages=[{"role": "user", "content": "Hi"}]),
            _oai_chat_resp(content="Hello!"),
        )
        s = _output_summary(n)
        assert s["text"] == "Hello!"
        assert "media" not in s

    def test_output_summary_with_image(self):
        from leer.integrations.openai import _output_summary
        output = [
            {"type": "message", "content": [
                {"type": "output_text", "text": "Here:"},
                {"type": "output_image", "mime_type": "image/png", "file_id": "f1"},
            ]},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))
        s = _output_summary(n)
        assert s["text"] == "Here:"
        assert "[image]" in s["media"]

    def test_response_preview_with_media(self):
        from leer.integrations.openai import _response_preview
        output = [
            {"type": "message", "content": [
                {"type": "output_image", "mime_type": "image/png"},
            ]},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))
        preview = _response_preview(n)
        assert "image" in preview.lower()

    def test_request_preview_with_image_input(self):
        from leer.integrations.openai import _request_preview
        req = _oai_chat_req(messages=[
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "..."}},
                {"type": "text", "text": "Describe"},
            ]},
        ])
        n = normalize_openai(req, _oai_chat_resp())
        preview = _request_preview(n)
        assert "[image]" in preview


# ===================================================================
# Summary behavior: Anthropic
# ===================================================================

class TestAnthropicSummaries:

    def test_input_summary_text_only(self):
        from leer.integrations.anthropic import _input_summary
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Hello"}]),
            _ant_resp(content=[{"type": "text", "text": "Hi"}]),
        )
        s = _input_summary(n)
        assert s["user"] == "Hello"

    def test_input_summary_with_image(self):
        from leer.integrations.anthropic import _input_summary
        req = _ant_req(messages=[
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
                {"type": "text", "text": "What's this?"},
            ]},
        ])
        n = normalize_anthropic(req, _ant_resp(content=[{"type": "text", "text": "A cat"}]))
        s = _input_summary(n)
        assert "[image]" in s["user"]
        assert "What's this?" in s["user"]

    def test_input_summary_with_document(self):
        from leer.integrations.anthropic import _input_summary
        req = _ant_req(messages=[
            {"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "..."}},
                {"type": "text", "text": "Summarize this"},
            ]},
        ])
        n = normalize_anthropic(req, _ant_resp(content=[{"type": "text", "text": "Done"}]))
        s = _input_summary(n)
        assert "[document]" in s["user"]
        assert "Summarize this" in s["user"]

    def test_output_summary_text_only(self):
        from leer.integrations.anthropic import _output_summary
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Hi"}]),
            _ant_resp(content=[{"type": "text", "text": "Hello!"}]),
        )
        s = _output_summary(n)
        assert s["text"] == "Hello!"
        assert "media" not in s

    def test_output_summary_with_image(self):
        from leer.integrations.anthropic import _output_summary
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Draw a cat"}]),
            _ant_resp(content=[
                {"type": "text", "text": "Here:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            ]),
        )
        s = _output_summary(n)
        assert s["text"] == "Here:"
        assert "[image]" in s["media"]

    def test_output_summary_with_document(self):
        from leer.integrations.anthropic import _output_summary
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Generate PDF"}]),
            _ant_resp(content=[
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "..."}, "title": "report.pdf"},
            ]),
        )
        s = _output_summary(n)
        assert "media" in s
        assert "[document: report.pdf]" in s["media"]

    def test_response_preview_with_media(self):
        from leer.integrations.anthropic import _response_preview
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Draw"}]),
            _ant_resp(content=[
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
            ]),
        )
        preview = _response_preview(n)
        assert "image" in preview.lower()

    def test_request_preview_with_image_input(self):
        from leer.integrations.anthropic import _request_preview
        req = _ant_req(messages=[
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
                {"type": "text", "text": "Describe"},
            ]},
        ])
        n = normalize_anthropic(req, _ant_resp(content=[{"type": "text", "text": "A cat"}]))
        preview = _request_preview(n)
        assert "[image]" in preview


# ===================================================================
# Cross-provider: ordering preserved
# ===================================================================

class TestOrderingPreserved:

    def test_anthropic_interleaved_text_and_media(self):
        n = normalize_anthropic(
            _ant_req(messages=[{"role": "user", "content": "Go"}]),
            _ant_resp(content=[
                {"type": "text", "text": "First"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}},
                {"type": "text", "text": "Second"},
            ]),
        )
        blocks = n.output.content_blocks
        assert len(blocks) == 3
        assert blocks[0] == {"type": "text", "text": "First"}
        assert blocks[1]["type"] == "image"
        assert blocks[2] == {"type": "text", "text": "Second"}

    def test_openai_responses_text_then_image(self):
        output = [
            {"type": "message", "content": [
                {"type": "output_text", "text": "Here:"},
                {"type": "output_image", "mime_type": "image/png"},
            ]},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))
        blocks = n.output.content_blocks
        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "image"


# ===================================================================
# Media artifact materialization
# ===================================================================

PNG_1PX = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image-bytes").decode()
PDF_FAKE = base64.b64encode(b"%PDF-1.4 fake-document-bytes").decode()


class TestMaterializeAnthropicImage:

    def test_base64_image_becomes_artifact(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "Here:"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": PNG_1PX},
                },
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        req = _ant_req(messages=[{"role": "user", "content": "Draw"}])
        n = normalize_anthropic(req, response)

        artifacts = materialize_media_artifacts(n, response, step_id="s1")

        assert len(artifacts) == 1
        art = artifacts[0]
        assert art.artifact_type == "output_image"
        assert art.mime_type == "image/png"
        assert art.binary_data == base64.b64decode(PNG_1PX)
        assert art.role == "output"
        assert art.step_id == "s1"

        img_block = n.output.content_blocks[1]
        assert img_block["artifact_id"] == art.id
        assert img_block["source"]["kind"] == "artifact"
        assert img_block["size_bytes"] == len(art.binary_data)

    def test_url_image_not_materialized(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "url", "media_type": "image/jpeg", "url": "https://example.com/img.jpg"},
                },
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Show"}]), response)

        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0
        assert n.output.content_blocks[0]["source"]["kind"] == "url"


class TestMaterializeAnthropicDocument:

    def test_base64_pdf_becomes_artifact(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": PDF_FAKE},
                    "title": "report.pdf",
                },
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "PDF"}]), response)

        artifacts = materialize_media_artifacts(n, response, step_id="s2")

        assert len(artifacts) == 1
        art = artifacts[0]
        assert art.artifact_type == "output_document"
        assert art.mime_type == "application/pdf"
        assert art.binary_data == base64.b64decode(PDF_FAKE)

        doc_block = n.output.content_blocks[0]
        assert doc_block["artifact_id"] == art.id
        assert doc_block["source"]["kind"] == "artifact"
        assert doc_block["filename"] == "report.pdf"


class TestMaterializeOpenAI:

    def test_text_only_no_artifacts(self):
        output = [
            {"type": "message", "content": [{"type": "output_text", "text": "Hello"}]},
        ]
        response = _oai_resp_resp(output=output)
        n = normalize_openai(_oai_resp_req(), response)

        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0

    def test_image_generation_with_base64_result(self):
        output = [
            {"type": "image_generation_call", "result": PNG_1PX},
        ]
        response = _oai_resp_resp(output=output)
        n = normalize_openai(_oai_resp_req(), response)

        artifacts = materialize_media_artifacts(n, response, step_id="s3")

        assert len(artifacts) == 1
        art = artifacts[0]
        assert art.artifact_type == "output_image"
        assert art.mime_type == "image/png"

        img = n.output.content_blocks[0]
        assert img["artifact_id"] == art.id
        assert img["source"]["kind"] == "artifact"


class TestMaterializeIdempotent:

    def test_already_linked_not_duplicated(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": PNG_1PX},
                },
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Draw"}]), response)

        arts1 = materialize_media_artifacts(n, response)
        assert len(arts1) == 1

        arts2 = materialize_media_artifacts(n, response)
        assert len(arts2) == 0


class TestMaterializePreservesTextAndToolCalls:

    def test_text_and_tool_calls_unaffected(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "Checking..."},
                {"type": "tool_use", "id": "t1", "name": "weather", "input": {"city": "NYC"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Weather"}]), response)

        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0
        assert n.output.content_blocks[0] == {"type": "text", "text": "Checking..."}
        assert n.output.content_blocks[1]["type"] == "tool_call"


# ===================================================================
# Step 4 edge cases — multiple media, unknown types, fallbacks
# ===================================================================


class TestMultipleMediaBlocksMaterialization:
    """Multiple image/document blocks in one response are each materialized."""

    def test_two_anthropic_images_both_materialized(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "Two images:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_1PX}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_1PX}},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Draw two"}]), response)
        artifacts = materialize_media_artifacts(n, response)

        assert len(artifacts) == 2
        # v1 heuristic: both match the first response block, so both get image/png
        assert artifacts[0].mime_type == "image/png"
        assert artifacts[1].mime_type == "image/png"
        assert n.output.content_blocks[1]["artifact_id"] == artifacts[0].id
        assert n.output.content_blocks[2]["artifact_id"] == artifacts[1].id

    def test_mixed_image_and_document(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_1PX}},
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": PDF_FAKE}, "title": "r.pdf"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Both"}]), response)
        artifacts = materialize_media_artifacts(n, response)

        assert len(artifacts) == 2
        assert artifacts[0].artifact_type == "output_image"
        assert artifacts[1].artifact_type == "output_document"


class TestUnknownBlockTypeFallback:
    """Unknown/unsupported block types should normalize as 'file' and not crash materialization."""

    def test_anthropic_unknown_type_normalizes_as_file(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "spreadsheet", "data": "some-data", "source": {"media_type": "text/csv"}},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "CSV"}]), response)
        blocks = n.output.content_blocks
        assert len(blocks) == 1
        assert blocks[0]["type"] == "file"

    def test_openai_unknown_output_normalizes_as_file(self):
        output = [
            {"type": "audio_output", "data": "fake-audio-data"},
        ]
        n = normalize_openai(_oai_resp_req(), _oai_resp_resp(output=output))
        blocks = n.output.content_blocks
        assert len(blocks) == 1
        assert blocks[0]["type"] == "file"

    def test_materialization_skips_file_type(self):
        """File-type blocks do not get materialized — only image and document do."""
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "spreadsheet", "data": "some-data", "source": {"media_type": "text/csv"}},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "CSV"}]), response)
        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0


class TestContentBlockEdgeCases:
    """Edge cases: empty content blocks, blocks with only text, etc."""

    def test_empty_content_blocks_no_crash(self):
        """Anthropic response with no content blocks at all."""
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Empty"}]), response)
        assert n.output.content_blocks == []
        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0

    def test_text_only_blocks_untouched_by_materialization(self):
        response = {
            "id": "msg-test",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "Hello world"},
                {"type": "text", "text": "Second paragraph"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        n = normalize_anthropic(_ant_req(messages=[{"role": "user", "content": "Hi"}]), response)
        artifacts = materialize_media_artifacts(n, response)
        assert len(artifacts) == 0
        assert len(n.output.content_blocks) == 2
        assert all(b["type"] == "text" for b in n.output.content_blocks)


class TestSummaryMediaPresence:
    """Summaries should reveal media type markers, not drop them."""

    def test_multimodal_input_summary_shows_all_media_types(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze these"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,def"}},
            ]},
        ]
        summary = _summarize_content_for_user(msgs[0]["content"])
        assert summary.count("[image]") == 2
        assert "Analyze these" in summary

    def test_summary_with_file_blocks(self):
        content = [
            {"type": "text", "text": "Read this"},
            {"type": "file", "filename": "data.csv"},
        ]
        summary = _summarize_content_for_user(content)
        assert "[file: data.csv]" in summary

    def test_summary_with_document_block(self):
        content = [
            {"type": "text", "text": "Review the report"},
            {"type": "document", "filename": "report.pdf"},
        ]
        summary = _summarize_content_for_user(content)
        assert "[document: report.pdf]" in summary
