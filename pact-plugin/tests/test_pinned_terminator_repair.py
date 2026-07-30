"""
Location: pact-plugin/tests/test_pinned_terminator_repair.py
Summary: Verification tests for `claude_md_manager.ensure_pinned_terminator`
         (the case-5 repair), its placement rule, its two refusal guards, its
         ordering against the managed-structure migration, and the SessionStart
         directive that reports an unbounded pinned region.
Used by: the pytest suite. Companion to hooks/shared/claude_md_manager.py and
         hooks/session_init.py.

THE PROPERTY UNDER TEST IS PLACEMENT, NOT PRESENCE. Inserting the terminating
heading anywhere makes `bounded` read True, so any assertion that only checks
`bounded` passes for the WRONG implementation — the one that appends at the end
of the region, leaves the absorbed entries inside, and re-arms the very
over-block the repair exists to prevent. Every test below asserts the PIN COUNT
alongside boundedness, because the count is the discriminator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from pin_caps import parse_pins  # noqa: E402
from shared.claude_md_manager import (  # noqa: E402
    MANAGED_END_MARKER,
    MANAGED_START_MARKER,
    PINNED_TERMINATOR_HEADING,
    ensure_pinned_terminator,
    migrate_to_managed_structure,
)
from staleness import _parse_pinned_section  # noqa: E402

_REAL_PIN = "<!-- pinned: 2026-07-30 -->\n### Real pin {n}\nShort body.\n\n"
_NOTE = "### 2026-07-{d:02d}\n**Context**: routine session note.\n\n"

REAL_PINS = 2
NOTES = 12


def _pins_body(real_pins: int = REAL_PINS, notes: int = NOTES) -> str:
    return (
        "## Pinned Context\n\n"
        + "".join(_REAL_PIN.format(n=i) for i in range(1, real_pins + 1))
        + "".join(_NOTE.format(d=d) for d in range(1, notes + 1))
    )


def case_5(**kwargs) -> str:
    """A MIGRATED file whose pinned region lost its terminating heading.

    Markers come from the imported constants. A hand-spelled marker makes
    `extract_managed_region` return None, the parser falls back to the whole
    file, and every arm lands on the branch where right and wrong agree.
    """
    return (
        "# PACT Framework and Managed Project Memory\n\n"
        f"{MANAGED_START_MARKER}\n"
        f"{_pins_body(**kwargs)}"
        f"{MANAGED_END_MARKER}\n"
    )


def unmigrated(**kwargs) -> str:
    """An UNMIGRATED unbounded file — no managed markers.

    The ordering test needs this shape: `migrate_to_managed_structure`
    early-returns when the start marker is present, so a migrated fixture
    cannot show the ordering at all.
    """
    return "# Project Memory\n\n" + _pins_body(**kwargs)


def measure(content: str) -> tuple[int, bool]:
    """Return (pin count, bounded) for a CLAUDE.md body."""
    parsed = _parse_pinned_section(content)
    if parsed is None:
        return 0, True
    return len(parse_pins(parsed.content)), parsed.bounded


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project dir whose CLAUDE.md the repair will resolve and write."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    claude_md = tmp_path / "CLAUDE.md"

    def write(content: str) -> Path:
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    write.path = claude_md  # type: ignore[attr-defined]
    return write


class TestPlacement:
    """Certification row 6. The row that catches the defect the constraint,
    as originally worded, would have shipped."""

    def test_the_fixture_starts_in_the_broken_state(self, project):
        """Precondition control. Without this the repair could be a no-op
        on an already-correct file and every assertion below would pass."""
        content = case_5()
        count, bounded = measure(content)
        assert bounded is False
        assert count == REAL_PINS + NOTES == 14, (
            "the fixture must reproduce the inflation, otherwise the repair "
            "has nothing to fix and this file certifies nothing"
        )

    def test_repair_excludes_the_absorbed_notes(self, project):
        """The count is the discriminator, not `bounded`.

        END placement also makes `bounded` True. It leaves the count at 14.
        """
        path = project(case_5())
        status = ensure_pinned_terminator()
        assert status is not None and "Repaired" in status

        count, bounded = measure(path.read_text(encoding="utf-8"))
        assert bounded is True
        assert count == REAL_PINS, (
            f"placement is wrong: the region is bounded but still holds "
            f"{count} entries. A terminator at the END of the region bounds "
            f"it at the end it already had and re-arms the over-block."
        )

    def test_heading_lands_before_the_first_undated_entry(self, project):
        """Pin the POSITION directly, so a count that happens to be right
        for another reason cannot satisfy this."""
        path = project(case_5())
        ensure_pinned_terminator()
        text = path.read_text(encoding="utf-8")

        heading_at = text.index(PINNED_TERMINATOR_HEADING)
        last_real_pin_at = text.index("### Real pin 2")
        first_note_at = text.index("### 2026-07-01")
        assert last_real_pin_at < heading_at < first_note_at

    def test_the_real_pins_stay_inside_the_region(self, project):
        """Guard against the opposite error: a heading placed too EARLY
        pushes genuine pins out of the region and under-counts."""
        path = project(case_5())
        ensure_pinned_terminator()
        parsed = _parse_pinned_section(path.read_text(encoding="utf-8"))
        assert parsed is not None
        headings = [pin.heading for pin in parse_pins(parsed.content)]
        assert headings == ["### Real pin 1", "### Real pin 2"]

    def test_repair_changes_no_pin_text(self, project):
        """Constraint 1: one heading inserted, nothing else altered.

        Asserts the original bytes survive as a contiguous run on each side
        of the insertion, so the change is exactly an insertion.
        """
        before = case_5()
        path = project(before)
        ensure_pinned_terminator()
        after = path.read_text(encoding="utf-8")

        inserted = f"{PINNED_TERMINATOR_HEADING}\n\n"
        assert after.replace(inserted, "", 1) == before


class TestRefusalGuards:

    def test_guard_1_refuses_when_no_entry_is_dated(self, project):
        """Certification row 8. A hand-maintained file has no signal that
        separates a pin from a note; inserting before the first `### `
        would push EVERY pin out of the region."""
        hand_maintained = (
            "# PACT Framework and Managed Project Memory\n\n"
            f"{MANAGED_START_MARKER}\n"
            "## Pinned Context\n\n"
            + "".join(_NOTE.format(d=d) for d in range(1, 4))
            + f"{MANAGED_END_MARKER}\n"
        )
        path = project(hand_maintained)
        status = ensure_pinned_terminator()

        assert status is not None and "skipped" in status.lower()
        assert path.read_text(encoding="utf-8") == hand_maintained, (
            "guard 1 must not write. Refusing leaves the file unbounded, "
            "which is the SAFE state: the gate declines rather than "
            "enforcing on a false measure."
        )

    def test_guard_2_refuses_when_nothing_was_absorbed(self, project):
        """No undated entry after a dated one — there is nothing to exclude."""
        only_real_pins = case_5(notes=0)
        # Control: this fixture must still be UNBOUNDED, or the refusal
        # under test would be indistinguishable from the bounded no-op.
        assert measure(only_real_pins)[1] is False
        path = project(only_real_pins)
        status = ensure_pinned_terminator()

        assert status is not None and "skipped" in status.lower()
        assert path.read_text(encoding="utf-8") == only_real_pins

    def test_the_two_refusals_give_different_reasons(self, project):
        """Anti-vacuity: two guards that emit one string cannot be told
        apart by the curator who has to act on them."""
        project(
            "# T\n\n" + MANAGED_START_MARKER + "\n## Pinned Context\n\n"
            + "".join(_NOTE.format(d=d) for d in range(1, 4))
            + MANAGED_END_MARKER + "\n"
        )
        guard_1 = ensure_pinned_terminator()
        project(case_5(notes=0))
        guard_2 = ensure_pinned_terminator()
        assert guard_1 != guard_2


class TestIdempotence:
    """Certification row 9.

    THE ROW AS ORIGINALLY WORDED WAS VACUOUS AND IS REPAIRED HERE. Its GREEN
    was "the second run is a no-op" and its RED was "run against a bounded
    file, it must not write" — BOTH DIRECTIONS ASSERT A NON-WRITE. A stub
    that always returns None and never writes satisfies both. So the
    non-write assertions below are each paired with a POSITIVE control that
    the repair DOES write when it should.
    """

    def test_second_run_is_a_no_op_and_the_first_run_was_not(self, project):
        path = project(case_5())

        first = ensure_pinned_terminator()
        after_first = path.read_text(encoding="utf-8")
        assert first is not None and "Repaired" in first
        assert after_first != case_5(), (
            "POSITIVE CONTROL: the first run must actually write. Without "
            "this, a function that never writes passes the no-op assertion "
            "below and the whole test certifies nothing."
        )

        second = ensure_pinned_terminator()
        assert second is None
        assert path.read_text(encoding="utf-8") == after_first

    def test_bounded_file_is_untouched(self, project):
        bounded = case_5().replace(
            "### 2026-07-01", f"{PINNED_TERMINATOR_HEADING}\n\n### 2026-07-01", 1
        )
        assert measure(bounded)[1] is True, "control: fixture must be bounded"
        path = project(bounded)
        assert ensure_pinned_terminator() is None
        assert path.read_text(encoding="utf-8") == bounded


class TestOrderingAgainstMigration:
    """Certification row 7. The order is measured, not preferred."""

    def test_repair_then_migrate_yields_only_the_real_pins(self, project):
        path = project(unmigrated())
        assert measure(unmigrated()) == (14, False), "control: broken to start"

        ensure_pinned_terminator()
        migrate_to_managed_structure()

        count, bounded = measure(path.read_text(encoding="utf-8"))
        assert bounded is True
        assert count == REAL_PINS

    def test_migrate_first_locks_the_phantom_entries_in(self, project):
        """The reverse order, run as a MEASUREMENT rather than described.

        The migration bounds the region without correcting the placement.
        The repair then sees a bounded file and declines, so the absorbed
        entries stay inside the pinned region permanently.

        This is the RED control for the ordering, and it also records a
        defect in the shipped migration that outlives this change.
        """
        path = project(unmigrated())

        migrate_to_managed_structure()
        after_migration = measure(path.read_text(encoding="utf-8"))
        repair_status = ensure_pinned_terminator()

        count, bounded = measure(path.read_text(encoding="utf-8"))
        assert bounded is True
        assert repair_status is None, "the repair declines on a bounded file"
        assert count == REAL_PINS + NOTES, (
            f"expected the phantom entries to be locked in by the migration; "
            f"measured {count}. If this now reads {REAL_PINS}, the migration "
            f"itself was fixed and the ordering constraint can be revisited."
        )
        assert after_migration[0] == count

    def test_the_two_orders_disagree(self, project):
        """Mandatory anti-vacuity control for the ordering pair."""
        path = project(unmigrated())
        ensure_pinned_terminator()
        migrate_to_managed_structure()
        correct_order = measure(path.read_text(encoding="utf-8"))

        path = project(unmigrated())
        migrate_to_managed_structure()
        ensure_pinned_terminator()
        wrong_order = measure(path.read_text(encoding="utf-8"))

        assert correct_order[0] != wrong_order[0]


class TestNeverRaises:
    """Certification row 10, on the writer. Fail open on every fault."""

    def test_returns_none_when_the_parser_raises(self, project, monkeypatch):
        project(case_5())
        import staleness

        def boom(_content):
            raise RuntimeError("parser fault")

        monkeypatch.setattr(staleness, "_parse_pinned_section", boom)
        # PROBE CONTROL: prove the injected fault is actually reached,
        # otherwise "returns None" is satisfied by never calling the parser.
        with pytest.raises(RuntimeError):
            staleness._parse_pinned_section("x")
        assert ensure_pinned_terminator() is None

    def test_returns_none_without_a_project_dir(self, project, monkeypatch):
        project(case_5())
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert ensure_pinned_terminator() is None

    def test_returns_none_when_the_file_is_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert ensure_pinned_terminator() is None


class TestUnboundedDirective:
    """Step 5: the SessionStart emission surface."""

    @pytest.fixture(autouse=True)
    def _resolve_to_tmp(self, project, monkeypatch):
        import staleness
        monkeypatch.setattr(
            staleness, "get_project_claude_md_path", lambda: project.path
        )
        self.project = project

    def _directive(self, agent_type="pact-orchestrator", **kwargs):
        from session_init import check_pinned_region_unbounded_directive
        return check_pinned_region_unbounded_directive(
            {"agent_type": agent_type}, **kwargs
        )

    def test_fires_on_an_unbounded_region(self):
        self.project(case_5())
        message = self._directive()
        assert message is not None
        assert "Pinned Context" in message
        assert PINNED_TERMINATOR_HEADING in message, (
            "the directive must name the exact repair, not just report a state"
        )

    def test_silent_on_a_bounded_region(self):
        """Anti-vacuity partner. A directive that always fires is not a signal."""
        self.project(
            case_5().replace(
                "### 2026-07-01",
                f"{PINNED_TERMINATOR_HEADING}\n\n### 2026-07-01",
                1,
            )
        )
        assert self._directive() is None

    def test_silent_for_a_teammate_frame(self):
        """SCOPE. SessionStart runs for every frame; the gate does not run
        for a teammate. An unscoped directive would instruct exactly the
        actors the gate does not control to edit a file they do not own."""
        self.project(case_5())
        assert self._directive(agent_type="pact-backend-coder") is None
        assert self._directive(agent_type=None) is None

    def test_surfaces_the_refusal_reason(self):
        """A refusal reaching the curator is the whole point of the
        status pass-through: the plugin says what it already tried."""
        self.project(case_5())
        message = self._directive(repair_status="Pinned-region repair skipped: XYZZY.")
        assert message is not None and "XYZZY" in message

    def test_says_so_when_no_repair_ran(self):
        self.project(case_5())
        message = self._directive()
        assert message is not None and "did not repair it automatically" in message

    def test_returns_none_when_the_parse_raises(self, monkeypatch):
        """PATCH THE SEAM THE CALLER ACTUALLY USES.

        `session_init` binds `_parse_pinned_section` with a module-level
        `from staleness import ...`, so the name is frozen at import. Patching
        `staleness._parse_pinned_section` leaves that binding untouched and
        the directive runs the REAL parser — the first version of this test
        did exactly that, and it failed by reporting a live directive where
        it expected None. The failure was in the instrument, not the code.

        The repair's own equivalent test patches `staleness` and is correct
        to, because `_ensure_pinned_terminator_inner` imports at FUNCTION
        level and therefore re-reads the attribute on every call. Two
        different seams in the same change; neither patch works for the other.
        """
        self.project(case_5())
        import session_init

        def boom(_content):
            raise RuntimeError("parser fault")

        monkeypatch.setattr(session_init, "_parse_pinned_section", boom)
        # PROBE CONTROL: prove the injected fault is on the path the caller
        # takes, so "returns None" cannot be satisfied by a patch that misses.
        with pytest.raises(RuntimeError):
            session_init._parse_pinned_section("x")
        assert self._directive() is None


class TestCallOrderInSessionInit:
    """Certification row 7 AT THE CALL SITE, driven through the real
    `session_init.main()`.

    The ordering tests above call the two functions directly, so they prove
    the ORDER MATTERS. They cannot prove `session_init` uses the right one —
    a coder who fixes the placement and then wires the call in after the
    migration passes every one of them. This drives the real hook and
    records which function ran first.
    """

    def _order(self, monkeypatch, tmp_path, agent_type="pact-orchestrator"):
        import io
        import json
        from unittest.mock import patch

        import session_init

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        calls: list[str] = []

        stdin_data = json.dumps({
            "session_id": "11111111-2222-3333-4444-555555555555",
            "source": "startup",
            "agent_type": agent_type,
        })
        with patch("session_init.setup_plugin_symlinks", return_value=None), \
             patch("session_init.ensure_project_memory_md", return_value=None), \
             patch("session_init.check_pinned_staleness", return_value=None), \
             patch("session_init.get_task_list", return_value=None), \
             patch("session_init.restore_last_session", return_value=None), \
             patch("session_init.build_context_cache",
                   return_value=(Path("/tmp/ctx.json"), {})), \
             patch("session_init.persist_context", return_value=None), \
             patch("session_init.append_event"), \
             patch("session_init.update_session_info", return_value=None), \
             patch("session_init.check_resume_state", return_value=None), \
             patch("session_init._registry_resolve", return_value=None), \
             patch("session_init.get_peer_context", return_value=None), \
             patch("session_init.ensure_pinned_terminator",
                   side_effect=lambda: calls.append("repair")), \
             patch("session_init.migrate_to_managed_structure",
                   side_effect=lambda: calls.append("migrate")), \
             patch("sys.stdin", io.StringIO(stdin_data)), \
             patch("sys.stdout", new_callable=io.StringIO):
            with pytest.raises(SystemExit) as exc:
                session_init.main()
        assert exc.value.code == 0
        return calls

    def test_repair_runs_before_the_migration(self, monkeypatch, tmp_path):
        calls = self._order(monkeypatch, tmp_path)
        assert calls == ["repair", "migrate"], (
            "the repair MUST precede migrate_to_managed_structure. After the "
            "migration the file is bounded, so the repair declines and the "
            "absorbed entries are locked inside the pinned region for good."
        )

    @pytest.mark.parametrize(
        "agent_type",
        ["pact-backend-coder", "pact-orchestratr", None],
        ids=["teammate", "typo'd agent_type", "no --agent flag"],
    )
    def test_the_repair_runs_in_a_non_lead_frame(
        self, monkeypatch, tmp_path, agent_type
    ):
        """The repair is NOT lead-scoped, asserted POSITIVELY.

        THIS TEST WAS INVERTED. It previously asserted `"repair" not in
        calls` for a teammate frame, pinning a lead scope that turned out to
        be wrong. It is written positively on purpose: an inverted test that
        merely STOPS asserting the old property certifies nothing, and a
        guard silently downgraded into a rubber stamp is the exact failure
        this suite exists to prevent.

        The scope mattered because the migration below is NOT lead-scoped.
        With the repair scoped and the migration not, a non-lead frame ran
        the migration alone, bounded the region without fixing the
        placement, and locked the absorbed entries inside permanently.

        The parameters are the three frames where `is_lead` reads False.
        The third is the ordinary way a session launches with no `--agent`
        flag — the common case, not an edge case, which is what made the
        old scoping a defect rather than a curiosity.
        """
        calls = self._order(monkeypatch, tmp_path, agent_type=agent_type)
        assert "repair" in calls, (
            "the repair MUST run in a non-lead frame. Re-scoping it to the "
            "lead makes the outcome depend on which frame type starts a "
            "session first, and the losing branch is permanent."
        )
        assert "migrate" in calls, (
            "the migration is not lead-scoped and must not be narrowed as a "
            "side effect. This assertion is MORE load-bearing now, not less: "
            "the two calls' scopes finally match, so a future reader may be "
            "tempted to 'tidy' both into a lead block and reintroduce the "
            "defect from the other direction."
        )

    def test_the_directive_stays_lead_scoped(self, monkeypatch, tmp_path):
        """The WRITER is unscoped; the DIRECTIVE is not. Pin the asymmetry.

        Deleting the lead scope from the writer must not drag the directive
        with it. The directive TELLS AN ACTOR to edit a file the pin gate
        does not control for a teammate; the writer instructs nobody. Same
        file, different surfaces, different rules.

        BINDING CONTROL, and it earned its place immediately: the first
        version of this test patched `staleness.get_project_claude_md_path`
        and left `CLAUDE_PROJECT_DIR` alone. `session_init` binds the
        resolver by module-level import, so that patch missed the seam and
        the resolver read the REAL repository CLAUDE.md — which is bounded,
        so the directive returned None for BOTH frames. The teammate
        assertion would have passed for a reason that has nothing to do with
        scope. The control below failed instead, which is the whole point of
        putting it before the assertion it protects.
        """
        from session_init import check_pinned_region_unbounded_directive
        from staleness import get_project_claude_md_path

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(case_5(), encoding="utf-8")

        resolved = get_project_claude_md_path()
        assert resolved is not None and tmp_path in resolved.parents, (
            f"BINDING CONTROL FAILED: the resolver returned {resolved}, "
            f"outside the temp directory. Every verdict below would describe "
            f"the real repository file rather than the fixture."
        )

        lead = check_pinned_region_unbounded_directive(
            {"agent_type": "pact-orchestrator"}
        )
        teammate = check_pinned_region_unbounded_directive(
            {"agent_type": "pact-backend-coder"}
        )
        assert lead is not None, (
            "control: the directive must fire for a lead on this fixture, "
            "otherwise the teammate assertion below is vacuous"
        )
        assert teammate is None


class TestFrameTypeDoesNotChangeTheOutcome:
    """The property Option A actually buys: SAME INPUT, ONE OUTCOME.

    The absence of this property is what caused the defect. The old code
    produced 2 pins from a lead frame and 14 permanently from any other,
    on byte-identical input — a race whose losing branch could not be
    recovered. This asserts the two frames converge.
    """

    def _run_session(self, tmp_path, monkeypatch, agent_type):
        """Drive the REAL `session_init.main()` and measure the file after.

        IT MUST GO THROUGH session_init, NOT CALL THE TWO FUNCTIONS DIRECTLY.
        Neither `ensure_pinned_terminator` nor `migrate_to_managed_structure`
        reads the frame, so a direct-call version of this test is
        frame-independent BY CONSTRUCTION — it would pass no matter how
        session_init gates them, which is the only thing under test here.
        Both writers are left UNPATCHED for the same reason.
        """
        import io
        import json
        from unittest.mock import patch

        import session_init

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(unmigrated(), encoding="utf-8")

        frame = {"agent_type": agent_type} if agent_type else {}
        stdin_data = json.dumps({
            "session_id": "11111111-2222-3333-4444-555555555555",
            "source": "startup",
            **frame,
        })
        with patch("session_init.setup_plugin_symlinks", return_value=None), \
             patch("session_init.ensure_project_memory_md", return_value=None), \
             patch("session_init.check_pinned_staleness", return_value=None), \
             patch("session_init.get_task_list", return_value=None), \
             patch("session_init.restore_last_session", return_value=None), \
             patch("session_init.build_context_cache",
                   return_value=(Path("/tmp/ctx.json"), {})), \
             patch("session_init.persist_context", return_value=None), \
             patch("session_init.append_event"), \
             patch("session_init.update_session_info", return_value=None), \
             patch("session_init.check_resume_state", return_value=None), \
             patch("session_init._registry_resolve", return_value=None), \
             patch("session_init.get_peer_context", return_value=None), \
             patch("sys.stdin", io.StringIO(stdin_data)), \
             patch("sys.stdout", new_callable=io.StringIO):
            with pytest.raises(SystemExit) as exc:
                session_init.main()
        assert exc.value.code == 0
        return measure(claude_md.read_text(encoding="utf-8"))

    def test_lead_and_non_lead_frames_converge(self, tmp_path, monkeypatch):
        lead = self._run_session(tmp_path, monkeypatch, "pact-orchestrator")

        other = tmp_path / "other"
        other.mkdir()
        non_lead = self._run_session(other, monkeypatch, None)

        assert lead == non_lead, (
            f"byte-identical input produced different outcomes by frame "
            f"type: lead={lead}, non-lead={non_lead}. That is the race "
            f"Option A removes, and its losing branch is permanent."
        )
        assert lead == (REAL_PINS, True), (
            f"both frames converged on the WRONG state {lead}; expected "
            f"{(REAL_PINS, True)}. Convergence alone is not the property — "
            f"two frames agreeing on 14 phantom pins would also be equal."
        )
