#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/dispatch_helpers.py
Summary: Shared helpers for #662 dispatch_gate.py and task_lifecycle_gate.py.

Exposes:
  - is_registered_pact_specialist(subagent_type) — registry check (one
    of the dispatch_gate rules; rejects unregistered pact-* spawns)
  - is_pact_specialist_owner(owner, team_name) — bare-owner → team-config
    agentType → registry resolution (one leg of the dispatch recognition)
  - is_owner_wiring_shape(tool_input) — pure structural recognition of an
    owner-wiring TaskUpdate's SHAPE (one leg of the dispatch recognition;
    see its docstring for the other two legs, why they are deliberately
    NOT folded into one composite, and — important — what this predicate
    does NOT establish)
  - has_task_assigned(team_name, name) — task-assigned check (one of
    the dispatch_gate rules; rejects spawn before TaskCreate)
  - trustworthy_actor_name(input_data) — actor resolution for the
    task_lifecycle_gate self-completion rule
  - SOLO_EXEMPT — research/exploration agents that bypass dispatch_gate

Module-load discipline (architect §5.6):
  Stdlib imports (json/sys) AND _emit_load_failure_deny defined BEFORE
  the wrapped try/except BaseException block. The wrapped block catches
  cross-package import failures (functools/re/pathlib/shared.pact_context)
  and emits a structured DENY with hookEventName=PreToolUse so any
  importer (dispatch_gate, task_lifecycle_gate) inherits the fail-closed
  contract automatically: if THIS module fails to load, the importer's
  own wrapped import block fires its own _emit_load_failure_deny via the
  re-raised BaseException.
