from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .semconv import CACHE_CREATION_INPUT_TOKENS, CACHE_READ_INPUT_TOKENS, INPUT_TOKENS, OUTPUT_TOKENS, USAGE_RAW


def get_usage_attributes(
    response: Any,
    usage: Any,
    input_tokens: int | None,
    output_tokens: int | None,
    provider_id: str,
    api_flavor: str | None = None,
    provider_url: str | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> dict[str, Any]:
    """Build usage attributes: INPUT_TOKENS, OUTPUT_TOKENS, USAGE_RAW, operation.cost.

    Callers extract input/output (and optionally cache read/write) tokens themselves (API-surface-specific).
    response is the full API response object, passed to genai_prices for cost calculation
    (genai_prices extracts both model and usage from it). usage is the usage sub-object,
    used for USAGE_RAW. api_flavor is needed for OpenAI ('chat', 'responses', or 'embeddings').
    Returns only attributes that have values.

    provider_url is the client's base URL. When present it takes precedence over provider_id
    for identifying the provider, since the URL identifies who actually served (and bills)
    the request, e.g. Anthropic models served by Bedrock are priced under `aws`. This mirrors
    pydantic-ai's resolution order:
    https://github.com/pydantic/pydantic-ai/blob/28a58d53b4d75b4da6d3b372edb9651f9cbe2411/pydantic_ai_slim/pydantic_ai/usage.py#L327-L329

    When the response comes through the Logfire AI Gateway, the cost the gateway reported
    (which includes custom prices) is used instead of the genai_prices estimate.

    Token/raw-usage and cost fail independently: a cost error does not prevent tokens
    from being set. Cost errors are silently caught (expected for unknown models etc.).
    """
    result: dict[str, Any] = {}

    if isinstance(input_tokens, int):
        result[INPUT_TOKENS] = input_tokens
    if isinstance(output_tokens, int):
        result[OUTPUT_TOKENS] = output_tokens
    # Only recorded when non-zero, so spans without prompt caching are unchanged.
    if isinstance(cache_read_tokens, int) and cache_read_tokens:
        result[CACHE_READ_INPUT_TOKENS] = cache_read_tokens
    if isinstance(cache_write_tokens, int) and cache_write_tokens:
        result[CACHE_CREATION_INPUT_TOKENS] = cache_write_tokens
    try:
        if hasattr(usage, 'model_dump'):
            result[USAGE_RAW] = usage.model_dump(exclude_none=True)
    except Exception:
        pass

    # Dump the response once, up front: the gateway-cost check reads the usage block and the
    # genai_prices estimate below reads the same data (model + usage only for embeddings,
    # which would otherwise serialize the embedding vectors).
    try:
        if not hasattr(response, 'model_dump'):
            response_data = None
        elif api_flavor == 'embeddings':
            response_data = response.model_dump(include={'model', 'usage'})
        else:
            response_data = response.model_dump()
    except Exception:
        response_data = None

    # A response served by the Logfire AI Gateway carries the actual cost charged, including
    # any custom prices, in its usage object. Use it instead of the genai_prices estimate.
    gateway_cost = _gateway_reported_cost(response_data)
    if gateway_cost is not None:
        result['operation.cost'] = float(gateway_cost)
        return result

    # Resolve the provider the way pydantic-ai's RequestUsage.extract does: the client's
    # base URL first, then the integration's provider id, trying each in turn because
    # find_provider raises when a candidate does not resolve. The URL wins because it
    # identifies who actually served and bills the request, e.g. Anthropic models served
    # by Bedrock are priced under `aws`.
    candidates: list[tuple[str | None, str | None]] = [(None, provider_url), (provider_id, None)]

    try:
        from genai_prices import calc_price
        from genai_prices.data_snapshot import get_snapshot

        for candidate_id, candidate_url in candidates:
            try:
                provider = get_snapshot().find_provider(None, candidate_id, candidate_url)

                # `anthropic` is a flavor on the aws provider only, so it is chosen from
                # the resolved provider rather than assumed.
                api_flavor = api_flavor or (
                    'anthropic' if provider.id == 'aws' and provider_id == 'anthropic' else 'default'
                )
                model_ref, price_usage = provider.extract_usage(response_data, api_flavor=api_flavor)
                if model_ref is None:
                    continue

                price = calc_price(price_usage, model_ref=model_ref, provider_id=provider.id)
                result['operation.cost'] = float(price.total_price)
                break
            except Exception:
                pass
    except Exception:
        pass

    return result


def _gateway_reported_cost(response_data: Any) -> Decimal | None:
    """Cost the Logfire AI Gateway injected into a response's `usage` object, if any.

    The gateway adds e.g. `usage.logfire_ai_gateway = {'cost': '0.0038'}` (a decimal string; a
    JSON number is accepted too); older and self-hosted gateways only send the deprecated
    `usage.pydantic_ai_gateway.cost_estimate`. A reported `0` (e.g. a gateway response-cache
    hit) is a real cost, not a missing one. Mirrors pydantic-ai's `_gateway_cost.py`:
    https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/_gateway_cost.py
    """
    if not isinstance(response_data, dict):
        return None
    usage_data = response_data.get('usage')
    if not isinstance(usage_data, dict):
        return None
    for block_name, field_name in (('logfire_ai_gateway', 'cost'), ('pydantic_ai_gateway', 'cost_estimate')):
        block = usage_data.get(block_name)
        if isinstance(block, dict):
            cost = _parse_cost(block.get(field_name))
            if cost is not None:
                return cost
    return None


def _parse_cost(value: Any) -> Decimal | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        cost = Decimal(str(value))
    except InvalidOperation:
        return None
    # NaN/inf would break comparisons and a negative cost would reduce the run total.
    return cost if cost.is_finite() and cost >= 0 else None
