"""
Tests for check_pinned_staleness() in session_init.py.

Tests cover:
1. No pinned context section -- no-op
2. Pinned context with recent PR -- not flagged
3. Pinned context with old PR -- flagged stale
4. Pinned context without PR dates -- skipped
5. Over budget -- warning comment added, and refreshed to match later edits
6. Under budget -- no warning, and an earlier warning removed
7. Already-marked stale entries -- not double-marked
8. Multiple entries with mixed staleness
9. _estimate_tokens twin copy equivalence (staleness.py vs working_memory.py)
"""

import ast
import inspect
import os
import re
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
# Add working_memory scripts directory to path for twin-copy equivalence test
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts"))

# Pulls the token figure out of a warning comment, so a test can compare the
# number in the file against the number in the returned status string.
_WARNING_NUMBER_RE = re.compile(r"<!-- WARNING: Pinned context ~(\d+) tokens")


def over_budget_body(margin_words=200):
    """Build a pin body whose estimated tokens exceed the pinned-context budget.

    THE MAGNITUDE IS DERIVED FROM THE CONSTANT, NEVER WRITTEN AS A LITERAL.
    `estimate_tokens` is `int(words * 1.3)`, so a word count above the budget
    always estimates above the budget, whatever value the budget takes next.

    The assertion makes that structural. A hard-coded fixture went silently
    under a raised threshold once already -- it still passed, while no longer
    testing the thing its comment claimed -- and only a check against the live
    constant can refuse to repeat that.
    """
    from staleness import PINNED_CONTEXT_TOKEN_BUDGET, estimate_tokens

    body = "word " * (PINNED_CONTEXT_TOKEN_BUDGET + margin_words)
    assert estimate_tokens(body) > PINNED_CONTEXT_TOKEN_BUDGET, (
        "fixture no longer exceeds the budget it is derived from"
    )
    return body


def warning_number(text):
    """Return the token figure carried by the warning comment, or None."""
    match = _WARNING_NUMBER_RE.search(text)
    return int(match.group(1)) if match else None


