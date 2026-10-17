"""Anthropic Claude API client wrapper with prompt caching support."""

from typing import Optional

import streamlit as st

from core.config import CLAUDE_BATCH_MODEL, CLAUDE_DETAIL_MODEL


def _get_client():
    """Lazy-initialize the Anthropic client using the key from st.secrets."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package is required. Install with: pip install anthropic")

    api_key = None
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass

    if not api_key:
        import os
        api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. Add it to .streamlit/secrets.toml or set the environment variable."
        )

    return anthropic.Anthropic(api_key=api_key)


def call_claude(
    system_prompt: str,
    user_prompt: str,
    model: str = CLAUDE_BATCH_MODEL,
    max_tokens: int = 1500,
    cache_system: bool = True,
) -> str:
    """Call Claude and return the response text.

    Args:
        system_prompt: system instruction (cached if cache_system=True)
        user_prompt: the actual query
        model: Claude model ID
        max_tokens: max response tokens
        cache_system: whether to add cache_control to the system prompt
                      (reduces cost on repeated batch calls)

    Returns:
        Response text string
    """
    import anthropic

    client = _get_client()

    if cache_system:
        system: list = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system: list = [{"type": "text", "text": system_prompt}]

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text
