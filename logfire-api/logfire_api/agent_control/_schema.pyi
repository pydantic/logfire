from _typeshed import Incomplete
from typing import Any

MAX_MODEL_FACING_TEXT_LENGTH: int
AGENT_CONFIG_JSON_SCHEMA: dict[str, Any]

def canonical_json(document: dict[str, Any]) -> bytes:
    '''The bytes every copy of this contract digests, and the only definition of "canonical" here.

    Sorted keys and `(\',\', \':\')` separators make the document independent of how each copy\'s literal
    happens to be written. `ensure_ascii=False` makes it independent of the language: `json.dumps`
    escapes non-ASCII by default and `JSON.stringify` does not, so without it the first non-ASCII
    character in a description or a sample value would give two identical documents different digests.

    Public, and not only because [`SCHEMA_SHA256`][logfire.agent_control.SCHEMA_SHA256] is taken over
    it. Every digest this contract carries has to be taken over the same three flags -- the schema\'s,
    the one an agent\'s reported baseline carries as `agent_control.baseline_sha256`, and any an
    adapter computes for itself -- and a second implementation of "canonical" is how two sides come to
    disagree about one document. One function, exported, so there is nothing to restate.
    '''

SCHEMA_SHA256: Incomplete
