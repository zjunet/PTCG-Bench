"""Shared OpenAI client factory for all LLM agents."""

from __future__ import annotations

import logging
import os
from typing import Any

import openai
from openai import OpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_BACKBONE_MODELS = (
    "openai/gpt-5.5",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "google/gemini-3.1-pro-preview",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "qwen/qwen3.6-plus",
    "qwen/qwen3.5-flash-02-23",
    "qwen/qwen3-coder",
    "qwen/qwen3-coder-plus",
    "qwen/qwen3.5-flash-02-23",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-v4-pro",
    "mistralai/mistral-large-2512",
    "mistralai/mistral-medium-3.1",
    "mistralai/mistral-small-2603",
    "x-ai/grok-4.1-fast",
    "meta-llama/llama-4-scout",
    "meta-llama/llama-3.3-70b-instruct",
    "z-ai/glm-4.7-flash",
    "minimax/minimax-m2.5",
)

_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

MODEL_CONFIGS: dict[str, dict[str, str]] = {
    "deepseek-chat": {
        "base_url": "https://api.deepseek.com",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    },
    "deepseek-v4-flash": {
        "base_url": "https://api.deepseek.com",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    },
    "deepseek-v4-pro": {
        "base_url": "https://api.deepseek.com",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    },
    "glm-4.7": {
        "base_url": "https://api.z.ai/api/paas/v4",
        "api_key": os.getenv("ZAI_API_KEY", ""),
    },
    "qwen3.5-flash": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
    },
    "MiniMax-M2.5": {
        "base_url": "https://api.minimax.io/v1",
        "api_key": os.getenv("MINIMAX_API_KEY", ""),
    },
    **{
        model: {
            "base_url": OPENROUTER_BASE_URL,
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
        }
        for model in OPENROUTER_BACKBONE_MODELS
    },
}


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def chat_completion_with_retry(client: OpenAI, **kwargs: Any) -> Any:
    """Call client.chat.completions.create with exponential-backoff retry."""
    return client.chat.completions.create(**kwargs)


def assistant_message_to_history(message: Any) -> dict[str, Any]:
    """Convert an SDK assistant message into a history item for the next request."""
    if hasattr(message, "model_dump"):
        raw = message.model_dump(exclude_unset=True)
    elif isinstance(message, dict):
        raw = dict(message)
    else:
        raw = {}

    history: dict[str, Any] = {"role": "assistant"}
    allowed_fields = (
        "content",
        "tool_calls",
        "function_call",
        "name",
        "refusal",
        "audio",
        # DeepSeek thinking-mode models require this field to be passed back.
        "reasoning_content",
    )

    for field in allowed_fields:
        value = raw.get(field, getattr(message, field, None))
        if value is not None:
            history[field] = value

    return history


def build_client(model: str) -> OpenAI:
    cfg = MODEL_CONFIGS.get(model, {})
    return OpenAI(
        base_url=cfg.get("base_url"),
        api_key=cfg.get("api_key", ""),
    )
