from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Provider = Literal["claude", "gemini", "openai"]
Source = Literal["voice", "text"]


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str
    situation: str
    user_role: str
    model_role: str
    llm_provider: Provider


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    source: Source = "text"


class ProviderInfo(BaseModel):
    provider: Provider
    available: bool
    model: str
    label: str
