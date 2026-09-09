AGENT_VARIABLE_PREFIX: str

def normalize_agent_name(name: str) -> str:
    """Reduce an agent's display name to the key its variable is built from.

    Trim, lowercase, turn every character outside `[a-z0-9_]` into `_`, collapse runs of `_`, and
    strip `_` from both ends. The result is the *key*, not the variable name; see
    [`agent_variable_name`][logfire.agent_control.agent_variable_name].

    Lowercasing is the part worth justifying, because it is the lossy one. The rule exists to make
    two SDKs agree with the Logfire UI, and the UI's own rule -- the one the Pydantic AI harness
    already applies to an agent's telemetry name -- lowercases. Diverging from it would mean an
    agent named `Checkout Assistant` in one service and `checkout_assistant` in another shows up as
    two configs in a UI that only ever renders one name for them. It is lossy in the other
    direction too: `checkout-assistant`, `Checkout Assistant`, and `checkout_assistant` are one key,
    so two genuinely different agents whose names differ only in punctuation or case share a config.
    Give them explicit, distinct names when that is not what you want.

    Returns an empty string for a name with nothing usable in it -- whitespace, punctuation, or a
    script with no ASCII in it -- which callers turn into an error rather than a variable.
    """
def agent_variable_name(name: str) -> str:
    """The Logfire variable holding the config for the agent called `name`.

    `agent__` plus [`normalize_agent_name(name)`][logfire.agent_control.normalize_agent_name]. The
    prefix is added here, so passing a name that already carries it is a mistake the caller is warned
    about rather than one that produces `agent__agent__checkout`.

    Raises:
        ValueError: when `name` has nothing a key can be made of.
    """
