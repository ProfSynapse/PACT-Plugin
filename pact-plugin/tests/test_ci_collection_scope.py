"""The CI test invocation must not be narrower than the test corpus on disk.

WHAT THIS EXISTS TO STOP, stated as the defect rather than the rule
-------------------------------------------------------------------
Test modules that live beside the skill they guard — rather than under
``tests/`` — are invisible to a path-scoped pytest invocation. A run scoped to
``tests/`` collects them nowhere, passes, and reports a five-digit total that
reads as the whole suite. Nothing in the output distinguishes a complete run
from one that silently dropped a directory: the count is the only tell, and no
reader has a reference value for it. An edit to those skills was then certified
by a gate that never loaded their guards.

The invocation itself is already correct — the workflow runs a bare
``python -m pytest`` from ``pact-plugin/``, which collects whatever is there.
This module is the half that keeps it correct. A comment saying "do not add
path arguments" is not a test, and the scope can re-narrow silently through
either of two doors:

  1. a path argument returning to the pytest command line;
  2. a ``testpaths`` entry in pytest config, which takes effect precisely
     BECAUSE the command line has no path arguments to override it.

MEASURED, so door 2 is not taken on faith (both restored afterward):

  * ``pact-plugin/pytest.ini`` with ``testpaths = tests`` -> collection drops
    13822 to 13774. That is the same 48-module gap, re-opened without touching
    the command line at all.
  * The repository-root ``pyproject.toml`` with the same key -> collection
    stays 13822. It does NOT narrow: rootdir stays at the repository root, so
    the entry resolves to a directory that does not exist and pytest ignores
    it in silence.

The second result is why the config check below scans a FAMILY of filenames in
both directories rather than the one config file that exists today. That file
is the repository-root ``pyproject.toml`` — which is the single placement where
the door does not open. A check scoped to the config it can see would be a
check aimed at the only harmless location.

WHY NO ASSERTION HERE COUNTS ANYTHING
-------------------------------------
A pinned collected-test total goes red on every legitimate test addition, which
trains its readers to bump the number rather than investigate — so the guard
that cried wolf is retired right before the run where it was right. These
assertions are directional on SCOPE: they fire when a test root becomes
unreachable, and say nothing about how many tests live in it.

PARSE FAILURE AND DRIFT ARE REPORTED SEPARATELY, ALWAYS
-------------------------------------------------------
Every parse below asserts an anchor with ground truth INDEPENDENT of the parse,
before the comparison it feeds, and with a distinct message. An absence-shaped
assertion is satisfied trivially by a parser that read nothing — so "no path
arguments found" from a workflow this module failed to parse would be a false
green of exactly the genus the whole file is about. Convention followed from
``test_memory_init.py``, which parses the same workflow for its install line.
"""

import re
from pathlib import Path

import pytest

# The two collection roots pytest resolves from `pact-plugin/`, and the pytest
# config filenames that can carry a `testpaths` entry. Both directories are
# scanned: rootdir resolution depends on which one holds a config, and that in
# turn decides whether a `testpaths` entry resolves to a real directory.
_PYTEST_CONFIG_NAMES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


def _plugin_root():
    """The `pact-plugin/` directory — this file's grandparent."""
    return Path(__file__).resolve().parents[1]


def _source_repo_root():
    """Repo root by a POSITIVE marker, or None when this is not a checkout.

    Deliberately NOT "did I find the workflow file?". "I cannot find it" and
    "it is wrong" must never produce the same outcome — that equivalence is the
    silent-narrowing defect this module exists to prevent. The skip decision is
    made on an INDEPENDENT marker, which leaves the workflow's own absence free
    to be a FAILURE. Marker matches the convention in test_memory_init.py.
    """
    for base in Path(__file__).resolve().parents:
        if (base / ".claude-plugin" / "marketplace.json").exists():
            return base
    return None


def _require_checkout():
    """Return (repo_root, workflow_text), or skip when outside a source checkout."""
    root = _source_repo_root()
    if root is None:
        pytest.skip(
            "SKIPPED, NOT PASSED — no .claude-plugin/marketplace.json above "
            f"{Path(__file__).resolve()}, so this is not a PACT source checkout. "
            "The expected case is an INSTALLED PLUGIN CACHE, which has no "
            ".github/ tree by design. This skip is NO INFORMATION about the CI "
            "collection scope — never read it as a pass."
        )

    # INSIDE a checkout the workflow is required, so its absence is a FAILURE.
    workflow = root / ".github" / "workflows" / "tests.yml"
    assert workflow.exists(), (
        f"source checkout detected at {root} (marketplace.json present) but "
        f"{workflow} is missing. The collection-scope guard cannot run. This is "
        f"a FAILURE, not a skip: inside a checkout the workflow is required."
    )
    return root, workflow.read_text(encoding="utf-8")


