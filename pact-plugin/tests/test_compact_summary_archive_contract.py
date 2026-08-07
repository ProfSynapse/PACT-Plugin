"""
The compact-summary archive naming convention is stated in TWO files and
nothing links them.

  * ``agents/pact-secretary.md`` tells the secretary what to name the file it
    archives.
  * ``hooks/session_init.py`` archives a summary the secretary left behind, and
    tells a resuming lead what to look for when the canonical path is empty.

BOTH FILES DESCRIBE A CONVENTION THEY BOTH ACT ON, and neither is the reference
for the other. An earlier version of this docstring named the agent body the
WRITER and the hook the READER, on the ground that the hook "only describes what
the writer does". That stopped being true when the hook gained its own archive
step: it now writes an archive name as well as describing one. This pin never
adjudicated that role and does not need it — it compares the two PROSE
STATEMENTS of the convention against each other, and EITHER file may be the one
that drifted.

Neither can import from the other — one is Markdown loaded into an LLM's
context, the other is a hook module — so a single source of truth is not
available across that boundary and a pin is the only instrument that can see a
divergence. The hook's archive step takes its prefix from a constant in
``hooks/shared/constants.py``, so the CODE cannot drift from itself; what stays
unlinked, and what this pin watches, is the PROSE.

WHAT THIS PIN DOES AND DOES NOT DO, stated so no reader infers more:

  * It CATCHES a rename or a deletion on either side. That is the failure mode
    worth catching: both spellings were written on the same day and agree now,
    so any later drift is silent and leaves the lead hunting for a filename
    that no longer exists.
  * It does NOT prevent divergence. It converts a silent drift into a red.
  * It does NOT check that the secretary HONOURS the convention at runtime.
    That is LLM behaviour and nothing here observes it. A green here means the
    two documents agree, not that the file on disk is named correctly.

NON-VACUITY: the prefix is CAPTURED from each file and the two captures are
compared with each other. It is never asserted against a literal retyped in
this file. A test that grepped both files for ``compact-summary-`` would pass
by construction, and would keep passing after one side was renamed to any
other string that still contained it.

REVERT CARDINALITY: change the prefix in ONE of the two files (for example
``compact-summary-<timestamp>.txt`` to ``compaction-summary-<timestamp>.txt``
in hooks/session_init.py) and run:
    python3 -m pytest tests/test_compact_summary_archive_contract.py
EXPECTED: {1 failed} — the agreement test; the arity test still passes because
both files still state the convention exactly once.

Remove the convention from one file instead and EXPECTED is {2 failed}, not
one: the arity test fails on the count, and the agreement test fails too
because unpacking an empty capture list raises. Both cardinalities were
observed, not predicted — the {2 failed} case was written down as {1 failed}
first and corrected against the run.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Named for WHICH FILE, not for the role it plays. A role-shaped name is a
# claim, and this one went stale the moment the hook started archiving; a name
# that identifies the surface cannot.
SECRETARY_SURFACE = _PLUGIN_ROOT / "agents" / "pact-secretary.md"
HOOK_SURFACE = _PLUGIN_ROOT / "hooks" / "session_init.py"

# A literal filename prefix followed by an angle-bracket placeholder and the
# extension: `compact-summary-<timestamp>.txt` -> `compact-summary-`. The
# placeholder BODY deliberately does not participate — the two files describe
# the timestamp differently on purpose, one for an LLM and one for a human
# reading a hook, and only the prefix has to agree.
_ARCHIVE_NAME_RE = re.compile(r"([A-Za-z0-9._-]+?)<[^>]+>\.txt")


def _stated_prefixes(path: Path) -> list[str]:
    return _ARCHIVE_NAME_RE.findall(path.read_text(encoding="utf-8"))


class TestCompactSummaryArchiveNaming:
    def test_each_file_states_the_convention_exactly_once(self):
        """Guards the agreement test from BOTH degenerate directions.

        Zero matches would make the comparison vacuous — two empty lists are
        equal. More than one would make "the" prefix ambiguous and let a
        second, divergent spelling sit in the same file unnoticed.
        """
        for path in (SECRETARY_SURFACE, HOOK_SURFACE):
            found = _stated_prefixes(path)
            assert len(found) == 1, (
                f"{path.relative_to(_PLUGIN_ROOT)} states the archive filename "
                f"convention {len(found)} times, expected exactly once: "
                f"{found}. Zero means the convention was removed or reworded "
                f"out of the `<placeholder>.txt` shape this pin reads; more "
                f"than one means a second spelling can diverge invisibly."
            )
            assert found[0], "captured an empty prefix — the pattern matched nothing useful"

    def test_the_two_surfaces_agree_on_the_prefix(self):
        """The whole point: two files, one convention, no mechanical link."""
        (secretary,) = _stated_prefixes(SECRETARY_SURFACE)
        (hook,) = _stated_prefixes(HOOK_SURFACE)
        assert hook == secretary, (
            f"the archive filename prefix has diverged.\n"
            f"  {SECRETARY_SURFACE.relative_to(_PLUGIN_ROOT)}: {secretary!r}\n"
            f"  {HOOK_SURFACE.relative_to(_PLUGIN_ROOT)}: {hook!r}\n"
            f"Both files archive under this convention and both state it in "
            f"prose. When they disagree a resuming lead is sent after a "
            f"filename that is never written, and nothing else fails — the "
            f"instruction is only read when the canonical path is already "
            f"empty. NEITHER side is automatically the reference: decide which "
            f"spelling is correct, fix the other, and check that the hook's "
            f"COMPACT_SUMMARY_ARCHIVE_PREFIX still matches what they say."
        )
