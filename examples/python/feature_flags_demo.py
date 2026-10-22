"""A support service using native typed flags, managed templates, and OpenFeature.

Run `make demo-feature-flags` from the repository root, then open /docs.
The default configuration is entirely local; no telemetry leaves the machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from pydantic import BaseModel, Field, SecretStr

import logfire
from logfire.experimental.feature_flags import feature_context, flag
from logfire.experimental.openfeature import LogfireProvider
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
)


class AgentPolicy(BaseModel):
    """Validated settings shared by the support agent and its tools."""

    model: Literal['small', 'large'] = 'small'
    max_documents: Annotated[int, Field(ge=1, le=10)] = 1
    api_key: SecretStr = SecretStr('demo-local-credential')


class Ticket(BaseModel):
    """A simulated support request; no model provider is called."""

    customer_id: str
    plan: Literal['free', 'team'] = 'free'
    topic: str = 'installation'


class PromptInputs(BaseModel):
    """The fields available to the managed support prompt."""

    topic: str


def demo_config() -> VariablesConfig:
    """Return a small, representative configuration using the public wire models."""

    def configured(name: str, value: Any) -> VariableConfig:
        return VariableConfig(
            name=name,
            labels={'live': LabeledValue(version=1, serialized_value=json.dumps(value))},
            rollout=Rollout(labels={'live': 1}),
            overrides=[],
        )

    values = {
        'assist_enabled': False,
        'agent_policy': {'model': 'large', 'max_documents': 3, 'api_key': 'demo-remote-credential'},
        'layout': 'compact',
        'sources': ['docs', 'tickets'],
        'banner': 'How can we help?',
        'brand': 'Acme',
        'support_prompt': 'Help @{brand}@ customers with {{topic}}.',
        # These flags deliberately have no native Python declaration.
        'citations': True,
        'voice': 'friendly',
        'reply_budget': 256,
        'temperature': 0.2,
        'tool_options': {'search': True, 'timeout': 2},
    }
    config = VariablesConfig(variables={name: configured(name, value) for name, value in values.items()})
    assist = config.variables['assist_enabled']
    assist.labels['team'] = LabeledValue(version=1, serialized_value='true')
    assist.overrides = [
        RolloutOverride(conditions=[ValueEquals(attribute='plan', value='team')], rollout=Rollout(labels={'team': 1}))
    ]
    config.variables['layout'].labels['detailed'] = LabeledValue(version=1, serialized_value='"detailed"')
    config.variables['layout'].rollout = Rollout(labels={'live': 0.5, 'detailed': 0.5})
    config.variables['reply_budget'].aliases = ['legacy_reply_budget']
    config.variables['support_prompt'].template_inputs_schema = PromptInputs.model_json_schema()
    return config


def create_app(sdk: logfire.Logfire | None = None) -> FastAPI:
    """Create the demo; an injected instance lets the same app exercise remote delivery."""
    owns_sdk = sdk is None
    if sdk is None:
        sdk = logfire.configure(
            local=True,
            send_to_logfire=False,
            console=False,
            variables=logfire.LocalVariablesOptions(config=demo_config()),
        )
    assist = flag('assist_enabled', default=False, logfire_instance=sdk)
    policy = flag('agent_policy', default=AgentPolicy(), logfire_instance=sdk)
    layout = flag('layout', type=Literal['compact', 'detailed'], default='compact', logfire_instance=sdk)
    sources = flag('sources', type=list[str], default=['docs'], logfire_instance=sdk)
    banner = flag('banner', type=str | None, default=None, logfire_instance=sdk)
    brand = flag('brand', default='Support', logfire_instance=sdk)
    emergency = flag('emergency_shutdown', default=False, logfire_instance=sdk)
    prompt = sdk.template_var('support_prompt', default='Help with {{topic}}.', inputs_type=PromptInputs)
    request_counter = sdk.metric_counter('support.requests', description='Completed support requests')
    provider = LogfireProvider(sdk)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Background initialization lets the app start safely during a configuration outage.
        api.set_provider(provider, domain='support-demo')
        try:
            yield
        finally:
            provider.shutdown()
            if owns_sdk:
                await asyncio.to_thread(sdk.shutdown)

    app = FastAPI(title='Feature flags support demo', lifespan=lifespan)
    client = api.get_client(domain='support-demo')

    @app.post('/support')
    async def support(ticket: Ticket) -> dict[str, Any]:
        attributes = {'plan': ticket.plan}
        with feature_context(ticket.customer_id, attributes=attributes):
            with sdk.span('answer support request', plan=ticket.plan):
                before = assist.value()
                # Yield and cross a thread boundary to exercise request-local context propagation.
                await asyncio.sleep(0)
                after = await asyncio.to_thread(assist.details)
                settings = policy.details()
                experiment = layout.details()
                context = EvaluationContext(targeting_key=ticket.customer_id, attributes=attributes)
                budget = client.get_integer_details('reply_budget', 64, context)
                # Legacy template telemetry includes its targeting key. This shared prompt needs
                # service-level targeting, not the customer's identity used by the flags.
                rendered = prompt.get(PromptInputs(topic=ticket.topic), targeting_key='support-service').value
                request_counter.add(1, attributes)
                sdk.info('Support request completed', assisted=after.value, variant=experiment.variant)
                return {
                    'assisted': after.value and not emergency.value(),
                    'assisted_before_yield': before,
                    'assist_reason': after.reason,
                    'model': settings.value.model,
                    'max_documents': settings.value.max_documents,
                    'policy_error': settings.error_code,
                    'layout': experiment.value,
                    'layout_reason': experiment.reason,
                    'variant': experiment.variant,
                    'sources': sources.value(),
                    'banner': banner.value(),
                    'brand': brand.value(),
                    'prompt': rendered,
                    'citations': client.get_boolean_value('citations', False, context),
                    'voice': client.get_string_value('voice', 'neutral', context),
                    'reply_budget': budget.value,
                    'budget_reason': budget.reason,
                    'budget_error': budget.error_code,
                    'alias_budget': client.get_integer_value('legacy_reply_budget', 64, context),
                    'temperature': client.get_float_value('temperature', 0.0, context),
                    'tool_options': client.get_object_value('tool_options', {}, context),
                }

    # Request identity and content belong in the targeting context, not captured endpoint arguments.
    sdk.instrument_fastapi(app, request_attributes_mapper=lambda _request, _attributes: {})
    return app


def main() -> None:
    """Serve the local-only demo and its interactive API documentation."""
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
