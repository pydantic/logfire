from dataclasses import dataclass
from typing import Any, Generic, Mapping, Sequence

from typing_extensions import TypeVar

KT = TypeVar('KT')
VT = TypeVar('VT')


FlattenValue = TypeVar('FlattenValue', bound=Mapping[Any, Any] | Sequence[Any])


@dataclass(slots=True)
class Flatten(Generic[FlattenValue]):
    value: FlattenValue


def flatten(value: FlattenValue) -> Flatten[FlattenValue]:
    """
    A wrapper class that tells logfire to flatten the first level of a mapping or sequence into OTel
    parameters so they can be easily queried.

    Importantly, wrapping something in `flatten` doesn't affect how it's formatted in the log message.

    The function can be used on any `Mapping` or `Sequence` type, including `dict`, `list`, `tuple`, etc.

    Sample usage:
    ```py
    logfire.info('{my_dict=} {my_list=}', my_dict=flatten({'a': 1, 'b': 2}), my_list=flatten([3, 4]))
    #> my_dict={'a': 1, 'b': 2} my_list=[3, 4]
    ```
    Will have OTel attributes:
    ```json
    {
        "my_dict.a": 1,
        "my_dict.b": 2,
        "my_list.0": 3,
        "my_list.1": 4
    }
    ```
    """
    return Flatten(value)
