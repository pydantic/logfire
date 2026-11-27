from __future__ import annotations

import traceback
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from logfire._internal.scrubbing import NOOP_SCRUBBER, JsonPath, ScrubbedNote, Scrubber
from logfire._internal.validation_errors import _hides_input, replace_validation_errors, scrubbed_validation_error  # pyright: ignore[reportPrivateUsage]

PATH = ('attributes', 'exception.logfire.data')


def test_scrubbed_validation_error() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)
        age: int

    password = 'hunter2'
    try:
        Login.model_validate({'password': password, 'age': 'bad'})
    except ValidationError as original:
        original.add_note('safe note')
        rebuilt = scrubbed_validation_error(original, Scrubber(None), PATH)
        assert rebuilt is not None
        assert password not in str(rebuilt)
        assert "[Scrubbed due to 'password']" in str(rebuilt)
        assert "input_value='bad'" in str(rebuilt)
        assert rebuilt.__traceback__ is original.__traceback__
        assert rebuilt.__notes__ == ['safe note']
        assert rebuilt.__notes__ is not original.__notes__
        assert scrubbed_validation_error(original, NOOP_SCRUBBER, PATH) is None
        assert password in str(original)
    else:
        raise AssertionError('Expected validation to fail')


def test_hidden_input_stays_hidden() -> None:
    class Login(BaseModel):
        model_config = ConfigDict(hide_input_in_errors=True)
        password: str = Field(min_length=12)

    try:
        Login(password='hunter2')
    except ValidationError as original:
        rebuilt = scrubbed_validation_error(original, Scrubber(None), PATH)
        assert rebuilt is not None
        assert 'input_value=' not in str(rebuilt)
    else:
        raise AssertionError('Expected validation to fail')


def test_custom_error_rebuilds() -> None:
    class Login(BaseModel):
        password: str

        @field_validator('password')
        @classmethod
        def reject(cls, value: str) -> str:
            raise PydanticCustomError('weak_value', 'Weak {kind}', {'kind': 'value'})

    try:
        Login(password='hunter2')
    except ValidationError as original:
        rebuilt = scrubbed_validation_error(original, Scrubber(None), PATH)
        assert rebuilt is not None
        assert 'hunter2' not in str(rebuilt)
        assert 'Weak value' in str(rebuilt)
        assert 'weak_value' in str(rebuilt)
        original.__reduce__ = lambda: (ValidationError, ())
        assert _hides_input(original, cast('list[dict[str, Any]]', original.errors(include_url=False))) is False
    else:
        raise AssertionError('Expected validation to fail')


def test_hidden_input_with_custom_message_mentioning_input_value() -> None:
    class Login(BaseModel):
        model_config = ConfigDict(hide_input_in_errors=True)
        password: str
        pin: str = Field(min_length=10)

        @field_validator('password')
        @classmethod
        def reject(cls, value: str) -> str:
            raise PydanticCustomError('weak_password', '[type=x, input_value=x, input_type=str]')

    try:
        Login(password='hunter2', pin='1234')
    except ValidationError as original:
        rebuilt = scrubbed_validation_error(original, Scrubber(['^pin$']), PATH)
        assert rebuilt is not None
        assert '[type=x, input_value=x, input_type=str]' in str(rebuilt)
        assert 'hunter2' not in str(rebuilt)
        assert '1234' not in str(rebuilt)
        assert 'input_value="' not in str(rebuilt)
    else:
        raise AssertionError('Expected validation to fail')


def test_older_pydantic_hidden_input_fallback() -> None:
    for hidden in (False, True):

        class Login(BaseModel):
            model_config = ConfigDict(hide_input_in_errors=hidden)
            password: str = Field(min_length=12)

        try:
            Login(password='hunter2')
        except ValidationError as original:
            # Pydantic 2.4 returns no reduction arguments.
            original.__reduce__ = lambda: (ValidationError, ())
            assert _hides_input(original, cast('list[dict[str, Any]]', original.errors(include_url=False))) is hidden
            assert _hides_input(original, [{}]) is True
        else:
            raise AssertionError('Expected validation to fail')

    class UnmatchableError:
        title = 'Login'

        def __reduce__(self) -> tuple[Any, ...]:
            return ValidationError, ()

        def __str__(self) -> str:
            return 'unmatchable'

    assert (
        _hides_input(
            cast(ValidationError, UnmatchableError()),
            [
                {
                    'type': 'string_too_short',
                    'loc': ('password',),
                    'msg': 'String should have at least 12 characters',
                    'input': 'hunter2',
                    'ctx': {'min_length': 12},
                }
            ],
        )
        is True
    )

    class UnreducibleError(UnmatchableError):
        def __reduce__(self) -> tuple[Any, ...]:
            raise ValueError('cannot inspect reduction')

    assert _hides_input(cast(ValidationError, UnreducibleError()), []) is True


def test_invalid_scrubber_result_falls_back() -> None:
    class InvalidScrubber(Scrubber):
        def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:
            return {'input': 'changed'}, []

    class Login(BaseModel):
        password: str = Field(min_length=12)

    try:
        Login(password='hunter2')
    except ValidationError as original:
        assert scrubbed_validation_error(original, InvalidScrubber(None), PATH) is None
    else:
        raise AssertionError('Expected validation to fail')


def test_invalid_rebuilt_error_falls_back() -> None:
    class InvalidScrubber(Scrubber):
        def scrub_value(self, path: JsonPath, value: Any) -> tuple[Any, list[ScrubbedNote]]:
            return [{'input': 'changed'}], []

    class Login(BaseModel):
        password: str = Field(min_length=12)

    try:
        Login(password='hunter2')
    except ValidationError as original:
        assert scrubbed_validation_error(original, InvalidScrubber(None), PATH) is None
    else:
        raise AssertionError('Expected validation to fail')