def _pytest_run_commands(workflow_text):
    """Every non-comment `run:` command in the workflow that invokes pytest.

    Comment lines are dropped FIRST and that is load-bearing, not tidiness: the
    workflow discusses `python -m pytest` in roughly ten comment lines — several
    of them quoting the narrow `pytest tests/` form this module exists to keep
    out. A parser that read comments would find the forbidden shape in prose
    that argues against it, and report the file as already broken.

    The `pip install` line names pytest as a package rather than running it, so
    it is excluded on the same principle: it is not an invocation.
    """
    found = []
    for raw in workflow_text.splitlines():
        line = raw.strip()
        if line.startswith("#") or not line.startswith("run:"):
            continue
        command = line[len("run:"):].strip()
        if re.search(r"\bpytest\b", command) and "pip install" not in command:
            found.append(command)
    return found


def _the_pytest_command(workflow_text):
    """The single CI pytest invocation, with its parse anchored before use.

    NON-VACUITY, with ground truth independent of the parse: this assertion is
    EXECUTING under pytest, and it runs in CI, so CI demonstrably invokes
    pytest. A correct parse of the workflow therefore cannot yield nothing. If
    it does, the parser is wrong — not the workflow — and that must be reported
    as a parse failure rather than as a clean scope check over an empty read.
    """
    commands = _pytest_run_commands(workflow_text)
    assert commands, (
        "PARSE FAILURE, not a scope regression: no `run:` line invoking pytest "
        "could be read from the workflow, yet this assertion is running under "
        "pytest in that same workflow, so one exists. The parser models a "
        "single-line `run: <command>`; a refactor to a block scalar (`run: |`) "
        "or a composite action defeats it. RE-POINT THE PARSER — do NOT relax "
        "the assertions below, which pass vacuously over an empty command list."
    )
    assert len(commands) == 1, (
        f"PARSE AMBIGUITY, not a scope regression: {len(commands)} pytest "
        f"invocations were read from the workflow ({commands}). Every check "
        f"below reasons about THE CI invocation, singular. If the workflow "
        f"genuinely gained a second pytest step, these checks must be re-pointed "
        f"to cover both — a guard that silently examines only the first one is "
        f"the narrowing defect wearing a different hat."
    )
    return commands[0]


def _path_operands(command, working_dir):
    """Path operands in a pytest command — non-flag words naming a real path.

    Models pytest's argv: operands are the non-flag words after the `pytest`
    token. The extra requirement that the word NAME AN EXISTING PATH is what
    keeps a separated flag value (`--maxfail 3`, `-p no:cacheprovider`) from
    reading as a path and producing a false red. It cannot fail open in the
    direction that matters: a path argument that does not exist collects
    nothing, so it is not a silent narrowing — it is a broken CI run.
    """
    words = command.split()
    if "pytest" not in words:
        return None
    after = words[words.index("pytest") + 1:]
    return [w for w in after if not w.startswith("-") and (working_dir / w).exists()]


def _discovered_test_roots(plugin_root):
    """First path component of every test module under `pact-plugin/`.

    The nested-worktree exclusion is tested on the RELATIVE path, and that is
    the whole point rather than a detail: a checkout INSIDE a worktree has
    `.worktrees` in the absolute path of every file it contains, so an absolute
    test excludes the entire tree and returns an empty set. Empty is the one
    result this scan must never return quietly — the comparison it feeds is a
    set difference, which is satisfied trivially by nothing. Only a worktree
    nested BELOW pact-plugin/ is a real duplicate worth skipping.
    """
    roots = set()
    for path in plugin_root.rglob("test_*.py"):
        relative = path.relative_to(plugin_root)
        if ".worktrees" in relative.parts:
            continue
        roots.add(relative.parts[0])
    return roots


