# A/B Testing Configurations

Here's a complete example showing how to A/B test two complete agent configurations. In this example, we use local configuration for development — in production, you'd create the versions and labels in the Logfire UI instead.

```python skip="true"
from pydantic import BaseModel
from pydantic_ai import Agent

import logfire
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

logfire.configure()


class AgentConfig(BaseModel):
    """Configuration for a customer support agent."""

    instructions: str
    model: str
    temperature: float
    max_tokens: int


# For local development/testing, you can define versions and labels in code.
# In production, you'd configure these in the Logfire UI.
variables_config = VariablesConfig(
    variables={
        'support_agent_config': VariableConfig(
            name='support_agent_config',
            # The latest version (what traffic gets if no label matches)
            latest_version=LatestVersion(
                version=2,
                serialized_value="""{
                    "instructions": "You are an expert support agent. Provide thorough explanations with examples. Always acknowledge the customer's concern before providing assistance.",
                    "model": "openai:gpt-4o",
                    "temperature": 0.3,
                    "max_tokens": 800
                }""",
            ),
            # Labels pointing to specific versions
            labels={
                'control': LabeledValue(
                    version=1,
                    serialized_value="""{
                        "instructions": "You are a helpful support agent. Be brief and direct.",
                        "model": "openai:gpt-4o-mini",
                        "temperature": 0.7,
                        "max_tokens": 300
                    }""",
                ),
                'treatment': LabelRef(
                    version=2,
                    ref='latest',  # Points to the same value as latest_version
                ),
            },
            # 50/50 A/B test between control and treatment
            rollout=Rollout(labels={'control': 0.5, 'treatment': 0.5}),
            overrides=[],
            json_schema={
                'type': 'object',
                'properties': {
                    'instructions': {'type': 'string'},
                    'model': {'type': 'string'},
                    'temperature': {'type': 'number'},
                    'max_tokens': {'type': 'integer'},
                },
            },
        ),
    }
)

logfire.configure(
    variables=logfire.LocalVariablesOptions(config=variables_config),
)

# Define the variable
agent_config = logfire.var(
    name='support_agent_config',
    type=AgentConfig,
    default=AgentConfig(
        instructions='You are a helpful assistant.',
        model='openai:gpt-4o-mini',
        temperature=0.7,
        max_tokens=500,
    ),
)


async def handle_ticket(user_id: str, message: str) -> str:
    """Handle a support ticket with A/B tested configuration."""
    with agent_config.get(targeting_key=user_id) as config:
        # The label (control or treatment) and version are now in baggage.
        # All spans created below will be tagged with this info.

        agent = Agent(config.value.model, system_prompt=config.value.instructions)
        result = await agent.run(
            message,
            model_settings={
                'temperature': config.value.temperature,
                'max_tokens': config.value.max_tokens,
            },
        )
        return result.output
```

**Analyzing the A/B test in Logfire:**

After running traffic through both labels, you can:

1. Filter traces by the label baggage to see only requests that used a specific version
2. Compare metrics like response latency, token usage, and error rates between labels
3. Look at actual responses to qualitatively assess which configuration performs better
4. Make data-driven decisions about which version to promote to all traffic
