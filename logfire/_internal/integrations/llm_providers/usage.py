from __future__ import annotations

from typing import Any

from .semconv import INPUT_TOKENS, OUTPUT_TOKENS, USAGE_RAW


def get_usage_attributes(
    response: Any,
    usage: Any,
    input_tokens: int | None,
    output_tokens: int | None,
    provider_id: str,
    api_flavor: str | None = None,
    model_ref: str | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> dict[str, Any]:
    """Build usage attributes: INPUT_TOKENS, OUTPUT_TOKENS, USAGE_RAW, operation.cost.

    Callers extract input/output tokens themselves (API-surface-specific).
    response is the full API response object, passed to genai_prices for cost calculation
    (genai_prices extracts both model and usage from it). usage is the usage sub-object,
    used for USAGE_RAW. api_flavor is needed for OpenAI ('chat', 'responses', or 'embeddings').
    Returns only attributes that have values.

    Pass model_ref when the response body isn't shaped the way genai_prices' extractor for
    provider_id expects, so that the model and token counts the caller already has are priced
    directly instead. cache_read_tokens/cache_write_tokens are only read in that case, and
    input_tokens is expected to already include them.

    Token/raw-usage and cost fail independently — a cost error does not prevent tokens
    from being set. Cost errors are silently caught (expected for unknown models etc.).
    """
    result: dict[str, Any] = {}

    if isinstance(input_tokens, int):
        result[INPUT_TOKENS] = input_tokens
    if isinstance(output_tokens, int):
        result[OUTPUT_TOKENS] = output_tokens
    try:
        if hasattr(usage, 'model_dump'):
            result[USAGE_RAW] = usage.model_dump(exclude_none=True)
    except Exception:
        pass

    try:
        from genai_prices import calc_price

        if model_ref is not None:
            from genai_prices import Usage as PriceUsage

            price_usage = PriceUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            )
        else:
            from genai_prices import extract_usage

            if api_flavor == 'embeddings':
                response_data = response.model_dump(include={'model', 'usage'})
            else:
                response_data = response.model_dump()
            extract_kwargs: dict[str, Any] = {'provider_id': provider_id}
            if api_flavor is not None:
                extract_kwargs['api_flavor'] = api_flavor
            usage_data = extract_usage(response_data, **extract_kwargs)
            if usage_data.model is None:
                return result
            model_ref = usage_data.model.id
            price_usage = usage_data.usage

        result['operation.cost'] = float(
            calc_price(price_usage, model_ref=model_ref, provider_id=provider_id).total_price
        )
    except Exception:
        pass

    return result
