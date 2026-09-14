"""Wiring one Claude Agent SDK agent to its Logfire config: baseline out, published value in."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from logfire.agent_control import (
    AgentConfig,
    AgentControl,
    OnUnmatched,
    Resolution,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
    use_resolution,
)

from ._instructions import apply_instruction_blocks, instruction_blocks
from ._settings import (
    SUPPORTED_SETTINGS,
    apply_managed_settings,
    baseline_model,
    baseline_settings,
    managed_model,
)
from ._tools import (
    managed_references,
    rebuild_servers,
    tool_definitions,
    tool_names,
)

if TYPE_CHECKING:
    from logfire import Logfire


def baseline(options: ClaudeAgentOptions) -> AgentConfig:
    """Describe the agent `options` states, for the Logfire editor to diff published values against.

    Everything this SDK can be told is plain data on `ClaudeAgentOptions` -- the only callables it
    carries are hooks, permission handlers, and tool implementations -- so the whole baseline is
    knowable before a session starts, and there is nothing to wait for a first request to learn.
    """
    return build_baseline(
        instructions=instruction_blocks(options),
        model=baseline_model(options),
        settings=baseline_settings(options),
        tools=tool_definitions(options),
    )


class ManagedAgent:
    """One Claude Agent SDK agent, configurable from Logfire.

    Everything this SDK lets an adapter rewrite is decided when a session starts: the system prompt,
    the subagents, the model, the effort, and the in-process tool definitions all become CLI arguments
    and one `initialize` message, and nothing after that reaches the model request the CLI builds. So
    a managed config is applied by rewriting `ClaudeAgentOptions` -- once, before `query()` or
    `ClaudeSDKClient.connect()` -- and takes effect on the *next* session rather than the next
    request. [`refresh_model`][logfire.agent_control.claude_agent_sdk.ManagedAgent.refresh_model] is
    the one exception the SDK offers mid-session.

    Use [`agent_control`][logfire.agent_control.claude_agent_sdk.agent_control] for a one-shot
    `query()`; keep a `ManagedAgent` when a long-lived `ClaudeSDKClient` should pick up a newly
    published model, or when the run's spans should carry the config version that produced them.
    """

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        logfire_instance: Logfire | None = None,
        on_unmatched: OnUnmatched = 'warn',
        publish_baseline: bool = True,
    ) -> None:
        """Declare the Logfire variable backing this agent's config.

        Args:
            name: The agent's name, which its config is stored under as `agent__<name>`. Required and
                explicit: `ClaudeAgentOptions` has no name of its own, and one inferred from a Python
                variable would point the agent at a different config the day someone renames it.
            label: The label to resolve, such as `'production'`. `None` lets the variable's own
                targeting rules and rollout choose.
            logfire_instance: The Logfire instance to resolve and publish through; defaults to the
                one `logfire.configure()` sets up.
            on_unmatched: What to do about a published entry this agent cannot apply -- `'warn'`
                (the default, once per process), `'error'`, or `'ignore'`.
            publish_baseline: Whether to publish the code baseline the Logfire editor diffs against.
        """
        self.control = AgentControl(
            name,
            label=label,
            logfire_instance=logfire_instance,
            on_unmatched=on_unmatched,
            publish_baseline=publish_baseline,
        )
        """The underlying [`AgentControl`][logfire.agent_control.AgentControl]."""
        self._publish_thread: threading.Thread | None = None
        """The background baseline publish, for a process that may exit before it finishes."""

    def __repr__(self) -> str:
        return f'{type(self).__name__}(name={self.control.name!r}, label={self.control.label!r})'

    def options(self, options: ClaudeAgentOptions) -> ClaudeAgentOptions:
        """`options` with the published config applied, ready to start a session with.

        The argument is never mutated: what comes back is a new `ClaudeAgentOptions`, or the original
        object itself when Logfire has nothing published for this agent.

        The config is resolved here and the returned options carry it, but the session is started by
        the caller, after this returns. So the resolved label and version reach the spans this
        adapter can still get inside -- a hook, a permission check -- and not the spans of the query
        itself. Use [`session`][logfire.agent_control.claude_agent_sdk.ManagedAgent.session] to put
        them on the whole run.
        """
        return self._resolved(options)[1]

    @contextmanager
    def session(self, options: ClaudeAgentOptions) -> Generator[ClaudeAgentOptions]:
        """`options` with the published config applied, for the session run inside this block.

        Resolving *and running* inside one context is what puts the resolved label and version on the
        spans the block emits, so a run can be traced back to the config version that produced it.
        Run the whole session inside it:

        ```python skip-run="true" skip-reason="illustrative-fragment"
        with managed.session(code_options) as options:
            async for message in query(prompt='Refund my last order.', options=options):
                ...
        ```
        """
        resolution, managed = self._resolved(options)
        with use_resolution(resolution):
            yield managed

    def _resolved(self, options: ClaudeAgentOptions) -> tuple[Resolution, ClaudeAgentOptions]:
        """Resolve this agent's config once, and apply it to `options`.

        One resolution per call, held only as data: the session it configures is started by the
        caller, so the scope it is reported in is re-entered later, at the callbacks the applied
        options carry, rather than kept open across a session this adapter does not run.
        """
        self._publish_thread = self.control.publish_baseline(baseline(options))
        with self.control.resolution() as resolution:
            config = resolution.config
            return resolution, options if config is None else self._applied(options, config, resolution)

    async def refresh_model(self, client: ClaudeSDKClient, options: ClaudeAgentOptions) -> str | None:
        """Re-resolve the managed model and set it on a connected client, for the turns still to come.

        The model is the one thing this SDK can change without a new session, so it is the one thing a
        long-lived client can pick up from Logfire while it runs. Everything else was sealed into the
        CLI's arguments at connect time.

        `options` is the same object the session was started from: it supplies the model to go back to
        when the managed one is withdrawn, which is what keeps un-publishing a revert to code rather
        than a switch to the CLI default.

        Returns:
            The model now in effect, or `None` when that is the CLI's own default.
        """
        with self.control.resolution() as resolution:
            config = resolution.config
            model = options.model
            if config is not None and config.model is not None:
                managed, reason = managed_model(config.model)
                if reason is None:
                    model = managed
                else:
                    self.control.report_unmatched(reason)
            await client.set_model(model)
            return model

    def _applied(self, options: ClaudeAgentOptions, config: AgentConfig, resolution: Resolution) -> ClaudeAgentOptions:
        """`options` rewritten by every section of `config` this SDK has somewhere to put.

        Section by section, each on the options the section before it produced: a subagent's prompt
        and its tool list live on the same `AgentDefinition`, so rewriting them in one pass over the
        original options would have the second overwrite the first.
        """
        on_unmatched = self.control.on_unmatched

        blocks = instruction_blocks(options)
        instruction_changes, unapplied = apply_instruction_blocks(
            options, apply_instructions(blocks, config, on_unmatched=on_unmatched).blocks
        )
        for message in unapplied:
            self.control.report_unmatched(message)
        options = replace(options, **instruction_changes)

        code_tools = tool_definitions(options)
        applied = apply_tool_definitions(
            code_tools,
            config,
            on_unmatched=on_unmatched,
            # Every in-process tool is advertised as `mcp__<server>__<tool>`, so two servers may each
            # have a `search` and renaming one of them collides only inside its own server.
            collision_scope='toolset',
        )
        changes: dict[str, Any] = {}
        servers = rebuild_servers(options, code_tools, applied.tools)
        if servers is not None:
            changes['mcp_servers'] = servers
        references, unpreservable = managed_references(options, tool_names(applied.forward), resolution)
        changes.update(references)
        for message in unpreservable:
            self.control.report_unmatched(message)

        changes.update(
            apply_managed_settings(
                options, apply_settings(config, supported=SUPPORTED_SETTINGS, on_unmatched=on_unmatched)
            )
        )

        if config.model is not None:
            model, reason = managed_model(config.model)
            if reason is None:
                changes['model'] = model
            else:
                self.control.report_unmatched(reason)

        return replace(options, **changes)


def agent_control(
    options: ClaudeAgentOptions | None = None,
    *,
    name: str,
    label: str | None = None,
    on_unmatched: OnUnmatched = 'warn',
    publish_baseline: bool = True,
    logfire_instance: Logfire | None = None,
) -> ClaudeAgentOptions:
    """Make one agent's prompt, model, effort, and tool descriptions editable from Logfire.

    Wrap the options you would pass to `query()` or `ClaudeSDKClient`, and pass what comes back
    instead:

    ```python skip-run="true" skip-reason="illustrative-fragment"
    options = agent_control(ClaudeAgentOptions(system_prompt='...'), name='checkout_assistant')
    async for message in query(prompt='Refund my last order.', options=options):
        ...
    ```

    Call it last, once the options say everything your code wants them to say: what a published value
    changes is applied over them, and anything you change afterwards wins over Logfire.

    Nothing here can take the agent down. An unreachable Logfire, nothing published, or a value this
    release cannot parse all return the options you passed in, unchanged.

    Args:
        options: The options your code would start a session with. Never mutated: what comes back is
            a new `ClaudeAgentOptions`, or this same object when Logfire has nothing published.
            Omitting it manages an agent that says nothing in code, so every section comes from
            Logfire.
        name: The agent's name, which its config is stored under as `agent__<name>`. Required and
            explicit: `ClaudeAgentOptions` has no name of its own, and one inferred from a Python
            variable would point the agent at a different config the day someone renames it.
        label: The label to resolve, such as `'production'`. `None` lets the variable's own targeting
            rules and rollout choose.
        on_unmatched: What to do about a published entry this agent cannot apply -- `'warn'` (the
            default, once per process), `'error'`, or `'ignore'`.
        publish_baseline: Whether to publish the code baseline the Logfire editor diffs against.
        logfire_instance: The Logfire instance to resolve and publish through; defaults to the one
            `logfire.configure()` sets up.

    Returns:
        The `ClaudeAgentOptions` to start the session with.

    The config is resolved when this is called, so call it where you build the options for each
    session rather than once at import time. Because the session is started afterwards, the resolved
    version reaches the spans of the hooks and permission checks the returned options carry, but not
    the spans of the query itself; use
    [`ManagedAgent.session`][logfire.agent_control.claude_agent_sdk.ManagedAgent.session] to put it on
    the whole run, and to pick up a newly published model on a client that is already connected.
    """
    return ManagedAgent(
        name,
        label=label,
        logfire_instance=logfire_instance,
        on_unmatched=on_unmatched,
        publish_baseline=publish_baseline,
    ).options(options if options is not None else ClaudeAgentOptions())