class TestCheckPinnedStaleness:
    """Tests for check_pinned_staleness() -- stale pin detection."""

    def _create_project_claude_md(self, tmp_path, content):
        """Helper to create a project CLAUDE.md and patch path resolution."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    def test_no_pinned_section_returns_none(self, tmp_path):
        """Should return None when no Pinned Context section exists."""
        from session_init import check_pinned_staleness

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Working Memory\n"
            "Some working memory content\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is None

    def test_empty_pinned_section_returns_none(self, tmp_path):
        """Should return None when Pinned Context section is empty."""
        from session_init import check_pinned_staleness

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            "## Working Memory\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is None

    def test_no_claude_md_returns_none(self):
        """Should return None when CLAUDE.md does not exist."""
        from session_init import check_pinned_staleness

        with patch("session_init._get_project_claude_md_path", return_value=None), \
             patch("staleness._get_project_claude_md_path", return_value=None), \
             patch("staleness._resolve_project_claude_md_with_base",
                   return_value=(None, None)):
            result = check_pinned_staleness()

        assert result is None

    def test_recent_pr_not_flagged(self, tmp_path):
        """Entries with PR merged within threshold should not be flagged."""
        from session_init import check_pinned_staleness

        # Use a date that is clearly recent (5 days ago)
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Recent Feature (PR #100, merged {recent_date})\n"
            "- Some details about the feature\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is None
        # File should not be modified
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- STALE:" not in content

    def test_old_pr_flagged_stale(self, tmp_path):
        """Entries with PR merged beyond threshold should be flagged stale."""
        from session_init import check_pinned_staleness, PINNED_STALENESS_DAYS

        # Use a date well beyond the staleness threshold
        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Details about the old feature\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is not None
        assert "stale" in result.lower()

        # File should have stale marker
        content = claude_md.read_text(encoding="utf-8")
        assert f"<!-- STALE: Last relevant {old_date} -->" in content

    def test_entry_without_pr_date_skipped(self, tmp_path):
        """Entries without PR merge dates should be skipped (not flagged)."""
        from session_init import check_pinned_staleness

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            "### Plugin Architecture\n"
            "- Source repo details\n"
            "- No PR date mentioned here\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is None
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- STALE:" not in content

    def test_already_stale_entry_not_double_marked(self, tmp_path):
        """Entry already marked stale should not get a second marker (idempotent)."""
        from session_init import check_pinned_staleness, PINNED_STALENESS_DAYS

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        # Marker is placed after the heading (inside entry text), matching
        # the format that check_pinned_staleness() itself produces.
        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            f"<!-- STALE: Last relevant {old_date} -->\n"
            "- Details\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is not None
        assert "stale" in result.lower()

        # Marker count must remain exactly 1 -- no duplicates
        content = claude_md.read_text(encoding="utf-8")
        stale_count = content.count("<!-- STALE:")
        assert stale_count == 1

    def test_over_budget_adds_warning(self, tmp_path):
        """Should add token budget warning when pinned content exceeds budget."""
        from session_init import check_pinned_staleness

        # Pinned content sized from PINNED_CONTEXT_TOKEN_BUDGET, so it stays
        # over budget after any future change to that constant.
        big_content = over_budget_body()

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Big Feature\n{big_content}\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        # Should report budget info
        assert result is not None
        assert "budget" in result.lower()

        # File should have budget warning comment
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- WARNING: Pinned context" in content

    def test_under_budget_no_warning(self, tmp_path):
        """Should not add warning when pinned content is within budget."""
        from session_init import check_pinned_staleness

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            "### Small Feature\n"
            "- Just a few words here\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- WARNING: Pinned context" not in content

    def test_mixed_entries_only_old_flagged(self, tmp_path):
        """With mixed recent and old entries, only old ones should be flagged."""
        from session_init import check_pinned_staleness, PINNED_STALENESS_DAYS

        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Recent Feature (PR #100, merged {recent_date})\n"
            "- Recent details\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Old details\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is not None
        assert "1 stale" in result

        content = claude_md.read_text(encoding="utf-8")
        # Only the old entry should have a stale marker
        assert content.count("<!-- STALE:") == 1
        assert f"<!-- STALE: Last relevant {old_date} -->" in content

    def test_pinned_context_at_end_of_file(self, tmp_path):
        """Should handle Pinned Context as the last section (no next section)."""
        from session_init import check_pinned_staleness, PINNED_STALENESS_DAYS

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 5)).strftime("%Y-%m-%d")

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Working Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #99, merged {old_date})\n"
            "- Details here\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        assert result is not None
        assert "stale" in result.lower()


class TestGetProjectClaudeMdPath:
    """Tests for _get_project_claude_md_path() helper."""

    @pytest.fixture
    def clean_env_no_claude_project_dir(self):
        """Remove CLAUDE_PROJECT_DIR from the environment."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            yield

    def test_uses_env_var_when_set(self, tmp_path):
        """Should use CLAUDE_PROJECT_DIR env var first."""
        from session_init import _get_project_claude_md_path

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Test", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = _get_project_claude_md_path()

        assert result == claude_md

    def test_falls_back_to_git_root(self, tmp_path, clean_env_no_claude_project_dir):
        """Should use git root when env var not set.

        --git-common-dir returns the .git directory path; the code resolves
        its parent to get the repo root where CLAUDE.md lives.
        """
        from session_init import _get_project_claude_md_path

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Test", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = str(tmp_path / ".git") + "\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _get_project_claude_md_path()

        assert result == claude_md

    def test_returns_none_when_no_claude_md_found(self, tmp_path, clean_env_no_claude_project_dir):
        """Should return None when CLAUDE.md does not exist anywhere."""
        from session_init import _get_project_claude_md_path

        with patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _get_project_claude_md_path()

        assert result is None

    def test_finds_dot_claude_via_env_var(self, tmp_path):
        """Should find .claude/CLAUDE.md when CLAUDE_PROJECT_DIR is set."""
        from session_init import _get_project_claude_md_path

        dot_claude = tmp_path / ".claude" / "CLAUDE.md"
        dot_claude.parent.mkdir()
        dot_claude.write_text("# Test", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = _get_project_claude_md_path()

        assert result == dot_claude

    def test_prefers_dot_claude_over_legacy_via_env_var(self, tmp_path):
        """When both files exist under env var path, .claude/CLAUDE.md wins."""
        from session_init import _get_project_claude_md_path

        dot_claude = tmp_path / ".claude" / "CLAUDE.md"
        dot_claude.parent.mkdir()
        dot_claude.write_text("# preferred", encoding="utf-8")
        legacy = tmp_path / "CLAUDE.md"
        legacy.write_text("# legacy", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = _get_project_claude_md_path()

        assert result == dot_claude
        assert result != legacy

    def test_finds_dot_claude_via_git_root(self, tmp_path, clean_env_no_claude_project_dir):
        """Should find .claude/CLAUDE.md under the git root when env var unset."""
        from session_init import _get_project_claude_md_path

        dot_claude = tmp_path / ".claude" / "CLAUDE.md"
        dot_claude.parent.mkdir()
        dot_claude.write_text("# Test", encoding="utf-8")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = str(tmp_path / ".git") + "\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _get_project_claude_md_path()

        assert result == dot_claude

    def test_finds_dot_claude_via_cwd(self, tmp_path, clean_env_no_claude_project_dir):
        """Should find .claude/CLAUDE.md under the current working directory as last resort."""
        from session_init import _get_project_claude_md_path

        dot_claude = tmp_path / ".claude" / "CLAUDE.md"
        dot_claude.parent.mkdir()
        dot_claude.write_text("# Test", encoding="utf-8")

        with patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _get_project_claude_md_path()

        assert result == dot_claude

    def test_finds_legacy_when_only_legacy_exists_via_env_var(self, tmp_path):
        """Falls back to legacy ./CLAUDE.md when only it exists."""
        from session_init import _get_project_claude_md_path

        legacy = tmp_path / "CLAUDE.md"
        legacy.write_text("# Test", encoding="utf-8")

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = _get_project_claude_md_path()

        assert result == legacy


class TestSessionInitEstimateTokens:
    """Tests for _estimate_tokens() in session_init.py (separate copy)."""

    def test_empty_returns_zero(self):
        """Empty string should return 0."""
        from session_init import _estimate_tokens
        assert _estimate_tokens("") == 0

    def test_matches_working_memory_implementation(self):
        """Should produce same results as working_memory._estimate_tokens."""
        from session_init import _estimate_tokens as session_est

        text = "one two three four five six seven eight nine ten"
        assert session_est(text) == 13


class TestBudgetWarningIdempotency:
    """Tests that budget warning is not duplicated on repeated runs."""

    def _create_project_claude_md(self, tmp_path, content):
        """Helper to create a project CLAUDE.md and patch path resolution."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    def test_budget_warning_not_duplicated_on_second_run(self, tmp_path):
        """Running check_pinned_staleness twice on over-budget content should
        produce exactly one <!-- WARNING: comment, not two."""
        from session_init import check_pinned_staleness

        # Sized from PINNED_CONTEXT_TOKEN_BUDGET, so a raised budget cannot
        # leave this fixture under the threshold it claims to exceed.
        big_content = over_budget_body()

        claude_md = self._create_project_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Big Feature\n{big_content}\n\n"
        ))

        with patch("session_init._get_project_claude_md_path", return_value=claude_md):
            # First run -- should add the warning
            result1 = check_pinned_staleness()
            assert result1 is not None
            assert "budget" in result1.lower()

            # Second run -- should NOT add a second warning
            result2 = check_pinned_staleness()

        content_after = claude_md.read_text(encoding="utf-8")
        warning_count = content_after.count("<!-- WARNING: Pinned context")
        assert warning_count == 1, (
            f"Expected exactly 1 budget warning comment, found {warning_count}"
        )


class TestBudgetWarningRefresh:
    """The warning must describe the CURRENT pinned content.

    WHICH ARMS FALSIFY THE OLD BEHAVIOUR, measured against the pre-repair code
    rather than predicted: five of these seven FAIL there. Two PASS both before
    and after -- `test_repeated_runs_do_not_compound` and
    `test_entryless_section_never_gains_a_warning` -- because they guard
    properties of the repair itself, not the defect. Each says so in its own
    docstring. An arm that passes either way proves nothing about a fix unless
    it declares that.
    """

    def _create_project_claude_md(self, tmp_path, content):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    def _pinned_doc(self, body, warning=None):
        head = "# Project Memory\n\n## Pinned Context\n\n"
        if warning is not None:
            head += warning
        return f"{head}### Big Feature\n{body}\n\n"

    def test_stale_number_is_refreshed(self, tmp_path):
        """A warning carrying an outdated number must be rewritten. FAILS before.

        The pre-repair guard skipped insertion whenever any warning was
        present, so the first number written stayed forever. A real document
        reported roughly a third of its true size this way.
        """
        from staleness import check_pinned_staleness, estimate_tokens

        body = over_budget_body()
        stale_warning = (
            "<!-- WARNING: Pinned context ~7 tokens (budget: 5). "
            "Consider archiving stale pins. -->\n"
        )
        claude_md = self._create_project_claude_md(
            tmp_path, self._pinned_doc(body, warning=stale_warning)
        )
        # Precondition: the wrong number really is in the parsed region.
        assert warning_number(claude_md.read_text(encoding="utf-8")) == 7

        check_pinned_staleness(claude_md_path=claude_md)

        content = claude_md.read_text(encoding="utf-8")
        assert content.count("<!-- WARNING: Pinned context") == 1
        assert warning_number(content) == estimate_tokens(f"### Big Feature\n{body}\n\n")

    def test_status_string_agrees_with_file_comment(self, tmp_path):
        """The returned figure and the written figure must match. FAILS before.

        Before the repair the two came from different measurements: the file
        kept its original number while the status string re-measured a body
        that now contained the warning, so the two disagreed from the second
        run onward by the warning's own word count.
        """
        from staleness import check_pinned_staleness

        claude_md = self._create_project_claude_md(
            tmp_path, self._pinned_doc(over_budget_body())
        )

        check_pinned_staleness(claude_md_path=claude_md)
        status = check_pinned_staleness(claude_md_path=claude_md)

        assert status is not None
        in_status = int(re.search(r"~(\d+) tokens", status).group(1))
        in_file = warning_number(claude_md.read_text(encoding="utf-8"))
        assert in_status == in_file, (
            f"status string reports {in_status} while the file says {in_file}"
        )

    def test_warning_removed_when_back_under_budget(self, tmp_path):
        """A breach that has ended must take its warning with it. FAILS before."""
        from staleness import check_pinned_staleness

        body = over_budget_body()
        claude_md = self._create_project_claude_md(
            tmp_path, self._pinned_doc(body)
        )
        check_pinned_staleness(claude_md_path=claude_md)
        assert "<!-- WARNING: Pinned context" in claude_md.read_text(encoding="utf-8")

        # The user archives the bulk of the pin.
        shrunk = claude_md.read_text(encoding="utf-8").replace(body, "a short pin")
        claude_md.write_text(shrunk, encoding="utf-8")

        result = check_pinned_staleness(claude_md_path=claude_md)

        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- WARNING: Pinned context" not in content
        assert result is None or "budget" not in result.lower()

    def test_warning_removed_when_last_pin_deleted(self, tmp_path):
        """Deleting every pin must not strand the warning. FAILS before.

        The entry scan returned early when no `### ` heading remained, so the
        warning sat in a section that nothing could reach.
        """
        from staleness import check_pinned_staleness

        body = over_budget_body()
        claude_md = self._create_project_claude_md(
            tmp_path, self._pinned_doc(body)
        )
        check_pinned_staleness(claude_md_path=claude_md)
        assert "<!-- WARNING: Pinned context" in claude_md.read_text(encoding="utf-8")

        emptied = claude_md.read_text(encoding="utf-8").replace(
            f"### Big Feature\n{body}\n", ""
        )
        claude_md.write_text(emptied, encoding="utf-8")
        assert "### " not in claude_md.read_text(encoding="utf-8")

        check_pinned_staleness(claude_md_path=claude_md)

        assert "<!-- WARNING: Pinned context" not in claude_md.read_text(
            encoding="utf-8"
        )

    def test_repeated_runs_do_not_compound(self, tmp_path):
        """Three runs give one warning and one unchanging number.

        PASSES BEFORE AND AFTER. This arm guards the repair, not the defect:
        rebuilding the warning on every pass could have let each pass measure
        the previous one and creep upward. It cannot, because the measured body
        never holds a warning.
        """
        from staleness import check_pinned_staleness

        claude_md = self._create_project_claude_md(
            tmp_path, self._pinned_doc(over_budget_body())
        )

        check_pinned_staleness(claude_md_path=claude_md)
        after_first = claude_md.read_text(encoding="utf-8")
        check_pinned_staleness(claude_md_path=claude_md)
        check_pinned_staleness(claude_md_path=claude_md)
        after_third = claude_md.read_text(encoding="utf-8")

        assert after_third.count("<!-- WARNING: Pinned context") == 1
        assert after_third == after_first, "a later pass rewrote a settled document"

    def test_entryless_section_never_gains_a_warning(self, tmp_path):
        """Prose with no `### ` entry stays untouched, over budget or not.

        PASSES BEFORE AND AFTER, and that is the point. Widening the entry
        guard so a stranded warning can be REMOVED must not also start ADDING
        warnings to documents this code has always left alone. Removal repairs
        a line the hook wrote; insertion here would be new behaviour.
        """
        from staleness import check_pinned_staleness

        claude_md = self._create_project_claude_md(
            tmp_path,
            f"# Project Memory\n\n## Pinned Context\n\n{over_budget_body()}\n\n",
        )
        before = claude_md.read_text(encoding="utf-8")

        result = check_pinned_staleness(claude_md_path=claude_md)

        assert result is None
        assert claude_md.read_text(encoding="utf-8") == before

    def test_user_line_quoting_the_warning_is_preserved(self, tmp_path):
        """A pin body that quotes the warning must survive, and must not silence
        the real one. FAILS before, for a reason worth naming.

        Two properties are asserted here, and only the second was expected to
        need a test. The removal is anchored at the head of the pinned body,
        which is the only place the hook writes a warning, so it cannot reach a
        look-alike line inside a pin. CLAUDE.md is frequently gitignored, so an
        over-broad strip would delete user text no commit could restore.

        The pre-repair presence check searched the WHOLE region for the marker
        as a plain substring, so a pin that merely QUOTED the warning text
        satisfied it and the hook never wrote its own warning at all -- the
        advisory failed open for the entire document on the strength of one
        line of user prose. Anchoring the probe closes that as a side effect,
        which is why this arm asserts a count of two rather than one.
        """
        from staleness import check_pinned_staleness

        quoted = (
            "<!-- WARNING: Pinned context ~99 tokens (budget: 1). "
            "Consider archiving stale pins. -->"
        )
        claude_md = self._create_project_claude_md(
            tmp_path,
            "# Project Memory\n\n## Pinned Context\n\n"
            f"### Doc Pin\nThe hook writes this line:\n{quoted}\n"
            f"{over_budget_body()}\n\n",
        )

        check_pinned_staleness(claude_md_path=claude_md)
        check_pinned_staleness(claude_md_path=claude_md)

        content = claude_md.read_text(encoding="utf-8")
        assert quoted in content, "the strip deleted a line a user wrote"
        # One line the hook owns, plus the one the user quoted.
        assert content.count("<!-- WARNING: Pinned context") == 2


class TestStalenessErrorPaths:
    """Tests for error handling paths in staleness.py."""

    def _create_claude_md(self, tmp_path, content):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    def test_read_text_ioerror_returns_none(self, tmp_path):
        """IOError on read_text() (line 116) should return None gracefully."""
        from staleness import check_pinned_staleness

        claude_md = self._create_claude_md(tmp_path, "# Project\n")

        # Patch read_text to raise IOError after the path is validated
        with patch.object(type(claude_md), "read_text", side_effect=IOError("disk error")):
            result = check_pinned_staleness(claude_md_path=claude_md)

        assert result is None

    def test_read_text_unicode_decode_error_returns_none(self, tmp_path):
        """UnicodeDecodeError on read_text() should return None gracefully."""
        from staleness import check_pinned_staleness

        claude_md = self._create_claude_md(tmp_path, "# Project\n")

        error = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        with patch.object(type(claude_md), "read_text", side_effect=error):
            result = check_pinned_staleness(claude_md_path=claude_md)

        assert result is None

    def test_write_text_ioerror_returns_error_message(self, tmp_path):
        """IOError on write_text() (line 218) should return an error message string."""
        from staleness import check_pinned_staleness, PINNED_STALENESS_DAYS
        from datetime import datetime, timedelta

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Details\n\n"
        ))

        # Let read_text work normally, but make the write fail. staleness.py
        # writes via claude_md_manager._atomic_write_text (temp + rename), not
        # Path.write_text -- patching write_text here would no-op silently.
        import shared.claude_md_manager as cmm
        with patch.object(cmm, "_atomic_write_text", side_effect=IOError("read-only fs")):
            result = check_pinned_staleness(claude_md_path=claude_md)

        # Should return an error message string (not None)
        assert result is not None
        assert "Failed to update pinned staleness" in result
        assert "read-only fs" in result

    def test_write_text_os_error_returns_error_message(self, tmp_path):
        """OSError on write_text() should also return an error message string."""
        from staleness import check_pinned_staleness, PINNED_STALENESS_DAYS
        from datetime import datetime, timedelta

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Details\n\n"
        ))

        import shared.claude_md_manager as cmm
        with patch.object(cmm, "_atomic_write_text", side_effect=OSError("permission denied")):
            result = check_pinned_staleness(claude_md_path=claude_md)

        assert result is not None
        assert "Failed to update pinned staleness" in result

    def test_successful_update_normalizes_file_mode_to_0o600(self, tmp_path):
        """A successful staleness update clamps the file mode to 0o600.

        staleness.py's write site calls _atomic_write_text, which chmods the temp
        to 0o600 before os.replace, so a pre-existing 0o644 file is clamped to
        0o600 on update. This pins the SITE behaviour (that check_pinned_staleness
        actually invokes the clamp) — distinct from the helper's clamp (covered by
        test_claude_md_manager.py's migration test) and the create path
        (test_created_file_has_secure_permissions). Before this site switched from
        bare write_text to _atomic_write_text it left the existing mode alone, so
        the site normalization was asserted only in a commit message.

        The explicit chmod 0o644 (NOT an ambient-umask default) is load-bearing:
        it proves the update CHANGES 0o644 -> 0o600. A test relying on the umask
        to make the pre-file non-0o600 would pass trivially under umask 077 —
        itself a latent phantom-green.

        Revert-coupled: reverting the write site to bare write_text leaves the
        0o644 mode untouched and turns this test RED.
        """
        import stat
        from staleness import check_pinned_staleness, PINNED_STALENESS_DAYS
        from datetime import datetime, timedelta

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Details\n\n"
        ))
        # Explicit non-0o600 starting mode so the post-update assertion proves a
        # CLAMP, not an ambient-umask coincidence.
        claude_md.chmod(0o644)
        assert stat.S_IMODE(claude_md.stat().st_mode) == 0o644, (
            "precondition: the seeded file must start at 0o644"
        )

        result = check_pinned_staleness(claude_md_path=claude_md)

        # The stale pin triggered a real update (the write path ran), not a
        # no-op skip — so the mode assertion below observes a write, not the seed.
        assert result is not None
        # SITE behaviour: the successful update landed the file at 0o600, clamping
        # the 0o644 it started with.
        final_mode = stat.S_IMODE(claude_md.stat().st_mode)
        assert final_mode == 0o600, (
            f"staleness update must clamp the file mode to 0o600, got {oct(final_mode)}"
        )


class TestStalenessModuleDirect:
    """Tests for staleness.py called directly (not via session_init wrapper)."""

    def _create_claude_md(self, tmp_path, content):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(content, encoding="utf-8")
        return claude_md

    def test_explicit_path_parameter(self, tmp_path):
        """check_pinned_staleness(claude_md_path=...) should use the given path
        without calling _get_project_claude_md_path."""
        from staleness import check_pinned_staleness, PINNED_STALENESS_DAYS

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        claude_md = self._create_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #50, merged {old_date})\n"
            "- Details\n\n"
        ))

        # Call with explicit path -- should NOT need _get_project_claude_md_path
        with patch("staleness._get_project_claude_md_path") as mock_get:
            result = check_pinned_staleness(claude_md_path=claude_md)

        # The path resolver should never have been called
        mock_get.assert_not_called()
        # But the stale entry should still be detected
        assert result is not None
        assert "stale" in result.lower()

        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- STALE:" in content

    def test_entry_with_no_newline_after_heading_skipped(self, tmp_path):
        """An entry whose heading has no trailing newline (single-line entry)
        should be skipped gracefully by the .find('\n') guard."""
        from staleness import check_pinned_staleness, PINNED_STALENESS_DAYS

        old_date = (datetime.now() - timedelta(days=PINNED_STALENESS_DAYS + 10)).strftime("%Y-%m-%d")

        # Construct pinned content where the LAST entry has no trailing newline.
        # This means entry_text.find("\n") returns -1 and the code should skip it.
        claude_md = self._create_claude_md(tmp_path, (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Heading-only entry (PR #80, merged {old_date})"
        ))

        result = check_pinned_staleness(claude_md_path=claude_md)

        # The entry should be skipped (no stale marker added) because there is
        # no newline after the heading to insert the marker after.
        content = claude_md.read_text(encoding="utf-8")
        assert "<!-- STALE:" not in content

    def test_nonexistent_explicit_path_returns_none(self, tmp_path):
        """Passing a path to a non-existent file should return None gracefully."""
        from staleness import check_pinned_staleness

        missing = tmp_path / "does_not_exist.md"
        result = check_pinned_staleness(claude_md_path=missing)
        assert result is None


class TestDeclaredPinnedEndMarker:
    """The declared END boundary of `## Pinned Context`.

    WHY THIS CLASS EXISTS AT ALL, stated first because it is the trap. The
    declared parse is a NO-OP on every document that carries the shipped
    marker name: `PINNED_END_MARKER` sits in the `PACT_MEMORY_` family, so the
    INFERRED forward scan already stops at its line and the two offsets
    coincide. A suite that only feeds documents to the parser therefore
    certifies the change as a no-op, which it is, and PROVES NOTHING.

    THE NON-VACUITY ARM IS `test_rename_arm_*` BELOW, AND IT MUTATES THE
    CONSTANT, NOT THE DOCUMENT. That is the only configuration in which the
    declared parse and the inferred scan disagree. Any future edit that drops
    that arm leaves this class unable to fail for the right reason.
    """

    def _doc(self, pinned_body, above="", tail="## Working Memory\nnotes\n"):
        """`above` goes between `## Retrieved Context` and the pinned heading.

        THE START MARKER BELONGS THERE, NOT IN `pinned_body`. It carries the
        `PACT_MEMORY_` prefix, so a copy placed as the body's first line
        TERMINATES the scan at once and the section parses as empty (None).
        The writer emits it immediately ABOVE the heading, and a fixture that
        puts it below is testing a document the writer cannot produce.
        """
        from shared.claude_md_manager import (
            MANAGED_START_MARKER, MANAGED_END_MARKER,
        )
        return (
            "# Project\npreamble\n"
            + MANAGED_START_MARKER + "\n"
            "# PACT Framework and Managed Project Memory\n\n"
            "## Retrieved Context\n\n"
            + above
            + "## Pinned Context\n"
            + pinned_body + tail
            + MANAGED_END_MARKER + "\ntail\n"
        )

    PIN_A = "<!-- pinned: 2026-01-01 -->\n### Alpha\nalpha body\n\n"
    PIN_B = "<!-- pinned: 2026-01-02 -->\n### Beta\nbeta body\n\n"

    def test_rename_arm_declared_parse_excludes_what_inferred_scan_charges(
        self, monkeypatch
    ):
        """THE NON-VACUITY ARM. Rename the marker out of the boundary family
        and the two parses diverge: the inferred scan overruns the marker and
        charges its text to the pinned body, while the declared parse still
        ends the region at it.

        Today the marker escapes the body only because its NAME matches a
        generic alternation -- an INCIDENTAL exclusion. This arm is what makes
        the exclusion INTENTIONAL, and it is the sole measured difference
        between the two parses.
        """
        import staleness

        renamed = "<!-- PINNED_REGION_END -->"
        # CONTROL: the rename must actually leave the family, or this arm
        # silently degrades into the no-op case it exists to escape.
        from shared.claude_md_manager import PACT_BOUNDARY_PREFIXES
        assert not any(
            renamed.startswith("<!-- " + p) for p in PACT_BOUNDARY_PREFIXES
        ), "rename arm is vacuous: the substitute marker is still in the family"

        content = self._doc(self.PIN_A + self.PIN_B + renamed + "\n")

        # Arm 1: shipped constant -> the substitute is not the declared end,
        # so the parse falls through to the inferred scan and CHARGES it.
        inferred_body = staleness._parse_pinned_section(content)[2]

        # Arm 2: the constant IS the substitute -> the declared parse excludes.
        monkeypatch.setattr(staleness, "PINNED_END_MARKER", renamed)
        declared_body = staleness._parse_pinned_section(content)[2]

        assert renamed in inferred_body, (
            "inferred scan should have overrun the out-of-family marker"
        )
        assert renamed not in declared_body, (
            "declared parse must exclude the marker it was told to look for"
        )
        assert len(declared_body) < len(inferred_body), (
            f"declared ({len(declared_body)}) must be shorter than inferred "
            f"({len(inferred_body)}); equal lengths mean the arm went vacuous"
        )

    def test_absent_end_marker_uses_the_inferred_scan(self):
        """Fail open. No marker at all is the production shape on day one."""
        import staleness
        with_marker = staleness._parse_pinned_section(
            self._doc(self.PIN_A + self.PIN_B
                      + staleness.PINNED_END_MARKER + "\n")
        )[2]
        without = staleness._parse_pinned_section(
            self._doc(self.PIN_A + self.PIN_B)
        )[2]
        assert with_marker == without

    def test_start_marker_without_end_does_not_raise_and_parses_the_same(self):
        """Half-marked tolerance is REQUIRED, not optional. If the marker
        writer lands before a document gains an END, every file it touches
        carries a START alone. That is correct, not broken."""
        import staleness
        from shared.claude_md_manager import PINNED_START_MARKER

        half = self._doc(self.PIN_A + self.PIN_B,
                         above=PINNED_START_MARKER + "\n")
        plain = self._doc(self.PIN_A + self.PIN_B)

        half_parsed = staleness._parse_pinned_section(half)
        assert half_parsed is not None, (
            "a START-only document must still parse; None means the half-marked "
            "state was treated as absent rather than tolerated"
        )
        assert half_parsed[2] == staleness._parse_pinned_section(plain)[2]

    def test_heading_between_body_and_declared_end_is_not_swallowed(self):
        """A foreign H2 section before the declared end must stay OUT of the
        pinned span.

        THE OUTCOME IS UNCHANGED; THE MECHANISM IS NOT. This case used to be
        caught by a well-formedness gate that probed for headings. The gate is
        gone: the parse now bounds the declared end by the inferred one, so an
        interloping section stops the inferred scan and `min` takes it. The gate
        was an enumeration of bad shapes and it enumerated them too narrowly --
        headings yes, PACT boundary comments no -- which shipped a cardinal
        over-block. This test survives because the PROPERTY survives.

        Do not read a pass here as coverage of the alphabet. See
        `test_span_never_exceeds_inferred_for_every_scan_terminator`, which is
        the arm that ranges over the terminator alternation rather than over the
        one member this test happens to use.
        """
        import staleness

        content = self._doc(
            self.PIN_A + self.PIN_B
            + "## Interloper\nforeign content\n\n"
            + staleness.PINNED_END_MARKER + "\n"
        )
        body = staleness._parse_pinned_section(content)[2]
        assert "foreign content" not in body, (
            "the gate must refuse a declared end that lies beyond a heading"
        )
        assert "## Interloper" not in body

    def test_span_never_exceeds_inferred_for_every_scan_terminator(self):
        """THE CEILING INVARIANT, ranged over the SCAN's alphabet.

        THE INPUT ALPHABET IS DERIVED FROM THE TERMINATOR SCAN, NEVER FROM THE
        PARSE RULE, and that is the whole point of this test rather than a
        stylistic note. The predecessor gate probed `#{1,2}\\s`; the test written
        for it exercised an H2 heading. Its alphabet was read off the
        implementation, so it could not falsify the implementation's CHOICE of
        alphabet -- it exercised exactly the shape the gate already covered, and
        reported green while a boundary comment sailed through. A TEST WHOSE
        INPUT SPACE COMES FROM THE CODE UNDER TEST CANNOT FALSIFY THAT CODE'S
        CHOICE OF INPUT SPACE.

        So the members here are enumerated from `PACT_BOUNDARY_PREFIXES` plus
        the heading form -- the two branches of the scan's own alternation. A
        fourth prefix added to that tuple appears here automatically.

        THE ASSERTION IS THE INVARIANT ITSELF, not a table of expected offsets:
        the span returned for a MARKED document is never larger than the span
        returned for the same document unmarked. Unmarked is the pre-change
        behaviour, so this states that no declared end can widen any region.

        COUNTER-TEST PROTOCOL, TWO MUTANTS WITH DIFFERENT SIGNATURES. Both were
        run; the second is the one that matters:

          MUTANT A -- replace the `min` with a bare unbounded override.
            EVERY member fails, headings included.

          MUTANT B -- restore the shipped defect exactly: a heading-only probe
            `#{1,2}\\s` guarding an unbounded override.
            The HEADING members PASS and all three BOUNDARY members FAIL.

        MUTANT B IS THE PROOF THAT THIS TEST WOULD HAVE CAUGHT THE SHIPPED
        DEFECT, and its asymmetry is the reason the defect shipped: the gate
        covered the heading subset, the test exercised the heading subset, and
        the two agreed with each other while both missed the boundary subset.

        A NOTE ON BUILDING MUTANT B, because getting it wrong reads like a
        result. A first attempt over-escaped the pattern into a literal
        backslash, which matched nothing, silently degrading mutant B into
        mutant A -- every member failed and the asymmetry vanished. The tell was
        that headings failed too. If you rebuild it, first assert the mutant
        pattern MATCHES `## Interloper` and does NOT match a boundary comment;
        otherwise you are testing a bare override and will conclude the wrong
        thing about what this test covers.
        """
        import staleness
        from shared.claude_md_manager import PACT_BOUNDARY_PREFIXES

        members = [
            ("h2 heading", "## Interloper\nforeign\n\n"),
            ("h1 heading", "# Interloper\nforeign\n\n"),
        ] + [
            (f"boundary comment {p}", f"<!-- {p}NOTE -->\nforeign\n\n")
            for p in PACT_BOUNDARY_PREFIXES
        ]
        assert len(members) >= 5, "alphabet collapsed; the sweep is vacuous"

        for label, interloper in members:
            marked = staleness._parse_pinned_section(
                self._doc(self.PIN_A + self.PIN_B + interloper
                          + staleness.PINNED_END_MARKER + "\n")
            )
            inferred = staleness._parse_pinned_section(
                self._doc(self.PIN_A + self.PIN_B + interloper)
            )
            assert marked is not None and inferred is not None, label
            assert len(marked[2]) <= len(inferred[2]), (
                f"{label}: the declared end WIDENED the region "
                f"({len(marked[2])} > {len(inferred[2])}). A declared end must "
                f"only ever bound the inferred one."
            )
            assert "foreign" not in marked[2], (
                f"{label}: foreign section pulled into the pinned span"
            )

    def test_indented_marker_quoted_in_a_pin_body_does_not_truncate(self):
        """THE FAIL-OPEN GUARD, and it is the reason
        `_find_declared_end_offset` tolerates trailing whitespace only.

        `_find_terminator_offset` matches the RAW line, so it does not match an
        indented marker. A `.strip()` compare in the declared locator WOULD,
        the two would disagree about which line ends the region, and the
        declared offset would land INSIDE the pinned body -- dropping a pin out
        of the counted span and failing the cap OPEN.

        Counter-test protocol: change `.rstrip()` to `.strip()` in
        `staleness._find_declared_end_offset` and this test must fail.
        """
        import staleness

        content = self._doc(
            "<!-- pinned: 2026-01-01 -->\n### Alpha\ntext\n"
            "  " + staleness.PINNED_END_MARKER + "\n"
            "more alpha\n\n"
            + self.PIN_B
        )
        body = staleness._parse_pinned_section(content)[2]
        assert body.count("### ") == 2, (
            f"expected both pins to stay in the counted span, got "
            f"{body.count('### ')} -- an indented quote truncated the region"
        )

    def test_trailing_whitespace_on_the_marker_line_is_tolerated(self):
        """The other half of the same asymmetry. A trailing-space marker line
        is still at column 0, so the inferred scan matches it too and the two
        locators stay in agreement. Tolerating it costs nothing."""
        import staleness

        padded = staleness._parse_pinned_section(
            self._doc(self.PIN_A + self.PIN_B
                      + staleness.PINNED_END_MARKER + "   \n")
        )[2]
        clean = staleness._parse_pinned_section(
            self._doc(self.PIN_A + self.PIN_B
                      + staleness.PINNED_END_MARKER + "\n")
        )[2]
        assert padded == clean


class TestParsePinnedSectionMarkerBoundary:
    r"""Direct unit tests for `staleness._parse_pinned_section`'s marker-aware
    section-end detection.

    Round-4 Item 4: the integration test `TestCheckPinnedStaleness.test_pinned_content_before_memory_end_marker`
    passes even if the next_section regex is relaxed back to `^#{1,2}\s`
    because the fixture content has no stale entries, so no write-back occurs
    and the marker is never touched. A unit-level test on `_parse_pinned_section`
    directly asserts that the returned `pinned_end` index stops BEFORE the
    marker — this is the differentiated behavior the round-3 fix protects.

    Counter-test protocol: if the `next_section` regex in
    `staleness._parse_pinned_section` is reverted to `^#{1,2}\s`, this test
    must fail because the returned `pinned_end` would overshoot into the
    marker and any downstream content.
    """

    def test_pinned_end_stops_before_pact_memory_end_marker(self):
        """`_parse_pinned_section` must return `pinned_end` at the line that
        begins with `<!-- PACT_MEMORY_END -->`, not past it.

        Without the marker alternative in the regex, the parser would scan
        past the marker looking for the next H1/H2 heading, and `pinned_end`
        would either land on that later heading or on EOF — both causing
        subsequent write-back to eat the boundary marker.
        """
        from staleness import _parse_pinned_section

        content = (
            "# PACT Framework and Managed Project Memory\n"
            "\n"
            "<!-- PACT_MEMORY_START -->\n"
            "## Retrieved Context\n"
            "\n"
            "## Pinned Context\n"
            "### Some pin (PR #100, merged 2026-04-01)\n"
            "Pin body content.\n"
            "<!-- PACT_MEMORY_END -->\n"
            "\n"
            "<!-- PACT_MANAGED_END -->\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        pinned_start, pinned_end, pinned_content = result

        # The returned pinned_content must contain the pin body but must
        # STOP before the marker line. The marker itself must NOT appear
        # inside the extracted pinned_content.
        assert "### Some pin" in pinned_content
        assert "Pin body content." in pinned_content
        assert "<!-- PACT_MEMORY_END -->" not in pinned_content
        assert "<!-- PACT_MANAGED_END -->" not in pinned_content

        # pinned_end must point to the start of the PACT_MEMORY_END marker
        # line, not past it. The character at content[pinned_end] should
        # be the start of the `<!-- PACT_MEMORY_END -->` marker.
        marker_idx = content.index("<!-- PACT_MEMORY_END -->")
        assert pinned_end == marker_idx, (
            f"pinned_end ({pinned_end}) should point to the PACT_MEMORY_END "
            f"marker start ({marker_idx}), not past it"
        )

    def test_pinned_end_stops_before_pact_managed_end_marker(self):
        """Same boundary behavior for PACT_MANAGED_END when the memory
        marker is absent (e.g., malformed file missing PACT_MEMORY_END).
        """
        from staleness import _parse_pinned_section

        content = (
            "# PACT Framework and Managed Project Memory\n"
            "\n"
            "## Pinned Context\n"
            "### Pin one\n"
            "Body one.\n"
            "<!-- PACT_MANAGED_END -->\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        _, pinned_end, pinned_content = result

        assert "Pin one" in pinned_content
        assert "<!-- PACT_MANAGED_END -->" not in pinned_content

        marker_idx = content.index("<!-- PACT_MANAGED_END -->")
        assert pinned_end == marker_idx

    def test_pinned_end_stops_before_pact_routing_end_marker(self):
        """Same boundary behavior for PACT_ROUTING_END. This is an edge
        case — normally routing precedes Pinned Context in the file, but
        the regex alternative lists all three prefixes symmetrically.

        Defensive coverage: the regex alternative lists all three boundary
        prefixes (PACT_MEMORY_, PACT_MANAGED_, PACT_ROUTING_) symmetrically,
        and the parser must terminate the pinned section at ANY of them
        even when the canonical file layout would never put PACT_ROUTING_END
        after ## Pinned Context. This test guarantees the invariant holds
        regardless of file layout reshuffling in the future.
        """
        from staleness import _parse_pinned_section

        content = (
            "## Pinned Context\n"
            "### Pin two\n"
            "Body two.\n"
            "<!-- PACT_ROUTING_END -->\n"
            "\n"
            "## Some Later Heading\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        _, pinned_end, pinned_content = result

        assert "Pin two" in pinned_content
        assert "<!-- PACT_ROUTING_END -->" not in pinned_content

        marker_idx = content.index("<!-- PACT_ROUTING_END -->")
        assert pinned_end == marker_idx

    def test_pinned_end_still_stops_at_heading_when_no_markers(self):
        """Regression: the marker alternative must NOT break the pre-existing
        heading-based boundary when no markers are present. Pre-migration
        files must still parse correctly.
        """
        from staleness import _parse_pinned_section

        content = (
            "## Pinned Context\n"
            "### Pre-migration pin\n"
            "Legacy body.\n"
            "\n"
            "## Working Memory\n"
            "- entry\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        _, pinned_end, pinned_content = result

        assert "Pre-migration pin" in pinned_content
        assert "## Working Memory" not in pinned_content

        heading_idx = content.index("## Working Memory")
        assert pinned_end == heading_idx


class TestEstimateTokensEquivalence:
    """Verify _estimate_tokens is identical across its two twin copies.

    Cross-package isolation (hooks/ vs skills/pact-memory/scripts/) prevents
    direct imports between the two packages. The _estimate_tokens function is
    intentionally duplicated as a "twin copy" with cross-reference comments in
    each file. This test ensures the two copies stay in sync by comparing their
    source code via inspect.getsource().

    Twin locations:
    - hooks/staleness.py: estimate_tokens() (public name, aliased as _estimate_tokens)
    - skills/pact-memory/scripts/working_memory.py: _estimate_tokens() (private name)
    """

    def test_function_bodies_are_identical(self):
        """The function body of _estimate_tokens must be identical in both files.

        Uses inspect.getsource() to get the raw source of each function, then
        strips docstrings and normalizes whitespace so that differences in
        function name or docstring wording do not cause false failures. Only
        the executable lines (the actual logic) are compared.
        """
        from staleness import estimate_tokens as staleness_fn
        from working_memory import _estimate_tokens as working_memory_fn

        staleness_source = inspect.getsource(staleness_fn)
        working_memory_source = inspect.getsource(working_memory_fn)

        staleness_body = self._extract_body(staleness_source)
        working_memory_body = self._extract_body(working_memory_source)

        assert staleness_body == working_memory_body, (
            "Twin copies of _estimate_tokens have diverged.\n"
            f"staleness.py body:\n{staleness_body}\n\n"
            f"working_memory.py body:\n{working_memory_body}"
        )

    def test_both_use_word_count_times_1_3(self):
        """Both copies must use the word_count * 1.3 formula."""
        from staleness import estimate_tokens as staleness_fn
        from working_memory import _estimate_tokens as working_memory_fn

        staleness_source = inspect.getsource(staleness_fn)
        working_memory_source = inspect.getsource(working_memory_fn)

        for name, source in [("staleness.py", staleness_source),
                             ("working_memory.py", working_memory_source)]:
            assert "text.split()" in source, (
                f"{name}: missing text.split() call"
            )
            assert "* 1.3" in source, (
                f"{name}: missing * 1.3 multiplier"
            )

    def test_both_return_zero_for_empty(self):
        """Both copies must return 0 for empty/falsy input."""
        from staleness import estimate_tokens as staleness_fn
        from working_memory import _estimate_tokens as working_memory_fn

        assert staleness_fn("") == 0
        assert working_memory_fn("") == 0
        assert staleness_fn("") == working_memory_fn("")

    def test_both_produce_same_result(self):
        """Both copies must produce identical results for the same input."""
        from staleness import estimate_tokens as staleness_fn
        from working_memory import _estimate_tokens as working_memory_fn

        test_inputs = [
            "",
            "hello",
            "one two three four five six seven eight nine ten",
            "word " * 100,
        ]
        for text in test_inputs:
            assert staleness_fn(text) == working_memory_fn(text), (
                f"Results differ for input: {text[:50]!r}..."
            )

    @staticmethod
    def _extract_body(source: str) -> str:
        """Extract the executable body of a function, stripping docstring and def line.

        Removes the function signature line, any docstring (triple-quoted block),
        and dedents the remaining lines to normalize indentation. This allows
        comparison of the actual logic regardless of function name or doc content.
        """
        lines = source.split("\n")

        # Skip the def line
        body_lines = lines[1:]

        # Join and dedent
        body_text = textwrap.dedent("\n".join(body_lines)).strip()

        # Remove docstring if present (triple double-quotes or triple single-quotes)
        for quote in ['"""', "'''"]:
            if body_text.startswith(quote):
                end_idx = body_text.find(quote, len(quote))
                if end_idx != -1:
                    body_text = body_text[end_idx + len(quote):].strip()
                break

        return body_text


class TestCheckPinnedStalenessHardening:
    """SECURITY + CONCURRENCY hardening for check_pinned_staleness (#366 R5 H1).

    Background: staleness.py is the 6th writer to project CLAUDE.md. The
    other 5 writers (claude_md_manager.{remove_stale_kernel_block,
    update_pact_routing, ensure_project_memory_md} and
    session_resume.update_session_info, plus the test fixture writers)
    use the canonical pattern: file_lock around the read-mutate-write
    block, symlink check INSIDE the lock as a TOCTOU defense, opaque
    skip status when the precondition fails. Pre-fix, check_pinned_staleness
    used a bare read_text/write_text pair with no lock and no symlink
    guard — a concurrent update_session_info or update_pact_routing
    could clobber the SESSION_START block, and a planted symlink would
    redirect the write to an attacker-chosen target.

    This class pins the canonical hardening:
    1. Symlink target rejected with opaque skip status
    2. Concurrent content change detected via inside-lock re-read; no write
       occurs and the function returns None (idempotent skip — staleness
       markers are re-detectable next session, so dropping this pass is
       always safe)
    """

    STALE_DATE = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    def _stale_pinned_content(self):
        """Build CLAUDE.md content with one pinned entry stale enough to
        trigger the modified=True branch of check_pinned_staleness."""
        return (
            "# Project Memory\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #100, merged {self.STALE_DATE})\n"
            "- Some details about the feature\n\n"
            "## Working Memory\n"
        )

    def test_leaf_symlink_out_of_project_allowed_victim_untouched(self, tmp_path):
        """A leaf symlink pointing OUT of the project is ALLOWED, and the write
        lands in-project rather than on the out-of-project victim.

        THIS IS THE TRAP-1 COUPLING TRIPWIRE at this site, and it could not
        exist before the corrected predicate, because the earlier one refused
        this topology outright. It replaces a negative that asserted the
        refusal. That refusal was an over-block: containment is decided on the
        parent chain and the leaf is never consulted. The genuine escape shape
        at this site is a symlinked PARENT, which is covered separately.

        DO NOT 'fix' a failure here by making the guard refuse the topology.
        The victim survives because os.replace is renameat(2) -- it binds the
        final component as a directory ENTRY without following it. A failure
        here means the WRITE SHAPE changed, not that the guard weakened.
        """
        from session_init import check_pinned_staleness

        # Project root is proj_dir (the lexical base of proj_dir/CLAUDE.md).
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()

        # Plant a file OUTSIDE the project root, seeded with stale content so
        # the read-through drives modified=True (the gate into the write path).
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_victim = outside_dir / "external_target.md"
        outside_victim.write_text(self._stale_pinned_content(), encoding="utf-8")

        # project CLAUDE.md is a leaf symlink pointing at that outside file.
        managed_path = proj_dir / "CLAUDE.md"
        os.symlink(str(outside_victim), str(managed_path))
        assert managed_path.is_symlink()

        with patch("session_init._get_project_claude_md_path", return_value=managed_path), \
             patch("staleness._get_project_claude_md_path", return_value=managed_path):
            result = check_pinned_staleness()

        assert result is not None
        assert "skipped" not in result.lower()

        # Boundary 1 -- the out-of-project victim is BYTE-identical: no STALE
        # marker, no budget warning, no write-through. Note this would ALSO hold
        # under a refusal, so it cannot by itself show the write was permitted.
        assert outside_victim.read_text(encoding="utf-8") == self._stale_pinned_content()
        # Boundary 2 -- the write landed at the IN-PROJECT entry, which is now a
        # real file. This is the assertion that pins the ALLOW and the one that
        # flips if the write is ever made to follow the leaf.
        assert not managed_path.is_symlink()
        assert "STALE" in managed_path.read_text(encoding="utf-8")

    def test_in_project_symlink_redirect_allowed_containment_supersedes_ban(self, tmp_path):
        """#1247 deliberate behavior change: an IN-PROJECT symlink redirect is
        ALLOWED. Containment refuses only ESCAPES; an in-project target is
        contained. The former blunt leaf-is_symlink guard refused ALL symlinks
        (an over-block on benign in-project symlinks) — containment removes
        that over-block while still closing the F1 escape.

        Security-engineer-signed-off residual: os.replace REPLACES the symlink
        entry, it does NOT write through it, so even a crafted in-project
        redirect cannot overwrite its pointed-to file. This pins that safety:
        the pointed-to in-project file is byte-unchanged and CLAUDE.md becomes
        a regular file carrying the staleness update.
        """
        from session_init import check_pinned_staleness

        # Both the symlink and its target are IN-PROJECT (project root =
        # tmp_path, the lexical base of tmp_path/CLAUDE.md) -> contained.
        sibling = tmp_path / "sib.md"
        sibling.write_text(self._stale_pinned_content(), encoding="utf-8")
        sibling_before = sibling.read_text(encoding="utf-8")

        managed_path = tmp_path / "CLAUDE.md"
        os.symlink(str(sibling), str(managed_path))
        assert managed_path.is_symlink()

        with patch("session_init._get_project_claude_md_path", return_value=managed_path), \
             patch("staleness._get_project_claude_md_path", return_value=managed_path):
            result = check_pinned_staleness()

        # ALLOWED: the write proceeded (a detection message, not the opaque skip).
        assert result is not None
        assert "skipped" not in result.lower()

        # os.replace does NOT write through the leaf symlink: the pointed-to
        # in-project file is byte-unchanged...
        assert sibling.read_text(encoding="utf-8") == sibling_before
        # ...and CLAUDE.md is now a real file carrying the staleness marker.
        assert not managed_path.is_symlink()
        assert "<!-- STALE:" in managed_path.read_text(encoding="utf-8")

    def test_containment_refusal_attributed_not_lock_contention(self, tmp_path):
        """A containment refusal must surface the CONTAINMENT status, never the
        lock-contention status. ContainmentError subclasses OSError, so if the
        `except ContainmentError` arm were ordered after `except OSError` (or
        dropped), an escape would be silently misattributed to a lock failure.
        This pins the arm ordering end-to-end via the real write path.

        THE TOPOLOGY IS LOAD-BEARING, not incidental scenery. The escape must be
        a symlinked PARENT, never a symlinked leaf. Containment is decided on the
        parent chain and the leaf is never consulted, so a leaf pointing outside
        is ALLOWED and raises nothing -- this test would then go green while
        exercising no refusal path at all, and would keep passing with the
        `except` arms in the wrong order. Only a parent-out topology reaches the
        refusal this test exists to attribute.
        """
        from session_init import check_pinned_staleness

        project = tmp_path / "proj"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        os.symlink(str(outside), str(project / ".claude"), target_is_directory=True)
        managed_path = project / ".claude" / "CLAUDE.md"  # resolves into `outside`
        managed_path.write_text(self._stale_pinned_content(), encoding="utf-8")
        before = (outside / "CLAUDE.md").read_text(encoding="utf-8")

        with patch("session_init._get_project_claude_md_path", return_value=managed_path), \
             patch("staleness._get_project_claude_md_path", return_value=managed_path):
            result = check_pinned_staleness()

        assert result == "Pinned staleness skipped: path precondition not met."
        assert "lock contention" not in result.lower()
        # The out-of-project victim is untouched by the refusal.
        assert (outside / "CLAUDE.md").read_text(encoding="utf-8") == before

    def test_concurrent_content_change_skips_write(self, tmp_path, monkeypatch):
        """If content changes between the outer read at L348 and the
        inner re-read inside the lock, the function returns None and does
        NOT write.

        Justification: staleness markers are idempotent — the next session
        will re-detect any stale entries. Better to sacrifice this pass
        than to clobber a concurrent update_pact_routing or
        update_session_info that landed between our outer read and lock
        acquisition.

        We simulate the concurrent change by monkeypatching Path.read_text
        so the SECOND call (inside the lock) returns DIFFERENT content
        than the first.
        """
        from session_init import check_pinned_staleness

        # Plant the project CLAUDE.md with stale content (triggers modified=True)
        claude_md = tmp_path / "CLAUDE.md"
        original_content = self._stale_pinned_content()
        claude_md.write_text(original_content, encoding="utf-8")

        # The "concurrent writer" simulated content — different bytes,
        # represents a SESSION_START block landing between our outer read
        # and our lock acquisition.
        concurrent_content = (
            "# Project Memory\n\n"
            "<!-- SESSION_START -->\n"
            "## Current Session\n"
            "- Resume: claude --resume abc123\n"
            "<!-- SESSION_END -->\n\n"
            "## Pinned Context\n\n"
            f"### Old Feature (PR #100, merged {self.STALE_DATE})\n"
            "- Some details about the feature\n\n"
        )

        original_read_text = Path.read_text
        call_state = {"count": 0}

        def fake_read_text(self, *args, **kwargs):
            # Only intercept reads of the managed path; let other reads
            # (e.g., site-packages, pyc inspection) pass through.
            if str(self) == str(claude_md):
                call_state["count"] += 1
                if call_state["count"] == 1:
                    return original_content
                # All subsequent reads (the inside-lock re-read) return the
                # "concurrent change" content.
                return concurrent_content
            return original_read_text(self, *args, **kwargs)

        # Track writes so we can assert no write occurred. The managed-path write
        # goes through _atomic_write_text (temp + rename), NOT Path.write_text, so
        # tracking Path.write_text would never fire and the "no write" assertion
        # would pass vacuously whether or not the write was skipped. Track the REAL
        # write seam. staleness.check_pinned_staleness imports _atomic_write_text
        # from shared.claude_md_manager at call time, so patching the module
        # attribute is what its local `from ... import` binds to.
        import shared.claude_md_manager as cmm
        write_calls = []
        real_atomic = cmm._atomic_write_text

        def tracking_atomic(target, content, *args, **kwargs):
            if str(target) == str(claude_md):
                write_calls.append(content)
            return real_atomic(target, content, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fake_read_text)
        monkeypatch.setattr(cmm, "_atomic_write_text", tracking_atomic)

        with patch("session_init._get_project_claude_md_path", return_value=claude_md), \
             patch("staleness._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        # The inside-lock re-read detected the content change → skip write
        # → return None (idempotent skip).
        assert result is None
        # Critical: NO write occurred to the managed path.
        assert write_calls == [], (
            f"Expected zero writes when content changed under the writer, "
            f"but {len(write_calls)} write(s) occurred. The inside-lock "
            f"re-read guard is not protecting the concurrent writer's content."
        )
        # Both reads happened (outer + inner re-read), confirming the lock
        # path was actually entered.
        assert call_state["count"] >= 2, (
            f"Expected at least 2 reads of the managed path (outer + "
            f"inner re-read), got {call_state['count']}. The inside-lock "
            f"re-read may have been skipped."
        )

    def test_modified_write_succeeds_when_no_concurrent_change(self, tmp_path):
        """Sanity check: when no concurrent change happens, the function
        DOES write the modified content (stale marker insertion).

        This is the positive complement to the concurrent-change test —
        without it, a future bug that disables ALL writes would silently
        pass the concurrent-change test.
        """
        from session_init import check_pinned_staleness

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(self._stale_pinned_content(), encoding="utf-8")

        with patch("session_init._get_project_claude_md_path", return_value=claude_md), \
             patch("staleness._get_project_claude_md_path", return_value=claude_md):
            result = check_pinned_staleness()

        # Function reports the stale entry was found
        assert result is not None
        assert "stale pin" in result.lower()

        # The file was actually modified — STALE marker is now present
        post_content = claude_md.read_text(encoding="utf-8")
        assert "<!-- STALE: Last relevant" in post_content
        assert self.STALE_DATE in post_content


class TestParsePinnedSectionTerminator:
    """Regression guard: `_parse_pinned_section` must terminate on PACT
    boundary markers and H2 headings.

    Round 10 simplified these tests: fence-awareness tests are deleted
    because the parser now operates within the PACT-managed region only
    (no user-authored fenced code blocks). The unfenced terminator test
    remains as a regression guard for the basic termination contract.
    """

    def test_unfenced_pact_marker_still_terminates_pinned_section(self):
        """PACT boundary markers terminate the pinned section scan."""
        from staleness import _parse_pinned_section

        content = (
            "# Project Memory\n"
            "\n"
            "## Pinned Context\n"
            "\n"
            "### Regular pin\n"
            "No fences here.\n"
            "\n"
            "<!-- PACT_MEMORY_END -->\n"
            "## Working Memory\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        _pinned_start, pinned_end, pinned_content = result

        assert "Regular pin" in pinned_content
        # The marker is the terminator — pinned_content must NOT contain it
        assert "PACT_MEMORY_END" not in pinned_content
        assert content[pinned_end:].lstrip().startswith("<!-- PACT_MEMORY_END -->")

class TestParsePinnedSectionManagedRegionBounding:
    """Round 10: _parse_pinned_section bounds its search to the managed region
    and returns full-file positions for write-back.
    """

    def test_returns_full_file_offsets_with_managed_region(self):
        """Positions in the returned tuple must be absolute in the full
        content, not relative to the managed region.
        """
        from staleness import _parse_pinned_section
        from shared.claude_md_manager import (
            MANAGED_START_MARKER,
            MANAGED_END_MARKER,
        )

        preamble = "user notes above\n\n"
        managed_body = (
            "## Pinned Context\n"
            "\n"
            "### Real pin\n"
            "Pin content here.\n"
            "\n"
        )

        content = (
            preamble
            + MANAGED_START_MARKER + "\n"
            + managed_body
            + MANAGED_END_MARKER + "\n"
            + "user notes below\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        pinned_start, pinned_end, pinned_content = result

        # Offsets must be in the full content, not managed-region-relative
        assert pinned_start > len(preamble), (
            "pinned_start must be an absolute offset past the preamble"
        )
        assert content[pinned_start:pinned_start + 3] == "\n##" or "### " in content[pinned_start:pinned_start + 20]
        assert "Pin content here." in pinned_content

    def test_fallback_to_full_content_without_managed_markers(self):
        """Pre-migration file: no managed markers, parser scans full content."""
        from staleness import _parse_pinned_section

        content = (
            "# Project Memory\n"
            "\n"
            "## Pinned Context\n"
            "\n"
            "### Old pin\n"
            "Old content.\n"
            "\n"
            "## Working Memory\n"
        )

        result = _parse_pinned_section(content)
        assert result is not None
        _, _, pinned_content = result
        assert "Old content." in pinned_content


class TestPinCapsTwinCopyDrift:
    """Drift detection for pin_caps constants twin-copied into working_memory.

    pin_caps.py lives under pact-plugin/hooks/ and working_memory.py lives
    under pact-plugin/skills/pact-memory/scripts/ — separate package
    boundary means direct import is not available. Constants MUST stay in
    sync; this test fails loudly when they drift.
    """

    def test_pin_count_cap_twins_match(self):
        import pin_caps
        import working_memory

        assert pin_caps.PIN_COUNT_CAP == working_memory.PIN_COUNT_CAP, (
            "PIN_COUNT_CAP drift between hooks/pin_caps.py and "
            "skills/pact-memory/scripts/working_memory.py — update both "
            "in the same commit"
        )

    def test_pin_size_cap_twins_match(self):
        import pin_caps
        import working_memory

        assert pin_caps.PIN_SIZE_CAP == working_memory.PIN_SIZE_CAP, (
            "PIN_SIZE_CAP drift between hooks/pin_caps.py and "
            "skills/pact-memory/scripts/working_memory.py — update both "
            "in the same commit"
        )

    def test_pin_stale_block_threshold_twins_match(self):
        import pin_caps
        import working_memory

        assert pin_caps.PIN_STALE_BLOCK_THRESHOLD == working_memory.PIN_STALE_BLOCK_THRESHOLD, (
            "PIN_STALE_BLOCK_THRESHOLD drift between hooks/pin_caps.py and "
            "skills/pact-memory/scripts/working_memory.py — update both "
            "in the same commit"
        )

    def test_override_rationale_max_twins_match(self):
        import pin_caps
        import working_memory

        assert pin_caps.OVERRIDE_RATIONALE_MAX == working_memory.OVERRIDE_RATIONALE_MAX, (
            "OVERRIDE_RATIONALE_MAX drift between hooks/pin_caps.py and "
            "skills/pact-memory/scripts/working_memory.py — update both "
            "in the same commit"
        )

    def test_forbidden_line_terminator_chars_twins_match(self):
        """Line-terminator char set MUST agree across parser and hook.

        Cycle-7 introduced a CLI-side refusal for line terminators in
        override rationales. Cycle-8 demoted the CLI to advisory-only;
        rationale validation moved to the PreToolUse hook
        (hooks/pin_caps_gate.py). The CLI no longer carries its own
        forbidden-char set, so this test compares parser ↔ hook only.

        Drift guard: the hook DERIVES its forbidden-char set from
        `pin_caps._FORBIDDEN_TERMINATOR_TABLE` at module load (single
        source of truth). In a correctly wired repo the equality always
        holds because the hook's set is literally `chr(k) for k in the
        parser table`. This test catches the regression of someone
        reverting the derivation to a hand-maintained literal — if that
        happens, drift is possible, and this assertion fires with both
        sides enumerated.
        """
        import pin_caps
        import pin_caps_gate

        parser_chars = set(chr(k) for k in pin_caps._FORBIDDEN_TERMINATOR_TABLE.keys())
        hook_chars = set(pin_caps_gate._FORBIDDEN_RATIONALE_CHARS)

        assert parser_chars == hook_chars, (
            "Line-terminator char-set drift between parser and hook:\n"
            f"  pin_caps._FORBIDDEN_TERMINATOR_TABLE (parser):   {sorted(parser_chars)!r}\n"
            f"  pin_caps_gate._FORBIDDEN_RATIONALE_CHARS (hook): {sorted(hook_chars)!r}\n"
            "The hook SHOULD derive from the parser table at module load "
            "(see pin_caps_gate.py) so it cannot drift. If you see this "
            "failure, someone reverted the derivation to a hand-maintained "
            "literal. Fix by restoring the `chr(k) for k in "
            "pin_caps._FORBIDDEN_TERMINATOR_TABLE.keys()` form."
        )


class TestFileLockTwinCopyDrift:
    """Drift detection for the file_lock twin vendored into working_memory.

    file_lock is twin-copied from hooks/shared/claude_md_manager into
    skills/pact-memory/scripts/working_memory (skills/ cannot import from
    hooks/shared/). The function BODY must stay byte-identical so the skill
    serializes against the hook on the same sidecar inode; the docstring may
    differ. This fails loudly when the executable logic drifts.
    """

    @staticmethod
    def _extract_body(source: str) -> str:
        """Return the executable body, stripping decorators, the def line,
        and a leading docstring; then dedent + normalize.

        Unlike TestEstimateTokensEquivalence._extract_body, file_lock carries a
        @contextmanager decorator, so this skips ALL leading ``@`` lines before
        dropping the def line. This makes the comparison docstring-tolerant
        (the twin carries a shorter docstring) while pinning the logic.
        """
        lines = source.split("\n")
        idx = 0
        while idx < len(lines) and lines[idx].lstrip().startswith("@"):
            idx += 1
        # lines[idx] is the def line; drop it too.
        body_lines = lines[idx + 1:]
        body_text = textwrap.dedent("\n".join(body_lines)).strip()
        for quote in ['"""', "'''"]:
            if body_text.startswith(quote):
                end_idx = body_text.find(quote, len(quote))
                if end_idx != -1:
                    body_text = body_text[end_idx + len(quote):].strip()
                break
        return body_text

    def test_file_lock_bodies_are_identical(self):
        """The file_lock body MUST be byte-identical across the two copies.

        Cross-process serialization correctness depends on the twin behaving
        exactly like the canonical lock (same sidecar path, same fcntl flock
        semantics, same timeout/poll loop). Compares logic only — docstrings
        are allowed to differ.
        """
        from shared.claude_md_manager import file_lock as canonical
        from working_memory import file_lock as twin

        canonical_body = self._extract_body(inspect.getsource(canonical))
        twin_body = self._extract_body(inspect.getsource(twin))

        assert canonical_body == twin_body, (
            "file_lock twin drift between hooks/shared/claude_md_manager.py "
            "and skills/pact-memory/scripts/working_memory.py — update both "
            "in the SAME commit.\n"
            f"canonical body:\n{canonical_body}\n\n"
            f"twin body:\n{twin_body}"
        )

    def test_lock_timeout_constants_match(self):
        """The two lock-tuning constants are part of the twin and must match."""
        import shared.claude_md_manager as cmm
        import working_memory as wm

        assert cmm._LOCK_TIMEOUT_SECONDS == wm._LOCK_TIMEOUT_SECONDS, (
            "_LOCK_TIMEOUT_SECONDS drift between claude_md_manager.py and "
            "working_memory.py — update both in the same commit"
        )
        assert cmm._LOCK_POLL_INTERVAL == wm._LOCK_POLL_INTERVAL, (
            "_LOCK_POLL_INTERVAL drift between claude_md_manager.py and "
            "working_memory.py — update both in the same commit"
        )


class TestStalenessLexicalBaseParity:
    """#1247: the lexical base recovered from a SUPPLIED path (option D in
    check_pinned_staleness, via staleness._lexical_base_of) MUST equal the base
    the resolver itself used. session_init passes staleness a resolved PATH
    (not a base), so the containment anchor is recovered by inverting the
    resolver's construction; if _resolve_project_claude_md_with_base ever grows
    a THIRD path shape, that lexical formula would silently diverge and the
    guard would anchor on the wrong root. This test turns that divergence into
    a RED -- the single-source-of-truth safeguard the architect mandated
    (twin-drift discipline applied to anchor derivation). It exercises the REAL
    production formula (_lexical_base_of), not a test copy.
    """

    def test_lexical_base_matches_resolver_base_dot_claude(self, tmp_path, monkeypatch):
        import staleness as st

        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "CLAUDE.md").write_text("# x\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        path, base = st._resolve_project_claude_md_with_base()
        assert path is not None and base is not None
        assert st._lexical_base_of(path) == base, (
            "lexical base recovery diverged from the resolver's base for the "
            ".claude/CLAUDE.md shape — option D would anchor containment on the "
            "wrong root"
        )

    def test_lexical_base_matches_resolver_base_legacy(self, tmp_path, monkeypatch):
        import staleness as st

        (tmp_path / "CLAUDE.md").write_text("# x\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        path, base = st._resolve_project_claude_md_with_base()
        assert path is not None and base is not None
        assert st._lexical_base_of(path) == base, (
            "lexical base recovery diverged from the resolver's base for the "
            "legacy ./CLAUDE.md shape — option D would anchor containment on "
            "the wrong root"
        )


class TestAtomicWriteTwinCopyDrift:
    """Drift detection for the _atomic_write_text twin (#1247).

    _atomic_write_text is twin-copied from hooks/shared/claude_md_manager into
    skills/pact-memory/scripts/working_memory (skills/ cannot import from
    hooks/shared/). Since #1247 it carries the CONTAINMENT SECURITY CHECK, so
    the function BODY must stay byte-identical across the two copies -- a
    silent divergence in the security check between the hook and skill copies
    is the #1118-class hazard this gate exists to prevent. The docstring may
    differ (each copy points at the other); the executable logic may not.
    """

    @staticmethod
    def _extract_body(source: str) -> str:
        """Return the executable body: skip leading decorators + the def line,
        strip a leading docstring, dedent, normalize. Same extractor as
        TestFileLockTwinCopyDrift (docstring-tolerant, logic-pinning)."""
        lines = source.split("\n")
        idx = 0
        while idx < len(lines) and lines[idx].lstrip().startswith("@"):
            idx += 1
        body_lines = lines[idx + 1:]
        body_text = textwrap.dedent("\n".join(body_lines)).strip()
        for quote in ['"""', "'''"]:
            if body_text.startswith(quote):
                end_idx = body_text.find(quote, len(quote))
                if end_idx != -1:
                    body_text = body_text[end_idx + len(quote):].strip()
                break
        return body_text

    def test_atomic_write_text_bodies_are_identical(self):
        """The _atomic_write_text body MUST be byte-identical across the twins.

        The body carries the #1247 containment check (kernel object ancestry on
        a pinned directory descriptor, fail-closed); a divergence would let the
        hook and skill write paths enforce different containment, silently
        defeating the guard on one side. Compares logic only -- docstrings are
        allowed to differ.

        THIS GATE PROVES BYTE-IDENTITY, NOT THAT EITHER COPY IS EXERCISED. It
        goes red whenever the bodies diverge for ANY reason, including a
        deliberate single-twin experiment -- so a red here is not by itself
        evidence of a behavioural regression, and counting it as one inflates
        the apparent coverage of whichever twin was left untouched. The
        behavioural coverage of each copy lives in
        test_containment_certification.py, which drives both independently.
        """
        from shared.claude_md_manager import _atomic_write_text as canonical
        from working_memory import _atomic_write_text as twin

        canonical_body = self._extract_body(inspect.getsource(canonical))
        twin_body = self._extract_body(inspect.getsource(twin))

        assert canonical_body == twin_body, (
            "_atomic_write_text twin drift between "
            "hooks/shared/claude_md_manager.py and "
            "skills/pact-memory/scripts/working_memory.py — the #1247 "
            "containment check must stay identical; update both in the SAME "
            "commit.\n"
            f"canonical body:\n{canonical_body}\n\n"
            f"twin body:\n{twin_body}"
        )


class TestContainmentErrorTwinCopyDrift:
    """Drift detection for the ContainmentError twin.

    `working_memory` vendors this from `hooks/shared/claude_md_manager` for the
    same reason as its siblings — skills/ cannot import from hooks/shared/ —
    and it is the exception the containment check raises, so the two copies
    disagreeing means the hook and skill paths signal a containment failure
    differently.

    IT IS GATED ON AST EQUALITY, NOT BYTE EQUALITY, and that is not a
    weakening. The two copies are already not byte-identical: each docstring
    points at the other, which is exactly the divergence the sibling gates
    permit by stripping docstrings before comparing. A byte gate here would go
    red on day one, and a gate that is red on arrival gets deleted rather than
    investigated.
    """

    @staticmethod
    def _executable_shape(obj) -> str:
        """AST dump of the definition with any leading docstring removed."""
        node = ast.parse(textwrap.dedent(inspect.getsource(obj))).body[0]
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            node.body = node.body[1:]
        return ast.dump(node)

    def test_containment_error_shapes_are_identical(self):
        from shared.claude_md_manager import ContainmentError as canonical
        from working_memory import ContainmentError as twin

        assert self._executable_shape(canonical) == self._executable_shape(twin), (
            "ContainmentError twin drift between "
            "hooks/shared/claude_md_manager.py and "
            "skills/pact-memory/scripts/working_memory.py — the containment "
            "failure signal must stay identical across the copies; update "
            "both in the SAME commit."
        )

    def test_the_gate_can_tell_the_shapes_apart(self):
        """NON-VACUITY. An AST comparison that returns equal for everything
        would pass the assertion above forever."""
        from working_memory import ContainmentError as twin
        from working_memory import _project_root_of as unrelated

        assert self._executable_shape(twin) != self._executable_shape(unrelated), (
            "the shape extractor cannot distinguish two different definitions, "
            "so the drift assertion above proves nothing"
        )


class TestProjectRootLayoutKnowledgeDrift:
    """`_project_root_of` duplicates LAYOUT KNOWLEDGE, not a function body.

    Its siblings above are twin-copied implementations, compared against their
    originals. This one has no original to compare with: it is the INVERSE of
    `claude_md_manager.resolve_project_claude_md_path` (path -> root rather
    than root -> path), so no copy of it exists to diverge from. What it
    duplicates is the two-layout rule — that CLAUDE.md lives at
    `<project>/.claude/CLAUDE.md` or `<project>/CLAUDE.md` — whose SSOT is
    `_DOT_CLAUDE_RELATIVE` / `_LEGACY_RELATIVE`.

    SO IT IS PINNED AGAINST THE CONSTANTS RATHER THAN AGAINST A TWIN, and the
    difference matters: measured, renaming the SSOT constant breaks 21 tests
    elsewhere in the tree and ZERO in the memory layer. The knowledge is fully
    decoupled, so a third supported location — or a rename — diverges here in
    silence. `archive_pin.project_dir_for` carries the same rule and the same
    exposure.
    """

    def test_inverts_the_canonical_resolver_for_both_layouts(self):
        from shared.claude_md_manager import (
            _DOT_CLAUDE_RELATIVE,
            _LEGACY_RELATIVE,
            resolve_project_claude_md_path,
        )
        from working_memory import _project_root_of

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            # Legacy layout: seed the file the SSOT constant names.
            legacy_root = root / "legacy"
            (legacy_root).mkdir()
            (legacy_root / _LEGACY_RELATIVE).write_text("x", encoding="utf-8")
            resolved, source = resolve_project_claude_md_path(legacy_root)
            assert source == "legacy", f"fixture drift: got source={source!r}"
            assert _project_root_of(resolved) == legacy_root, (
                "_project_root_of does not invert the canonical resolver for "
                f"the legacy layout named by _LEGACY_RELATIVE ({_LEGACY_RELATIVE!r})"
            )

            # Dot layout.
            dot_root = root / "dot"
            (dot_root / _DOT_CLAUDE_RELATIVE).parent.mkdir(parents=True)
            (dot_root / _DOT_CLAUDE_RELATIVE).write_text("x", encoding="utf-8")
            resolved, source = resolve_project_claude_md_path(dot_root)
            assert source == "dot_claude", f"fixture drift: got source={source!r}"
            assert _project_root_of(resolved) == dot_root, (
                "_project_root_of does not invert the canonical resolver for "
                f"the dot layout named by _DOT_CLAUDE_RELATIVE "
                f"({_DOT_CLAUDE_RELATIVE!r}) — a third supported location or a "
                f"rename of that constant diverges here silently"
            )
