from __future__ import annotations

import ast
import inspect
import types
import warnings
from functools import lru_cache
from string import Formatter
from types import CodeType
from typing import Any, Final, Literal, Mapping

import executing
from typing_extensions import NotRequired, TypedDict

import logfire

from .constants import MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT
from .scrubbing import Scrubber
from .utils import truncate_string

__all__ = 'chunks_formatter', 'LiteralChunk', 'ArgChunk', 'logfire_format'


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
        fstring_frame: types.FrameType | None = None,
    ) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str]:
        if fstring_frame:
            result = self._fstring_chunks(kwargs, scrubber, fstring_frame)
            if result:
                return result

        chunks = self._vformat_chunks(
            format_string,
            kwargs=kwargs,
            scrubber=scrubber,
            stack_offset=stack_offset + 1,
        )
        return chunks, {}, format_string

    def _fstring_chunks(
        self,
        kwargs: Mapping[str, Any],
        scrubber: Scrubber,
        frame: types.FrameType,
    ) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str] | None:
        called_code = frame.f_code
        frame = frame.f_back  # type: ignore
        assert frame is not None

        ex = executing.Source.executing(frame)
        if not ex.source.tree:
            return None

        call_node = ex.node
        if call_node is None:  # type: ignore[reportUnnecessaryComparison]
            if len(ex.statements) != 1:
                return None

            [statement] = ex.statements
            if isinstance(statement, ast.Expr):
                call_node = statement.value
            elif isinstance(statement, ast.With) and len(statement.items) == 1:
                call_node = statement.items[0].context_expr
            if not (
                call_node and [child for child in ast.walk(call_node) if isinstance(child, ast.Call)] == [call_node]
            ):
                return None

        if not isinstance(call_node, ast.Call):
            return None

        if called_code == logfire.Logfire.log.__code__:
            if len(call_node.args) >= 2:
                arg_node = call_node.args[1]
            else:
                # Find the arg named 'msg_template'
                for keyword in call_node.keywords:
                    if keyword.arg == 'msg_template':
                        arg_node = keyword.value
                        break
                else:
                    return None
        elif call_node.args:
            arg_node = call_node.args[0]
        else:
            return None

        if not isinstance(arg_node, ast.JoinedStr):
            return None

        result: list[LiteralChunk | ArgChunk] = []
        new_template = ''
        extra_attrs: dict[str, Any] = {}
        globs = frame.f_globals
        locs = {**frame.f_locals}
        for k, v in kwargs.items():
            for ns in (locs, globs):
                if k in ns:
                    if ns[k] is not v:
                        warnings.warn(
                            f'The attribute {k!r} has the same name as a variable with a different value. '
                            f'Using the attribute.',
                            stacklevel=get_stacklevel(frame),
                        )
                    break
            locs[k] = v

        locs = {**frame.f_locals, **kwargs}
        for node_value in arg_node.values:
            if isinstance(node_value, ast.Constant):
                assert isinstance(node_value.value, str)
                result.append({'v': node_value.value, 't': 'lit'})
                new_template += node_value.value
            elif isinstance(node_value, ast.FormattedValue):
                source, value_code, formatted_code = compile_formatted_value(node_value, ex.source)
                value = eval(value_code, globs, locs)
                formatted = eval(formatted_code, globs, {**locs, '@fvalue': value})
                formatted = self._clean_value(source, formatted, scrubber)
                result.append({'v': formatted, 't': 'arg'})
                new_template += '{' + source + '}'
                extra_attrs[source] = value

        return result, extra_attrs, new_template

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
                    obj, _arg_used = self.get_field(field_name, args, kwargs)
                except KeyError as exc:
                    try:
                        # fall back to getting a key with the dots in the name
                        obj = kwargs[field_name]
                    except KeyError:
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
                    value = self._clean_value(field_name, value, scrubber)
                d: ArgChunk = {'v': value, 't': 'arg'}
                if format_spec:
                    d['spec'] = format_spec
                result.append(d)

        return result

    def _clean_value(self, field_name: str, value: str, scrubber: Scrubber) -> str:
        # Scrub before truncating so that the scrubber can see the full value.
        # For example, if the value contains 'password=123' and 'password' is replaced by '...'
        # because of truncation, then that leaves '=123' in the message, which is not good.
        if field_name not in scrubber.SAFE_KEYS:
            value = scrubber.scrub(('message', field_name), value)
        return truncate_string(value, max_length=MESSAGE_FORMATTED_VALUE_LENGTH_LIMIT)


chunks_formatter = ChunksFormatter()


def logfire_format(format_string: str, kwargs: dict[str, Any], scrubber: Scrubber, stack_offset: int = 3) -> str:
    result, _frame_vars, _span_name = logfire_format_with_magic(
        format_string,
        kwargs,
        scrubber,
        stack_offset + 1,
    )
    return result


def logfire_format_with_magic(
    format_string: str,
    kwargs: dict[str, Any],
    scrubber: Scrubber,
    stack_offset: int = 3,
    fstring_frame: types.FrameType | None = None,
) -> tuple[str, dict[str, Any], str]:
    """Return the formatted string and any frame variables that were used in the formatting."""
    chunks, extra_attrs, new_template = chunks_formatter.chunks(
        format_string,
        kwargs,
        scrubber=scrubber,
        stack_offset=stack_offset,
        fstring_frame=fstring_frame,
    )
    return ''.join(chunk['v'] for chunk in chunks), extra_attrs, new_template


@lru_cache
def compile_formatted_value(node: ast.FormattedValue, ex_source: executing.Source) -> tuple[str, CodeType, CodeType]:
    """Returns three things that can be expensive to compute.

    1. Source code corresponding to the node value.
    2. A compiled code object which can be evaluated to calculate the value.
    3. Another code object which formats the value.
    """
    source = get_node_source_text(node.value, ex_source)
    value_code = compile(source, '<fvalue1>', 'eval')
    expr = ast.Expression(
        ast.JoinedStr(
            values=[
                # Similar to the original FormattedValue node,
                # but replace the actual expression with a simple variable lookup.
                # Use @ in the variable name so that it can't possibly conflict
                # with a normal variable.
                # The value of this variable will be provided in the eval() call
                # and will come from evaluating value_code above.
                ast.FormattedValue(
                    value=ast.Name(id='@fvalue', ctx=ast.Load()),
                    conversion=node.conversion,
                    format_spec=node.format_spec,
                )
            ]
        )
    )
    ast.fix_missing_locations(expr)
    formatted_code = compile(expr, '<fvalue2>', 'eval')
    return source, value_code, formatted_code


def get_node_source_text(node: ast.AST, ex_source: executing.Source):
    """Returns some Python source code representing `node`.

    Preferably the actual original code given by `ast.get_source_segment`,
    but falling back to `ast.unparse(node)` if the former is incorrect.
    """
    source_unparsed = ast.unparse(node)
    source_segment = ast.get_source_segment(ex_source.text, node) or ''
    try:
        source_segment_unparsed = ast.unparse(ast.parse(source_segment, mode='eval'))
    except Exception:
        source_segment_unparsed = ''
    return source_segment if source_unparsed == source_segment_unparsed else source_unparsed


def get_stacklevel(frame: types.FrameType):
    current_frame = inspect.currentframe()
    stacklevel = 0
    while current_frame:
        if current_frame == frame:
            break
        stacklevel += 1
        current_frame = current_frame.f_back
    return stacklevel
