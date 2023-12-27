from __future__ import annotations

import base64
import io
from datetime import timedelta
from functools import partial
from typing import Any, Callable, Literal, cast

from ._json_encoder import DataType


class JsonArgsValueFormatter:
    """Format values recursively based on the information provided in value dict.

    When a custom format is identified, the `$__datatype__` key is always present.
    """

    def __init__(self, *, indent: int):
        self._indent_step = indent
        self._newlines = indent != 0
        self._data_type_map: dict[DataType, Callable[[int, Any, str | None], None]] = {
            'BaseModel': partial(self._format_items, '(', '=', ')', False),
            'dataclass': partial(self._format_items, '(', '=', ')', False),
            'Mapping': partial(self._format_items, '({', ': ', '})', True),
            'tuple': partial(self._format_list_like, '(', ')'),
            'Sequence': partial(self._format_sequence, '([', '])'),
            'set': partial(self._format_list_like, '{', '}'),
            'frozenset': partial(self._format_list_like, 'frozenset({', '})'),
            'deque': partial(self._format_list_like, 'deque([', '])'),
            'generator': partial(self._format_list_like, 'generator((', '))'),
            'bytes-utf8': partial(self._format_bytes, 'utf8'),
            'bytes-base64': partial(self._format_bytes, 'base64'),
            'Decimal': partial(self._write, 'Decimal(', ')', True),
            'date': partial(self._write, 'date(', ')', True),
            'datetime': partial(self._write, 'datetime(', ')', True),
            'time': partial(self._write, 'time(', ')', True),
            'timedelta': self._format_timedelta,
            'Enum': partial(self._write, '(', ')', True),
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
            'NameEmail': partial(self._write, '', '', False),
            'UUID': partial(self._write, "UUID('", "')", False),
            'Exception': partial(self._write, '(', ')', True),
            'array': partial(self._format_list_like, 'array([', '])'),
            'matrix': partial(self._format_list_like, 'matrix([', '])'),
            'attrs': partial(self._format_items, '(', '=', ')', False),
            'sqlalchemy': partial(self._format_items, '(', '=', ')', False),
            'unknown': partial(self._write, '', '', False),
        }

    def __call__(self, value: Any, *, indent_current: int = 0):
        self._stream = io.StringIO()
        self._format(indent_current, True, value)
        return self._stream.getvalue()

    def _format(self, indent_current: int, use_repr: bool, value: dict[str, Any] | list[Any] | Any) -> None:
        if isinstance(value, dict):
            data_type: Any = value.get('$__datatype__')
            data: Any = value.get('data')
            if data_type is not None and data is not None:
                data_type = cast(DataType, data_type)
                cls: str = cast(str, value.get('cls', ''))

                if data_type == 'DataFrame':
                    self._format_data_frame(indent_current, value)
                elif func := self._data_type_map.get(data_type):
                    func(indent_current, data, cls)
                else:
                    self._write('', '', False, 0, str(data), None)
            else:  # normal dict
                self._format_items('{', ': ', '}', True, indent_current, value, None)

        elif isinstance(value, list):
            self._format_list_like('[', ']', indent_current, value, None)
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

    def _format_timedelta(self, _indent_current: int, value: Any, _cls: str | None) -> None:
        self._write('', '', True, 0, timedelta(seconds=value), None)

    def _format_sequence(self, open_: str, close_: str, indent_current: int, value: Any, cls: str | None) -> None:
        if cls == 'range':
            self._write('(', ')', False, 0, f'{value[0]}, {value[-1] + 1}', 'range')
        else:
            self._format_list_like(f'{cls}{open_}', close_, indent_current, value, None)

    def _format_list_like(self, open_: str, close_: str, indent_current: int, value: Any, _cls: str | None) -> None:
        indent_new = indent_current + self._indent_step
        before = indent_new * ' '
        comma = ',\n' if self._newlines else ', '

        self._stream.write(open_)

        first = True
        for v in value:
            if first:
                first = False
                if self._newlines:
                    self._stream.write('\n')
            else:
                # write comma here not after so that we don't have a trailing comma
                self._stream.write(comma)
            self._stream.write(before)
            self._format(indent_new, True, v)

        if self._newlines and not first:
            self._stream.write(comma)
        self._stream.write(indent_current * ' ' + close_)

    def _format_items(
        self,
        open_: str,
        split_: str,
        close_: str,
        repr_key: bool,
        indent_current: int,
        value: Any,
        cls: str | None,
    ) -> None:
        indent_new = indent_current + self._indent_step
        before_ = indent_new * ' '
        comma = ',\n' if self._newlines else ', '

        if cls:
            open_ = f'{cls}{open_}'
        self._stream.write(open_)
        first = True
        for k, v in value.items():
            if first:
                if self._newlines:
                    self._stream.write('\n')
                first = False
            else:
                # write comma here not after so that we don't have a trailing comma
                self._stream.write(comma)
            self._stream.write(before_)
            self._format(indent_new, repr_key, k)
            self._stream.write(split_)
            self._format(indent_new, True, v)

        if self._newlines and not first:
            self._stream.write(',\n')
        self._stream.write(indent_current * ' ' + close_)

    def _format_bytes(self, mode: Literal['utf8', 'base64'], _indent_current: int, value: Any, cls: str | None) -> None:
        b = value.encode()
        if mode == 'base64':
            b = base64.b64decode(b)
        if cls:
            self._stream.write(f'{cls}({b!r})')
        else:
            self._stream.write(repr(b))

    def _format_table(
        self, columns: list[Any], indexes: list[Any], rows: list[Any], real_column_count: int, real_row_count: int
    ) -> None:
        """Inspired by https://gist.github.com/lonetwin/4721748.

        >>> columns = ['col1', 'col2', 'col4', 'col5']
        >>> indexes = ['a', 'b', 'd', 'e']
        >>> rows = [[1, 2, 4, 5], [2, 4, 8, 10], [4, 8, 16, 20], [5, 10, 20, 25]]
        >>> real_column_count = 5
        >>> real_rows_count = 5
        >>> _format_table(columns, indexes, rows, real_column_count, real_rows_count)

            | col1 | col2 | ... | col4 | col5
        ----+------+------+-----+------+-----
        a   | 1    | 2    | ... | 4    | 5
        b   | 2    | 4    | ... | 8    | 10
        ... | ...  | ...  | ... | ...  | ...
        d   | 4    | 8    | ... | 16   | 20
        e   | 5    | 10   | ... | 20   | 25

        [5 rows x 5 columns]
        """

        def insert_into_list_middle(items: list[Any], item: str | list[str]) -> list[Any]:
            midpoint = len(items) // 2
            return items[0:midpoint] + [item] + items[midpoint:]

        # add a column at the begging for index
        column_count = len(columns)
        if column_count < real_column_count:
            columns = insert_into_list_middle(columns, '...')
        columns = [''] + [str(x) for x in columns]

        converted_rows: list[Any] = []
        for i, row in enumerate(rows):
            # add index at the beggining of row
            if column_count < real_column_count:
                row = insert_into_list_middle(row, '...')
            row = [indexes[i]] + [str(x) for x in row]
            converted_rows.append(row)

        if len(rows) < real_row_count:
            converted_rows = insert_into_list_middle(converted_rows, ['...'] * len(columns))

        # figure out column widths
        widths = [len(max(cols, key=len)) for cols in zip(*([columns] + converted_rows))]

        # write the header
        self._stream.write(' | '.join(format(title, '%ds' % width) for width, title in zip(widths, columns)) + '\n')

        # write the separator
        self._stream.write('-+-'.join('-' * width for width in widths) + '\n')

        # write the data
        for row in converted_rows:
            self._stream.write(' | '.join(format(cdata, '%ds' % width) for width, cdata in zip(widths, row)) + '\n')

        # write summary
        self._stream.write(f'\n[{real_row_count} rows x {real_column_count} columns]')

    def _format_data_frame(
        self,
        _indent_current: int,
        value: dict[str, Any],
    ) -> None:
        self._format_table(
            columns=value.get('columns', []),
            indexes=value.get('indexes', []),
            rows=value.get('data', []),
            real_column_count=value.get('column_count', 0),
            real_row_count=value.get('row_count', 0),
        )


json_args_value_formatter = JsonArgsValueFormatter(indent=4)
json_args_value_formatter_compact = JsonArgsValueFormatter(indent=0)
