def main() -> None:
    """Smoke-test native feature flags with only the `feature-flags` extra installed."""
    import importlib.util

    assert importlib.util.find_spec('openfeature') is None, 'The feature-flags extra must not install OpenFeature'

    import logfire
    from logfire.experimental.feature_flags import flag

    logfire.configure(send_to_logfire=False, console=False)
    details = flag('deployment_region', default='us').details()
    assert details.value == 'us', 'A native flag must return its code default without a provider'
    assert details.reason == 'default', 'Evaluation must identify the code-default fallback'


if __name__ == '__main__':
    main()
