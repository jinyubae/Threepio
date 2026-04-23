from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal


@dataclass
class Attachment:
    path: str
    filename: str
    mime_type: str


@dataclass
class Msg:
    role: Literal["user", "assistant"]
    content: str


class LLMClient(ABC):
    """Abstract interface so routes can stay provider-agnostic."""

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    async def stream_reply(
        self,
        system: str,
        history: list[Msg],
        attachments: list[Attachment],
    ) -> AsyncIterator[str]:
        """Yield text deltas. The first user turn receives attachments."""

    @abstractmethod
    async def one_shot(self, system: str, user: str) -> str:
        """Non-streaming single-turn call (used by scoring)."""

    @abstractmethod
    async def one_shot_json(
        self, system: str, user: str, schema: dict
    ) -> str:
        """Non-streaming call constrained to a JSON object matching `schema`.

        Returns a JSON string (never wrapped in code fences). Each provider
        enforces validity via its native structured-output mechanism:
        Gemini response_mime_type, OpenAI response_format, Claude tool_use.
        """
