from typing import Any


GPT_5_PREFIXES = ("gpt-5",)
OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")


def is_gpt5_model(model: str) -> bool:
    return model.startswith(GPT_5_PREFIXES)


def is_openai_model(model: str) -> bool:
    return model.startswith(OPENAI_MODEL_PREFIXES)


def make_async_openai_client(settings: Any) -> Any:
    from openai import AsyncOpenAI

    if settings.minimax_api_key and not is_openai_model(settings.openai_model):
        return AsyncOpenAI(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


def chat_completion_kwargs(
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float | None = 0,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build Chat Completions kwargs with GPT-5.x compatibility.

    GPT-5.5 rejects non-default temperature values and the legacy
    max_tokens parameter, so callers should go through this helper instead of
    passing model-specific parameters inline.
    """
    params: dict[str, Any] = {
        "model": model,
        "messages": messages,
        **kwargs,
    }
    if max_tokens is not None:
        if is_gpt5_model(model):
            params["max_completion_tokens"] = max_tokens
        else:
            params["max_tokens"] = max_tokens
    if temperature is not None and not is_gpt5_model(model):
        params["temperature"] = temperature
    return params
