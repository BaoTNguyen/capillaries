"""
LLM completion engine — the "last mile" that actually runs retrieved prompts.

Takes a resolved prompt (template variables already filled) and sends it to
any OpenAI-compatible chat API for completion. Supports both single prompts
and individual skill steps.

Usage:
    from capillaries.agent.generate import generate, generate_stream

    # Blocking
    result = await generate("You are a strategist. Analyze this market...")

    # Streaming (yields chunks)
    async for chunk in generate_stream("You are a strategist..."):
        print(chunk, end="")
"""

from __future__ import annotations

import json as _json
import os
from typing import AsyncIterator

import httpx

GENERATE_URL = os.getenv("GENERATE_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("GENERATE_MODEL", "qwen3:8b")
DEFAULT_TEMPERATURE = 0.7
MAX_PROMPT_CHARS = 12_000


async def generate(
    prompt_text: str,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    system: str | None = None,
    timeout: float = 120.0,
) -> dict:
    """
    Send a resolved prompt to the configured LLM and return the full completion.

    Returns:
        {"content": str, "model": str, "eval_count": int, "eval_duration_ns": int}
    """
    model = model or DEFAULT_MODEL
    messages = _build_messages(prompt_text, system)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GENERATE_URL,
            json={
                "model": model,
                "stream": False,
                "messages": messages,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "content": data["message"]["content"],
        "model": data.get("model", model),
        "eval_count": data.get("eval_count", 0),
        "eval_duration_ns": data.get("eval_duration", 0),
    }


async def generate_stream(
    prompt_text: str,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    system: str | None = None,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """
    Stream a completion token-by-token.

    Yields content strings as they arrive. Use with FastAPI's
    StreamingResponse for real-time output.
    """
    model = model or DEFAULT_MODEL
    messages = _build_messages(prompt_text, system)

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            GENERATE_URL,
            json={
                "model": model,
                "stream": True,
                "messages": messages,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = _json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content


def _build_messages(prompt_text: str, system: str | None) -> list[dict]:
    prompt_text = prompt_text[:MAX_PROMPT_CHARS]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt_text})
    return messages
