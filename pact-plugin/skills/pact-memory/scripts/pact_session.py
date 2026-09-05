"""
Location: pact-plugin/skills/pact-memory/scripts/pact_session.py
Summary: Shared session context helpers for pact-memory skill scripts.
Used by: memory_api.py, memory_init.py

Provides a single implementation of the context file reader so that
memory_api.py and memory_init.py don't each define their own copy.

The context file is written once per session by session_init.py and
read by all subsequent hooks and skill scripts.

Note: hooks/shared/pact_context.py has the authoritative implementation.
This module IMPORTS the slug derivation and the config-root resolver rather
than re-implementing them (see the bootstrap below).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# A direct-script invocation (`python3 .../scripts/cli.py`) puts only this
# directory on sys.path, so a bare `from shared.paths import ...` raises
# ModuleNotFoundError. parents[3] is the plugin root; its hooks/ dir holds the
# ONE config-root resolver. Importing it beats re-implementing it: a local copy
# has drifted from the authoritative one before.
#
# NO try/except fallback here, deliberately. A fallback would silently rebuild
# the local copy this import replaced, turning a loud startup failure into a
# session-state split across two config roots that nothing reports.
#
# APPEND, not insert(0): this path stays on sys.path for the rest of the
# process, and hooks/ holds ~29 importable names. Prepending would let a future
# hooks/config.py or hooks/database.py shadow this package's own modules of
# those names. Appending cannot — nothing else on the path provides `shared`.
sys.path.append(str(Path(__file__).resolve().parents[3] / "hooks"))

from shared.paths import get_claude_config_dir  # noqa: E402  # requires the sys.path bootstrap above
from shared.pact_context import project_slug  # noqa: E402  # requires the sys.path bootstrap above


def _context_file_path(session_id: str, project_dir: str) -> Path | None:
    """Return the path to the PACT session context file.

    Computed dynamically (not cached at import time) so that tests can
    monkeypatch Path.home() before calling get_session_id_from_context_file().

    Returns the session-scoped path when both identifiers are provided:
        <config-root>/pact-sessions/{project-slug}/{session-id}/pact-session-context.json
    where the config root is resolved by get_claude_config_dir() and project-slug
    is project_slug(project_dir), the resolved directory's basename
    (e.g., "PACT-Plugin").

    Returns None when either identifier is missing — callers should treat
    this as "no context file available" and return a safe default.

    Must match hooks/shared/pact_context.py path logic.

    Note: hooks/shared/pact_context.py uses init() + _context_path for the
    same purpose (testable there because hooks call init() after parsing stdin).
    """
    if session_id and project_dir:
        slug = project_slug(project_dir)
        return (
            get_claude_config_dir() / "pact-sessions"
            / slug / session_id / "pact-session-context.json"
        )
    return None


_DISCOVERY_UNSET = object()
# Cached RESULT OF THE FILESYSTEM LOOKUP only, plus the session id it was
# resolved for. Deliberately NOT a cache of the function's return value: the
# guards below must be re-evaluated on every call, because a cached answer must
# never outlive the conditions that permitted it.
_discovered_session_id = _DISCOVERY_UNSET
_discovered_for_env = None


def _resolve_context_on_disk(env_session: str) -> str:
    """Find the one context file naming this session id, and read the id back.

    The expensive half of discovery, split out so it can be cached without the
    guards being cached with it.
    """
    try:
        sessions_root = get_claude_config_dir() / "pact-sessions"
        matches = list(sessions_root.glob(f"*/{env_session}/pact-session-context.json"))
    except OSError:
        return ""

    # Fail closed on anything but a single match. Uniqueness was measured on one
    # machine, not guaranteed, so picking the first would be a coin toss over
    # which project's session this is.
    if len(matches) != 1:
        return ""

    try:
        data = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return ""

    if not isinstance(data, dict):
        return ""
    found = data.get("session_id", "")
    return found if isinstance(found, str) else ""


def _discover_session_id() -> str:
    """Find this session's id without already knowing it.

    The caller normally has no session id, and the context file that holds one
    is stored under a directory named after it — so the id cannot be read from
    the path that requires it. This breaks that circle by taking the id from
    the environment and confirming it against exactly one context file on disk.

    Returns the empty string whenever the answer is not unambiguous. Every
    failure is silent and lands the caller on its own degraded fallback.
    """
    # A test process inherits the developer's real session id from the
    # environment. Resolving it here would let the suite compute paths that
    # belong to a live session and write to them, so refuse before reading it.
    # Bare variable, not the sys.modules narrowing used elsewhere: both spawned
    # children and in-process runs must be caught.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""

    env_session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not env_session:
        return ""

    # Cache the filesystem lookup ONLY, and key it on the id it was resolved
    # for. Both guards above have already run, so a cached value can never be
    # returned to a caller the guards would now refuse.
    global _discovered_session_id, _discovered_for_env
    if _discovered_session_id is _DISCOVERY_UNSET or _discovered_for_env != env_session:
        _discovered_session_id = _resolve_context_on_disk(env_session)
        _discovered_for_env = env_session
    return _discovered_session_id


def get_session_id_from_context_file(
    session_id: str = "",
    project_dir: str = "",
) -> str:
    """
    Read session_id from the PACT session context file.

    The context file is written at session start by session_init.py.
    This is the primary source for session ID in skill scripts that
    run outside the hooks package.

    When the caller supplies both identifiers the named context file is read
    directly. When it supplies neither — which is every production call — the
    id is discovered from the environment instead, because the path of the file
    holding the id is itself named after the id.

    Args:
        session_id: If known, used to locate the session-scoped context file.
        project_dir: If known, used with session_id to locate the context file.
                     When empty, falls back to CLAUDE_PROJECT_DIR env var.

    Returns:
        Session ID string, or empty string if unavailable
    """
    # Resolve project_dir from env var if not provided;
    # session_id comes only from the caller or the context file itself.
    resolved_session = session_id
    resolved_project = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", "")

    # Compute session-scoped path (requires both identifiers)
    path = _context_file_path(resolved_session, resolved_project)
    if path is None:
        # Call discovery EVERY time. Caching here instead would return a stored
        # answer without re-running the guards inside it, so a process that had
        # once resolved an id would keep handing it out after the conditions
        # that permitted it had gone. The expensive filesystem work is cached
        # inside _discover_session_id, below its guards.
        return _discover_session_id()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("session_id", "")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError):
        return ""
