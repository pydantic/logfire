from typing import assert_type

import logfire
from logfire.variables import Variable

# Documenting the current behavior: including a default of an incompatible type extends the union rather than producing
# a type error. This is arguably a feature, not a bug — the `type` is only used for validating provider values, not the
# code default, so this behavior makes it more ergonomic to do things like sentinel patterns if you want to easily
# detect whether you got a variable-provider-provided value.
# Anyway, the _main_ reason it works this way is not because we prefer it, but because we can't see a way to make it a
# type error, so the above argument is just a way of turning lemons into lemonade.
my_variable_2 = logfire.Logfire().var(name='my-variable-2', default=None, type=int)
assert_type(my_variable_2, Variable[int | None])
