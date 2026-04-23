from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from .base import Attachment, LLMClient, Msg

_JSON_TOOL_NAME = "submit_feedback"


def _attachment_block(att: Attachment) -> dict:
    data = base64.standard_b64encode(Path(att.path).read_bytes()).decode()
    if att.mime_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": att.mime_type, "data": data},
    }


def _build_messages(history: list[Msg], attachments: list[Attachment]) -> list[dict]:
    """Embed attachments in the first user message, pass rest as-is."""
    msgs: list[dict] = []
    first_user_seen = False
    for m in history:
        if m.role == "user" and not first_user_seen and attachments:
            first_user_seen = True
            blocks = [_attachment_block(a) for a in attachments]
            if blocks:
                blocks[-1]["cache_control"] = {"type": "ephemeral"}
            blocks.append({"type": "text", "text": m.content})
            msgs.append({"role": "user", "content": blocks})
        else:
            if m.role == "user":
                first_user_seen = True
            msgs.append({"role": m.role, "content": m.content})
    return msgs


class ClaudeClient(LLMClient):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=api_key)

    async def stream_reply(
        self,
        system: str,
        history: list[Msg],
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        messages = _build_messages(history, attachments)
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            async for delta in stream.text_stream:
                yield delta

    async def one_shot(self, system: str, user: str) -> str:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts)

    async def one_shot_json(self, system: str, user: str, schema: dict) -> str:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "name": _JSON_TOOL_NAME,
                "description": "Submit the structured feedback payload.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": _JSON_TOOL_NAME},
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _JSON_TOOL_NAME:
                return json.dumps(block.input, ensure_ascii=False)
        return ""
