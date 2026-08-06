"""
The compact-summary archive naming convention is stated in TWO files and
nothing links them.

  * ``agents/pact-secretary.md`` tells the secretary what to name the file it
    archives. That is the WRITER, so it is the reference.
  * ``hooks/session_init.py`` tells a resuming lead what to look for when the
    canonical path is empty. That is the READER; it only describes what the
    writer does.

Neither can import from the other — one is Markdown loaded into an LLM's
context, the other is a hook module — so a single source of truth is not
available across that boundary and a pin is the only instrument that can see a
divergence.

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

WRITER = _PLUGIN_ROOT / "agents" / "pact-secretary.md"
READER = _PLUGIN_ROOT / "hooks" / "session_init.py"

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
        for path in (WRITER, READER):
            found = _stated_prefixes(path)
            assert len(found) == 1, (
                f"{path.relative_to(_PLUGIN_ROOT)} states the archive filename "
                f"convention {len(found)} times, expected exactly once: "
                f"{found}. Zero means the convention was removed or reworded "
                f"out of the `<placeholder>.txt` shape this pin reads; more "
                f"than one means a second spelling can diverge invisibly."
            )
            assert found[0], "captured an empty prefix — the pattern matched nothing useful"

    def test_the_reader_and_the_writer_agree_on_the_prefix(self):
        """The whole point: two files, one convention, no mechanical link."""
        (writer,) = _stated_prefixes(WRITER)
        (reader,) = _stated_prefixes(READER)
        assert reader == writer, (
            f"the archive filename prefix has diverged.\n"
            f"  writer {WRITER.relative_to(_PLUGIN_ROOT)}: {writer!r}\n"
            f"  reader {READER.relative_to(_PLUGIN_ROOT)}: {reader!r}\n"
            f"The secretary names the archived file; session_init tells a "
            f"resuming lead what to look for. When they disagree the lead is "
            f"sent after a filename that is never written, and nothing else "
            f"fails — the instruction is only read when the canonical path is "
            f"already empty. Update whichever side is wrong; the writer is the "
            f"reference."
        )
