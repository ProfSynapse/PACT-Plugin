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

from pin_caps import PIN_COUNT_CAP, parse_pins  # noqa: E402
from shared.claude_md_manager import (  # noqa: E402
    MANAGED_END_MARKER,
    MANAGED_START_MARKER,
    PINNED_TERMINATOR_HEADING,
    ensure_pinned_terminator,
    match_project_claude_md,
    migrate_to_managed_structure,
)
# IDENTIFY A REFUSAL BY CONSTANT IDENTITY, NEVER BY MATCHING ITS TEXT. A
# message-text assertion reddens on the next legitimate reword — which this
# module has already had once — and that churn is what teaches people to
# weaken assertions rather than to fix code. Importing the private names is
# deliberate: the constant IS the contract between the guard and its test.
from shared.claude_md_manager import (  # noqa: E402
    _REPAIR_REFUSED_NO_DATED_PIN,
    _REPAIR_REFUSED_NOTHING_ABSORBED,
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
    """A project dir whose CLAUDE.md the repair will resolve and write.

    ISOLATION IS BY `CLAUDE_PROJECT_DIR`, NOT BY PATCHING THE RESOLVER, and
    the difference is not stylistic. `session_init` binds
    `_get_project_claude_md_path` at MODULE IMPORT, so a
    `monkeypatch.setattr(staleness, ...)` never reaches the SessionStart
    directive — while `claude_md_manager` imports the same name INSIDE the
    function, where the identical patch does take effect. One target is
    correct for one consumer and dead for the other in the same test file,
    and the dead half reads exactly like the live half. The environment
    variable is read at call time on every path, so it removes the accident
    instead of detecting it.

    THE CONTROL BELOW IS BINDING AND IT IS HERE RATHER THAN IN A TEST OF ITS
    OWN. If the resolver escapes the temp directory, every consumer of this
    fixture silently measures the REAL repository CLAUDE.md — which reports
    a clean, plausible, entirely false result. Asserting it on the path that
    PRODUCES the fixture means a miss raises before any verdict exists,
    rather than annotating one that has already been believed.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    claude_md = tmp_path / "CLAUDE.md"

    def write(content: str) -> Path:
        claude_md.write_text(content, encoding="utf-8")

        import staleness
        resolved = staleness.get_project_claude_md_path()
        assert resolved is not None and resolved == claude_md, (
            f"BINDING CONTROL FAILED: the project CLAUDE.md resolved to "
            f"{resolved}, not to {claude_md}. The test would measure a file "
            f"outside the temp directory and report a verdict about it."
        )
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
        assert measure(hand_maintained)[1] is False, (
            "control: the fixture must be UNBOUNDED, or this refusal is "
            "indistinguishable from the bounded no-op"
        )
        path = project(hand_maintained)
        status = ensure_pinned_terminator()

        assert status == _REPAIR_REFUSED_NO_DATED_PIN, (
            f"expected the no-dated-pin refusal by CONSTANT IDENTITY. "
            f"Got {status!r}"
        )
        assert path.read_text(encoding="utf-8") == hand_maintained, (
            "guard 1 must not write. Refusing leaves the file unbounded, "
            "which is the SAFE state: the gate declines rather than "
            "enforcing on a false measure."
        )

    def test_guard_1_also_fires_when_the_section_holds_no_entries_at_all(
        self, project
    ):
        """SECOND REACHABLE INPUT for the same refusal, measured not assumed.

        A Pinned Context section holding prose and ZERO `### ` entries reaches
        guard 1 as well: both the pin list and the heading scan come back
        empty, their lengths agree, and no entry is dated. The wording holds
        here only VACUOUSLY — "no entry carries a date comment" when there are
        no entries — which is true rather than false, and the cure it names
        stays followable. That is the distinction from the heading-exists
        refusal, whose old wording asserted the existence of something absent.
        """
        prose_only = (
            "# PACT Framework and Managed Project Memory\n\n"
            f"{MANAGED_START_MARKER}\n"
            "## Pinned Context\n\n"
            "Some ordinary prose that carries no headings at all.\n\n"
            f"{MANAGED_END_MARKER}\n"
        )
        assert measure(prose_only) == (0, False), (
            "control: zero parsed entries AND unbounded. With entries "
            "present this is class (a) again; bounded, and the repair "
            "no-ops before reaching any guard."
        )
        path = project(prose_only)
        status = ensure_pinned_terminator()

        assert status == _REPAIR_REFUSED_NO_DATED_PIN, (
            f"expected the no-dated-pin refusal by CONSTANT IDENTITY. "
            f"Got {status!r}"
        )
        assert path.read_text(encoding="utf-8") == prose_only

    def test_guard_2_refuses_when_nothing_was_absorbed(self, project):
        """No undated entry after a dated one — there is nothing to exclude."""
        only_real_pins = case_5(notes=0)
        # Control: this fixture must still be UNBOUNDED, or the refusal
        # under test would be indistinguishable from the bounded no-op.
        assert measure(only_real_pins)[1] is False
        path = project(only_real_pins)
        status = ensure_pinned_terminator()

        assert status == _REPAIR_REFUSED_NOTHING_ABSORBED, (
            f"expected the nothing-absorbed refusal by CONSTANT IDENTITY. "
            f"Got {status!r}"
        )
        assert path.read_text(encoding="utf-8") == only_real_pins

    def test_guard_2_also_fires_when_the_undated_entry_precedes_the_dated_one(
        self, project
    ):
        """SECOND REACHABLE INPUT for the same refusal, measured not assumed.

        The predicate is not "there are no undated entries" but "no undated
        entry follows a dated one". So a section whose undated entry sits
        BEFORE the first dated pin reaches the same refusal, with an undated
        entry plainly present. THE WORDING SURVIVES THIS because it restates
        that predicate — "no undated `### ` entry AFTER a dated one" — rather
        than claiming there are none. A wording that had said "every entry is
        dated" would be FALSE here, which is the shape that made the
        heading-exists message wrong.
        """
        undated_first = (
            "# PACT Framework and Managed Project Memory\n\n"
            f"{MANAGED_START_MARKER}\n"
            "## Pinned Context\n\n"
            + _NOTE.format(d=1)
            + _REAL_PIN.format(n=1)
            + f"{MANAGED_END_MARKER}\n"
        )
        count, bounded = measure(undated_first)
        assert (count, bounded) == (2, False), (
            "control: both entries must parse and the region stay unbounded, "
            "or this is not the input class it claims to be"
        )
        path = project(undated_first)
        status = ensure_pinned_terminator()

        assert status == _REPAIR_REFUSED_NOTHING_ABSORBED, (
            f"expected the nothing-absorbed refusal by CONSTANT IDENTITY. "
            f"Got {status!r}"
        )
        assert path.read_text(encoding="utf-8") == undated_first, (
            "guard 2 must not write. Inserting before the undated entry here "
            "would push the dated pin OUT of the region and under-count it."
        )

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


# ---------------------------------------------------------------------------
# Guard 3: a `## Working Memory` heading already exists in the managed region.
#
# THE REPAIR CREATED THIS DEFECT; IT DID NOT INHERIT IT. Measured before the
# guard existed: on a file whose Working Memory heading sits ABOVE
# `## Pinned Context`, the repair inserted a SECOND one. The pin outcome was
# correct (5 pins to 2, bounded) and the repair was idempotent, so nothing in
# the cap suite could see it. The damage showed up in a DIFFERENT module:
# `working_memory._parse_working_memory_section` locates its section with
# `re.search`, which takes the FIRST match, so the pact-memory writer kept
# maintaining the heading above the pins while the entries the repair moved
# out sat under the second heading, synced and pruned by nothing.
# ---------------------------------------------------------------------------

#
# THE PIN COUNT IS SIZED FROM `REAL_PINS` AND `NOTES`, NOT HAND-WRITTEN, and
# that is what keeps `test_the_gate_declines_on_the_refused_file` honest. An
# earlier three-note version parsed 5 phantom pins against a cap of 12 — UNDER
# the cap, where an ENFORCING gate allows as well. Its `assert reason is None`
# therefore PASSED under a removed decline (measured, not supposed), so the
# classification assertion beside it carried the whole discriminating power.
# Sharing the constants with `case_5` puts the count above the cap and keeps it
# there as those constants move.
WM_HEADING_ABOVE_PINS = (
    "# PACT Framework and Managed Project Memory\n\n"
    f"{MANAGED_START_MARKER}\n"
    f"{PINNED_TERMINATOR_HEADING}\n"
    "- an existing note\n\n"
    "## Pinned Context\n\n"
    + "".join(_REAL_PIN.format(n=i) for i in range(1, REAL_PINS + 1))
    + "".join(_NOTE.format(d=d) for d in range(1, NOTES + 1))
    + f"{MANAGED_END_MARKER}\n"
)


class TestGuard3ExistingWorkingMemoryHeading:

    def test_the_fixture_is_the_measured_broken_input(self, project):
        """Precondition control, pinning the three rows I measured.

        Without this the guard could be passing because the fixture stopped
        reproducing the condition rather than because the guard works.
        """
        assert WM_HEADING_ABOVE_PINS.count(PINNED_TERMINATOR_HEADING) == 1
        count, bounded = measure(WM_HEADING_ABOVE_PINS)
        assert (count, bounded) == (REAL_PINS + NOTES, False)
        # The cap comparison is not decoration. It is the property that keeps
        # the decline test's VERDICT assertion alive: below the cap an
        # enforcing gate allows too. Shrink the fixture, or raise the cap
        # above it, and this reddens HERE rather than going quietly vacuous
        # one class down.
        assert count > PIN_COUNT_CAP, (
            f"the fixture parses {count} phantom pins against a cap of "
            f"{PIN_COUNT_CAP}. It must sit ABOVE the cap, or an enforcing "
            f"gate allows on it and the decline cannot be told apart from a "
            f"clean evaluation."
        )

    def test_the_repair_refuses_and_writes_nothing(self, project):
        path = project(WM_HEADING_ABOVE_PINS)
        status = ensure_pinned_terminator()

        assert status is not None and "skipped" in status.lower()
        after = path.read_text(encoding="utf-8")
        assert after == WM_HEADING_ABOVE_PINS, "guard 3 must not write"
        assert after.count(PINNED_TERMINATOR_HEADING) == 1, (
            "the second heading reappeared. Without the guard the repair "
            "inserts one, and the pact-memory writer then maintains the "
            "heading ABOVE the pins while the moved entries sit under the "
            "one below it, maintained by nothing."
        )

    def test_the_refusal_is_reported_not_silent(self, project):
        """A SILENT refusal is worse than the duplicate heading.

        The region stays unbounded, so the caps stay off on this file. If
        nothing says why, the curator has no way to learn the state — which
        is the condition the SessionStart directive exists to answer.
        """
        project(WM_HEADING_ABOVE_PINS)
        status = ensure_pinned_terminator()
        assert status, "the refusal must be reported, not returned as None"
        # "skipped" is load-bearing, not decoration. Without it this test
        # passes when the guard is REMOVED: the repair then succeeds and
        # returns a status that also names the heading. Asserting the
        # refusal KIND is what makes the arm discriminate.
        assert "skipped" in status.lower(), (
            f"expected a refusal, got a success status: {status!r}"
        )
        assert PINNED_TERMINATOR_HEADING in status, (
            "the message must name the heading the curator has to move"
        )

    def test_the_refusal_reaches_the_curator_through_the_directive(
        self, project, monkeypatch
    ):
        """End of the chain: refusal -> repair_status -> directive text."""
        from session_init import check_pinned_region_unbounded_directive

        import staleness
        monkeypatch.setattr(
            staleness, "get_project_claude_md_path", lambda: project.path
        )
        project(WM_HEADING_ABOVE_PINS)
        status = ensure_pinned_terminator()

        message = check_pinned_region_unbounded_directive(
            {"agent_type": "pact-orchestrator"}, repair_status=status
        )
        assert message is not None
        # POSITIVE about the CURRENT property, not merely silent about the
        # former one. The old wording asserted the file "already has a
        # `## Working Memory` heading"; the guard is a SUBSTRING test, so that
        # claim is false on the pin-body input. This asserts the containment
        # framing, which the old wording could not satisfy — so a revert to
        # the heading-presence claim reddens here rather than passing quietly.
        assert "contains the text" in message, (
            f"the directive must carry the containment framing. A message "
            f"claiming a heading EXISTS is false for the pin-body input that "
            f"reaches the same guard. Got: {message!r}"
        )
        assert PINNED_TERMINATOR_HEADING in message, (
            "the message must still name the text the curator has to act on"
        )

    def test_the_gate_declines_on_the_refused_file(
        self, project, monkeypatch, pact_context
    ):
        """THE ASSERTION THAT MATTERS, and it is not the refusal.

        A refusal that left the gate ENFORCING would be the impossible-cure
        over-block again: the region still parses REAL_PINS + NOTES pins
        against a real REAL_PINS, over the cap, and a curator would be denied
        for pins they do not have. So the refusal is only safe because the
        gate declines on it. Assert the DECLINE, not the refusal.

        BOTH assertions below are independently live, and that is a property
        of the FIXTURE rather than of the assertions. Binding control 2 holds
        it.
        """
        pact_context(
            team_name="test-team",
            session_id="session-guard3",
            project_dir=str(project.path.parent),
        )

        failures: list[dict] = []
        import pin_caps_gate
        monkeypatch.setattr(
            pin_caps_gate,
            "append_failure",
            lambda classification, error=None, cwd=None, source=None:
                failures.append({"classification": classification}),
        )

        path = project(WM_HEADING_ABOVE_PINS)
        assert ensure_pinned_terminator() is not None, "precondition: refused"

        # BINDING CONTROL 1, REACH: without this the gate short-circuits on a
        # non-matching path and reports ALLOW for a reason unrelated to
        # boundedness. Placed before the verdict so a miss withholds it.
        canonical = match_project_claude_md(str(path))
        assert canonical is not None and path.parent in canonical.parents, (
            "BINDING CONTROL FAILED: the gate would short-circuit before "
            "reaching the boundedness decline."
        )

        # BINDING CONTROL 2, DISCRIMINABILITY: the refused file must parse
        # ABOVE the cap, or `reason is None` below is equally true of an
        # ENFORCING gate and certifies nothing. Not hypothetical — on the
        # earlier under-cap fixture that assertion passed with the decline
        # deleted. Placed before the verdict so a fixture that drifts back
        # under the cap WITHHOLDS the verdict rather than reporting a false
        # clean one.
        count, bounded = measure(path.read_text(encoding="utf-8"))
        assert bounded is False and count > PIN_COUNT_CAP, (
            f"BINDING CONTROL FAILED: the refused file parses {count} pins "
            f"(bounded={bounded}) against a cap of {PIN_COUNT_CAP}. Under "
            f"the cap an enforcing gate also allows, so the verdict below "
            f"cannot tell a decline from an enforcement."
        )

        reason = pin_caps_gate._check_tool_allowed({
            "tool_name": "Edit",
            "agent_type": "pact-orchestrator",
            "tool_input": {
                "file_path": str(path),
                "old_string": "### Real pin 1\nShort body.\n",
                "new_string": (
                    "### Real pin 1\nShort body.\n\n"
                    "<!-- pinned: 2026-07-31 -->\n### Real pin new\nBody.\n"
                ),
                "replace_all": False,
            },
        })
        assert reason is None, (
            f"the refused file must be DECLINED, not enforced. The region "
            f"still parses {count} pins against a real {REAL_PINS}, so "
            f"enforcing here denies a curator for pins they do not have. "
            f"Got {reason!r}"
        )
        assert [f["classification"] for f in failures] == [
            "pin_caps_gate_declined_unbounded_both"
        ], "the allow must come from the boundedness decline, not from a clean evaluation"


# ---------------------------------------------------------------------------
# Guard 3, SUBSTRING CASE: a pin BODY that mentions the terminator literal.
#
# Guard 3 tests `PINNED_TERMINATOR_HEADING in region_text` — a substring test,
# not a heading test. So a pin whose body mentions "## Working Memory" in prose
# trips it, and the repair refuses on a file that carries no such heading.
#
# THAT IS THE SAFE DIRECTION, AND THIS FIXTURE ASSERTS THE DIRECTION RATHER
# THAN MERELY THE REFUSAL. Refusing leaves the region UNBOUNDED, and the gate
# declines on an unbounded region — so the caps stay off and no curator is
# denied for phantom pins. Over-caution costs one unenforced file. The opposite
# error costs a curator a deny they cannot cure, which is the whole defect this
# PR removes.
#
# THE MENTION MUST NOT SIT AT THE START OF A LINE, and that is what makes this
# a substring case at all. `_find_terminator_offset` matches `#{1,2}\s` against
# each line, so a line-initial mention IS a real terminator: the region would
# read bounded, the repair would no-op at the earlier check, and guard 3 would
# never be reached. An inline mention is invisible to the line scan and visible
# to the substring test, which is exactly the gap.
# ---------------------------------------------------------------------------

_PIN_BODY_MENTIONS_TERMINATOR = (
    "<!-- pinned: 2026-07-30 -->\n"
    "### Real pin 1\n"
    f"Keep the `{PINNED_TERMINATOR_HEADING}` heading below the pins.\n\n"
)

TERMINATOR_INSIDE_A_PIN_BODY = (
    "# PACT Framework and Managed Project Memory\n\n"
    f"{MANAGED_START_MARKER}\n"
    "## Pinned Context\n\n"
    + _PIN_BODY_MENTIONS_TERMINATOR
    + "".join(_REAL_PIN.format(n=i) for i in range(2, REAL_PINS + 1))
    + "".join(_NOTE.format(d=d) for d in range(1, NOTES + 1))
    + f"{MANAGED_END_MARKER}\n"
)


def _require_midline_mention() -> None:
    """WITHHOLDING PRECONDITION for the substring class. Raises rather than
    warns, and every behavioural test calls it BEFORE it acts.

    THE MENTION MUST BE MID-LINE OR THIS CLASS TESTS SOMETHING ELSE ENTIRELY,
    and it does so while still passing. `_find_terminator_offset` matches
    `#{1,2}\\s` against each LINE, so a line-initial mention is a genuine
    terminator: the region reads bounded, `ensure_pinned_terminator` no-ops at
    the earlier bounded check, and guard 3 is never reached. Every assertion
    downstream would then be about the bounded no-op while appearing to be
    about the guard. A mid-line mention is invisible to the line scan and
    visible to the substring test, which is the whole gap under test.
    """
    assert PINNED_TERMINATOR_HEADING in TERMINATOR_INSIDE_A_PIN_BODY, (
        "PRECONDITION FAILED: the fixture no longer mentions the terminator "
        "text at all, so guard 3 cannot fire and nothing below is about it."
    )
    assert not any(
        line.startswith(PINNED_TERMINATOR_HEADING)
        for line in TERMINATOR_INSIDE_A_PIN_BODY.splitlines()
    ), (
        "PRECONDITION FAILED: the mention sits at the start of a line, so it "
        "is a REAL terminator. The region is bounded, the repair no-ops "
        "before guard 3, and this class silently becomes a test of the "
        "bounded no-op."
    )
    count, bounded = measure(TERMINATOR_INSIDE_A_PIN_BODY)
    assert bounded is False, (
        "PRECONDITION FAILED: the region is bounded, so the repair no-ops at "
        "the earlier check and never reaches guard 3."
    )
    assert count > PIN_COUNT_CAP, (
        f"PRECONDITION FAILED: the fixture parses {count} phantom pins "
        f"against a cap of {PIN_COUNT_CAP}. Below the cap an enforcing gate "
        f"allows too, so a decline cannot be told from an enforcement."
    )


class TestGuard3TerminatorLiteralInsideAPinBody:

    def test_the_mention_is_a_substring_and_not_a_heading(self):
        """The precondition, asserted on its own so a fixture regression
        names itself instead of surfacing as a confusing behavioural
        failure three tests later."""
        _require_midline_mention()

    def test_the_repair_refuses_and_writes_nothing(self, project):
        """The substring test wins over the absent heading, and refusing is
        the direction that leaves the safe state."""
        _require_midline_mention()
        path = project(TERMINATOR_INSIDE_A_PIN_BODY)
        status = ensure_pinned_terminator()

        assert status is not None and "skipped" in status.lower(), (
            f"expected a refusal. A SUCCESS here would mean the repair "
            f"placed a terminator on a file whose only mention of one is "
            f"prose inside a pin body. Got {status!r}"
        )
        assert path.read_text(encoding="utf-8") == TERMINATOR_INSIDE_A_PIN_BODY, (
            "guard 3 must not write"
        )

    def test_the_refusal_does_not_claim_a_heading_that_is_absent(self, project):
        """THE MESSAGE MUST BE TRUE OF THIS INPUT, not only of the other one.

        Guard 3 is reached by two different files: one with a real
        `## Working Memory` heading above the pins, and this one, which has
        NO such heading and only prose mentioning the text. Both receive the
        SAME constant, so the wording has to hold for both. An earlier
        version asserted the file "already has a ... heading" and told the
        curator to move it — an instruction nobody can follow here, which is
        the same unfollowable-cure shape this work exists to remove.
        """
        _require_midline_mention()
        content = project(TERMINATOR_INSIDE_A_PIN_BODY).read_text(encoding="utf-8")
        headings_present = sum(
            1 for line in content.splitlines()
            if line.startswith(PINNED_TERMINATOR_HEADING)
        )
        assert headings_present == 0, (
            "BINDING CONTROL FAILED: this fixture is supposed to carry NO "
            "terminator heading. With one present the message's heading "
            "claim would be true and this test would certify nothing."
        )

        status = ensure_pinned_terminator()
        assert status is not None

        # POSITIVE: the trigger is described as text CONTAINMENT, which is
        # what the guard actually tests, and BOTH cures are named — the
        # pin-body cure is the one the old wording had no way to express.
        assert "contains the text" in status, (
            f"the message must describe the trigger as containment. Got {status!r}"
        )
        assert "reword the mention" in status, (
            f"the message must name the cure for THIS input. Without it a "
            f"curator holding this file has no action to take. Got {status!r}"
        )
        # NEGATIVE: the specific false claim must not come back.
        assert "already has a" not in status, (
            f"the message asserts a heading EXISTS. It does not, on this "
            f"input. Got {status!r}"
        )

        # 7a DISCIPLINE: state the remedy, promise no allowance. The detector
        # is asserted able to FIRE on a doctored string, so its silence on the
        # real one is evidence rather than an untested absence.
        promises = ("will then be allowed", "will be allowed", "then succeed",
                    "and the edit will", "unblocks", "will pass")
        doctored = status + " The edit will then be allowed."
        assert any(p in doctored for p in promises), (
            "the promise detector cannot fire at all; its silence below "
            "would certify nothing"
        )
        assert not any(p in status for p in promises), (
            f"the refusal promises an outcome it does not control. Got {status!r}"
        )

    def test_refusing_leaves_the_region_unbounded_so_the_caps_stay_off(
        self, project, monkeypatch, pact_context
    ):
        """THE DIRECTION, ASSERTED. A refusal is only safe because the gate
        declines on what it leaves behind."""
        _require_midline_mention()
        pact_context(
            team_name="test-team",
            session_id="session-guard3-substring",
            project_dir=str(project.path.parent),
        )

        failures: list[dict] = []
        import pin_caps_gate
        monkeypatch.setattr(
            pin_caps_gate,
            "append_failure",
            lambda classification, error=None, cwd=None, source=None:
                failures.append({"classification": classification}),
        )

        path = project(TERMINATOR_INSIDE_A_PIN_BODY)
        assert ensure_pinned_terminator() is not None, "precondition: refused"

        # BINDING CONTROL 1, REACH.
        canonical = match_project_claude_md(str(path))
        assert canonical is not None and path.parent in canonical.parents, (
            "BINDING CONTROL FAILED: the gate would short-circuit before "
            "reaching the boundedness decline."
        )
        # BINDING CONTROL 2, DISCRIMINABILITY.
        count, bounded = measure(path.read_text(encoding="utf-8"))
        assert bounded is False and count > PIN_COUNT_CAP, (
            f"BINDING CONTROL FAILED: {count} pins, bounded={bounded}. "
            f"Under the cap an enforcing gate also allows."
        )

        reason = pin_caps_gate._check_tool_allowed({
            "tool_name": "Edit",
            "agent_type": "pact-orchestrator",
            "tool_input": {
                "file_path": str(path),
                "old_string": "### Real pin 2\nShort body.\n",
                "new_string": (
                    "### Real pin 2\nShort body.\n\n"
                    "<!-- pinned: 2026-07-31 -->\n### Real pin new\nBody.\n"
                ),
                "replace_all": False,
            },
        })
        assert reason is None, (
            f"the refused file must be DECLINED. It parses {count} pins "
            f"against a real {REAL_PINS}, so enforcing denies a curator for "
            f"pins they do not have. Got {reason!r}"
        )
        assert [f["classification"] for f in failures] == [
            "pin_caps_gate_declined_unbounded_both"
        ], "the allow must come from the decline, not from a clean evaluation"
