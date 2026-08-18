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
    provider_url: str | None = None,
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

    provider_url is the client's base URL. When present it takes precedence over provider_id
    for identifying the provider, since the URL identifies who actually served (and bills)
    the request, e.g. Anthropic models served by Bedrock are priced under `aws`. This mirrors
    pydantic-ai's resolution order:
    https://github.com/pydantic/pydantic-ai/blob/28a58d53b4d75b4da6d3b372edb9651f9cbe2411/pydantic_ai_slim/pydantic_ai/usage.py#L327-L329

    Pass model_ref when the response body isn't shaped the way genai_prices' extractors
    expect, so that the model and token counts the caller already has are priced directly
    instead. cache_read_tokens/cache_write_tokens are only read in that case, and
    input_tokens is expected to already include them (the genai_prices convention).

    Token/raw-usage and cost fail independently: a cost error does not prevent tokens
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

    # (provider_id, provider_api_url) candidates, URL first: genai_prices raises on a
    # candidate that doesn't resolve, and the next one is tried.
    candidates: list[tuple[str | None, str | None]] = [(provider_id, None)]
    if provider_url is not None:
        candidates.insert(0, (None, provider_url))

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
            for candidate_id, candidate_url in candidates:
                try:
                    result['operation.cost'] = float(
                        calc_price(
                            price_usage, model_ref=model_ref, provider_id=candidate_id, provider_api_url=candidate_url
                        ).total_price
                    )
                    break
                except Exception:
                    pass
        else:
            from genai_prices import extract_usage

            if api_flavor == 'embeddings':
                response_data = response.model_dump(include={'model', 'usage'})
            else:
                response_data = response.model_dump()
            extract_kwargs: dict[str, Any] = {}
            if api_flavor is not None:
                extract_kwargs['api_flavor'] = api_flavor
            for candidate_id, candidate_url in candidates:
                try:
                    usage_data = extract_usage(
                        response_data, provider_id=candidate_id, provider_api_url=candidate_url, **extract_kwargs
                    )
                    if usage_data.model is None:
                        continue
                    result['operation.cost'] = float(
                        calc_price(
                            usage_data.usage,
                            model_ref=usage_data.model.id,
                            provider_id=candidate_id,
                            provider_api_url=candidate_url,
                        ).total_price
                    )
                    break
                except Exception:
                    pass
    except Exception:
        pass

    return result
