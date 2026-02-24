"""Tests for HandlebarsEnvironment and custom helpers."""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnusedFunction=false

from __future__ import annotations

from typing import Any

import pytest

from logfire.handlebars import HandlebarsEnvironment, HelperOptions


class TestEnvironmentCreation:
    def test_create_environment(self) -> None:
        env = HandlebarsEnvironment()
        result = env.render('Hello {{name}}!', {'name': 'World'})
        assert result == 'Hello World!'

    def test_environment_has_builtin_helpers(self) -> None:
        env = HandlebarsEnvironment()
        result = env.render('{{#if val}}yes{{/if}}', {'val': True})
        assert result == 'yes'


class TestRegisterHelper:
    def test_register_helper(self) -> None:
        env = HandlebarsEnvironment()
        env.register_helper('shout', lambda *args, options: str(args[0]).upper() + '!!!')
        result = env.render('{{shout name}}', {'name': 'hello'})
        assert result == 'HELLO!!!'

    def test_unregister_helper(self) -> None:
        env = HandlebarsEnvironment()
        env.register_helper('custom', lambda *args, options: 'custom')
        env.unregister_helper('custom')
        with pytest.raises(KeyError, match='Helper not found'):
            env.unregister_helper('custom')


class TestHelperDecorator:
    def test_decorator_without_name(self) -> None:
        env = HandlebarsEnvironment()

        @env.helper
        def double(val: Any, *args: Any, options: HelperOptions) -> str:
            return str(val) * 2

        result = env.render('{{double name}}', {'name': 'ha'})
        assert result == 'haha'

    def test_decorator_with_name(self) -> None:
        env = HandlebarsEnvironment()

        @env.helper('repeat')
        def _my_repeat(val: Any, *args: Any, options: HelperOptions) -> str:
            return str(val) * 3

        result = env.render('{{repeat name}}', {'name': 'ha'})
        assert result == 'hahaha'


class TestCustomHelperOptions:
    def test_helper_receives_options(self) -> None:
        env = HandlebarsEnvironment()
        received_options: list[HelperOptions] = []

        def capture_helper(*args: Any, options: HelperOptions) -> str:
            received_options.append(options)
            return 'ok'

        env.register_helper('capture', capture_helper)
        env.render('{{capture "arg1" key="value"}}', {})

        assert len(received_options) == 1
        assert received_options[0].hash == {'key': 'value'}

    def test_block_helper_fn_and_inverse(self) -> None:
        env = HandlebarsEnvironment()

        def my_block(context: Any, *args: Any, options: HelperOptions) -> str:
            if args and args[0]:
                return options.fn(context)
            return options.inverse(context)

        env.register_helper('myblock', my_block)

        template = '{{#myblock val}}yes{{else}}no{{/myblock}}'
        assert env.render(template, {'val': True}) == 'yes'
        assert env.render(template, {'val': False}) == 'no'


class TestCompile:
    def test_compile_returns_callable(self) -> None:
        env = HandlebarsEnvironment()
        template = env.compile('{{name}}')
        assert callable(template)
        assert template({'name': 'test'}) == 'test'

    def test_compile_captures_helpers(self) -> None:
        env = HandlebarsEnvironment()
        env.register_helper('exclaim', lambda *args, options: str(args[0]) + '!')
        template = env.compile('{{exclaim name}}')
        assert template({'name': 'hi'}) == 'hi!'


class TestEnvironmentIsolation:
    def test_separate_environments(self) -> None:
        env1 = HandlebarsEnvironment()
        env2 = HandlebarsEnvironment()

        env1.register_helper('greet', lambda *args, options: 'hello')
        env2.register_helper('greet', lambda *args, options: 'bonjour')

        assert env1.render('{{greet}}', {}) == 'hello'
        assert env2.render('{{greet}}', {}) == 'bonjour'
