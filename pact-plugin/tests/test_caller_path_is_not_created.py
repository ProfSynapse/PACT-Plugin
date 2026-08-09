"""A caller-supplied store path is OPENED, never brought into existence.

THE HALF THIS CLOSES. An earlier refusal covered a typo in the DIRECTORY. A
typo in the FILE NAME reached a directory that was present, built a store, and
reported an ordinary result. In the true spelling that throwaway store lands
INSIDE the live store directory, so the caller keeps working against a store
that holds nothing.

THE REFUSAL LIVES AT THE CLI BOUNDARY, IN `cli.main`, AND THESE ARMS DRIVE THE
CLI. A refusal inside `database.get_connection` was built first and rejected:
it reaches EACH caller of the connection factory, so it breaks the custom-store
contract that production and the test suite depend on. The boundary can read
the command name as a fact on `args`, so it separates `setup` from the commands
that open a store.

THE ASYMMETRY IS DELIBERATE. `setup` creates, because bringing a store into
existence at a named location is its operation. `save`, `get` and `list` open a
store that should be there, so an absent one is a typo.

THE CLASS OF EACH ARM, BECAUSE RED HAS SEVERAL CAUSES AND ONLY ONE OF THEM IS
THE MECHANISM.

  RED FOR THE MECHANISM on the unfixed code:
    test_an_absent_caller_file_is_refused. The store was built and the caller
    saw an ordinary result.

  OVER-BLOCK GUARDS. These cannot go red on the unfixed code, because it
  carries no refusal to over-block. They bound the refusal instead:
    test_a_store_that_is_present_still_opens
    test_a_path_holding_shell_or_uri_syntax_still_opens
    test_setup_may_bring_a_caller_path_into_existence

  GREEN BEFORE AND AFTER, AND IT OUTRANKS THE REFUSAL:
    test_the_derived_route_still_creates. An arm proving only the refusal would
    pass against a fix that broke each production caller.

  PINS AN ACCEPTED TRADE RATHER THAN A DESIRED OUTCOME:
    test_an_absent_path_is_reported_before_malformed_input. Read its docstring
    before you change the boundary check.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_PARENT = Path(__file__).parent.parent / "skills" / "pact-memory"
if str(SCRIPTS_PARENT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PARENT))

from scripts.database import get_connection  # noqa: E402

_CLI = SCRIPTS_PARENT / "scripts" / "cli.py"


def _run(*argv):
    """Run the memory CLI as a real subprocess, the way its own tests do."""
    return subprocess.run(
        [sys.executable, str(_CLI), *argv],
        capture_output=True, text=True, timeout=60,
    )


def _envelope(proc):
    """Return the parsed error envelope, failing with the streams on a mis-parse."""
    try:
        return json.loads(proc.stderr)
    except json.JSONDecodeError:
        pytest.fail(
            f"stderr did not parse as JSON, so the envelope contract is broken. "
            f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def _make_store(path):
    """Bring a store into existence at `path` by the one command that may."""
    proc = _run("setup", "--db-path", str(path))
    assert proc.returncode == 0, (
        f"setup could not create the store, so the arm below would measure the "
        f"setup failure rather than its own subject. "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert path.exists(), "setup reported success and left no store behind"
    return path


class TestACallerPathIsOpenedNotCreated:
    def test_an_absent_caller_file_is_refused(self, tmp_path):
        """RED BEFORE THE FIX: the store was built and the caller saw a result.

        The parent directory is present here on purpose. That is what separates
        this arm from the directory half: the earlier guard has nothing to
        refuse, so only a guard on the FILE can fail this call.
        """
        present_dir = tmp_path / "present-dir"
        present_dir.mkdir()
        typo = present_dir / "memroy.db"

        proc = _run("get", "x" * 32, "--db-path", str(typo))

        assert proc.returncode != 0, "a mistyped file name reported success"
        assert _envelope(proc)["error"] == "DB_PATH_NOT_FOUND"
        assert not typo.exists(), (
            "a mistyped file name built its own store, so the typo succeeded "
            "against an empty database instead of failing"
        )

    def test_a_store_that_is_present_still_opens(self, tmp_path):
        """THE OVER-BLOCK GUARD. A refusal that also refuses correct paths is
        worse than the defect. This arm is why the refusal is bounded to
        ABSENT files rather than to caller paths as a class."""
        store = _make_store(tmp_path / "already-there.db")

        proc = _run("list", "--db-path", str(store))

        assert proc.returncode == 0, (
            f"a store that is present was refused. rc={proc.returncode} "
            f"stderr={proc.stderr!r}"
        )

    @pytest.mark.parametrize(
        "name", ["has#hash.db", "has?query.db", "has%pct.db", "has space.db"]
    )
    def test_a_path_holding_shell_or_uri_syntax_still_opens(self, tmp_path, name):
        """THE CARDINAL ARM, AND IT IS NOT OPTIONAL.

        Over-block is the cardinal failure here. A store path may hold `#`, `?`,
        `%` or a space. Each of those is syntax to a URI, and a space is syntax
        to a shell. The path must survive the argument vector AND the existence
        test, so a correct path holding one of them continues to open.
        """
        store = _make_store(tmp_path / name)

        proc = _run("list", "--db-path", str(store))

        assert proc.returncode == 0, (
            f"a correct path holding {name!r} was refused, which turns a guard "
            f"against typos into a guard against good-faith callers. "
            f"stderr={proc.stderr!r}"
        )

    def test_setup_may_bring_a_caller_path_into_existence(self, tmp_path):
        """THE EXEMPTION, AND IT IS THE OTHER HALF OF THE RULE.

        `setup` is the one command allowed to create at a path a caller typed.
        Without this arm the refusal would read as correct while leaving no way
        to make a store at a named location at all.
        """
        store = tmp_path / "brand-new.db"
        assert not store.exists()

        proc = _run("setup", "--db-path", str(store))

        assert proc.returncode == 0, f"setup was refused. stderr={proc.stderr!r}"
        assert store.exists(), "setup reported success and created no store"


class TestTheDirectoryHalfStillHoldsBelowTheBoundary:
    """THE DIRECTORY HALF IS PINNED HERE, AT THE LAYER THE CLI SEAM CANNOT SEE.

    WHY THIS ARM EXISTS, AND IT IS A COVERAGE REPAIR RATHER THAN A NEW RULE.
    `database.get_db_path` creates the parent directory for a DERIVED origin
    only, so a caller path with an absent parent gets no tree built for it. A
    CLI arm used to prove that. It cannot any longer: the boundary refusal now
    fires FIRST for an absent caller path, so the CLI arm passes without ever
    reaching the resolver, and the directory-half guard would ship unpinned.

    A LIBRARY CALLER IS THE ONE ROUTE THAT STILL REACHES IT. That is the same
    route the CLI seam names as its accepted residual, so this arm covers what
    the seam does not.
    """

    def test_a_caller_path_with_an_absent_parent_builds_no_tree(self, tmp_path):
        """MUTANT THAT KILLS THIS ARM: make the `mkdir` in `get_db_path`
        unconditional rather than gated on a derived origin. The directory then
        appears and this arm reddens."""
        absent_parent = tmp_path / "typo-dir"
        target = absent_parent / "x.db"
        assert not absent_parent.exists()

        with pytest.raises(Exception):
            get_connection(target)

        assert not absent_parent.exists(), (
            "a caller path with a mistyped directory had its tree built, so the "
            "typo would succeed against an empty store instead of failing"
        )
        assert not target.exists()


class TestTheCreatingRouteKeepsItsHardening:
    def test_the_derived_route_still_creates(self, tmp_path, monkeypatch):
        """THE RULE THAT OUTRANKS THE REFUSAL. A pathless production caller
        must reach AND create its store.

        This is the arm that fails if the refusal is placed where it cannot
        tell a caller path from a derived one.
        """
        derived_root = tmp_path / "derived" / "pact-memory"
        monkeypatch.setenv("PACT_TEST_MEMORY_DIR", str(derived_root))

        with get_connection() as conn:
            conn.execute("SELECT 1")

        assert (derived_root / "memory.db").exists()

    def test_a_new_derived_store_hardens_itself_and_its_sidecars(
        self, tmp_path, monkeypatch
    ):
        """`is_new` DRIVES THE CREATE AND THE SIDECAR PERMISSIONS.

        A change that suppressed the create would leave a genuinely new store
        with sidecars at the process umask, holding memory content. This arm
        measures the MODE rather than the presence.
        """
        derived_root = tmp_path / "derived" / "pact-memory"
        monkeypatch.setenv("PACT_TEST_MEMORY_DIR", str(derived_root))
        store = derived_root / "memory.db"

        with get_connection() as conn:
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")

            assert stat.S_IMODE(store.stat().st_mode) == 0o600

            hardened = 0
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(store) + suffix)
                if sidecar.exists():
                    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
                    hardened += 1
            # CONTROL: at least one sidecar was present, so the loop above was
            # not vacuous. WAL mode creates them on the first write.
            assert hardened > 0


class TestTheOrderOfTheBoundaryCheck:
    def test_an_absent_path_is_reported_before_malformed_input(self, tmp_path):
        """PINS AN ACCEPTED TRADE. DO NOT READ THIS AS A DESIRED OUTCOME.

        The boundary check runs BEFORE the handler, so a caller who makes TWO
        mistakes at one time, an absent `--db-path` AND malformed JSON, hears
        about the PATH and not about the JSON.

        WHY THAT ORDER SHIPS. To report the JSON first, the check must move
        after input validation, which means placing it inside each handler that
        opens a store. That is the per-caller seam this design rejected, and it
        returns the refusal to a place that cannot tell a person from a library
        caller.

        WHY IT IS TOLERABLE. The message is TRUE rather than misleading. The
        save cannot land anywhere, whatever the JSON says.

        THIS ARM MAKES THE TRADE VISIBLE. Without it the order is untested
        rather than chosen, and a later reader cannot tell which it was. If you
        change the boundary check, change this arm deliberately.
        """
        absent = tmp_path / "not-there.db"

        proc = _run("save", "--db-path", str(absent), "{not valid json")

        assert proc.returncode != 0
        assert _envelope(proc)["error"] == "DB_PATH_NOT_FOUND", (
            "the boundary check no longer precedes handler input validation. "
            "That may be an improvement. Read this docstring and decide, rather "
            "than update the expected string to whatever the code now returns."
        )
        assert not absent.exists()

    def test_an_absent_path_precedes_malformed_input_to_update_too(self, tmp_path):
        """THE SECOND HANDLER OF THE PAIR, SO NEITHER ONE STANDS ALONE.

        `cmd_save` and `cmd_update` are the ONLY two handlers that report an
        error before they open a store. An arm on one of them leaves the other
        free to drift. This arm is the same claim on `cmd_update`.
        """
        absent = tmp_path / "not-there.db"

        proc = _run(
            "update", "--db-path", str(absent), "a" * 32, "{not valid json"
        )

        assert proc.returncode != 0
        assert _envelope(proc)["error"] == "DB_PATH_NOT_FOUND"
        assert not absent.exists()

    @pytest.mark.parametrize(
        "argv_tail",
        [
            ("save", "{not valid json"),
            ("update", "a" * 32, "{not valid json"),
        ],
        ids=["save", "update"],
    )
    def test_with_the_store_present_the_handler_reports_the_input(
        self, memory_store, argv_tail
    ):
        """THE POSITIVE CONTROL, AND THE TWO ARMS ABOVE ARE VACUOUS WITHOUT IT.

        The arms above asserts that the PATH is named first. Each of them passes
        against a build that DELETED the JSON check, because a deleted check also
        never reports `INVALID_JSON`. This arm removes that reading: with the
        store PRESENT, the boundary has nothing to refuse, so the handler check
        runs and names the input.

        READ THE THREE TOGETHER. They say the boundary check CHANGES THE ORDER of
        two live checks. They do not say it suppresses one.
        """
        command, *rest = argv_tail
        store = memory_store("present.db")

        proc = _run(command, "--db-path", str(store), *rest)

        assert proc.returncode != 0
        assert _envelope(proc)["error"] == "INVALID_JSON", (
            "with the store present the handler no longer reports the malformed "
            "input, so the ordering arms above prove nothing about ordering"
        )
