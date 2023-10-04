from collections.abc import Mapping
from string import Formatter
from typing import Any, Final, Literal

from typing_extensions import NotRequired, TypedDict

from ._flatten import Flatten

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
        recursion_depth: int = 2,
        auto_arg_index: int = 0,
    ) -> list[LiteralChunk | ArgChunk]:
        """
        Copied from `string.Formatter._vformat` https://github.com/python/cpython/blob/v3.11.4/Lib/string.py#L198-L247
        then altered.
        """
        if recursion_depth < 0:
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
                if field_name == '':
                    if auto_arg_index is False:
                        raise ValueError('cannot switch from manual field specification to automatic field numbering')
                    field_name = str(auto_arg_index)
                    auto_arg_index += 1
                elif field_name.isdigit():
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
                obj, _arg_used = self.get_field(field_name, args, kwargs)

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

                # format the object and append to the result
                d: ArgChunk = {'v': self.format_field(obj, format_spec), 't': 'arg'}
                if format_spec:
                    d['spec'] = format_spec
                result.append(d)

        return result

    def format_field(self, value: Any, format_spec: str) -> Any:
        if value is None:
            value = self.NONE_REPR
        if isinstance(value, Flatten):
            value = value.value
        return super().format_field(value, format_spec)


chunks_formatter = ChunksFormatter()


def logfire_format(format_string: str, kwargs: dict[str, Any]) -> str:
    return ''.join(chunk['v'] for chunk in chunks_formatter.chunks(format_string, kwargs))
