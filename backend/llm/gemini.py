from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator

from google import genai
from google.genai import types

from .base import Attachment, LLMClient, Msg


def _attachment_part(att: Attachment) -> types.Part:
    data = Path(att.path).read_bytes()
    return types.Part.from_bytes(data=data, mime_type=att.mime_type)


def _build_contents(
    history: list[Msg], attachments: list[Attachment]
) -> list[types.Content]:
    contents: list[types.Content] = []
    first_user_seen = False
    for m in history:
        role = "user" if m.role == "user" else "model"
        parts: list[types.Part] = []
        if m.role == "user" and not first_user_seen and attachments:
            first_user_seen = True
            parts.extend(_attachment_part(a) for a in attachments)
        else:
            if m.role == "user":
                first_user_seen = True
        parts.append(types.Part.from_text(text=m.content))
        contents.append(types.Content(role=role, parts=parts))
    return contents


class GeminiClient(LLMClient):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=api_key)

    async def stream_reply(
        self,
        system: str,
        history: list[Msg],
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        contents = _build_contents(history, attachments)
        config = types.GenerateContentConfig(system_instruction=system)
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self.model, contents=contents, config=config
        ):
            if chunk.text:
                yield chunk.text

    async def one_shot(self, system: str, user: str) -> str:
        config = types.GenerateContentConfig(system_instruction=system)
        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=user)])],
            config=config,
        )
        return resp.text or ""

    async def one_shot_json(self, system: str, user: str, schema: dict) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
        )
        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=user)])],
            config=config,
        )
        return resp.text or ""
