"""Built-in helpers for logfire.handlebars.

Includes both standard Handlebars.js helpers and custom helpers.
"""

from __future__ import annotations

import json as json_module
import warnings
from typing import Any, cast

from logfire.handlebars._compiler import HelperOptions
from logfire.handlebars._utils import is_falsy, to_string


def _helper_if(context: Any, *args: Any, options: HelperOptions) -> str:
    """The #if block helper.

    Renders the block if the first argument (or context) is truthy.
    """
    # The condition is the first positional argument
    if args:
        condition = args[0]
    else:
        condition = context

    # Support callable conditions
    if callable(condition) and not isinstance(condition, (str, bool, int, float, list, dict)):
        condition = condition()

    if not is_falsy(condition):
        return options.fn(context)
    return options.inverse(context)


def _helper_unless(context: Any, *args: Any, options: HelperOptions) -> str:
    """The #unless block helper. Inverse of #if."""
    if args:
        condition = args[0]
    else:
        condition = context

    if callable(condition) and not isinstance(condition, (str, bool, int, float, list, dict)):
        condition = condition()

    if is_falsy(condition):
        return options.fn(context)
    return options.inverse(context)


def _helper_each(context: Any, *args: Any, options: HelperOptions) -> str:
    """The #each block helper.

    Iterates over arrays and objects, providing @index/@key, @first, @last.
    """
    items = args[0] if args else context

    if items is None:
        return options.inverse(context)

    parts: list[str] = []

    if isinstance(items, dict):
        dict_items = cast('dict[str, Any]', items)
        keys = list(dict_items.keys())
        if not keys:
            return options.inverse(context)
        for i, key in enumerate(keys):
            value = dict_items[key]
            data: dict[str, Any] = {
                'key': key,
                'index': i,
                'first': i == 0,
                'last': i == len(keys) - 1,
            }
            bp: list[Any] = [value, key]
            parts.append(options.fn(value, data=data, block_params=bp))
    elif isinstance(items, (list, tuple)):
        seq = cast('list[Any]', items)
        if not seq:
            return options.inverse(context)
        for i, item in enumerate(seq):
            data = {
                'index': i,
                'first': i == 0,
                'last': i == len(seq) - 1,
            }
            bp = [item, i]
            parts.append(options.fn(item, data=data, block_params=bp))
    else:
        return options.inverse(context)

    return ''.join(parts)


def _helper_with(context: Any, *args: Any, options: HelperOptions) -> str:
    """The #with block helper.

    Changes the context for the block body.
    """
    new_context = args[0] if args else context

    if is_falsy(new_context):
        return options.inverse(context)

    bp: list[Any] = [new_context]
    return options.fn(new_context, block_params=bp)


def _helper_lookup(*args: Any, options: HelperOptions) -> Any:
    """The lookup helper.

    Dynamic property lookup: {{lookup obj key}}.
    """
    if len(args) < 2:
        return None

    obj, key = args[0], args[1]

    if obj is None:
        return None

    if isinstance(obj, dict):
        dict_obj = cast('dict[str, Any]', obj)
        return dict_obj.get(str(key) if not isinstance(key, str) else key)

    if isinstance(obj, (list, tuple)):
        seq = cast('list[Any]', obj)
        try:
            idx = int(key)
            if 0 <= idx < len(seq):
                return seq[idx]
        except (ValueError, TypeError):
            pass
        return None

    # Try attribute access
    key_str = str(key)
    if key_str.startswith('__'):
        return None
    try:
        return getattr(obj, key_str)
    except AttributeError:
        return None


def _helper_log(*args: Any, options: HelperOptions) -> str:
    """The log helper.

    Logs values using warnings.warn.
    """
    level = options.hash.get('level', 'info')
    message = ' '.join(to_string(a) for a in args)
    warnings.warn(f'[Handlebars {level}] {message}', stacklevel=2)
    return ''


# Custom helpers (not part of Handlebars.js spec)


def _helper_json(*args: Any, options: HelperOptions) -> str:
    """Serialize value to JSON string."""
    if not args:
        return ''
    return json_module.dumps(args[0])


