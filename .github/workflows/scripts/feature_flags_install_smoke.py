from importlib import util


def main() -> None:
    """Smoke-test native feature flags without the optional OpenFeature adapter."""
    if util.find_spec('openfeature') is not None:
        raise AssertionError('logfire[feature-flags] must not install openfeature-sdk')

    import logfire
    from logfire.experimental.feature_flags import flag

    logfire.configure(send_to_logfire=False, console=False)
    details = flag('deployment_region', default='us').details()
    assert details.value == 'us'
    assert details.reason == 'default'


if __name__ == '__main__':
    main()
