"""Standing invariant for the leaf-symlink ALLOW on the CLAUDE.md write path.

WHY THIS EXISTS. `_atomic_write_text` deliberately ALLOWS a project CLAUDE.md
that is a symlink pointing OUTSIDE the project root. That ALLOW is sound only
because `os.replace` is renameat(2): it rebinds the directory ENTRY without
following the link, so the payload lands on the in-project entry and the
outside target is never touched.

The ALLOW inverts into a real escape under either of two rewrites:
  1. resolving the target once and using the resolved path downstream, or
  2. swapping temp-create + rename for open/truncate on the target path.
Neither touches the containment predicate, so the guard still reads correct
while the guarantee is gone. This test fails on both.

POSITIVE REACH CONTROL IS MANDATORY. The victim file must carry REPAIRABLE
content, so the writer actually writes. With non-repairable content the repair
no-ops and every assertion below passes without the write path executing once
-- certifying the ALLOW without ever exercising it.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))


def _pin(title, date="2026-07-01"):
    return f"<!-- pinned: {date} -->\n### {title}\n\nbody\n\n"


def _note(day):
    return f"### 2026-01-{day:02d} 09:00\n**Context**: note.\n\n"


# Unbounded WITH absorbed content -> the repair acts. This is the reach control.
REPAIRABLE = (
    "# Project Memory\n\n## Pinned Context\n\n"
    + _pin("Real A", "2026-07-01") + _pin("Real B", "2026-07-02")
    + "".join(_note(d) for d in (10, 11, 12))
)


@pytest.fixture
def outside_victim(tmp_path, monkeypatch):
    """A project CLAUDE.md that is a symlink to a file OUTSIDE the project."""
    outside = Path(tempfile.mkdtemp(prefix="outside-")).resolve()
    victim = outside / "victim.md"
    victim.write_text(REPAIRABLE, encoding="utf-8")

    root = tmp_path / "project"
    root.mkdir()
    link = root / "CLAUDE.md"
    link.symlink_to(victim)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return {"victim": victim, "link": link, "root": root}


class TestLeafSymlinkAllowStaysAnEntryRebind:

    def test_write_rebinds_the_entry_and_never_touches_the_outside_target(
        self, outside_victim
    ):
        victim = outside_victim["victim"]
        link = outside_victim["link"]
        before = victim.read_bytes()

        from shared.claude_md_manager import (
            ensure_pinned_terminator, PINNED_TERMINATOR_HEADING,
        )
        status = ensure_pinned_terminator()

        # REACH CONTROL, branch-unique. Without this the three assertions
        # below are satisfied by a repair that never ran.
        assert status is not None and "Repaired" in status, (
            f"reach control: the writer did not act, so this test certifies "
            f"nothing about the write path. status={status!r}"
        )

        assert victim.read_bytes() == before, (
            "the file OUTSIDE the project root was modified. The write "
            "followed the symlink instead of rebinding the entry -- the "
            "leaf-symlink ALLOW has become a containment escape."
        )
        assert not link.is_symlink(), (
            "the project path is still a symlink, so the payload did not "
            "land on the in-project entry"
        )
        assert PINNED_TERMINATOR_HEADING in link.read_text(encoding="utf-8"), (
            "the repaired content is not on the in-project entry"
        )
