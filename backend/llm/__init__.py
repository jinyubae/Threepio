from __future__ import annotations

import os
from typing import Iterable

from .base import Attachment, LLMClient, Msg
from .claude import ClaudeClient
from .gemini import GeminiClient
from .openai_impl import OpenAIClient

PROVIDER_LABELS = {
    "claude": "Claude (Anthropic)",
    "gemini": "Gemini (Google)",
    "openai": "ChatGPT (OpenAI)",
}

DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o",
}

ENV_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def available_providers() -> list[dict]:
    out = []
    for p in ("claude", "gemini", "openai"):
        out.append({
            "provider": p,
            "available": bool(os.environ.get(ENV_KEYS[p])),
            "model": DEFAULT_MODELS[p],
            "label": PROVIDER_LABELS[p],
        })
    return out


def get_client(provider: str, model: str | None = None) -> LLMClient:
    model = model or DEFAULT_MODELS[provider]
    if provider == "claude":
        return ClaudeClient(model=model)
    if provider == "gemini":
        return GeminiClient(model=model)
    if provider == "openai":
        return OpenAIClient(model=model)
    raise ValueError(f"Unknown provider: {provider}")


__all__ = [
    "Attachment",
    "LLMClient",
    "Msg",
    "available_providers",
    "get_client",
    "DEFAULT_MODELS",
    "ENV_KEYS",
    "PROVIDER_LABELS",
]
