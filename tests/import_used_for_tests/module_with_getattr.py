# See test_dynamic_module_ignored_in_ensure_flush_after_aws_lambda


def __getattr__(name: str) -> str:
    return name
