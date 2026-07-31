"""Handover tests for the two BLOCKING findings of the PR 1 security review.

EXPECTED STATE ON THE UNFIXED TREE:
  TestStalenessSurfacesMustDeclineWhenUnbounded
    test_unbounded_region_gets_no_stale_markers_written   FAIL  (defect)
    test_unbounded_region_does_not_arm_the_block_gate     FAIL  (defect)
    test_bounded_stale_pins_are_STILL_marked              PASS  (control)
    test_bounded_stale_pins_STILL_arm_the_block_gate      PASS  (control)
  TestRepairMustNotExpelAGenuinePin
    test_interleaved_file_is_refused_not_corrupted        FAIL  (defect)
    test_normal_absorbed_file_still_repairs               PASS  (control)

THE TWO CONTROLS ARE THE POINT. Each defect test asserts that something
STOPS happening, and a fix that simply switches the whole surface off would
satisfy it. The controls assert the surface still works where it should, so
the pair discriminates. Do not delete a control to make a run green.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))


# --- fixture builders ------------------------------------------------------
def _pin(title, date="2026-07-01", body="ordinary pin body"):
    return f"<!-- pinned: {date} -->\n### {title}\n\n{body}\n\n"


def _stale_pin(title, date="2026-07-01"):
    """A pin that is GENUINELY stale: its body carries a merged-PR date."""
    return _pin(title, date=date, body="Landed in PR #123, merged 2026-01-05.")


def _note(day):
    """An ordinary Working Memory entry in this repository's own format."""
    return f"### 2026-01-{day:02d} 09:00\n**Context**: ordinary session note.\n\n"


def _claude_md(pins, terminated, tail=""):
    out = "# Project Memory\n\n## Pinned Context\n\n" + pins
    if terminated:
        out += "## Working Memory\n\n"
    return out + tail


NOTES = "".join(_note(d) for d in (10, 11, 12))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Write a CLAUDE.md and anchor every resolver at it."""
    def _make(content):
        md = tmp_path / "CLAUDE.md"
        md.write_text(content, encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        import staleness
        monkeypatch.setattr(staleness, "get_project_claude_md_path", lambda: md)
        return md
    return _make


def _measure(content):
    """Precondition oracle. Asserting the region was FOUND before asserting
    anything about it is mandatory here: a None parse and a bounded parse
    both make the defect assertions pass for the wrong reason."""
    from staleness import _parse_pinned_section
    from pin_caps import parse_pins
    parsed = _parse_pinned_section(content)
    assert parsed is not None, "control: the fixture has no Pinned Context region"
    return len(parse_pins(parsed.content)), parsed.bounded


# === BLOCKING 1 ============================================================
class TestStalenessSurfacesMustDeclineWhenUnbounded:
    """`check_pinned_staleness` and `check_pinned_block_signal` consume
    `parsed.content` without consulting `parsed.bounded`, so on an unbounded
    region they treat ordinary Working Memory entries as pins."""

    UNBOUNDED = _claude_md(
        _pin("Real A", "2026-07-01") + _pin("Real B", "2026-07-02"),
        terminated=False, tail=NOTES,
    )
    BOUNDED_STALE = _claude_md(
        _stale_pin("Real A", "2026-07-01") + _stale_pin("Real B", "2026-07-02"),
        terminated=True, tail=NOTES,
    )

    def test_unbounded_region_gets_no_stale_markers_written(self, project):
        """DEFECT: the staleness pass MUTATES the curator's own notes."""
        count, bounded = _measure(self.UNBOUNDED)
        assert (count, bounded) == (5, False), (
            "control: the fixture must parse as an UNBOUNDED region whose "
            "count is inflated by the notes, or this is not the input class"
        )
        md = project(self.UNBOUNDED)
        before = md.read_text(encoding="utf-8")

        from staleness import check_pinned_staleness
        check_pinned_staleness(claude_md_path=md)

        after = md.read_text(encoding="utf-8")
        marked = [d for d in (10, 11, 12)
                  if f"### 2026-01-{d:02d} 09:00\n<!-- STALE:" in after]
        assert not marked, (
            f"STALE markers were injected into ordinary Working Memory "
            f"entries {marked}. They are not pins. The region is unbounded, "
            f"so the measure is the one this PR declares untrustworthy."
        )
        assert after == before, "an unbounded region must not be written at all"

    def test_unbounded_region_does_not_arm_the_block_gate(self, project):
        """DEFECT: the phantom stale count arms a second deny gate, whose
        message names a cure over pins the curator does not hold."""
        md = project(self.UNBOUNDED)
        from staleness import check_pinned_staleness, check_pinned_block_signal
        check_pinned_staleness(claude_md_path=md)
        signal = check_pinned_block_signal(claude_md_path=md)
        assert signal is None, (
            f"block signal fired on an unbounded region: {signal!r}. "
            f"pin_staleness_gate then denies the curator's next ADD-shaped "
            f"edit with an impossible cure."
        )

    def test_bounded_stale_pins_are_STILL_marked(self, project):
        """CONTROL. A fix that disables staleness outright passes the two
        tests above and fails this one."""
        count, bounded = _measure(self.BOUNDED_STALE)
        assert (count, bounded) == (2, True), (
            "control: the fixture must be a BOUNDED region of 2 real pins"
        )
        md = project(self.BOUNDED_STALE)
        from staleness import check_pinned_staleness
        status = check_pinned_staleness(claude_md_path=md)
        after = md.read_text(encoding="utf-8")
        assert after.count("<!-- STALE: Last relevant") == 2, (
            f"genuinely stale pins on a BOUNDED region must still be marked. "
            f"status={status!r}"
        )

    def test_bounded_stale_pins_STILL_arm_the_block_gate(self, project):
        """CONTROL, on the second surface."""
        md = project(self.BOUNDED_STALE)
        from staleness import check_pinned_staleness, check_pinned_block_signal
        check_pinned_staleness(claude_md_path=md)
        signal = check_pinned_block_signal(claude_md_path=md)
        assert signal is not None and signal.kind == "stale", (
            f"a BOUNDED region holding 2 genuinely stale pins must still arm "
            f"the gate. Got {signal!r}"
        )


