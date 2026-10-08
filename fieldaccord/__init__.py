"""Field Accord offline, review-only human-agent contract kernel."""

from .core import (
    ContractError, assess, receipt_digest_is_valid,
    validate_intent, validate_capability, validate_proposal,
)
from .bridge import inspect_snapshot
from .interop import inspect_interop
from .acquisition import acquire_fielddeck, inspect_acquired_fielddeck
from .continuity import (
    GENESIS, attention_review, make_event, replay_work, validate_event,
)

__all__ = [
    "ContractError",
    "inspect_snapshot",
    "inspect_interop",
    "acquire_fielddeck",
    "inspect_acquired_fielddeck",
    "assess",
    "receipt_digest_is_valid",
    "validate_intent",
    "validate_capability",
    "validate_proposal",
    "GENESIS",
    "attention_review",
    "make_event",
    "replay_work",
    "validate_event",
]
