from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json

from . import prompts
from .llm import get_client

FEEDBACK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "quality": {"type": "integer", "minimum": 0, "maximum": 100},
                "fluency": {"type": "integer", "minimum": 0, "maximum": 100},
                "communication": {"type": "integer", "minimum": 0, "maximum": 100},
                "overall": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["quality", "fluency", "communication", "overall"],
        },
        "summary": {"type": "string"},
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["original", "suggestion", "explanation"],
            },
        },
    },
    "required": ["scores", "summary", "corrections"],
}

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def _try_parse(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Final safety net: repair common LLM JSON sloppiness
    # (unescaped quotes, trailing commas, truncated output, etc.)
    try:
        repaired = repair_json(_strip_fences(text))
        if repaired:
            return json.loads(repaired)
    except Exception:
        pass
    return None


async def generate_feedback(
    *, provider: str, model: str, user_utterances: list[str]
) -> dict[str, Any]:
    client = get_client(provider, model)
    raw = await client.one_shot_json(
        system=prompts.FEEDBACK_SYSTEM,
        user=prompts.build_feedback_prompt(user_utterances),
        schema=FEEDBACK_SCHEMA,
    )
    parsed = _try_parse(raw)
    if parsed is None:
        return {"raw_feedback": raw, "parse_error": True}
    return parsed
