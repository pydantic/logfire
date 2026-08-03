from functools import wraps
from unittest.mock import patch

from logfire.types import InstrumentMessageTemplateHelper


def test_instrument_message_template_helper() -> None:
    def foo() -> None:
        pass

    @wraps(foo)
    def decorated() -> None:
        foo()

    helper = InstrumentMessageTemplateHelper(decorated)
    assert helper.raw_callable is decorated
    assert helper.callable is foo
    assert helper.name == 'foo'
    assert helper.qualname == 'test_instrument_message_template_helper.<locals>.foo'
    assert helper.module_name == 'tests.test_types'
    assert helper.default_template() == 'Calling tests.test_types.test_instrument_message_template_helper.<locals>.foo'

    with patch('logfire.types.inspect.getmodule', return_value=None):
        helper = InstrumentMessageTemplateHelper(foo)
        assert helper.module_name == ''
        assert helper.default_template() == 'Calling test_instrument_message_template_helper.<locals>.foo'
