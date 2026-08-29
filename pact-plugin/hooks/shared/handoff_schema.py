"""
Location: pact-plugin/hooks/shared/handoff_schema.py
Summary: Canonical metadata.handoff schema constants and validators. SSOT for
         the canonical field order, the required/recommended split, and the
         legacy-spelling alias map used on the READ side.
Used by: hooks/task_lifecycle_gate.py (write-time + completion-time advisories),
         hooks/shared/session_resume.py (resume-brief decision summary),
         tests/test_handoff_schema.py (constants + both validators).

When the canonical field set or the required/recommended split changes, this is
the only Python edit site. The four LLM-loaded template surfaces
(protocols/pact-phase-transitions.md, protocols/pact-protocols.md,
skills/pact-agent-teams/SKILL.md, commands/rePACT.md) mirror these names in
prose via grep-at-edit-time alignment.

Contract: pure module; no I/O, no global state, no platform dependencies.
Functions never raise.

Public surface:
- HANDOFF_CANONICAL_FIELDS — every canonical field name, in the order the
  templates teach them.
- HANDOFF_RECOMMENDED_FIELDS — the recommended-not-required subset. SSOT for
  the required/recommended partition: both HANDOFF_REQUIRED_FIELDS and the
  schema echo derive their carve-out from this one tuple.
- HANDOFF_REQUIRED_FIELDS — derived: canonical minus recommended.
- HANDOFF_LEGACY_ALIASES — legacy spelling -> canonical key, read-side only.
- HANDOFF_SCHEMA_ECHO — reusable human-readable echo of the canonical schema.
  The enumerated names, the recommended marking and both counts are derived
  from the tuples, so they cannot drift from them.
- validate_handoff_schema(handoff) — pure validator returning None on
  well-formed input or a reason string suitable for advisory text.
- resolve_handoff_field(handoff, field) — pure reader returning the canonical
  value, falling back to a legacy spelling of that same field.
"""

from __future__ import annotations


# Canonical field order, as taught by the four LLM-loaded template surfaces.
HANDOFF_CANONICAL_FIELDS: tuple[str, ...] = (
    "produced",
    "decisions",
    "reasoning_chain",
    "uncertainty",
    "integration",
    "open_questions",
)

# reasoning_chain is RECOMMENDED, not required. The template surfaces state it
# directly: "Items 1-2 and 4-6 are required. Item 3 (reasoning chain) is
# recommended." THIS SPLIT IS LOAD-BEARING, NOT COSMETIC. A validator requiring
# the WHOLE canonical set fires on handoffs the docs themselves call correct —
# including this repo's own VALID_HANDOFF fixture (tests/fixtures/emitter.py),
# which carries the required fields and not the recommended one. Never fold
# reasoning_chain into the required set.
HANDOFF_RECOMMENDED_FIELDS: tuple[str, ...] = ("reasoning_chain",)

# Derived, never duplicated — the carve-out pattern of TEACHBACK_OBJECT_FIELDS
# in the sibling teachback_schema module. A field moving between required and
# recommended edits ONE tuple and every consumer follows.
HANDOFF_REQUIRED_FIELDS: tuple[str, ...] = tuple(
    f for f in HANDOFF_CANONICAL_FIELDS if f not in HANDOFF_RECOMMENDED_FIELDS
)

# Legacy spellings this repo's own protocol docs once taught (commit 42b17a94)
# and which remain readable in the append-only journal. BOUNDED BY THAT COMMIT:
# a spelling in neither it nor the durable record is not legacy — it is simply
# wrong, and it gets the ordinary missing-required advisory. Do NOT widen this
# map by inference; an unbounded synonym map is a new source of silent
# wrongness. Read-side only: nothing here teaches an agent to WRITE a legacy
# spelling, and no LLM-loaded surface carries one.
HANDOFF_LEGACY_ALIASES: dict[str, str] = {
    "key_decisions": "decisions",
    "areas_of_uncertainty": "uncertainty",
    "integration_points": "integration",
}

# Human-readable echo of the full canonical schema. The field names, the
# "(recommended)" marking and both counts are derived from the tuples above, so
# the enumeration cannot drift when a field is added, removed, or moved across
# the split. Appended to the schema-invalid advisories in task_lifecycle_gate
# so the author receives the whole schema in one read rather than only the
# offending field. The closing sentence is the arc's own lesson: the display
# label and the JSON key are different strings.
HANDOFF_SCHEMA_ECHO: str = (
    f"Expected canonical metadata.handoff schema "
    f"({len(HANDOFF_REQUIRED_FIELDS)} required, "
    f"{len(HANDOFF_RECOMMENDED_FIELDS)} recommended), in canonical order: "
    + ", ".join(
        f"{field} (recommended)" if field in HANDOFF_RECOMMENDED_FIELDS else field
        for field in HANDOFF_CANONICAL_FIELDS
    )
    + ". These are JSON keys, not the prose display labels — "
    "'Key decisions' is the label, 'decisions' is the key."
)


def validate_handoff_schema(handoff: object) -> str | None:
    """Return None if handoff is well-formed, or a short reason string
    describing the schema problem (suitable for advisory text).

    PRESENCE-ONLY on HANDOFF_REQUIRED_FIELDS, and the two silences are
    deliberate:
      - An empty value is never a defect. The templates sanction it
        explicitly ("No areas of uncertainty flagged"), and empty
        open_questions / uncertainty fields are the norm in real handoffs.
      - A missing reasoning_chain is never a defect. It is recommended.

    When a missing required key has a legacy spelling present in the same
    handoff, the reason names the alias, because that is the correction the
    author can actually act on.

    Pure function; never raises. Non-dict input returns the malformed reason
    rather than raising TypeError — callers can treat the return value as the
    load-bearing signal.
    """
    if not isinstance(handoff, dict):
        return f"metadata.handoff must be object, got {type(handoff).__name__}"
    missing = [f for f in HANDOFF_REQUIRED_FIELDS if f not in handoff]
    if not missing:
        return None
    reason = f"metadata.handoff missing required fields: {', '.join(missing)}"
    hints = [
        f"found `{alias}`, the canonical key is `{canonical}`"
        for alias, canonical in HANDOFF_LEGACY_ALIASES.items()
        if canonical in missing and alias in handoff
    ]
    if hints:
        reason += f" ({'; '.join(hints)})"
    return reason


def resolve_handoff_field(handoff: object, field: str) -> object:
    """Return handoff[field], falling back to a legacy spelling of that same
    field when the canonical key is absent or falsy.

    Read-side repair only. It lets a reader render a handoff written with a
    spelling this repo once taught, without teaching anyone to write one: the
    journal is append-only, so those handoffs are on disk permanently, while
    the write-time advisory pushes the other way at the same time.

    A falsy canonical value falls through to the alias and then returns the
    canonical value unchanged, so a legitimately empty field still reads as
    empty rather than as missing.

    Pure; never raises. Returns None for a non-dict handoff.
    """
    if not isinstance(handoff, dict):
        return None
    value = handoff.get(field)
    if value:
        return value
    for alias, canonical in HANDOFF_LEGACY_ALIASES.items():
        if canonical == field:
            alias_value = handoff.get(alias)
            if alias_value:
                return alias_value
    return value
