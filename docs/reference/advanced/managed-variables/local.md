# Local Variables

For development, testing, or self-hosted deployments, you can configure variables locally using `VariablesConfig`:

```python
import logfire
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
)

variables_config = VariablesConfig(
    variables={
        'support_agent_config': VariableConfig(
            name='support_agent_config',
            latest_version=LatestVersion(
                version=2,
                serialized_value='{"instructions": "...", "model": "...", "temperature": 0.3, "max_tokens": 1000}',
            ),
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value='{"instructions": "...", "model": "...", "temperature": 0.7, "max_tokens": 500}',
                ),
                'canary': LabelRef(
                    version=2,
                    ref='latest',  # Same as latest_version
                ),
            },
            # Default: everyone gets 'production'
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[
                # Enterprise users get 'canary'
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(labels={'canary': 1.0}),
                ),
            ],
            json_schema={'type': 'object'},
        ),
    }
)

logfire.configure(
    variables=logfire.LocalVariablesOptions(config=variables_config),
)
```

**When to use local variables:**

- **Development**: Test different configurations without connecting to Logfire
- **Testing**: Use fixed configurations in your test suite
- **Self-hosted**: Full control over variable configuration without external dependencies
- **Optimization harnesses**: Build automated optimization loops that monitor performance metrics and programmatically update variable values

The local provider exposes methods to create, update, and delete variables programmatically. This makes it possible to build optimization harnesses that:

1. Run your application with different configurations
2. Collect performance metrics from traces
3. Use the metrics to decide on new configurations to try
4. Create new versions and move labels via the local provider's API
5. Repeat until optimal configuration is found

This workflow is particularly useful for automated prompt optimization, where you want to systematically explore different prompt variations and measure their effectiveness.