class TestCiInvocationCollectsTheWholeCorpus:
    """The CI pytest step must reach every test root, through either door."""

    def test_no_test_root_is_unreachable_from_the_ci_invocation(self):
        """Every test root on disk must be collected by the CI invocation.

        Directional on purpose: this fires when a root becomes UNREACHABLE,
        which is the drift that actually happens. It permits path arguments
        that name every root, and it is indifferent to how many tests exist —
        so it survives test additions without ever needing a number bumped.
        """
        _, workflow_text = _require_checkout()
        plugin_root = _plugin_root()
        command = _the_pytest_command(workflow_text)

        discovered = _discovered_test_roots(plugin_root)

        # NON-VACUITY, ground truth independent of the scan: this file is
        # `tests/test_ci_collection_scope.py` and it is executing, so `tests`
        # is a test root whether or not the scan can see it.
        assert "tests" in discovered, (
            f"SCAN FAILURE, not a scope regression: the test-root scan of "
            f"{plugin_root} returned {sorted(discovered)}, which omits 'tests' "
            f"— yet this module lives in tests/ and is running. The scan is "
            f"therefore broken, and the comparison below would pass over a set "
            f"that does not describe the tree."
        )

        # The scan must be able to see PAST tests/, or the comparison is
        # trivially satisfied and this guard is dead while green.
        assert discovered - {"tests"}, (
            "THIS GUARD IS NOW VACUOUS — read the message before changing "
            "anything. Every test module under pact-plugin/ lives in tests/, so "
            "no path-scoped invocation could drop one and this comparison "
            "cannot fail. That is a legitimate state: it is what moving the "
            "skill-adjacent test modules into tests/ would produce, which was "
            "one of the proposed fixes. If that move was deliberate, RETIRE "
            "this test or re-point it at the new structure. Do not delete this "
            "assertion and leave the comparison standing — a guard that cannot "
            "fail is worse than none, because it is counted as coverage."
        )

        operands = _path_operands(command, plugin_root)
        assert operands is not None, (
            f"PARSE FAILURE, not a scope regression: no `pytest` token in the "
            f"CI command {command!r}, so its path operands cannot be read."
        )

        # No operands: a bare pytest collects the whole working directory, so
        # every root is reachable. Otherwise only the named roots are.
        covered = discovered if not operands else {Path(op).parts[0] for op in operands}
        missing = sorted(discovered - covered)
        assert not missing, (
            f"CI DOES NOT COLLECT {missing}. Test modules live under "
            f"{missing} and would pass locally while NEVER RUNNING IN CI — the "
            f"run would be green over a silently narrowed corpus, and nothing "
            f"in its output would say so. The CI command is {command!r}. Either "
            f"drop the path arguments (a bare `python -m pytest` collects "
            f"whatever is there, so new roots are picked up automatically) or "
            f"name every root above."
        )

    def test_the_ci_invocation_carries_no_path_arguments(self):
        """The pytest step must carry no path arguments at all.

        Stricter than the reachability check above, and deliberately so: a bare
        invocation is SELF-MAINTAINING, because a test root added later is
        collected without anyone remembering this decision. An explicit list
        that names every root passes the check above while re-introducing the
        requirement to maintain it — which is the discipline that already
        failed once.

        These two checks overlap today: with no path arguments, the reachability
        comparison cannot fail. They are both kept because they fail for
        DIFFERENT reasons and survive different futures — if a path argument
        ever becomes genuinely necessary, this check is the one to revisit, and
        the reachability check above is what must keep holding.
        """
        _, workflow_text = _require_checkout()
        command = _the_pytest_command(workflow_text)

        operands = _path_operands(command, _plugin_root())
        assert operands is not None, (
            f"PARSE FAILURE, not a scope regression: no `pytest` token in the "
            f"CI command {command!r}, so its path operands cannot be read."
        )
        assert not operands, (
            f"THE CI PYTEST STEP RE-ACQUIRED PATH ARGUMENTS: {operands}. A path "
            f"argument collects ONLY what it names, so every test directory not "
            f"listed is dropped SILENTLY — an edit is then certified by a gate "
            f"that never ran the tests written for it. The command is "
            f"{command!r}. Remove the path arguments; a bare `python -m pytest` "
            f"from pact-plugin/ collects the whole tree."
        )

    def test_no_pytest_config_declares_testpaths(self):
        """`testpaths` re-narrows collection without touching the command line.

        The second door, and the one a command-line check cannot see. It is
        armed BY the fix: `testpaths` applies only when no path arguments are
        given, so removing them is what gives such an entry its effect.

        Measured (see the module docstring): a `pytest.ini` in pact-plugin/
        declaring `testpaths = tests` drops collection by exactly the gap this
        module exists to keep closed.
        """
        repo_root, _ = _require_checkout()
        plugin_root = _plugin_root()

        checked = []
        declaring = []
        for directory in (repo_root, plugin_root):
            for name in _PYTEST_CONFIG_NAMES:
                config = directory / name
                if not config.exists():
                    continue
                checked.append(config)
                body = config.read_text(encoding="utf-8")
                # Ignore commented-out entries: the workflow's own prose warns
                # against testpaths, and a doc line is not a declaration.
                for raw in body.splitlines():
                    line = raw.strip()
                    if line.startswith("#") or line.startswith(";"):
                        continue
                    if re.match(r"^testpaths\s*=", line):
                        declaring.append(f"{config}: {line}")

        assert not declaring, (
            f"A PYTEST CONFIG DECLARES testpaths: {declaring}. That re-narrows "
            f"collection through a route the CI command line does not show — "
            f"the command stays a bare `python -m pytest` and looks correct "
            f"while the corpus shrinks. Remove the entry. If a narrower default "
            f"is genuinely wanted for local runs, it must not be the thing CI "
            f"inherits. (Config files examined: "
            f"{[str(c) for c in checked] or 'none'}.)"
        )