def test_replaces_explicit_chain_without_mutating_it() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    class AppError(Exception):
        def __init__(self, *, message: str) -> None:
            super().__init__(message)

    password = 'hunter2'
    try:
        try:
            Login(password=password)
        except ValidationError as error:
            raise AppError(message='login failed') from error
    except AppError as original:
        original.add_note('safe note')
        rebuilt = replace_validation_errors(original, Scrubber(None), PATH)
        assert rebuilt is not original
        assert rebuilt.__cause__ is not original.__cause__
        assert rebuilt.__notes__ == ['safe note']
        assert rebuilt.__notes__ is not original.__notes__
        assert password not in ''.join(traceback.format_exception(rebuilt))
        assert password in ''.join(traceback.format_exception(original))
        assert len(traceback.format_exception(rebuilt)) == len(traceback.format_exception(original))
        assert traceback.format_exception(rebuilt)[-1] == traceback.format_exception(original)[-1]
        assert replace_validation_errors(original, NOOP_SCRUBBER, PATH) is original
    else:
        raise AssertionError('Expected application error')


def test_replaces_implicit_context_and_group() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    password = 'hunter2'
    try:
        try:
            Login(password=password)
        except ValidationError:
            raise RuntimeError('login failed')
    except RuntimeError as original:
        group = ExceptionGroup('errors', [original, ValueError('safe')])
        rebuilt = replace_validation_errors(group, Scrubber(None), PATH)
        assert rebuilt is not group
        assert isinstance(rebuilt, ExceptionGroup)
        children = cast('ExceptionGroup[Exception]', rebuilt).exceptions
        assert children[0].__context__ is not original.__context__
        assert children[1] is group.exceptions[1]
        assert password not in ''.join(traceback.format_exception(cast(BaseException, rebuilt)))
        assert original.__context__ is not None
        assert 'hunter2' in str(original.__context__)
    else:
        raise AssertionError('Expected application error')


def test_cycle_does_not_mutate_original() -> None:
    outer = RuntimeError('outer')
    outer.__cause__ = outer
    assert replace_validation_errors(outer, Scrubber(None), PATH) is outer
    assert outer.__cause__ is outer


def test_repeated_error_in_group_is_scrubbed_everywhere() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    password = 'hunter2'
    try:
        try:
            Login(password=password)
        except ValidationError as error:
            raise ExceptionGroup('errors', [error])
    except ExceptionGroup as original:
        rebuilt = replace_validation_errors(original, Scrubber(None), PATH)
        assert password not in ''.join(traceback.format_exception(rebuilt))
        assert password in ''.join(traceback.format_exception(original))
    else:
        raise AssertionError('Expected exception group')


def test_native_exception_cause_is_scrubbed() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    password = 'hunter2'
    try:
        try:
            Login(password=password)
        except ValidationError as error:
            raise OSError('login failed') from error
    except OSError as original:
        rebuilt = replace_validation_errors(original, Scrubber(None), PATH)
        assert rebuilt is not original
        assert isinstance(rebuilt.__cause__, ValidationError)
        assert rebuilt.__cause__ is not original.__cause__
        assert password not in ''.join(traceback.format_exception(rebuilt))
        assert password in ''.join(traceback.format_exception(original))
    else:
        raise AssertionError('Expected operating system error')


def test_keyword_only_new_exception_cause_is_scrubbed() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    class AppError(Exception):
        def __new__(cls, *, code: int) -> AppError:
            return super().__new__(cls)

        def __init__(self, *, code: int) -> None:
            super().__init__(f'login failed: {code}')

    password = 'hunter2'
    try:
        try:
            Login(password=password)
        except ValidationError as error:
            raise AppError(code=401) from error
    except AppError as original:
        rebuilt = replace_validation_errors(original, Scrubber(None), PATH)
        assert rebuilt is not original
        assert isinstance(rebuilt.__cause__, ValidationError)
        assert password not in ''.join(traceback.format_exception(rebuilt))
    else:
        raise AssertionError('Expected application error')


def test_uncomparable_input_does_not_cancel_other_redactions() -> None:
    class Uncomparable:
        def __eq__(self, other: object) -> bool:
            raise ValueError('cannot compare')

    class Login(BaseModel):
        name: str
        password: str = Field(min_length=12)

    password = 'hunter2'
    try:
        Login.model_validate({'name': Uncomparable(), 'password': password})
    except ValidationError as original:
        rebuilt = scrubbed_validation_error(original, Scrubber(None), PATH)
        assert rebuilt is not None
        assert password not in str(rebuilt)
        assert "[Scrubbed due to 'password']" in str(rebuilt)
    else:
        raise AssertionError('Expected validation to fail')


def test_uncloneable_exception_keeps_original_chain() -> None:
    class Login(BaseModel):
        password: str = Field(min_length=12)

    class StrictOSError(OSError):
        def __new__(cls, *, code: int) -> StrictOSError:
            return super().__new__(cls, f'failed: {code}')

        def __init__(self, *, code: int) -> None:
            super().__init__(f'failed: {code}')

    try:
        try:
            Login(password='hunter2')
        except ValidationError as error:
            raise StrictOSError(code=401) from error
    except StrictOSError as original:
        assert replace_validation_errors(original, Scrubber(None), PATH) is original
    else:
        raise AssertionError('Expected operating system error')
