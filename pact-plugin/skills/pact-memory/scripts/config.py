"""
PACT Memory Configuration

Location: pact-plugin/skills/pact-memory/scripts/config.py

Centralized configuration for the PACT Memory skill.
All path resolution is defined here to ensure consistency across all modules.

Used by:
- database.py: Database path resolution (get_db_path, get_memory_dir)
- setup_memory.py: Directory creation (get_memory_dir)

EVERY PATH HERE RESOLVES AT USE TIME, NEVER AT IMPORT TIME. This module used to
export `PACT_MEMORY_DIR` and `DB_PATH` as module-level constants, each computed
from `Path.home()` when the module first imported. That made the store location
a property of WHEN the module was imported rather than of the environment, and
it produced two defects a caller could not see:

  1. A test that redirects `Path.home()` protected the store only when this
     module happened to import INSIDE that test. Import it at collection time --
     which any module-level `from scripts.memory_api import ...` does -- and the
     constant was already bound to the real home, so the redirect reached
     nothing. The protection existed and was ACCIDENTAL, decided by import order.
  2. `from .config import DB_PATH` COPIED the value into a second module's
     namespace, so patching it here did not reach that module at all.

Resolving in a function removes both: no stored value can go stale, and no
second copy can diverge. The environment variable exists because no in-process
mechanism crosses a process boundary -- a spawned child is a fresh interpreter,
in which a patched `Path.home()` never happened.
"""

from __future__ import annotations

import os
from pathlib import Path

# Environment variable that relocates the whole memory store.
#
# DELIBERATELY MEMORY-SPECIFIC. It names this store and nothing else. A general
# home or config override is the wrong shape here: `CLAUDE_CONFIG_DIR` takes
# precedence over `Path.home()` in `get_claude_config_dir`, so honouring that
# variable would shadow the home-redirect convention the rest of the suite is
# built on. Narrow scope is what makes this variable safe to add.
#
# AN EXPLICIT DISCRIMINATOR BEATS AN INFERRED ONE, and that is the load-bearing
# reason for this design rather than the relocation feature it also provides.
# Isolating a test process from the real store looks like it needs the code to
# work out whether it is under test, and every mechanism for working that out
# can be WRONG ABOUT THE WORLD: `_refuse_live_db_under_pytest` in cli.py keys on
# an inherited `PYTEST_CURRENT_TEST`, and its own docstring records that the
# variable is absent during collection and around session-scoped setup, and that
# its fail direction is ALLOW.
#
# This variable removes the inference entirely. A test harness SETS it and a
# production process does not, so there is nothing to detect and nothing to get
# wrong: the resolver cannot be mistaken about whether a variable was set. That
# also dissolves what looks like a conflict between isolating tests and keeping
# production working. They are not in tension, because they are distinguished by
# an explicit signal rather than by a guess about the caller.
MEMORY_DIR_ENV = "PACT_MEMORY_DIR"


def get_memory_dir() -> Path:
    """Return the base directory for all PACT memory data.

    Resolution order:
      1. The `PACT_MEMORY_DIR` environment variable, when set and non-empty.
      2. `~/.claude/pact-memory`.

    An empty value counts as unset, so `PACT_MEMORY_DIR=""` cannot silently
    relocate the store to the current directory.
    """
    override = os.environ.get(MEMORY_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "pact-memory"


def get_db_path() -> Path:
    """Return the memory database file path. Creates no directory."""
    return get_memory_dir() / "memory.db"


def get_session_tracking_dir() -> Path:
    """Return the session tracking directory."""
    return get_memory_dir() / "session-tracking"
