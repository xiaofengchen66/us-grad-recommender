from __future__ import annotations

import enum


class VerificationStatus(str, enum.Enum):
    """Case-state vocabulary from FULL_HANDOFF.md §15, reused for every
    catalog-derived fact (not just community-sourced ones). Tracked at the
    row level, not per-field — see docs/PHASE_2_CATALOG_DESIGN.md §5 for
    why a separate field-level provenance table was deliberately deferred.
    """

    RAW = "raw"
    PARSED = "parsed"
    NEEDS_REVIEW = "needs_review"
    USER_CONFIRMED = "user_confirmed"
    DOCUMENT_VERIFIED = "document_verified"
    REJECTED_AS_INVALID = "rejected_as_invalid"


class EntityStatus(str, enum.Enum):
    """Lifecycle status for a catalog entity (unit/program/track/etc.),
    distinct from VerificationStatus: this describes whether the thing
    itself is believed to still exist/operate, not how trustworthy our
    data about it is.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    DISCONTINUED = "discontinued"
    UNVERIFIED = "unverified"
