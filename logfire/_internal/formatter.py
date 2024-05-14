from __future__ import annotations

import ast
import inspect
import sys
import types
import warnings
from functools import lru_cache
from string import Formatter
from types import CodeType
from typing import Any, Final, Literal, Mapping

import executing
from typing_extensions import NotRequired, TypedDict

import logfire
from logfire._internal.stack_info import get_user_frame_and_stacklevel

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
        fstring_frame: types.FrameType | None = None,
    ) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str]:
        # Returns
        # 1. A list of chunks
        # 2. A dictionary of extra attributes to add to the span/log.
        #      These can come from evaluating values in f-strings.
        # 3. The final message template, which may differ from `format_string` if it was an f-string.
        if fstring_frame:
            result = self._fstring_chunks(kwargs, scrubber, fstring_frame)
            if result:  # returns None if failed
                return result

        chunks = self._vformat_chunks(
            format_string,
            kwargs=kwargs,
            scrubber=scrubber,
        )
        # When there's no f-string magic, there's no extra attributes or changes in the template string.
        return chunks, {}, format_string

    def _fstring_chunks(
        self,
        kwargs: Mapping[str, Any],
        scrubber: Scrubber,
        frame: types.FrameType,
    ) -> tuple[list[LiteralChunk | ArgChunk], dict[str, Any], str] | None:
        # `frame` is the frame of the method that's being called by the user,
        # so that we can tell if `logfire.log` is being called.
        called_code = frame.f_code
        frame = frame.f_back  # type: ignore
        # Now `frame` is the frame where the user called a logfire method.
        assert frame is not None

        # This is where the magic happens. It has caching.
        ex = executing.Source.executing(frame)

        call_node = ex.node
        if call_node is None:  # type: ignore[reportUnnecessaryComparison]
            # `executing` failed to find a node.
            # This shouldn't happen in most cases, but it's best not to rely on it always working.
            if not ex.source.text:
                # This is a very likely cause.
                # There's nothing we could possibly do to make magic work here,
                # and it's a clear case where the user should turn the magic off.
                warn_inspect_arguments(
                    'No source code available. '
                    'This happens when running in an interactive shell, '
                    'using exec(), or running .pyc files without the source .py files.',
                    get_stacklevel(frame),
                )
                return None

            msg = '`executing` failed to find a node.'
            if sys.version_info[:2] < (3, 11):
                # inspect_arguments is only on be default for 3.11+ for this reason.
                # The AST modifications made by auto-tracing and @instrument
                # mean that the bytecode doesn't match the source code seen by `executing`.
                # In 3.11+, a different algorithm is used by `executing` which can deal with this.
                msg += (
                    ' This may be caused by a combination of using Python < 3.11 '
                    'and auto-tracing or @logfire.instrument.'
                )

            # Try a simple fallback heuristic to find the node which should work in most cases.
            main_nodes: list[ast.AST] = []
            for statement in ex.statements:
                if isinstance(statement, ast.With):
                    # Only look at the 'header' of a with statement, not its body.
                    main_nodes += statement.items
                else:
                    main_nodes.append(statement)
            call_nodes = [
                node
                for main_node in main_nodes
                for node in ast.walk(main_node)
                if isinstance(node, ast.Call)
                if node.args or node.keywords
            ]
            if len(call_nodes) != 1:
                warn_inspect_arguments(msg, get_stacklevel(frame))
                return None

            [call_node] = call_nodes

        if not isinstance(call_node, ast.Call):  # pragma: no cover
            # Very unlikely.
            warn_inspect_arguments(
                '`executing` unexpectedly identified a non-Call node.',
                get_stacklevel(frame),
            )
            return None

        if called_code == logfire.Logfire.log.__code__:
            # The `log` method is a bit different from the others:
            # the argument that might be the f-string is the second argument and it can be named.
            if len(call_node.args) >= 2:
                arg_node = call_node.args[1]
            else:
                # Find the arg named 'msg_template'
                for keyword in call_node.keywords:
                    if keyword.arg == 'msg_template':
                        arg_node = keyword.value
                        break
                else:
                    warn_inspect_arguments(
                        "Couldn't identify the `msg_template` argument in the call.",
                        get_stacklevel(frame),
                    )
                    return None
        elif call_node.args:
            arg_node = call_node.args[0]
        else:
            # Very unlikely.
            warn_inspect_arguments(
                "Couldn't identify the `msg_template` argument in the call.",
                get_stacklevel(frame),
            )
            return None

        if not isinstance(arg_node, ast.JoinedStr):
            # Not an f-string, not a problem.
            # Just use normal formatting.
            return None

        # We have an f-string AST node.
        # Now prepare the namespaces that we will use to evaluate the components.
        global_vars = frame.f_globals
        local_vars = {**frame.f_locals}
        # Add any values in kwargs (i.e. attributes) to `local_vars` so that they take precedence.
        # Warn the user if there's a conflict.
        for kwarg_name, kwarg_value in kwargs.items():
            # Check the same namespaces that Python uses, in the same order.
            for namespace in (local_vars, global_vars, frame.f_builtins):
                if kwarg_name in namespace:
                    # No need to warn if they just passed the same value as an attribute, e.g. `foo=foo`.
                    if namespace[kwarg_name] is not kwarg_value:
                        warnings.warn(
                            f'The attribute {kwarg_name!r} has the same name as a variable with a different value. '
                            f'Using the attribute.',
                            stacklevel=get_stacklevel(frame),
                        )
                    # No need to check the other namespaces either way,
                    # since the earlier namespaces take precedence even in normal variable lookups.
                    break
            # Set the attribute value regardless of whether it's also an existing variable.
            local_vars[kwarg_name] = kwarg_value

        # Now for the actual formatting!
        result: list[LiteralChunk | ArgChunk] = []

        # We construct the message template (i.e. the span name) from the AST.
        # We don't use the source code of the f-string because that gets messy
        # if there's escaped quotes or implicit joining of adjacent strings.
        new_template = ''

        extra_attrs: dict[str, Any] = {}
        for node_value in arg_node.values:
            if isinstance(node_value, ast.Constant):
                # These are the parts of the f-string not enclosed by `{}`, e.g. 'foo ' in f'foo {bar}'
                value = node_value.value
                assert type(value) is str  # noqa
                result.append({'v': value, 't': 'lit'})
                new_template += value
            else:
                # These are the parts of the f-string enclosed by `{}`, e.g. 'bar' in f'foo {bar}'
                assert isinstance(node_value, ast.FormattedValue)

                # This is cached.
                source, value_code, formatted_code = compile_formatted_value(node_value, ex.source)

                # Note that this doesn't include:
                # - The format spec, e.g. `:0.2f`
                # - The conversion, e.g. `!r`
                # - The '=' sign within the braces, e.g. `{bar=}`.
                #     The AST represents f'{bar = }' as f'bar = {bar}' which is how the template will look.
                new_template += '{' + source + '}'

                # The actual value of the expression.
                value = eval(value_code, global_vars, local_vars)
                extra_attrs[source] = value

                # Format the value according to the format spec, converting to a string.
                formatted = eval(formatted_code, global_vars, {**local_vars, '@fvalue': value})
                formatted = self._clean_value(source, formatted, scrubber)
                result.append({'v': formatted, 't': 'arg'})

        return result, extra_attrs, new_template

    def _vformat_chunks(
        self,
        format_string: str,
        kwargs: Mapping[str, Any],
        *,
        scrubber: Scrubber,
        recursion_depth: int = 2,
        auto_arg_index: int = 0,
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
                        _frame, stacklevel = get_user_frame_and_stacklevel()
                        warnings.warn(f"The field '{field}' is not defined.", stacklevel=stacklevel)

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


def logfire_format(format_string: str, kwargs: dict[str, Any], scrubber: Scrubber) -> str:
    result, _extra_attrs, _new_template = logfire_format_with_magic(
        format_string,
        kwargs,
        scrubber,
    )
    return result


def logfire_format_with_magic(
    format_string: str,
    kwargs: dict[str, Any],
    scrubber: Scrubber,
    fstring_frame: types.FrameType | None = None,
) -> tuple[str, dict[str, Any], str]:
    # Returns
    # 1. The formatted message.
    # 2. A dictionary of extra attributes to add to the span/log.
    #      These can come from evaluating values in f-strings.
    # 3. The final message template, which may differ from `format_string` if it was an f-string.
    chunks, extra_attrs, new_template = chunks_formatter.chunks(
        format_string,
        kwargs,
        scrubber=scrubber,
        fstring_frame=fstring_frame,
    )
    return ''.join(chunk['v'] for chunk in chunks), extra_attrs, new_template


@lru_cache
def compile_formatted_value(node: ast.FormattedValue, ex_source: executing.Source) -> tuple[str, CodeType, CodeType]:
    """Returns three things that can be expensive to compute.

    1. Source code corresponding to the node value (excluding the format spec).
    2. A compiled code object which can be evaluated to calculate the value.
    3. Another code object which formats the value.
    """
    source = get_node_source_text(node.value, ex_source)
    value_code = compile(source, '<fvalue1>', 'eval')
    expr = ast.Expression(
        ast.JoinedStr(
            values=[
                # Similar to the original FormattedValue node,
                # but replace the actual expression with a simple variable lookup
                # so that it the expression doesn't need to be evaluated again.
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
    This happens sometimes due to Python bugs (especially for older Python versions)
    in the source positions of AST nodes inside f-strings.
    """
    # ast.unparse is not available in Python 3.8, which is why inspect_arguments is forbidden in 3.8.
    source_unparsed = ast.unparse(node)
    source_segment = ast.get_source_segment(ex_source.text, node) or ''
    try:
        # Verify that the source segment is correct by checking that the AST is equivalent to what we have.
        source_segment_unparsed = ast.unparse(ast.parse(source_segment, mode='eval'))
    except Exception:  # probably SyntaxError, but ast.parse can raise other exceptions too
        source_segment_unparsed = ''
    return source_segment if source_unparsed == source_segment_unparsed else source_unparsed


def get_stacklevel(frame: types.FrameType):
    # Get a stacklevel which can be passed to warn_inspect_arguments
    # which points at the given frame, where the f-string was found.
    current_frame = inspect.currentframe()
    stacklevel = 0
    while current_frame:  # pragma: no branch
        if current_frame == frame:
            break
        stacklevel += 1
        current_frame = current_frame.f_back
    return stacklevel


class InspectArgumentsFailedWarning(Warning):
    pass


def warn_inspect_arguments(msg: str, stacklevel: int):
    msg = (
        'Failed to introspect calling code. '
        'Please report this issue to Logfire. '
        'Falling back to normal message formatting '
        'which may result in loss of information if using an f-string. '
        'Set inspect_arguments=False in logfire.configure() to suppress this warning. '
        'The problem was:\n'
    ) + msg
    warnings.warn(msg, InspectArgumentsFailedWarning, stacklevel=stacklevel)
    logfire.log('warn', msg)
