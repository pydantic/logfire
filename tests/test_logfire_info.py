from unittest.mock import Mock, patch

import pytest

import logfire


@pytest.mark.parametrize('name', ['Typing_Extensions', 'typing.extensions', 'TYPING-EXTENSIONS'])
def test_logfire_info_normalizes_distribution_names(name: str) -> None:
    distribution = Mock(metadata={'Name': name, 'Version': '1.2.3'})
    with patch('importlib.metadata.distributions', return_value=[distribution]):
        report = logfire.logfire_info()

    assert f'{name}="1.2.3"' in report
