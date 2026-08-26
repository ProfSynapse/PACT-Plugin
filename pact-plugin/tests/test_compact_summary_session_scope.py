"""
Tests for the #1504 session-scoped compact-summary path.

The compact summary lives at ``{session_dir}/compact-summary.txt`` when the
frame is identifiable, and degrades LOSS-FREE to the root singleton when it is
not. ``resolve_compact_summary_path`` is TOTAL: one call, degradation inside,
never None — the writer has no fallback branch.

Arms here: the resolver's scoped leg, its two degradation legs, totality on
degenerate inputs, the two-session non-interference classes (one per race
arm), the legacy-drain two-pass demonstration, and the end-to-end degradation
pin. Identity-collapse suppression (a same-session_id teammate PostCompact
writes nothing) is covered by test_role_gate_flip_and_postcompact and
test_postcompact_archive, whose frames carry session_id since #1504.
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))


class TestResolveCompactSummaryPath:
    """The resolver contract: TOTAL, degradation inside, one filename spelling."""

    def test_scoped_frame_resolves_to_session_dir(self, tmp_path, monkeypatch):
        from shared.pact_context import resolve_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/where/my-project")
        path = resolve_compact_summary_path({"session_id": "abc-123"})
        assert path == (
            tmp_path / "pact-sessions" / "my-project" / "abc-123"
            / "compact-summary.txt"
        )

    def test_missing_session_id_degrades_to_root_singleton(self, tmp_path, monkeypatch):
        from shared.constants import get_compact_summary_path
        from shared.pact_context import resolve_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/where/my-project")
        assert resolve_compact_summary_path({}) == get_compact_summary_path()

    def test_missing_project_dir_degrades_to_root_singleton(self, tmp_path, monkeypatch):
        from shared.constants import get_compact_summary_path
        from shared.pact_context import resolve_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert resolve_compact_summary_path({"session_id": "abc-123"}) == (
            get_compact_summary_path()
        )

    def test_total_on_degenerate_inputs(self, tmp_path, monkeypatch):
        from shared.constants import get_compact_summary_path
        from shared.pact_context import resolve_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/where/my-project")
        expected_root = get_compact_summary_path()
        for degenerate in (None, "", {"session_id": ""}, {"session_id": None}):
            assert resolve_compact_summary_path(degenerate) == expected_root

    def test_session_leg_shares_the_root_filename_spelling(self, tmp_path, monkeypatch):
        from shared.constants import COMPACT_SUMMARY_NAME, get_compact_summary_path
        from shared.pact_context import resolve_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/where/my-project")
        scoped = resolve_compact_summary_path({"session_id": "abc-123"})
        assert scoped.name == COMPACT_SUMMARY_NAME == get_compact_summary_path().name


# ---------------------------------------------------------------------------
# Behavior-flip arms: the properties the architecture requires demonstrated
# ---------------------------------------------------------------------------

_SID_A = "aaaaaaaa-1111-0000-0000-000000000000"
_SID_B = "bbbbbbbb-2222-0000-0000-000000000000"
_PROJECT = "/some/where/my-project"


def _run_postcompact_main(frame, monkeypatch, tmp_path):
    """Drive postcompact_archive.main() end-to-end in-process under an
    isolated config root; returns the exit code (always 0 — fail-open)."""
    from postcompact_archive import main

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    with patch("sys.stdin", io.StringIO(json.dumps(frame))), \
         patch("sys.stdout", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            main()
    return exc.value.code


class TestTwoSessionWriterNonInterference:
    """Race arm 1: two same-root sessions both compact.

    Sequential interleaving, NO threads — both races are orderings of atomic
    syscalls, and the invariant is WHERE the bytes land, not concurrency.
    DISTINCT sentinel bytes: interference would show as a byte mismatch, not
    merely as existence.
    """

    def test_both_writes_land_byte_intact_in_own_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", _PROJECT)
        for sid, body in ((_SID_A, "SENTINEL-A summary bytes"),
                          (_SID_B, "SENTINEL-B summary bytes")):
            frame = {"session_id": sid, "agent_type": "PACT:pact-orchestrator",
                     "hook_event_name": "PostCompact", "compact_summary": body}
            assert _run_postcompact_main(frame, monkeypatch, tmp_path) == 0

        base = tmp_path / "pact-sessions" / "my-project"
        assert (base / _SID_A / "compact-summary.txt").read_text(
            encoding="utf-8") == "SENTINEL-A summary bytes"
        assert (base / _SID_B / "compact-summary.txt").read_text(
            encoding="utf-8") == "SENTINEL-B summary bytes"


class TestOwnDirClearDoesNotCrossSessions:
    """Race arm 2: session A wrote; session B's session_init clears.

    The own-dir clear is keyed on the CLEARING session's identifiers, so A's
    bytes must survive B's clear, while B's own stale bytes move to a
    timestamped archive in B's own directory (slot clear, bytes kept).
    """

    def test_other_sessions_file_untouched_by_this_sessions_clear(
        self, tmp_path, monkeypatch
    ):
        from session_init import _archive_own_dir_stale_summary

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        base = tmp_path / "pact-sessions" / "my-project"
        a_dir = base / _SID_A
        b_dir = base / _SID_B
        a_dir.mkdir(parents=True)
        b_dir.mkdir(parents=True)
        (a_dir / "compact-summary.txt").write_text("SENTINEL-A", encoding="utf-8")
        (b_dir / "compact-summary.txt").write_text("STALE-B", encoding="utf-8")

        _archive_own_dir_stale_summary(_SID_B, _PROJECT)

        # B's slot cleared, B's bytes archived in B's own dir.
        assert not (b_dir / "compact-summary.txt").exists()
        archives = list(b_dir.glob("compact-summary-*.txt"))
        assert len(archives) == 1
        assert archives[0].read_text(encoding="utf-8") == "STALE-B"
        # A's bytes untouched.
        assert (a_dir / "compact-summary.txt").read_text(
            encoding="utf-8") == "SENTINEL-A"


class TestLegacyDrainTwoPass:
    """Demonstration: pre-upgrade root bytes drain losslessly, exactly once.

    Pass 1 moves them (never deletes) into the starting session's archive;
    pass 2 is a no-op — the MOVE emptied the state, and there is no once-flag.
    """

    def test_root_bytes_rehome_byte_equal_and_second_pass_is_noop(
        self, tmp_path, monkeypatch
    ):
        from session_init import _archive_stale_compact_summary
        from shared.constants import get_compact_summary_path

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        root = get_compact_summary_path()
        root.parent.mkdir(parents=True, exist_ok=True)
        root.write_text("LEGACY SENTINEL", encoding="utf-8")

        _archive_stale_compact_summary(_SID_A, _PROJECT)

        assert not root.exists()
        dest_dir = tmp_path / "pact-sessions" / "my-project" / _SID_A
        archives = list(dest_dir.glob("compact-summary-*.txt"))
        assert len(archives) == 1
        assert archives[0].read_text(encoding="utf-8") == "LEGACY SENTINEL"

        # Pass 2: nothing new appears, pass-1 bytes unchanged.
        _archive_stale_compact_summary(_SID_A, _PROJECT)
        archives = list(dest_dir.glob("compact-summary-*.txt"))
        assert len(archives) == 1
        assert archives[0].read_text(encoding="utf-8") == "LEGACY SENTINEL"


class TestDegradationIsLossFree:
    """Degradation pin: an unidentified frame's bytes exist SOMEWHERE under
    the config root after the writer runs — at the root singleton. The rglob
    is positive on purpose: suppression and degradation both produce an empty
    session dir, so only a scan proves the bytes survived."""

    def _assert_bytes_under_root(self, tmp_path, body):
        found = [p for p in tmp_path.rglob("compact-summary.txt")
                 if p.read_text(encoding="utf-8") == body]
        assert found == [tmp_path / "pact-sessions" / "compact-summary.txt"], (
            f"degraded bytes must land at the root singleton, found {found}"
        )

    def test_missing_session_id_degrades_loss_free(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", _PROJECT)
        frame = {"agent_type": "PACT:pact-orchestrator",
                 "hook_event_name": "PostCompact",
                 "compact_summary": "DEGRADED-NO-SID"}
        assert _run_postcompact_main(frame, monkeypatch, tmp_path) == 0
        self._assert_bytes_under_root(tmp_path, "DEGRADED-NO-SID")

    def test_missing_project_dir_degrades_loss_free(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        frame = {"session_id": _SID_A, "agent_type": "PACT:pact-orchestrator",
                 "hook_event_name": "PostCompact",
                 "compact_summary": "DEGRADED-NO-PROJ"}
        assert _run_postcompact_main(frame, monkeypatch, tmp_path) == 0
        self._assert_bytes_under_root(tmp_path, "DEGRADED-NO-PROJ")
