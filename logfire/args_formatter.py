import io
from datetime import timedelta
from functools import partial
from typing import Any, Callable, cast


class JsonArgsValueFormatter:
    """Format values recursively based on the information provided in value dict.

    When a custom format is identified, the `$__datatype__` key is always present.
    """

    def __init__(self, indent_step: int = 4):
        self._indent_step = indent_step
        self._c = ' '
        self._data_type_map: dict[str, Callable[[int, Any, str | None], None]] = {
            'BaseModel': partial(self._format_items, ' (\n', '=', ',\n', ')', False),
            'dataclass': partial(self._format_items, ' (\n', '=', ',\n', ')', False),
            'Mapping': partial(self._format_items, '({\n', ': ', ',\n', '})', True),
            'tuple': partial(self._forrmat_list_like, '(\n', ',\n', ')'),
            'Sequence': partial(self._forrmat_sequence, '([\n', ',\n', '])'),
            'set': partial(self._forrmat_list_like, '{\n', ',\n', '}'),
            'frozenset': partial(self._forrmat_list_like, 'frozenset({\n', ',\n', '})'),
            'deque': partial(self._forrmat_list_like, 'deque([\n', ',\n', '])'),
            'bytes': partial(self._write, 'b', '', True),
            'Decimal': partial(self._write, 'Decimal(', ')', True),
            'date': partial(self._write, 'date(', ')', True),
            'datetime': partial(self._write, 'datetime(', ')', True),
            'time': partial(self._write, 'time(', ')', True),
            'enum': partial(self._write, '(', ')', True),
            'IPv4Address': partial(self._write, 'IPv4Address(', ')', True),
            'Url': partial(self._write, 'Url(', ')', True),
            'IPv4Interface': partial(self._write, 'IPv4Interface(', ')', True),
            'IPv4Network': partial(self._write, 'IPv4Network(', ')', True),
            'IPv6Address': partial(self._write, 'IPv6Address(', ')', True),
            'IPv6Interface': partial(self._write, 'IPv6Interface(', ')', True),
            'IPv6Network': partial(self._write, 'IPv6Network(', ')', True),
            'PosixPath': partial(self._write, 'PosixPath(', ')', True),
            'Pattern': partial(self._write, 're.compile(', ')', True),
            'SecretBytes': partial(self._write, 'SecretBytes(', ')', False),
            'SecretStr': partial(self._write, 'SecretStr(', ')', True),
            'UUID': partial(self._write, "UUID('", "')", False),
            'Exception': partial(self._write, '(', ')', True),
            'timedelta': partial(self._forrmat_timedelta),
        }

    def __call__(self, value: Any, *, indent: int = 0):
        self._stream = io.StringIO()
        self._format(indent, True, value)
        return self._stream.getvalue()

    def _format(self, indent_current: int, use_repr: bool, value: Any) -> None:
        if isinstance(value, dict):
            if '$__datatype__' in value and 'data' in value:
                data_type: str = cast(str, value['$__datatype__'])
                cls: str = cast(str, value.get('cls', ''))  # type: ignore
                data: Any = value['data']

                if func := self._data_type_map.get(data_type):
                    func(indent_current, data, cls)
                else:
                    self._write('', '', False, 0, str(data), None)
            else:  # normal dict
                self._format_items('{\n', ': ', ',\n', '}', True, indent_current, value, None)

        elif isinstance(value, list):
            self._forrmat_list_like('{\n', ',\n', '}', indent_current, value, None)
        else:
            if use_repr:
                value = repr(value)
            self._write('', '', False, 0, value, None)

    def _write(
        self,
        open_: str,
        after_: str,
        use_repr: bool,
        _indent_current: int,
        value: Any,
        cls: str | None,
    ) -> None:
        if cls:
            open_ = f'{cls}{open_}'

        if use_repr:
            value = repr(value)

        self._stream.write(f'{open_}{value}{after_}')

    def _forrmat_timedelta(self, _indent_current: int, value: Any, _cls: str):
        self._write('', '', True, 0, timedelta(seconds=value), None)

    def _forrmat_sequence(self, open_: str, after_: str, close_: str, indent_current: int, value: Any, cls: str):
        if cls == 'range':
            self._write('(', ')', False, 0, f'{value[0]}, {value[-1] + 1}', 'range')
        else:
            self._forrmat_list_like(f'{cls}{open_}', after_, close_, indent_current, value, None)

    def _forrmat_list_like(
        self, open_: str, after_: str, close_: str, indent_current: int, value: Any, _cls: str | None
    ):
        indent_new = indent_current + self._indent_step
        before_ = indent_new * self._c

        self._stream.write(open_)
        for v in value:
            self._stream.write(before_)
            self._format(indent_new, True, v)
            self._stream.write(after_)
        self._stream.write(indent_current * self._c + close_)

    def _format_items(
        self,
        open_: str,
        split_: str,
        after_: str,
        close_: str,
        repr_key: bool,
        indent_current: int,
        value: Any,
        cls: str | None,
    ) -> None:
        indent_new = indent_current + self._indent_step
        before_ = indent_new * self._c

        if cls:
            open_ = f'{cls}{open_}'
        self._stream.write(open_)
        for k, v in value.items():
            self._stream.write(before_)
            self._format(indent_new, repr_key, k)
            self._stream.write(split_)
            self._format(indent_new, True, v)
            self._stream.write(after_)
        self._stream.write(indent_current * self._c + close_)


json_args_value_formatter = JsonArgsValueFormatter()
