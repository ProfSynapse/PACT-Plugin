"""
Location: pact-plugin/hooks/shared/constants.py
Summary: Canonical constants shared across PACT hooks and tests.
Used by: test_patterns.py (cross-list consistency checks),
         verify-scope-integrity.sh (baseline checks),
         postcompact_archive.py (get_compact_summary_path),
         session_init.py (get_compact_summary_path).
"""

from __future__ import annotations

from pathlib import Path

from .paths import get_claude_config_dir

# Canonical list of all PACT specialist agents in lifecycle order.
# This is the single source of truth for agent enumeration.
# Keep in sync with: CLAUDE.md agent roster, task_utils.py agent_prefixes,
# refresh/patterns.py PACT_AGENT_PATTERN.
PACT_AGENTS = [
    "pact-preparer",
    "pact-architect",
    "pact-backend-coder",
    "pact-frontend-coder",
    "pact-database-engineer",
    "pact-devops-engineer",
    "pact-n8n",
    "pact-test-engineer",
    "pact-security-engineer",
    "pact-qa-engineer",
    "pact-auditor",
    "pact-secretary",
]

# Canonical path for the compact summary file written by postcompact_archive
# and read by session_init (post-compaction recovery) and pact-secretary
# (session briefing).
#
# SINGLE-USE, AND ARCHIVED RATHER THAN DELETED. The file must LEAVE this path
# once processed, because a copy left here is processed again by the next
# briefing in the same session. It does NOT follow that the bytes may go:
# postcompact_archive writes this path as a GLOBAL SINGLETON and no second copy
# exists anywhere, so whoever clears it destroys the only copy unless the clear
# is a MOVE. Both clearers move it — the secretary into its session directory,
# and session_init into the same place when it finds one left behind.
#
# Also referenced in: pact-plugin/agents/pact-secretary.md (the archive rule and
# its fallback) and pact-plugin/hooks/session_init.py (the stale-summary archive,
# and the resume-time pointer that tells a lead where the file went).
# Accessor (B1) — resolves $CLAUDE_CONFIG_DIR at CALL time (no import-time freeze).
def get_compact_summary_path() -> Path:
    return get_claude_config_dir() / "pact-sessions" / "compact-summary.txt"


# Filename prefix for an ARCHIVED compact summary. One definition, so the hook
# that writes an archive cannot drift from the convention the secretary states
# in prose. The two PROSE statements are pinned against each other by
# tests/test_compact_summary_archive_contract.py; this is the code-side
# spelling, deliberately kept out of that pin's `<placeholder>.txt` shape so
# that defining it here does not change either file's stated-convention count.
COMPACT_SUMMARY_ARCHIVE_PREFIX = "compact-summary-"

# Fixed-name slot for a stale summary that cannot be attributed to a session.
# A FIXED name, never a timestamped one: this lives in the shared sessions root,
# where timestamped files would accumulate without bound. One slot makes that
# growth UNREPRESENTABLE rather than merely policed.
#
# THE TRADE, so nobody discovers it by losing something: a second orphan
# OVERWRITES the first. That is a strict improvement on the previous behaviour,
# which lost the summary every time; and the newer copy is the more likely to be
# wanted, since an older orphan is from a session nobody came back for.
COMPACT_SUMMARY_ORPHAN_NAME = "compact-summary.orphan.txt"


# Subject prefixes that indicate synthetic / system-level tasks (phase
# markers and algedonic signal tasks) as opposed to real feature work.
# Used by session_state._derive_feature_from_journal and
# _read_feature_subject_from_disk to reject system tasks from the
# feature-subject derivation path.
#
# NOTE: This is distinct from `phase_prefixes` in task_utils.py
# (`PREPARE:`, `ARCHITECT:`, `CODE:`, `TEST:`, `Review:`) — those are
# phase-marker-task-subject prefixes, a narrower set used by
# find_feature_task / find_current_phase. The two tuples have
# different semantics and should not be unified.
SYSTEM_TASK_PREFIXES = ("Phase:", "BLOCKER:", "ALERT:", "HALT:")
