from __future__ import annotations

import inspect
import types
import warnings
from string import Formatter
from typing import Any, Final, Literal, Mapping

from typing_extensions import NotRequired, TypedDict

__all__ = 'chunks_formatter', 'LiteralChunk', 'ArgChunk', 'logfire_format'

from .constants import MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT
from .scrubbing import Scrubber
from .utils import truncate_string


class LiteralChunk(TypedDict):
    t: Literal['lit']
    v: str


class ArgChunk(TypedDict):
    t: Literal['arg']
    v: str
    spec: NotRequired[str]


class ChunksFormatter(Formatter):
    NONE_REPR: Final[str] = 'null'

    def chunks(
        self,
        format_string: str,
        kwargs: Mapping[str, Any],
        *,
        scrubber: Scrubber,
        stack_offset: int = 3,
        use_frame_vars: bool,
    ) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any]]:
        if use_frame_vars:
            frame = inspect.currentframe()
            for _ in range(stack_offset - 1):
                if frame:  # pragma: no branch
                    frame = frame.f_back
        else:
            frame = None
        lookup = InterceptFrameVars(kwargs, frame)
        chunks = self._vformat_chunks(
            format_string,
            kwargs=lookup,
            scrubber=scrubber,
            stack_offset=stack_offset + 1,
        )
        return chunks, lookup.intercepted

    def _vformat_chunks(
        self,
        format_string: str,
        kwargs: Mapping[str, Any],
        *,
        scrubber: Scrubber,
        recursion_depth: int = 2,
        auto_arg_index: int = 0,
        stack_offset: int = 3,
    ) -> list[LiteralChunk | ArgChunk]:
        """Copied from `string.Formatter._vformat` https://github.com/python/cpython/blob/v3.11.4/Lib/string.py#L198-L247 then altered."""
        if recursion_depth < 0:  # pragma: no cover
            raise ValueError('Max string recursion exceeded')
        result: list[LiteralChunk | ArgChunk] = []
        # here just to satisfy the call to `_vformat` below
        used_args: set[str | int] = set()
        # We currently don't use positional arguments
        args = ()
        for literal_text, field_name, format_spec, conversion in self.parse(format_string):
            # output the literal text
            if literal_text:
                result.append({'v': literal_text, 't': 'lit'})

            # if there's a field, output it
            if field_name is not None:
                # this is some markup, find the object and do
                #  the formatting

                # handle arg indexing when empty field_names are given.
                if field_name == '':  # pragma: no cover
                    if auto_arg_index is False:
                        raise ValueError('cannot switch from manual field specification to automatic field numbering')
                    field_name = str(auto_arg_index)
                    auto_arg_index += 1
                elif field_name.isdigit():  # pragma: no cover
                    if auto_arg_index:
                        raise ValueError('cannot switch from manual field  to automatic field numbering')
                    # disable auto arg incrementing, if it gets
                    # used later on, then an exception will be raised
                    auto_arg_index = False

                # ADDED BY US:
                if field_name.endswith('='):
                    if result and result[-1]['t'] == 'lit':
                        result[-1]['v'] += field_name
                    else:
                        result.append({'v': field_name, 't': 'lit'})
                    field_name = field_name[:-1]

                # we have lots of type ignores here since Formatter is typed as requiring kwargs to be a
                # dict, but we expect `Sequence[dict[str, Any]]` in get_value - effectively `Formatter` is really
                # generic over the type of the kwargs

                # given the field_name, find the object it references
                #  and the argument it came from
                try:
                    # First try looking up directly.
                    # This means that if the fields contain both 'foo.bar' and 'foo' as keys,
                    # the value of 'foo.bar' takes precedence over the attribute 'bar' of 'foo'
                    # since the latter was specified more explicitly.
                    # This is important for the case where 'foo' is the name of a local variable
                    # that the user may not be expecting to be used at all.
                    obj = kwargs[field_name]
                except KeyError:
                    try:
                        # Next try handling attribute/key access, e.g. 'foo.bar' or 'foo[bar]'
                        # where 'foo' is the only field we have.
                        obj, _arg_used = self.get_field(field_name, args, kwargs)
                    except KeyError as exc:
                        obj = '{' + field_name + '}'
                        field = exc.args[0]
                        warnings.warn(f"The field '{field}' is not defined.", stacklevel=stack_offset)

                # do any conversion on the resulting object
                if conversion is not None:
                    obj = self.convert_field(obj, conversion)

                # expand the format spec, if needed
                format_spec, auto_arg_index = self._vformat(
                    format_spec,  # type: ignore[arg-type]
                    args,
                    kwargs,
                    used_args,  # TODO(lig): using `_arg_used` from above seems logical here but needs more thorough testing
                    recursion_depth - 1,
                    auto_arg_index=auto_arg_index,
                )

                if obj is None:
                    value = self.NONE_REPR
                else:
                    value = self.format_field(obj, format_spec)
                    # Scrub before truncating so that the scrubber can see the full value.
                    # For example, if the value contains 'password=123' and 'password' is replaced by '...'
                    # because of truncation, then that leaves '=123' in the message, which is not good.
                    if field_name not in scrubber.SAFE_KEYS:
                        value = scrubber.scrub(('message', field_name), value)
                    value = truncate_string(value, max_length=MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT)
                d: ArgChunk = {'v': value, 't': 'arg'}
                if format_spec:
                    d['spec'] = format_spec
                result.append(d)

        return result


chunks_formatter = ChunksFormatter()


def logfire_format(format_string: str, kwargs: dict[str, Any], scrubber: Scrubber, stack_offset: int = 3) -> str:
    result, _frame_vars = logfire_format_with_frame_vars(
        format_string,
        kwargs,
        scrubber,
        stack_offset + 1,
        # This is called from internal code, so we don't want to use frame variables.
        use_frame_vars=False,
    )
    return result


def logfire_format_with_frame_vars(
    format_string: str, kwargs: dict[str, Any], scrubber: Scrubber, stack_offset: int = 3, use_frame_vars: bool = True
) -> tuple[str, dict[str, Any]]:
    """Return the formatted string and any frame variables that were used in the formatting."""
    chunks, frame_vars = chunks_formatter.chunks(
        format_string,
        kwargs,
        scrubber=scrubber,
        stack_offset=stack_offset,
        use_frame_vars=use_frame_vars,
    )
    return ''.join(chunk['v'] for chunk in chunks), frame_vars


class InterceptFrameVars(Mapping[str, Any]):
    """A mapping that detects when a field needs to be looked up in the frame locals or globals.

    Those fields are then stored in the `intercepted` attribute.

    Args:
        default: The default source of field values.
        frame: The frame to look up fields in when not found in default.
            If this is None, this mapping is mostly equivalent to `default`.
    """

    def __init__(self, default: Mapping[str, Any], frame: types.FrameType | None):
        self.default = default
        self.frame = frame
        self.intercepted: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        if key in self.default:
            return self.default[key]

        if self.frame:
            for ns in (self.frame.f_locals, self.frame.f_globals):
                if key in ns:
                    value = ns[key]
                    self.intercepted[key] = value
                    return value

        raise KeyError(key)

    # The following methods are required to implement the Mapping interface.
    # Their meaning is not well defined in this context,
    # and we don't want/expect them to be called, so we raise NotImplementedError.
    def __iter__(self) -> Any:  # pragma: no cover
        raise NotImplementedError

    def __len__(self) -> Any:  # pragma: no cover
        raise NotImplementedError
