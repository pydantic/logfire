from importlib import util


def main() -> None:
    """Smoke-test native feature flags without the optional OpenFeature adapter."""
    if util.find_spec('openfeature') is not None:
        raise AssertionError('logfire[feature-flags] must not install openfeature-sdk')

    import logfire
    from logfire.experimental.feature_flags import flag

    logfire.configure(send_to_logfire=False, console=False)
    details = flag('deployment_region', default='us').details()
    assert details.value == 'us', 'A native flag must return its code default without a provider'
    assert details.reason == 'default', 'Evaluation must identify the code-default fallback'


if __name__ == '__main__':
    main()