def _helper_uppercase(*args: Any, options: HelperOptions) -> str:
    """Convert value to uppercase."""
    if not args:
        return ''
    return to_string(args[0]).upper()


def _helper_lowercase(*args: Any, options: HelperOptions) -> str:
    """Convert value to lowercase."""
    if not args:
        return ''
    return to_string(args[0]).lower()


def _helper_trim(*args: Any, options: HelperOptions) -> str:
    """Strip leading/trailing whitespace."""
    if not args:
        return ''
    return to_string(args[0]).strip()


def _helper_join(*args: Any, options: HelperOptions) -> str:
    """Join array elements with separator."""
    if len(args) < 1:
        return ''
    arr = args[0]
    sep = args[1] if len(args) > 1 else ','
    if isinstance(arr, (list, tuple)):
        seq = cast('list[Any]', arr)
        return str(sep).join(to_string(item) for item in seq)
    return to_string(arr)


def _helper_truncate(*args: Any, options: HelperOptions) -> str:
    """Truncate string to N characters."""
    if len(args) < 1:
        return ''
    value = to_string(args[0])
    length = int(args[1]) if len(args) > 1 else 100
    if len(value) <= length:
        return value
    return value[:length]


def _helper_eq(*args: Any, options: HelperOptions) -> bool:
    """Equality comparison."""
    if len(args) < 2:
        return False
    return args[0] == args[1]


def _helper_ne(*args: Any, options: HelperOptions) -> bool:
    """Inequality comparison."""
    if len(args) < 2:
        return True
    return args[0] != args[1]


def _helper_gt(*args: Any, options: HelperOptions) -> bool:
    """Greater than comparison."""
    if len(args) < 2:
        return False
    return args[0] > args[1]


def _helper_gte(*args: Any, options: HelperOptions) -> bool:
    """Greater than or equal comparison."""
    if len(args) < 2:
        return False
    return args[0] >= args[1]


def _helper_lt(*args: Any, options: HelperOptions) -> bool:
    """Less than comparison."""
    if len(args) < 2:
        return False
    return args[0] < args[1]


def _helper_lte(*args: Any, options: HelperOptions) -> bool:
    """Less than or equal comparison."""
    if len(args) < 2:
        return False
    return args[0] <= args[1]


def _helper_and(*args: Any, options: HelperOptions) -> Any:
    """Boolean AND combinator."""
    if not args:
        return False
    for arg in args:
        if is_falsy(arg):
            return arg
    return args[-1]


def _helper_or(*args: Any, options: HelperOptions) -> Any:
    """Boolean OR combinator."""
    if not args:
        return False
    for arg in args:
        if not is_falsy(arg):
            return arg
    return args[-1]


def _helper_not(*args: Any, options: HelperOptions) -> bool:
    """Boolean NOT."""
    if not args:
        return True
    return is_falsy(args[0])


def _helper_default(*args: Any, options: HelperOptions) -> Any:
    """Use fallback if value is falsy."""
    if len(args) < 2:
        return args[0] if args else None
    value, fallback = args[0], args[1]
    if is_falsy(value):
        return fallback
    return value


def get_default_helpers() -> dict[str, Any]:
    """Get the default set of helpers.

    Returns:
        A dictionary mapping helper names to helper functions.
    """
    return {
        'if': _helper_if,
        'unless': _helper_unless,
        'each': _helper_each,
        'with': _helper_with,
        'lookup': _helper_lookup,
        'log': _helper_log,
        # Custom helpers
        'json': _helper_json,
        'uppercase': _helper_uppercase,
        'lowercase': _helper_lowercase,
        'trim': _helper_trim,
        'join': _helper_join,
        'truncate': _helper_truncate,
        'eq': _helper_eq,
        'ne': _helper_ne,
        'gt': _helper_gt,
        'gte': _helper_gte,
        'lt': _helper_lt,
        'lte': _helper_lte,
        'and': _helper_and,
        'or': _helper_or,
        'not': _helper_not,
        'default': _helper_default,
    }
