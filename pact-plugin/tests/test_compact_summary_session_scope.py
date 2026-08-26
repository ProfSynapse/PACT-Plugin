"""
Tests for the #1504 session-scoped compact-summary path.

The compact summary lives at ``{session_dir}/compact-summary.txt`` when the
frame is identifiable, and degrades LOSS-FREE to the root singleton when it is
not. ``resolve_compact_summary_path`` is TOTAL: one call, degradation inside,
never None — the writer has no fallback branch.

Arms here: the resolver's scoped leg, its two degradation legs, and totality
on degenerate inputs. The two-session non-interference classes, the legacy
drain two-pass demonstration, and the degradation pin land with the behavior
flip (C2).
"""
import sys
from pathlib import Path

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