# === BLOCKING 2 ============================================================
class TestRepairMustNotExpelAGenuinePin:
    """The placement discriminator -- first undated `### ` after a dated one
    -- is the SAME signature the gate uses for a smuggled pin, so a `### `
    inside a real pin body is indistinguishable from absorbed content."""

    INTERLEAVED = _claude_md(
        "<!-- pinned: 2026-07-01 -->\n### Real A\n\nbody text.\n"
        "### Sub heading\nmore of pin A's body.\n\n"
        "<!-- pinned: 2026-07-02 -->\n### Real B\n\nreal pin B body\n\n",
        terminated=False, tail=NOTES,
    )
    NORMAL = _claude_md(
        _pin("Real A", "2026-07-01") + _pin("Real B", "2026-07-02"),
        terminated=False, tail=NOTES,
    )

    def test_interleaved_file_is_refused_not_corrupted(self, project):
        """DEFECT: the terminator lands inside a pin body and expels a
        genuine dated pin from the region."""
        count, bounded = _measure(self.INTERLEAVED)
        assert (count, bounded) == (6, False), (
            "control: the fixture must parse the in-body heading as an entry "
            "and stay unbounded, or it is not the input class it claims"
        )
        md = project(self.INTERLEAVED)
        from shared.claude_md_manager import ensure_pinned_terminator
        status = ensure_pinned_terminator()
        after = md.read_text(encoding="utf-8")

        from staleness import _parse_pinned_section
        from pin_caps import parse_pins
        parsed = _parse_pinned_section(after)
        headings = [p.heading for p in parse_pins(parsed.content)] if parsed else []
        assert "### Real B" in headings, (
            f"the repair expelled a GENUINE dated pin from the pinned region. "
            f"region now holds {headings}; status={status!r}. Neither the caps "
            f"nor /PACT:prune-memory can reach an expelled pin."
        )
        assert after == self.INTERLEAVED, (
            "the safe outcome is a REFUSAL that writes nothing, leaving the "
            "region unbounded -- which this module already calls the safe state"
        )

    def test_normal_absorbed_file_still_repairs(self, project):
        """CONTROL. A fix that refuses everything passes the test above and
        fails this one."""
        count, bounded = _measure(self.NORMAL)
        assert (count, bounded) == (5, False), "control: wrong input class"
        md = project(self.NORMAL)
        from shared.claude_md_manager import (
            ensure_pinned_terminator, PINNED_TERMINATOR_HEADING,
        )
        status = ensure_pinned_terminator()
        after = md.read_text(encoding="utf-8")
        assert "Repaired" in (status or ""), (
            f"the ordinary absorbed-notes file must still repair. Got {status!r}"
        )
        heading_at = after.index(PINNED_TERMINATOR_HEADING)
        assert after.index("### Real B") < heading_at < after.index("### 2026-01-10"), (
            "the terminator must sit after the last real pin and before the "
            "first absorbed note"
        )
