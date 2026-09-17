"""Logfire Agent Control: one per-agent config, edited in Logfire, applied by any agent framework.

An agent's instructions, model, model settings, and tool descriptions become editable from the
Logfire UI -- versioned, labelled, rolled out, and rolled back as one unit, with no redeploy. This
package is the framework-neutral core: the config contract, the variable that holds it, and the pure
functions that say what a published value does to a request. Framework adapters are built on top.

Nothing here ever creates or updates a Logfire variable. An agent reports its code baseline on an
`agent_control_config_hint` span, and Logfire promotes that into a config when someone asks it to.
"""

from ._apply import (
    AppliedInstructions,
    AppliedSettings,
    AppliedTools,
    Block,
    CollisionScope,
    ToolDef,
    apply_instructions,
    apply_settings,
    apply_tool_definitions,
    build_baseline,
    canonical_settings,
)
from ._config import (
    AgentConfig,
    AgentConfigSettings,
    InstructionBlock,
    ParameterOverride,
    ToolDefinitionOverride,
    ToolKey,
)
from ._control import AgentControl, Resolution, current_resolution, use_resolution
from ._hint import BaselinePublication, BaselineSource
from ._merge import Provenance, SettingSource, merge_settings
from ._names import AGENT_VARIABLE_PREFIX, agent_variable_name, normalize_agent_name
from ._reporting import ApplyIssue, ApplyIssueReason, OnUnmatched, UnmatchedConfigError, report_issues
from ._schema import AGENT_CONFIG_JSON_SCHEMA, MAX_MODEL_FACING_TEXT_LENGTH, SCHEMA_SHA256, canonical_json
from ._support import AgentSupport, Destination, Section
from ._units import MAX_TIMEOUT_MILLISECONDS, MAX_TIMEOUT_SECONDS, is_representable_timeout, to_milliseconds

__all__ = (
    'AGENT_CONFIG_JSON_SCHEMA',
    'AGENT_VARIABLE_PREFIX',
    'MAX_MODEL_FACING_TEXT_LENGTH',
    'MAX_TIMEOUT_MILLISECONDS',
    'MAX_TIMEOUT_SECONDS',
    'SCHEMA_SHA256',
    'AgentConfig',
    'AgentConfigSettings',
    'AgentControl',
    'AgentSupport',
    'AppliedInstructions',
    'AppliedSettings',
    'AppliedTools',
    'ApplyIssue',
    'ApplyIssueReason',
    'BaselinePublication',
    'BaselineSource',
    'Block',
    'CollisionScope',
    'Destination',
    'InstructionBlock',
    'OnUnmatched',
    'ParameterOverride',
    'Provenance',
    'Resolution',
    'Section',
    'SettingSource',
    'ToolDef',
    'ToolDefinitionOverride',
    'ToolKey',
    'UnmatchedConfigError',
    'agent_variable_name',
    'apply_instructions',
    'apply_settings',
    'apply_tool_definitions',
    'build_baseline',
    'canonical_json',
    'canonical_settings',
    'current_resolution',
    'is_representable_timeout',
    'merge_settings',
    'normalize_agent_name',
    'report_issues',
    'to_milliseconds',
    'use_resolution',
)