"""

from __future__ import annotations

import json
import sys
from typing import NoReturn


def _emit_load_failure_deny(stage: str, error: BaseException) -> NoReturn:
    """Stdlib-only fail-closed deny for module-load failure.

    Mirrors PR #660 ``merge_guard_pre._emit_load_failure_deny`` and the
    bootstrap_gate analogue at hooks/bootstrap_gate.py. Uses ONLY stdlib
    (json, sys) so it remains functional even when every wrapped import
    below fails. Audit anchor: hookEventName must be present in any deny
    output (#658 invariant).
    """
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"PACT dispatch_helpers {stage} failure — blocking for safety. "
                f"{type(error).__name__}: {error}. Check hook installation "
                "and shared module availability."
            ),
        }
    }))
    print(
        f"Hook load error (dispatch_helpers / {stage}): {error}",
        file=sys.stderr,
    )
    sys.exit(2)


# ─── fail-closed wrapper around cross-package imports ─────────────────────
try:
    import functools
    from pathlib import Path
    import shared.pact_context as pact_context
    from shared.task_utils import iter_team_task_jsons
except BaseException as _module_load_error:  # noqa: BLE001 — fail-closed catch-all
    _emit_load_failure_deny("module imports", _module_load_error)


# ─── constants ─────────────────────────────────────────────────────────────

# Research/exploration agents that legitimately spawn WITHOUT name/team_name
# (per pinned-memory feedback_direct_agent_calls.md). These bypass the
# dispatch_gate entirely. The specialist registry stays simple — these are caught at
# step ① of evaluate_dispatch in dispatch_gate.py.
SOLO_EXEMPT = frozenset({"general-purpose", "Explore", "Plan"})

# ─── specialist registry ───────────────────────────────────────────────────

def _glob_specialists(plugin_root: str) -> frozenset[str]:
    """Glob the specialist stems at ``{plugin_root}/agents/pact-*.md``.

    Uncached, pure-of-cache: the caller supplies plugin_root explicitly. Empty
    plugin_root or missing agents/ directory → empty frozenset (registry
    fail-closed); OSError → empty frozenset. ``pact-orchestrator.md`` IS in the
    glob set; the "orchestrator is the persona, not a dispatchable specialist"
    semantic is enforced at a different layer (system-prompt --agent flag at
    session start), not at the registry.

    Extracted from ``_specialist_registry`` (#878) so the cached registry and
    an explicit-root caller (the session_init startup notice, which runs BEFORE
    the pact_context cache is populated and so must pass an env-resolved root)
    share ONE glob implementation without parameterizing the lru_cache.
    """
    if not plugin_root:
        return frozenset()
    agents_dir = Path(plugin_root) / "agents"
    try:
        return frozenset(p.stem for p in agents_dir.glob("pact-*.md"))
    except OSError:
        return frozenset()


@functools.lru_cache(maxsize=1)
def _specialist_registry() -> frozenset[str]:
    """Glob agents/pact-*.md once per hook subprocess (cached, arg-less).

    Hook subprocesses are short-lived (per-tool-call); the cache is rebuilt
    on every dispatch evaluation. Resolves plugin_root from the pact_context
    cache and delegates the glob to ``_glob_specialists``. Deliberately
    ARG-LESS so the lru_cache holds exactly one entry per subprocess (the hot
    dispatch path); the explicit-root path the startup notice needs pre-cache
    goes through ``_glob_specialists`` directly, never through this cache.
    Empty plugin_root / missing agents/ → empty registry (fail-closed).
    """
    return _glob_specialists(pact_context.get_plugin_root())


def is_registered_pact_specialist(
    subagent_type: str, plugin_root: str = ""
) -> bool:
    """True iff subagent_type matches a file at ``agents/pact-*.md``.

    ``plugin_root`` (#878, additive + backward-compatible): when a non-empty
    plugin_root is passed, resolve the registry against it directly via
    ``_glob_specialists`` (the uncached path) — required by the session_init
    startup notice, which runs BEFORE the pact_context cache is populated, so
    the cached ``_specialist_registry()`` would see an empty plugin_root and
    wrongly report every type as unregistered there. When omitted/empty (every
    existing caller, e.g. the dispatch self-completion gate), fall back to the
    cached ``_specialist_registry()`` — identical behavior to before this param
    existed.
    """
    if not isinstance(subagent_type, str) or not subagent_type:
        return False
    registry = (
        _glob_specialists(plugin_root) if plugin_root else _specialist_registry()
    )
    return subagent_type in registry


def is_pact_specialist_owner(
    owner: str, team_name: str, teams_dir: str | None = None
) -> bool:
    """True iff ``owner`` names a team member whose agentType is a registered
    pact specialist (``agents/pact-*.md``).

    Real task owners are BARE specialist names (``backend-coder``,
    ``test-engineer``), NOT ``pact-``-prefixed — ``pact-*`` is the team-config
    agentType, never the owner. So identifying "this owner is a pact specialist
    teammate" requires resolving the bare owner through team config to its
    agentType (the SAME owner→member→agentType resolution
    ``intentional_wait._is_exempt_agent_type`` uses), then checking registry
    membership. Composes the two existing primitives — ``_iter_members`` (the
    resolution SSOT) + ``is_registered_pact_specialist`` (the registry check) —
    rather than duplicating either.

    Fail-CLOSED to ``False`` on every unresolvable path (empty owner/team_name,
    missing/malformed config, member-not-found, missing/non-str agentType, OR
    any unexpected exception). For the dispatch-variety gate this composes to
    FAIL-OPEN: "not positively a pact specialist" → the gate returns None →
    does not fire, so an unresolvable owner never strands a dispatch.

    The outer bare-except is load-bearing: ``_iter_members`` resolves the
    config dir via ``get_claude_config_dir()`` (→ ``Path.home()``), which can
    raise ``RuntimeError`` that ESCAPES ``_iter_members``'s own typed except —
    so a totally fail-closed helper must catch it here, not rely on a caller's
    outer guard.
    """
    if not isinstance(owner, str) or not owner:
        return False
    if not isinstance(team_name, str) or not team_name:
        return False
    try:
        for member in pact_context._iter_members(team_name, teams_dir):
            if member.get("name") == owner:
                agent_type = member.get("agentType")
                return (
                    isinstance(agent_type, str)
                    and is_registered_pact_specialist(agent_type)
                )
        return False
    except Exception:
        return False  # fail-closed → gate fail-OPEN (never strands a dispatch)


# ─── dispatch-wiring recognition ───────────────────────────────────────────

def is_owner_wiring_shape(tool_input: dict) -> bool:
    """True iff ``tool_input`` carries the owner-wiring SHAPE — a non-empty
    string ``owner`` AND a non-empty list ``addBlockedBy`` in the SAME write.

    TWO THINGS IT DELIBERATELY DOES NOT ESTABLISH:

    1. NOT "this is a dispatch." A caller treating True as a dispatch verdict
       will count owner-wiring writes for non-specialist owners and for
       teachback Task-A gates. This is why the name says *shape* and not
       *dispatch*: the verdict needs all three legs below, and this function
       reaches only the first. (It is also why the name avoids the calling
       gate's local term *terminal* — that file defines it as "both halves
       present, as against a partial one-half write", which IS what this
       tests, but the local definition does not travel to a shared module.)
    2. NOT "this is the last such write." The predicate tests ONE
       ``tool_input``; whether a LATER write also carries the composite shape
       is UNMEASURED. The O_EXCL dedup marker — not this predicate — is what
       guarantees one emit per task. Treat dedup as cheap insurance against a
       high-severity failure (a correctly-stamped dispatch reading 0.5) whose
       rate is unmeasured, NOT as something the corpus has shown to occur:
       the repeat-write evidence counts *owner-bearing* writes, most of which
       are PARTIAL and correctly rejected here, and the *composite*-repeat
       rate has never been measured. A consumer needing at-most-once
       semantics must claim the marker rather than infer uniqueness from
       shape; note the "append-only, no dedup by design" comments in the
       lifecycle gate are scoped to ``TaskCreate`` and are a separate
       question from this one.

    The full recognition is three legs:

        is_owner_wiring_shape(tool_input)                # this function
        AND is_pact_specialist_owner(owner, team_name)   # above
        AND NOT is_teachback_subject(subject)            # shared.task_utils

    on top of which each consumer applies its OWN exemption predicate:
    ``handoff_ordering_gate`` asks "may this owner self-complete?"
    (``is_self_complete_exempt``); the dispatch-coverage denominator asks "is
    this a dispatch requiring understanding verification?"
    (``is_teachback_exempt``). Those two are deliberately NOT unified — see the
    "DO NOT recouple by aliasing to the prior constant" note on
    ``TEACHBACK_EXEMPT_AGENT_TYPES`` in shared/intentional_wait.py. No
    exemption leg belongs in this module.

    WHY THE THREE LEGS ARE NOT FOLDED INTO ONE COMPOSITE: each has a different
    cost. This one is pure and in-memory; ``is_pact_specialist_owner`` reads
    the team config; the subject leg needs a task read. A composite would force
    every caller to read the task before it knows the owner is even a
    specialist, turning a short-circuit into a disk hit. Callers apply the
    legs in their own cost order and share the recognition, not the ordering.

    WHY BOTH FIELDS, AND WHY TOGETHER: the workflow templates all wire Task B
    with a single ``TaskUpdate(B, owner=..., addBlockedBy=[A])``. Neither half
    alone is the wiring shape — ``TaskCreate(B)`` leaves owner empty (it is
    wired by this later update), and every other addBlockedBy use across the
    templates is addBlockedBy-ONLY with no owner in the same call. So the
    co-occurrence is the signal; each field on its own is a partial write.

    Owners are BARE names (``backend-coder``), never ``pact-``-prefixed —
    ``pact-*`` is the team-config agentType. This function deliberately does no
    name-shape test at all; ``is_pact_specialist_owner`` owns that resolution.

    Pure function: no FS, no I/O, never raises. Non-dict input → False.
    """
    if not isinstance(tool_input, dict):
        return False
    owner = tool_input.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        return False
    add_blocked_by = tool_input.get("addBlockedBy")
    return isinstance(add_blocked_by, list) and bool(add_blocked_by)


# ─── task-assigned check ───────────────────────────────────────────────────

def has_task_assigned(team_name: str, name: str) -> bool:
    """True iff at least one task in ``team_name``'s task store has
    ``owner==name`` AND ``status in {"pending", "in_progress"}``.

    Delegates path construction and per-file reading to
    ``shared.task_utils.iter_team_task_jsons``, the single source of truth
    for per-team task iteration. That helper enforces the canonical
    ``~/.claude/tasks/{team_name}/*.json`` layout and applies path-traversal
    + symlink-escape defenses; centralizing the path here prevents the
    layout duplication that previously caused this gate to read the wrong
    directory. TaskList is a harness tool unavailable in subprocess
    context, so direct FS read via the helper is the only viable channel.
    """
    if not isinstance(team_name, str) or not team_name:
        return False
    if not isinstance(name, str) or not name:
        return False
    for data in iter_team_task_jsons(team_name):
        if data.get("owner") != name:
            continue
        if data.get("status") in ("pending", "in_progress"):
            return True
    return False


# ─── actor resolution (for the self-completion rule) ──────────────────────

def trustworthy_actor_name(input_data: dict) -> str | None:
    """Extract actor name from harness-trustworthy ``agent_id`` ONLY.

    Bypasses ``resolve_agent_name``'s Step 1 (agent_name) and Step 4
    (agent_type) fallbacks because they are not strong enough trust
    signals for the self-completion check (architect §5.3 / PREPARE
    §10).

    Trust contract: ``agent_id`` is harness-set and lives at the top
    level of the hook stdin JSON, not inside ``tool_input`` — a teammate
    cannot collide with it via crafted tool arguments. Format is
    ``"name@team_name"``.

    Returns the ``name`` portion, or None if ``agent_id`` is missing or
    malformed (no ``@``). Caller (task_lifecycle_gate self-completion
    rule) treats None as "actor unresolvable — DO NOT exempt from the
    self-completion advisory".

    Pure function: no FS, no I/O, no exceptions.
    """
    if not isinstance(input_data, dict):
        return None
    agent_id = input_data.get("agent_id")
    if not isinstance(agent_id, str) or "@" not in agent_id:
        return None
    name, _, team = agent_id.partition("@")
    if not name or not team:
        return None
    return name
