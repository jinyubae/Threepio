from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import AsyncIterator

from openai import AsyncOpenAI
from pypdf import PdfReader

from .base import Attachment, LLMClient, Msg

PDF_TEXT_CHAR_BUDGET = 60_000  # per-session cap on extracted PDF text


def _extract_pdf_text(path: str) -> str:
    try:
        reader = PdfReader(path)
    except Exception as exc:
        return f"[Failed to read PDF: {exc}]"
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(f"--- page {i + 1} ---\n{page.extract_text() or ''}")
        except Exception as exc:
            parts.append(f"--- page {i + 1} (extract error: {exc}) ---")
    return "\n".join(parts)


def _image_content_item(att: Attachment) -> dict:
    data = base64.standard_b64encode(Path(att.path).read_bytes()).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{att.mime_type};base64,{data}"},
    }


def _augment_system(system: str, attachments: list[Attachment]) -> str:
    pdfs = [a for a in attachments if a.mime_type == "application/pdf"]
    if not pdfs:
        return system
    blocks = []
    budget = PDF_TEXT_CHAR_BUDGET
    for pdf in pdfs:
        text = _extract_pdf_text(pdf.path)
        if len(text) > budget:
            text = text[:budget] + "\n[...truncated...]"
            budget = 0
        else:
            budget -= len(text)
        blocks.append(f"### {pdf.filename}\n{text}")
        if budget <= 0:
            break
    return system + "\n\n## Attached documents\n" + "\n\n".join(blocks)


def _build_messages(
    system: str, history: list[Msg], attachments: list[Attachment]
) -> list[dict]:
    images = [a for a in attachments if a.mime_type != "application/pdf"]
    msgs: list[dict] = [{"role": "system", "content": _augment_system(system, attachments)}]
    first_user_seen = False
    for m in history:
        if m.role == "user" and not first_user_seen and images:
            first_user_seen = True
            content = [{"type": "text", "text": m.content}]
            content.extend(_image_content_item(a) for a in images)
            msgs.append({"role": "user", "content": content})
        else:
            if m.role == "user":
                first_user_seen = True
            msgs.append({"role": m.role, "content": m.content})
    return msgs


class OpenAIClient(LLMClient):
    def __init__(self, model: str) -> None:
        super().__init__(model)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = AsyncOpenAI(api_key=api_key)

    async def stream_reply(
        self,
        system: str,
        history: list[Msg],
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        messages = _build_messages(system, history, attachments)
        stream = await self._client.chat.completions.create(
            model=self.model, messages=messages, stream=True, max_tokens=1024
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def one_shot(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""

    async def one_shot_json(self, system: str, user: str, schema: dict) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""
