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
    # candidate that doesn't resolve, and the next one is tried. `calc_price` and
    # `extract_usage` overload the two provider arguments as mutually exclusive, so a
    # candidate is either a URL or an id and each is passed on its own.
    candidates: list[str] = [provider_id]
    if provider_url is not None:
        candidates.insert(0, provider_url)

    def is_url(candidate: str) -> bool:
        return candidate.startswith(('http://', 'https://'))

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
            for candidate in candidates:
                try:
                    if is_url(candidate):
                        price = calc_price(price_usage, model_ref=model_ref, provider_api_url=candidate)
                    else:
                        price = calc_price(price_usage, model_ref=model_ref, provider_id=candidate)
                    result['operation.cost'] = float(price.total_price)
                    break
                except Exception:
                    pass
        else:
            from genai_prices import extract_usage

            if api_flavor == 'embeddings':
                response_data = response.model_dump(include={'model', 'usage'})
            else:
                response_data = response.model_dump()
            flavor = api_flavor or 'default'
            for candidate in candidates:
                try:
                    if is_url(candidate):
                        usage_data = extract_usage(response_data, provider_api_url=candidate, api_flavor=flavor)
                    else:
                        usage_data = extract_usage(response_data, provider_id=candidate, api_flavor=flavor)
                    model = usage_data.model
                    if model is None:
                        continue
                    if is_url(candidate):
                        price = calc_price(usage_data.usage, model_ref=model.id, provider_api_url=candidate)
                    else:
                        price = calc_price(usage_data.usage, model_ref=model.id, provider_id=candidate)
                    result['operation.cost'] = float(price.total_price)
                    break
                except Exception:
                    pass
    except Exception:
        pass

    return result
