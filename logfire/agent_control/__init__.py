"""Logfire Agent Control: one per-agent config, edited in Logfire, applied by any agent framework.

An agent's instructions, model, model settings, and tool descriptions become editable from the
Logfire UI -- versioned, labelled, rolled out, and rolled back as one unit, with no redeploy. This
package is the framework-neutral core: the config contract, the variable that holds it, and the pure
functions that say what a published value does to a request. Framework adapters are built on top.
"""

from ._apply import (
    AppliedInstructions,
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
from ._control import AgentControl, BaselineSource, Resolution, current_resolution, use_resolution
from ._merge import Provenance, SettingSource, merge_settings
from ._names import AGENT_VARIABLE_PREFIX, agent_variable_name, normalize_agent_name
from ._reporting import OnUnmatched, UnappliedEntry, UnappliedReason
from ._schema import AGENT_CONFIG_JSON_SCHEMA, MAX_MODEL_FACING_TEXT_LENGTH, SCHEMA_SHA256
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
    'AppliedInstructions',
    'AppliedTools',
    'BaselineSource',
    'Block',
    'CollisionScope',
    'InstructionBlock',
    'OnUnmatched',
    'ParameterOverride',
    'Provenance',
    'Resolution',
    'SettingSource',
    'ToolDef',
    'ToolDefinitionOverride',
    'ToolKey',
    'UnappliedEntry',
    'UnappliedReason',
    'agent_variable_name',
    'apply_instructions',
    'apply_settings',
    'apply_tool_definitions',
    'build_baseline',
    'canonical_settings',
    'current_resolution',
    'is_representable_timeout',
    'merge_settings',
    'normalize_agent_name',
    'to_milliseconds',
    'use_resolution',
)
