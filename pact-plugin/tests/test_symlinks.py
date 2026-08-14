"""
Tests for shared/symlinks.py -- plugin symlink management.

Tests cover:
setup_plugin_symlinks():
1. Returns None when CLAUDE_PLUGIN_ROOT doesn't exist
2. Creates protocols symlink when missing
3. Updates protocols symlink when pointing to wrong target
4. Skips protocols symlink when already correct
5. Creates agent file symlinks
6. Updates agent symlinks when pointing to wrong target
7. Skips existing real agent files (user override)
8. Returns "PACT symlinks verified" when all links already correct
9. Handles OSError during protocol symlink creation
10. Repoints a link by an atomic swap, with no empty moment at the destination
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))


class TestSetupPluginSymlinks:
    """Tests for setup_plugin_symlinks() -- symlink creation."""

    def test_returns_none_when_plugin_root_missing(self, monkeypatch):
        """Should return None when CLAUDE_PLUGIN_ROOT doesn't exist."""
        from shared.symlinks import setup_plugin_symlinks

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/nonexistent/path")

        result = setup_plugin_symlinks()

        assert result is None

    def test_creates_protocols_symlink(self, tmp_path, monkeypatch):
        """Should create protocols symlink when it doesn't exist."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with protocols dir
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        (plugin_root / "protocols").mkdir()

        # Set up claude dir without symlink
        claude_dir = tmp_path / "home" / ".claude"
        claude_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert result is not None
        assert "protocols linked" in result
        protocols_link = claude_dir / "protocols" / "pact-plugin"
        assert protocols_link.is_symlink()
        assert protocols_link.resolve() == (plugin_root / "protocols").resolve()

    def test_updates_protocols_symlink_when_wrong_target(self, tmp_path, monkeypatch):
        """Should update protocols symlink when pointing to wrong location."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with protocols dir
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        (plugin_root / "protocols").mkdir()

        # Set up claude dir with existing wrong symlink
        claude_dir = tmp_path / "home" / ".claude"
        protocols_dir = claude_dir / "protocols"
        protocols_dir.mkdir(parents=True)
        old_target = tmp_path / "old_protocols"
        old_target.mkdir()
        protocols_link = protocols_dir / "pact-plugin"
        protocols_link.symlink_to(old_target)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert result is not None
        assert "protocols updated" in result
        assert protocols_link.resolve() == (plugin_root / "protocols").resolve()

    def test_skips_correct_protocols_symlink(self, tmp_path, monkeypatch):
        """Should not update protocols symlink when already correct."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with protocols dir
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        (plugin_root / "protocols").mkdir()

        # Set up claude dir with correct symlink
        claude_dir = tmp_path / "home" / ".claude"
        protocols_dir = claude_dir / "protocols"
        protocols_dir.mkdir(parents=True)
        protocols_link = protocols_dir / "pact-plugin"
        protocols_link.symlink_to(plugin_root / "protocols")

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        # No agents dir, so only protocols matters -- should be "verified"
        assert result == "PACT symlinks verified"

    def test_creates_agent_symlinks(self, tmp_path, monkeypatch):
        """Should create symlinks for agent files."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with agents
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir()
        (agents_dir / "pact-backend-coder.md").write_text("agent def")
        (agents_dir / "pact-frontend-coder.md").write_text("agent def")

        # Set up claude dir
        claude_dir = tmp_path / "home" / ".claude"
        claude_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert result is not None
        assert "2 agents linked" in result
        agents_dst = claude_dir / "agents"
        assert (agents_dst / "pact-backend-coder.md").is_symlink()
        assert (agents_dst / "pact-frontend-coder.md").is_symlink()

    def test_returns_verified_when_all_correct(self, tmp_path, monkeypatch):
        """Should return 'PACT symlinks verified' when everything is up to date."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with protocols and agents
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        (plugin_root / "protocols").mkdir()
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir()
        (agents_dir / "pact-test.md").write_text("agent def")

        # Set up claude dir with correct symlinks
        claude_dir = tmp_path / "home" / ".claude"
        protocols_dir = claude_dir / "protocols"
        protocols_dir.mkdir(parents=True)
        (protocols_dir / "pact-plugin").symlink_to(plugin_root / "protocols")
        agents_dst = claude_dir / "agents"
        agents_dst.mkdir()
        (agents_dst / "pact-test.md").symlink_to(agents_dir / "pact-test.md")

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert result == "PACT symlinks verified"

    def test_skips_real_agent_files(self, tmp_path, monkeypatch):
        """Should skip agent files that are real files (user override)."""
        from shared.symlinks import setup_plugin_symlinks

        # Set up plugin root with agents
        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir()
        (agents_dir / "pact-custom.md").write_text("plugin agent def")

        # Set up claude dir with real file (not symlink)
        claude_dir = tmp_path / "home" / ".claude"
        agents_dst = claude_dir / "agents"
        agents_dst.mkdir(parents=True)
        (agents_dst / "pact-custom.md").write_text("user override")

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        # Real file should not be replaced
        assert not (agents_dst / "pact-custom.md").is_symlink()
        assert (agents_dst / "pact-custom.md").read_text() == "user override"

    def test_protocols_oserror_reports_failure(self, tmp_path, monkeypatch):
        """Should include 'failed' in result when protocol symlink creation raises OSError."""
        from shared.symlinks import setup_plugin_symlinks

        plugin_root = tmp_path / "plugin"
        plugin_root.mkdir()
        (plugin_root / "protocols").mkdir()

        claude_dir = tmp_path / "home" / ".claude"
        protocols_dir = claude_dir / "protocols"
        protocols_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        # Make symlink_to raise OSError
        with patch.object(Path, "symlink_to", side_effect=OSError("Permission denied")):
            result = setup_plugin_symlinks()

        assert result is not None
        assert "protocols failed" in result


class TestConfigDirSymlinks:
    """C6 (#926): under a non-default CLAUDE_CONFIG_DIR, agents follow the config
    dir and the protocols symlink is created in BOTH roots (dual-location,
    answer-immune to the @-import ~ resolution question)."""

    @staticmethod
    def _plugin(tmp_path):
        plugin_root = tmp_path / "plugin"
        (plugin_root / "protocols").mkdir(parents=True)
        (plugin_root / "agents").mkdir(parents=True)
        (plugin_root / "agents" / "pact-secretary.md").write_text("x", encoding="utf-8")
        return plugin_root

    def test_protocols_dual_location_when_config_dir_differs(self, tmp_path, monkeypatch):
        from shared.symlinks import setup_plugin_symlinks
        plugin_root = self._plugin(tmp_path)
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        config_dir = tmp_path / "config-kimi"
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
        monkeypatch.setattr(Path, "home", lambda: home)
        setup_plugin_symlinks()
        src = (plugin_root / "protocols").resolve()
        home_link = home / ".claude" / "protocols" / "pact-plugin"
        config_link = config_dir / "protocols" / "pact-plugin"
        assert home_link.is_symlink() and home_link.resolve() == src
        assert config_link.is_symlink() and config_link.resolve() == src

    def test_agents_follow_config_dir(self, tmp_path, monkeypatch):
        from shared.symlinks import setup_plugin_symlinks
        plugin_root = self._plugin(tmp_path)
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        config_dir = tmp_path / "config-kimi"
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
        monkeypatch.setattr(Path, "home", lambda: home)
        setup_plugin_symlinks()
        # agents discovered from $CONFIG/agents — NOT $HOME/.claude/agents
        assert (config_dir / "agents" / "pact-secretary.md").is_symlink()
        assert not (home / ".claude" / "agents" / "pact-secretary.md").exists()

    def test_protocols_single_location_when_env_unset(self, tmp_path, monkeypatch):
        from shared.symlinks import setup_plugin_symlinks
        plugin_root = self._plugin(tmp_path)
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: home)
        setup_plugin_symlinks()
        # env unset → config root == $HOME/.claude → single create there
        assert (home / ".claude" / "protocols" / "pact-plugin").is_symlink()
        assert (home / ".claude" / "agents" / "pact-secretary.md").is_symlink()


class TestProtocolsMkdirFailOpen:
    """#926 (ea74cd0d): the protocols-symlink parent mkdir moved INSIDE the
    per-root try, so a pathological config_root whose mkdir raises must fail-open
    (a 'protocols failed' status), honoring setup_plugin_symlinks's
    'returns None/status, never raises' contract.

    NON-VACUITY: with the mkdir OUTSIDE the try (the pre-ea74cd0d shape) the
    OSError would PROPAGATE and setup_plugin_symlinks would RAISE -> this test
    (asserting no-raise + 'protocols failed') would ERROR. Verified: moving the
    mkdir above the try -> this test raises. Complements
    test_protocols_oserror_reports_failure, which covers the symlink_to (not
    mkdir) failure path.
    """

    def test_mkdir_failure_is_caught_and_reported(self, tmp_path, monkeypatch):
        from shared.symlinks import setup_plugin_symlinks

        plugin_root = tmp_path / "plugin"
        (plugin_root / "protocols").mkdir(parents=True)
        # No agents/ dir -> the (un-tried) agents mkdir block is skipped, so the
        # patched mkdir below only hits the protocols parent mkdir (in-try).
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with patch.object(Path, "mkdir", side_effect=OSError("Read-only file system")):
            result = setup_plugin_symlinks()  # must NOT raise

        assert result is not None
        assert "protocols failed" in result


class TestAtomicRepoint:
    """A repoint leaves NO moment with no file at the destination.

    The previous shape was ``dst.unlink()`` then ``dst.symlink_to(target)``,
    which left the destination EMPTY between the two calls. That window is
    harmless while the refresh runs at a launch only. It becomes a live risk
    once the refresh runs at each session start, because it can then fall
    mid-session while a spawn resolves the link, and a spawn that lands in it
    gets NO file at all.

    NON-VACUITY: the first two arms observe ``os.replace``, which the old pair
    does not call. A revert to unlink-then-symlink_to leaves the observation
    list EMPTY and reddens each of them. They also cover the two loops
    separately, so a revert of one loop alone cannot stay green.

    THE SWAP DOES NOT PROTECT A USER OVERRIDE. ``os.replace`` onto a path that
    holds a plain file succeeds and destroys that file. The ``is_symlink()``
    guard at each call site is what protects it, and
    ``test_skips_real_agent_files`` is the arm that catches its removal.
    """

    @staticmethod
    def _agent_link_at_wrong_target(tmp_path):
        """Build a plugin root, a home, and ONE agent link at a prior root."""
        plugin_root = tmp_path / "plugin"
        agents_src = plugin_root / "agents"
        agents_src.mkdir(parents=True)
        (agents_src / "pact-test.md").write_text("current agent def")

        prior_agents = tmp_path / "prior-plugin" / "agents"
        prior_agents.mkdir(parents=True)
        (prior_agents / "pact-test.md").write_text("prior agent def")

        agents_dst = tmp_path / "home" / ".claude" / "agents"
        agents_dst.mkdir(parents=True)
        (agents_dst / "pact-test.md").symlink_to(prior_agents / "pact-test.md")
        return plugin_root, agents_dst

    @staticmethod
    def _watch_replace(monkeypatch):
        """Record the destination state at the instant BEFORE each atomic move."""
        observed = []
        real_replace = os.replace

        def watched_replace(src, dst):
            observed.append((os.path.lexists(dst), Path(dst).is_symlink()))
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", watched_replace)
        return observed

    def test_agent_destination_holds_a_link_at_the_moment_of_the_swap(
        self, tmp_path, monkeypatch
    ):
        """The agents loop moves the new link ONTO a destination that holds the
        old link."""
        from shared.symlinks import setup_plugin_symlinks

        plugin_root, agents_dst = self._agent_link_at_wrong_target(tmp_path)
        dst_link = agents_dst / "pact-test.md"
        observed = self._watch_replace(monkeypatch)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert observed == [(True, True)], (
            "The destination must hold a symlink at the instant of the move. "
            "An EMPTY list means os.replace was not called at all, which is "
            "the unlink-then-symlink_to shape this test forbids."
        )
        assert "1 agents updated" in result
        assert dst_link.is_symlink()
        assert dst_link.resolve() == (plugin_root / "agents" / "pact-test.md").resolve()
        assert dst_link.read_text() == "current agent def"

    def test_protocols_destination_holds_a_link_at_the_moment_of_the_swap(
        self, tmp_path, monkeypatch
    ):
        """The protocols loop takes the same swap as the agents loop.

        PAIRS WITH the agents arm above: the two loops carry separate copies of
        the repoint, so one arm alone cannot see a revert of the other.
        """
        from shared.symlinks import setup_plugin_symlinks

        plugin_root = tmp_path / "plugin"
        (plugin_root / "protocols").mkdir(parents=True)
        prior_protocols = tmp_path / "prior-plugin" / "protocols"
        prior_protocols.mkdir(parents=True)

        protocols_dir = tmp_path / "home" / ".claude" / "protocols"
        protocols_dir.mkdir(parents=True)
        protocols_link = protocols_dir / "pact-plugin"
        protocols_link.symlink_to(prior_protocols)

        observed = self._watch_replace(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert observed == [(True, True)]
        assert "protocols updated" in result
        assert protocols_link.resolve() == (plugin_root / "protocols").resolve()

    def test_the_count_comes_from_a_comparison_made_before_the_write(
        self, tmp_path, monkeypatch
    ):
        """THE ORDER OF THE READ AND THE WRITE IS CORRECTNESS, NOT STYLE.

        The count of links that moved comes from a comparison of the link
        target against the file it is about to point at. THAT COMPARISON MUST
        RUN BEFORE THE WRITE. A later change that re-reads the link AFTER the
        write makes the two values agree at each run, so the count goes to 0
        and the report goes silent from then on, with a green suite.

        WHICH HALF OF THIS ARM DOES THE WORK, MEASURED RATHER THAN ASSUMED.
        Against a mutant that writes first and compares after, THE TARGET
        ASSERTION PASSES and THE COUNT ASSERTION REDDENS. The destination holds
        the prior link at the moment of the swap under either order, so the
        target assertion does NOT separate the two orders on its own. It
        records the state that the count is taken from, and the count is what
        catches the change.
        """
        from shared.symlinks import setup_plugin_symlinks

        plugin_root, agents_dst = self._agent_link_at_wrong_target(tmp_path)
        prior_target = os.readlink(agents_dst / "pact-test.md")

        targets_at_swap = []
        real_replace = os.replace

        def watched_replace(src, dst):
            targets_at_swap.append(os.readlink(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", watched_replace)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert targets_at_swap == [prior_target], (
            "At the instant of the swap the destination must still hold the "
            "PRIOR target. The count that reaches the user comes from a "
            "comparison against that target, and a comparison made after the "
            "write reports a clean pass on each run."
        )
        assert "1 agents updated" in result

    def test_stale_temporary_path_does_not_block_the_repoint(self, tmp_path, monkeypatch):
        """A crashed run can leave a temporary path behind. The swap removes it
        first, and leaves none of its own behind."""
        from shared.symlinks import _SWAP_SUFFIX, setup_plugin_symlinks

        plugin_root, agents_dst = self._agent_link_at_wrong_target(tmp_path)
        dst_link = agents_dst / "pact-test.md"
        stale_tmp = agents_dst / ("pact-test.md" + _SWAP_SUFFIX)
        stale_tmp.write_text("left behind by a crashed run")

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        result = setup_plugin_symlinks()

        assert "1 agents updated" in result
        assert dst_link.resolve() == (plugin_root / "agents" / "pact-test.md").resolve()
        assert not os.path.lexists(stale_tmp), (
            "The swap must leave no temporary path behind, so the next run "
            "does not meet one."
        )

    def test_temporary_name_sits_outside_the_agent_glob(self):
        """A sweep of the destination for "pact-*.md" must not meet a temporary
        path. The suffix does not end in ".md"."""
        from fnmatch import fnmatch

        from shared.symlinks import _SWAP_SUFFIX

        assert not fnmatch("pact-test.md" + _SWAP_SUFFIX, "pact-*.md")
        # Positive control: the pattern DOES meet the name it is meant for.
        assert fnmatch("pact-test.md", "pact-*.md")


class TestAgentFailureReport:
    """The agents loop REPORTS the files it could not write.

    THE MEASURED STATE THIS CLOSES: with the destination directory at mode
    0o500, so that no link can be written, setup_plugin_symlinks() returned
    'PACT: protocols updated'. Thirteen agent links stayed at the prior root
    and the message NAMED A SUCCESS. The agents loop caught OSError and ran a
    bare `continue`, while the protocols loop appended a failure message for
    the same error class.

    IT MATTERS MORE AFTER THE REFRESH RUNS AT EACH SESSION START, because this
    function is then the only mechanism that keeps the resolution surface
    current. A silent failure in it is a stale agent body with no signal.

    WHY THESE ARMS FORCE THE ERROR WITH A PATCH RATHER THAN WITH A DIRECTORY
    MODE: a mode-based fixture does not hold for a run as root, where a 0o500
    directory stays writable. The patch reaches the same except branch on each
    platform and for each user.
    """

    @staticmethod
    def _plugin_with_two_agents(tmp_path):
        """Build a plugin root with two agent files, and NO protocols dir.

        With no protocols directory, the protocols half is skipped, so each
        message in the result comes from the agents loop.
        """
        plugin_root = tmp_path / "plugin"
        agents_src = plugin_root / "agents"
        agents_src.mkdir(parents=True)
        (agents_src / "pact-good.md").write_text("agent def")
        (agents_src / "pact-bad.md").write_text("agent def")
        return plugin_root

    def test_reports_the_count_of_agent_links_it_could_not_write(
        self, tmp_path, monkeypatch
    ):
        """A run that writes NO agent link must not return a message that names
        a success."""
        from shared.symlinks import setup_plugin_symlinks

        plugin_root = self._plugin_with_two_agents(tmp_path)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with patch.object(Path, "symlink_to", side_effect=OSError("Permission denied")):
            result = setup_plugin_symlinks()  # must NOT raise

        assert result is not None
        assert "2 agents failed" in result
        assert "verified" not in result, (
            "A run that wrote nothing must not report the no-change message."
        )
        # CONTRACT WITH THE CALLER: session_init routes this result to the user
        # by the predicate below. A reword that drops "failed" breaks the route.
        assert "failed" in result.lower()

    def test_one_bad_agent_file_does_not_stop_the_loop(self, tmp_path, monkeypatch):
        """The loop CONTINUES past a file it cannot write, and reports the two
        outcomes separately."""
        from shared.symlinks import setup_plugin_symlinks

        plugin_root = self._plugin_with_two_agents(tmp_path)
        agents_dst = tmp_path / "home" / ".claude" / "agents"
        real_symlink_to = Path.symlink_to

        def fail_one_name(self, target, target_is_directory=False):
            # Reaches the repoint path too, whose temporary name carries the
            # same stem.
            if self.name.startswith("pact-bad"):
                raise OSError("Permission denied")
            return real_symlink_to(self, target, target_is_directory)

        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.setattr(Path, "symlink_to", fail_one_name)

        result = setup_plugin_symlinks()

        assert "1 agents linked" in result
        assert "1 agents failed" in result
        assert (agents_dst / "pact-good.md").is_symlink(), (
            "The good file must be written. A loop that stops at the first "
            "failure leaves the rest of the agents stale."
        )
        assert not (agents_dst / "pact-bad.md").exists()
