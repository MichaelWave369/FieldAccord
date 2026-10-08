"""Field Accord offline, review-only human-agent contract kernel."""

from .core import (
    ContractError, assess, receipt_digest_is_valid,
    validate_intent, validate_capability, validate_proposal,
)
from .bridge import inspect_snapshot
from .interop import inspect_interop
from .handoff import WorkJournal, sign_export_for_testing, verify_export
from .native import (
    native_vessie_metadata_export, issue_native_vessie_envelope,
    native_phios_status_export, issue_native_phios_envelope,
)
from .producers import (
    vessie_metadata_export, phios_status_export, issue_producer_envelope,
    frame_export, decode_export_frame, admit_export_frame,
)
from .acquisition import acquire_fielddeck, inspect_acquired_fielddeck
from .cloud_worker import inspect_cloud_worker
from .continuity import (
    GENESIS, attention_review, make_event, replay_work, validate_event,
)

__all__ = [
    "ContractError",
    "inspect_snapshot",
    "inspect_interop",
    "WorkJournal",
    "sign_export_for_testing",
    "verify_export",
    "vessie_metadata_export",
    "native_vessie_metadata_export",
    "issue_native_vessie_envelope",
    "native_phios_status_export",
    "issue_native_phios_envelope",
    "phios_status_export",
    "issue_producer_envelope",
    "frame_export",
    "decode_export_frame",
    "admit_export_frame",
    "inspect_cloud_worker",
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
