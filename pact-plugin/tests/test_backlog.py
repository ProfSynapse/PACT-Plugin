"""Substantive coverage for the cross-session backlog.

Five of these cases do not occur naturally and are constructed deliberately.
Each corresponds to a defect found in this feature by running something rather
than by reading it, and none would be sampled by an ordinary fixture:

  worktree containment   a session inside a worktree records the worktree path
                         while the writer stores the main root, so equality
                         misses and only containment matches
  symlink normalisation  `/var` resolves to `/private/var` on macOS, making
                         divergence the default under any temporary directory
  corrupt sibling        one flat store shared by every project, so another
                         project's unreadable file must not suppress this
                         project's healthy block
  repair round trip      the moved-aside name once ended `.json` while the read
                         path globs `*.json`, so the corrupt file was read
                         straight back and the loud state survived its repair
  partial-success ref    `gh api graphql` exits non-zero while carrying every
                         field that did resolve, so a return-code gate discards
                         good data and reports a blanket outage

Every assertion here is paired with the condition that turns it red. Where a
naive implementation would pass an assertion for the wrong reason, the test
states the discriminating fact explicitly rather than trusting the fixture to
be adversarial by luck.

Mutation record
---------------
This record quotes real assertions, so mutating this file by bare substring can
hit the prose copy instead of the code. Anchor on the `assert ` prefix, or work
from the AST.

Each arm was verified by mutating production source and confirming the NAMED
test reddens: 31 mutations, 31 killed, run against an unmutated green baseline
with the tree restored byte-identical after every arm. Naming which test kills
which mutation is what makes this a coverage claim rather than a survival
count, since one over-broad assertion can kill many mutants while pinning
nothing in particular.

One mutation SURVIVED on the way to that number, and the fixture it exposed is
recorded because the same shape will recur. Flagging a ref-less item survived
against a fixture whose items were ALL ref-less: `_ref_flags` returns early
when no item carries a ref, so the assertion was reached without the per-item
skip ever executing. A mixed fixture — one ref-carrying item, one without —
forces the loop and kills it.

Fixing that survivor produced a second lesson worth as much as the first. The
mixed fixture initially gave both items the same title, and flags are labelled
by TITLE rather than by id, so `len(flags) == 1` passed while the membership
assertion could not tell which item had been flagged. A COUNT IS NOT A
MEMBERSHIP CHECK: it is satisfied by the right number of the wrong things. Any
arm here asserting a flag count also asserts which item the flag names, and
fixtures give items distinct titles for that reason.

The two import-closure tests carry their own counter-test in this file rather
than a row in this record.

The harness itself is deliberately not committed: an executable nothing runs
in CI is exactly the check that stops firing while still looking like
coverage. This list is the checkable claim, and it can be rebuilt from in an
afternoon.

  MUTATION (in hooks/shared/ or hooks/session_init.py)  ->  TEST THAT KILLS IT

  containment becomes equality          test_worktree_session_finds_the_main_root_backlog
  containment becomes a string prefix   test_a_sibling_project_is_not_matched_by_containment
  `.resolve()` dropped                  test_containment_resolves_both_sides_across_a_symlink
  an unreadable file aborts the scan    test_corrupt_sibling_sorting_first_does_not_suppress_the_block
  the two channels made symmetric       test_corrupt_sibling_splits_the_two_channels_asymmetrically
  the read path repairs what it finds   test_the_read_path_writes_nothing_when_it_reports_corruption
  repair keeps the `.json` suffix       test_repair_then_read_round_trip_clears_the_loud_state
  repair overwrites the bytes           test_repair_preserves_the_corrupt_bytes
  tracker gated on the return code      test_partial_success_yields_per_ref_unverifiable
  tracker timeout dropped               test_every_tracker_call_carries_an_explicit_timeout
  unreachable tracker reads as open     test_an_unreachable_tracker_is_unverifiable_not_a_clean_pass
  absent tracker reads as open          test_no_tracker_configured_is_supported_end_to_end
  a ref-less item gets flagged          test_no_tracker_configured_is_supported_end_to_end
  note limit not enforced               test_an_over_long_note_is_rejected_and_nothing_is_written
  note limit off by one                 test_a_note_at_the_limit_is_accepted
  memory cap not enforced               test_a_sixth_memory_id_is_rejected_rather_than_dropped
  absolute plan path accepted           test_an_absolute_plan_path_is_rejected_at_write_time
  item id anchored on `$`               test_an_item_id_with_a_trailing_newline_is_rejected
  tie-break made alphabetical           test_a_rename_prefers_the_newer_stamp_and_reports_the_duplication
  filename used as a fallback match     test_nothing_matches_on_the_filename
  an absent store made loud             test_an_absent_store_is_silent
  a no-match state reads as empty       test_a_non_empty_store_with_no_match_is_loud_not_silent
  a relative project dir accepted       test_a_relative_project_dir_is_loud
  totality broken, exception escapes    test_session_block_never_raises_on_a_hostile_store
  call site emits nothing               test_session_init_emits_the_block_for_a_worktree_session
  block prepended, marker displaced     test_session_init_emits_the_block_for_a_worktree_session
  store no longer home-pinned           test_session_init_emits_the_block_for_a_worktree_session
  source gate deleted                   test_the_alert_channel_is_gated_on_the_launch_source
  source gate stuck off                 test_the_alert_channel_is_gated_on_the_launch_source
  `main` calls `sys.exit`               test_main_returns_an_exit_code_and_calls_no_sys_exit
  a `bin/pact-backlog` entry appears    test_no_bin_executable_was_added

The source-gate pair is the reason this record exists. Twenty-four arms all
killed their mutations while the launch-source gate sat entirely unpinned:
deleting `source in ("startup", "resume")` from the call site left the whole
file green. A kill count measures the mutations someone thought of, so it
cannot reveal a property nobody named. Mutation testing proves the arms
present are not vacuous; only enumerating the spec's properties says which
arms are missing, and neither substitutes for the other.
"""
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

from shared import backlog
from shared import backlog_store

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
SHARED_DIR = HOOKS_DIR / "shared"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _backlog(project_path, items=None, project="demo", updated="2026-09-01T00:00:00Z"):
    """The smallest valid file shape. Callers override only what they test."""
    return {
        "version": 1,
        "project": project,
        "project_path": str(project_path),
        "updated": updated,
        "items": items if items is not None else [_item()],
    }


def _item(item_id="a1b2", title="An item", status="planned", rank=1, **fields):
    item = {
        "id": item_id,
        "title": title,
        "status": status,
        "rank": rank,
        "blocked_by": [],
        "batch_with": [],
        "ref": None,
        "plan": None,
        "memory": [],
        "note": "",
        "added": "2026-09-01",
        "touched": "2026-09-01",
    }
    item.update(fields)
    return item


def _write(directory, name, payload):
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# constructed case 1 — the worktree
# --------------------------------------------------------------------------
def test_worktree_session_finds_the_main_root_backlog(tmp_path):
    """A session inside a worktree resolves the backlog stored at the main root.

    RED WHEN the match rule is equality rather than containment. The assertion
    on non-equality is what keeps this honest: without it a fixture whose two
    paths happened to coincide would pass under either rule and certify
    nothing.
    """
    main_root = tmp_path / "project"
    worktree = main_root / ".worktrees" / "feat-x"
    worktree.mkdir(parents=True)
    store = tmp_path / "store"
    _write(store, "demo.json", _backlog(main_root))

    # The discriminating fact: equality CANNOT match these two.
    assert str(worktree) != str(main_root)

    match, unreadable = backlog_store.find_for(str(worktree), store)
    assert match is not None, "containment failed to reach the main-root backlog"
    assert match.name == "demo.json"
    assert unreadable == []


def test_a_sibling_project_is_not_matched_by_containment(tmp_path):
    """Containment must not widen into matching an unrelated project.

    RED WHEN containment is implemented as a substring or prefix test on the
    raw string: `/tmp/project-other` starts with `/tmp/project` as text, and
    only a parts-wise comparison rejects it.
    """
    store = tmp_path / "store"
    _write(store, "other.json", _backlog(tmp_path / "project"))
    unrelated = tmp_path / "project-other"
    unrelated.mkdir()

    assert str(unrelated).startswith(str(tmp_path / "project"))  # textually a prefix
    match, _ = backlog_store.find_for(str(unrelated), store)
    assert match is None, "a textual prefix was accepted as containment"


# --------------------------------------------------------------------------
# constructed case 2 — symlink normalisation
# --------------------------------------------------------------------------
def test_containment_resolves_both_sides_across_a_symlink(tmp_path):
    """A stored resolved path matches an unresolved session directory.

    On macOS `tempfile` hands out `/var/...` whose resolved form is
    `/private/var/...`, so this divergence is the DEFAULT under any temporary
    directory rather than an exotic case. RED WHEN either side skips
    `.resolve()`, since the two spellings then compare unequal.
    """
    real = tmp_path / "real_project"
    real.mkdir()
    link = tmp_path / "link_to_project"
    link.symlink_to(real, target_is_directory=True)

    store = tmp_path / "store"
    # Writer stores the RESOLVED form; the session arrives by the symlink.
    _write(store, "demo.json", _backlog(real.resolve()))

    # The discriminating fact: the two spellings are not equal as strings.
    assert str(link) != str(real.resolve())

    match, _ = backlog_store.find_for(str(link), store)
    assert match is not None, "a symlinked project directory failed to match"


# --------------------------------------------------------------------------
# constructed case 3 — the corrupt sibling
# --------------------------------------------------------------------------
def test_corrupt_sibling_sorting_first_does_not_suppress_the_block(tmp_path):
    """Another project's unreadable file must not suppress this project's block.

    The sibling is named so it sorts FIRST, which is the ordering that used to
    abort the scan before any healthy file was reached. RED WHEN the scan
    raises or returns early on the first unreadable entry.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(store, "0000-other-project.json", "{ not json at all")
    _write(store, "demo.json", _backlog(project))

    # The discriminating fact: the corrupt file is reached first.
    assert sorted(p.name for p in store.glob("*.json"))[0] == "0000-other-project.json"

    notice = backlog_store.session_block(str(project), backlog_dir=store)
    assert "An item" in notice.context, "a corrupt sibling suppressed a healthy block"


def test_corrupt_sibling_splits_the_two_channels_asymmetrically(tmp_path):
    """`context` carries block PLUS note; `alert` carries the note ONLY.

    RED WHEN the two channels are symmetric. Checking only that `alert` is
    non-empty would stay green under a symmetric implementation, so the block's
    ABSENCE from `alert` is asserted positively — that absence is the whole
    claim.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(store, "0000-other-project.json", "{ not json at all")
    _write(store, "demo.json", _backlog(project))

    notice = backlog_store.session_block(str(project), backlog_dir=store)

    assert "An item" in notice.context          # block reaches context
    assert "could not read" in notice.context   # note reaches context too
    assert "could not read" in notice.alert     # note reaches the user
    assert "An item" not in notice.alert, "the block leaked into the alert channel"


def test_the_read_path_writes_nothing_when_it_reports_corruption(tmp_path):
    """Reporting corruption must not rename, rebuild or delete anything.

    RED WHEN the read path repairs what it finds. The read path runs at every
    session start, so a rename there would leave one moved-aside copy per
    session.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(store, "demo.json", "{ not json at all")
    before = {p.name: p.read_bytes() for p in store.iterdir()}

    notice = backlog_store.session_block(str(project), backlog_dir=store)

    assert notice.alert, "corruption was not reported"
    after = {p.name: p.read_bytes() for p in store.iterdir()}
    assert after == before, "the read path modified the store"


# --------------------------------------------------------------------------
# constructed case 4 — repair, then read
# --------------------------------------------------------------------------
def test_repair_then_read_round_trip_clears_the_loud_state(tmp_path):
    """The round trip, not `repair()` alone, is the instrument.

    `repair()` in isolation reports success under either naming scheme. The
    defect it hid was that the moved-aside name ended `.json` while the read
    path globs `*.json`, so the corrupt file was picked straight back up and
    the loud state SURVIVED ITS OWN REPAIR. RED WHEN the moved-aside name is
    still matched by that glob.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    corrupt = _write(store, "demo.json", "{ not json at all")

    loud = backlog_store.session_block(str(project), backlog_dir=store)
    assert loud.alert, "the corrupt file was not loud to begin with"

    aside, message = backlog.repair(corrupt)
    assert aside.exists() and not corrupt.exists()
    assert str(aside) in message

    # The discriminating fact: the moved-aside file is NOT in the read glob.
    assert aside not in set(store.glob("*.json"))

    _write(store, "demo.json", _backlog(project))
    rebuilt = backlog_store.session_block(str(project), backlog_dir=store)

    assert "An item" in rebuilt.context, "the rebuilt backlog did not render"
    assert rebuilt.alert == "", "the loud state survived its own repair"


def test_repair_preserves_the_corrupt_bytes(tmp_path):
    """Repair renames; it never overwrites and never deletes.

    RED WHEN repair truncates or rewrites the file. The moved-aside copy is
    what makes a wrong rebuild recoverable.
    """
    store = tmp_path / "store"
    original = "{ not json at all"
    corrupt = _write(store, "demo.json", original)

    aside, _ = backlog.repair(corrupt)
    assert aside.read_text(encoding="utf-8") == original


# --------------------------------------------------------------------------
# constructed case 5 — the partial-success tracker envelope
# --------------------------------------------------------------------------
def _partial_success_envelope(aliases):
    """The shape `gh api graphql` returns when SOME refs resolve.

    Reproduced from a live capture against a real repository: a `data` block
    carrying every field that resolved, a `null` for the one that did not, and
    a sibling `errors` array naming it by path. The alias keys are rebuilt to
    match whatever scheme the caller generates, since the alias names are an
    implementation detail while the envelope's SHAPE is what is under test.
    """
    good, dead = aliases[:-1], aliases[-1]
    repository = {alias: {"state": "OPEN"} for alias in good}
    repository[dead] = None
    return json.dumps(
        {
            "data": {"repository": repository},
            "errors": [
                {
                    "type": "NOT_FOUND",
                    "path": ["repository", dead],
                    "message": "Could not resolve to an Issue with the number of 999999.",
                }
            ],
        }
    )


def test_partial_success_yields_per_ref_unverifiable(monkeypatch):
    """Good resolutions survive a NON-ZERO exit; only the dead ref is flagged.

    RED WHEN any code path gates on the return code. `gh` exits 1 here while
    stdout carries every field that resolved, so a return-code gate discards
    the working refs and reports a blanket outage where the criteria require
    per-ref `unverifiable`.
    """
    refs = ["#1036", "#1544", "#999999"]

    def fake_run(command, **kwargs):
        # Read the aliases back out of the query the module built, so this
        # fake follows the implementation's naming instead of restating it.
        query = next(arg for arg in command if arg.startswith("query="))
        ordered = sorted(set(re.findall(r"\br\d+\b(?=:)", query)))
        assert len(ordered) == len(refs), f"unexpected alias set {ordered}"
        return subprocess.CompletedProcess(
            command, 1, stdout=_partial_success_envelope(ordered), stderr="gh: NOT_FOUND"
        )

    monkeypatch.setattr(backlog, "_repo_slug", lambda: ("owner", "repo"))
    monkeypatch.setattr(subprocess, "run", fake_run)

    outcome = backlog.resolve_refs(refs)

    states = {ref: outcome[ref]["state"] for ref in refs}
    unverifiable = [ref for ref, state in states.items() if state == "unverifiable"]
    assert len(unverifiable) == 1, f"expected exactly one unverifiable ref, got {states}"
    assert states["#999999"] == "unverifiable"
    assert states["#1036"] == "open"
    assert states["#1544"] == "open"


def test_every_tracker_call_carries_an_explicit_timeout(monkeypatch):
    """RED WHEN the timeout is dropped: `gh` runs until killed against an
    unreachable host, so an absent timeout hangs the command indefinitely."""
    captured = {}

    def fake_run(command, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(backlog, "_repo_slug", lambda: ("owner", "repo"))
    monkeypatch.setattr(subprocess, "run", fake_run)
    backlog.resolve_refs(["#1"])

    assert captured["timeout"] == 5, f"tracker timeout was {captured['timeout']!r}"


def test_an_unreachable_tracker_is_unverifiable_not_a_clean_pass(monkeypatch):
    """RED WHEN a timeout is swallowed into a resolved state."""

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(backlog, "_repo_slug", lambda: ("owner", "repo"))
    monkeypatch.setattr(subprocess, "run", fake_run)

    outcome = backlog.resolve_refs(["#1"])
    assert outcome["#1"]["state"] == "unverifiable"


def test_no_tracker_configured_is_supported_end_to_end(monkeypatch):
    """An item with no `ref` is never flagged, and a ref-carrying item under no
    tracker reports unverifiable rather than a clean pass.

    RED WHEN a ref-less item is flagged, which would make it second-class, or
    when an unresolvable ref passes silently.
    """
    monkeypatch.setattr(backlog, "_repo_slug", lambda: None)

    outcome = backlog.resolve_refs(["#1"])
    assert outcome["#1"]["state"] == "unverifiable"

    # A MIXED backlog, deliberately: with no ref-carrying item at all,
    # `_ref_flags` returns early and the per-item skip never executes, so a
    # ref-less-only fixture asserts an empty list by a route that says nothing
    # about how a ref-less item is treated. One of each forces the loop.
    # Distinct TITLES, because flags are labelled by title rather than by id:
    # two items sharing a title would make the count assertion pass while the
    # membership assertion could not tell which item had been flagged.
    data = _backlog(
        "/tmp/project",
        items=[
            _item(item_id="a1b2", title="REFLESS ITEM", ref=None),
            _item(item_id="c3d4", title="REFFED ITEM", ref="#1"),
        ],
    )
    flags = backlog._ref_flags(data["items"])

    assert len(flags) == 1, f"expected only the ref-carrying item flagged: {flags}"
    assert "REFFED ITEM" in flags[0], "the wrong item was flagged"
    assert "REFLESS ITEM" not in flags[0], "the ref-less item was flagged"


# --------------------------------------------------------------------------
# Y3 — the import closure, measured in a FRESH interpreter
# --------------------------------------------------------------------------
_PROBE = """
import json, sys, types, importlib.util
from pathlib import Path
shared_dir, target = Path(sys.argv[1]), Path(sys.argv[2])
# A stub package carrying only __path__: relative imports resolve against the
# real directory while the real __init__.py never executes. Loading the module
# by file path alone cannot work, because the module's own imports are
# relative and have no package to resolve against.
pkg = types.ModuleType("shared")
pkg.__path__ = [str(shared_dir)]
sys.modules["shared"] = pkg
spec = importlib.util.spec_from_file_location("shared." + target.stem, target)
mod = importlib.util.module_from_spec(spec)
sys.modules["shared." + target.stem] = mod
spec.loader.exec_module(mod)
print(json.dumps(sorted(sys.modules)))
"""

_FORBIDDEN = ("subprocess", "socket", "http", "urllib.request")


def _closure_of(target):
    """Modules present after loading `target` in a CLEAN interpreter.

    A fresh process is required rather than a `sys.modules` delta taken in
    this one. Under pytest `subprocess` is ALREADY imported, so a delta never
    contains it — including for a module that imports it directly. The
    counter-test in this file demonstrates exactly that.
    """
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(SHARED_DIR), str(target)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"probe failed: {result.stderr}"
    return set(json.loads(result.stdout))


def test_backlog_store_import_closure_excludes_subprocess_and_network():
    """The read side pulls no subprocess and no network module.

    RED WHEN `backlog_store.py` gains such an import, directly or through
    anything it imports. The package-level form of this test is defeated:
    `shared/__init__.py` imports `gh_helpers`, so `from shared import
    backlog_store` pulls `subprocess` regardless of what this module does, and
    an allowlist admitting `subprocess` would then pass a future direct import
    here.
    """
    closure = _closure_of(SHARED_DIR / "backlog_store.py")
    present = [name for name in _FORBIDDEN if name in closure]
    assert present == [], f"read path pulled {present}"
    # The stub resolved the REAL paths module rather than a namespace shim.
    assert "shared.paths" in closure


def test_the_import_closure_probe_detects_a_forbidden_import(tmp_path):
    """Counter-test: the probe must turn RED on a module that DOES import
    subprocess, and the in-process delta it replaces must NOT.

    Without this arm, a probe that silently measured nothing would report a
    clean closure forever. It also pins the reason a fresh interpreter is
    required: the delta arm is green for the mutant, which is the vacuity the
    subprocess form exists to escape.
    """
    mutant = tmp_path / "mutant.py"
    mutant.write_text(
        "from __future__ import annotations\n"
        "import subprocess\n"
        "from .paths import get_backlog_dir\n",
        encoding="utf-8",
    )
    # The probe imports `.paths` relatively, so the mutant needs it alongside.
    (tmp_path / "paths.py").write_text(
        (SHARED_DIR / "paths.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(tmp_path), str(mutant)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"probe failed on the mutant: {result.stderr}"
    assert "subprocess" in set(json.loads(result.stdout)), (
        "the probe cannot see a forbidden import and certifies nothing"
    )

    # The arm this replaces: an in-process delta is blind to the same mutant,
    # because pytest has already imported subprocess.
    assert "subprocess" in sys.modules
    before = set(sys.modules)
    pkg = types.ModuleType("mutantpkg")
    pkg.__path__ = [str(tmp_path)]
    sys.modules["mutantpkg"] = pkg
    spec = importlib.util.spec_from_file_location("mutantpkg.mutant", mutant)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutantpkg.mutant"] = module
    spec.loader.exec_module(module)
    delta = set(sys.modules) - before
    assert "subprocess" not in delta, (
        "the in-process delta unexpectedly saw the import; the probe's "
        "justification for spawning a fresh interpreter needs rechecking"
    )


# --------------------------------------------------------------------------
# validation: rejected, never truncated or silently dropped
# --------------------------------------------------------------------------
def test_an_over_long_note_is_rejected_and_nothing_is_written(tmp_path):
    """RED WHEN the writer truncates. Truncation would lose the intent the
    note exists to carry, so the file must stay absent rather than gain a
    shortened note."""
    path = tmp_path / "demo.json"
    data = _backlog(tmp_path, items=[_item(note="x" * 201)])

    problems = backlog.save(data, path)

    assert problems, "a 201-character note was accepted"
    assert "201" in problems[0] and "200" in problems[0]
    assert not path.exists(), "a rejected backlog was written anyway"


def test_a_note_at_the_limit_is_accepted(tmp_path):
    """The boundary case. RED WHEN the comparison is off by one and rejects a
    note of exactly the permitted length."""
    path = tmp_path / "demo.json"
    assert backlog.save(_backlog(tmp_path, items=[_item(note="x" * 200)]), path) == []
    assert path.exists()


def test_a_sixth_memory_id_is_rejected_rather_than_dropped(tmp_path):
    """RED WHEN the writer keeps five and discards the sixth silently."""
    path = tmp_path / "demo.json"
    ids = [f"{index:032x}" for index in range(6)]

    problems = backlog.save(_backlog(tmp_path, items=[_item(memory=ids)]), path)

    assert problems, "a sixth memory id was accepted"
    assert not path.exists()


def test_an_absolute_plan_path_is_rejected_at_write_time(tmp_path):
    """RED WHEN an absolute plan path is stored. An absolute path captured
    inside a worktree points into a directory `git worktree remove` deletes."""
    path = tmp_path / "demo.json"
    problems = backlog.save(
        _backlog(tmp_path, items=[_item(plan="/absolute/plan.md")]), path
    )
    assert problems, "an absolute plan path was accepted"
    assert not path.exists()


def test_an_item_id_with_a_trailing_newline_is_rejected():
    """RED WHEN the id pattern anchors on `$`, which matches before a trailing
    newline and would admit `a1b2\\n` as a valid four-hex id."""
    problems = backlog_store.validate(
        _backlog("/tmp/project", items=[_item(item_id="a1b2\n")])
    )
    assert problems, "an id with a trailing newline was accepted"


# --------------------------------------------------------------------------
# resolution states: absent is silent, unresolved is loud
# --------------------------------------------------------------------------
def test_an_absent_store_is_silent(tmp_path):
    """RED WHEN a project with no backlog emits anything. That is the normal
    case for most projects and must not produce noise."""
    project = tmp_path / "project"
    project.mkdir()
    notice = backlog_store.session_block(str(project), backlog_dir=tmp_path / "nope")
    assert notice == backlog_store.BacklogNotice("", "")


def test_a_non_empty_store_with_no_match_is_loud_not_silent(tmp_path):
    """A resolution failure must NOT read as an empty backlog.

    RED WHEN the no-match case returns empty, which would tell the
    orchestrator this project has no backlog when it may have one under a path
    that failed to match.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(store, "elsewhere.json", _backlog(tmp_path / "somewhere_else"))

    notice = backlog_store.session_block(str(project), backlog_dir=store)

    assert notice.alert, "a resolution failure was silent"
    assert "NOT an empty backlog" in notice.context


def test_a_relative_project_dir_is_loud(tmp_path):
    """RED WHEN a relative project directory is resolved against the process
    CWD, which would silently read some other project's backlog."""
    notice = backlog_store.session_block("relative/path", backlog_dir=tmp_path)
    assert notice.alert
    assert "absolute" in notice.alert


def test_session_block_never_raises_on_a_hostile_store(tmp_path, monkeypatch):
    """Totality. RED WHEN any state raises: an exception at the injection point
    does not surface a message, it discards every accumulated context part and
    replaces the whole block with a safety net."""
    store = tmp_path / "store"
    store.mkdir()
    _write(store, "demo.json", _backlog(tmp_path))

    def explode(*args, **kwargs):
        raise RuntimeError("hostile store")

    monkeypatch.setattr(backlog_store, "_scan", explode)
    notice = backlog_store.session_block(str(tmp_path), backlog_dir=store)

    assert isinstance(notice, backlog_store.BacklogNotice)
    assert "hostile store" in notice.alert


# --------------------------------------------------------------------------
# the rename case: newer `updated` wins, and the duplication is reported
# --------------------------------------------------------------------------
def test_a_rename_prefers_the_newer_stamp_and_reports_the_duplication(tmp_path):
    """Two files record one `project_path` after a rename.

    RED WHEN the tie-break is alphabetical or by path length. The fixture is
    built so alphabetical order and recency DISAGREE: `aaa-old.json` sorts
    first but carries the older stamp, so a green here means recency decided.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(
        store,
        "aaa-old.json",
        _backlog(project, items=[_item(title="STALE")], updated="2026-01-01T00:00:00Z"),
    )
    _write(
        store,
        "zzz-new.json",
        _backlog(project, items=[_item(title="CURRENT")], updated="2026-09-01T00:00:00Z"),
    )

    # The discriminating fact: the two orderings disagree.
    assert sorted(p.name for p in store.glob("*.json"))[0] == "aaa-old.json"

    notice = backlog_store.session_block(str(project), backlog_dir=store)

    assert "CURRENT" in notice.context, "the older stamp won the tie-break"
    assert "STALE" not in notice.context
    assert "2 stored backlogs claim this project" in notice.context


def test_nothing_matches_on_the_filename(tmp_path):
    """The read path derives no project name at any point.

    RED WHEN a filename is used as a fallback match: the file here is named
    for the project directory yet records a `project_path` that does not
    contain it, so a name-based rule would match and a path-based rule must
    not.
    """
    project = tmp_path / "project"
    project.mkdir()
    store = tmp_path / "store"
    _write(store, "project.json", _backlog(tmp_path / "somewhere_else"))

    match, _ = backlog_store.find_for(str(project), store)
    assert match is None, "the read path matched on the filename"


# --------------------------------------------------------------------------
# the module's CLI contract
# --------------------------------------------------------------------------
def test_main_returns_an_exit_code_and_calls_no_sys_exit(tmp_path, monkeypatch):
    """RED WHEN `main` calls `sys.exit` outside its `__main__` guard, which
    would make the module unusable as a library and untestable in-process."""
    monkeypatch.setattr(backlog, "store_path", lambda backlog_dir=None: tmp_path / "b.json")
    monkeypatch.setattr(backlog, "project_root", lambda: tmp_path)

    code = backlog.main(["show"])
    assert isinstance(code, int)


def test_no_bin_executable_was_added():
    """RED WHEN a `bin/pact-backlog` entry appears. Per-tool `bin/` entries are
    the proliferation the unified-CLI design rejects."""
    bin_dir = HOOKS_DIR.parent / "bin"
    assert not bin_dir.exists() or not list(bin_dir.glob("*backlog*"))


# --------------------------------------------------------------------------
# the live seam: session_init, driven for real
# --------------------------------------------------------------------------
def _drive_session_init(monkeypatch, home, project_dir, source):
    """Run the real `session_init.main()` and return (context, system_message).

    Only the heavy collaborators unrelated to this feature are stubbed. The
    resolution path — home-pinned directory, then containment against the
    stored main root — runs unstubbed, because that path IS what these tests
    exist to check and replacing it with a stub would leave the one thing that
    can break untested. The frame carries no `agent_type`, making it a NON-LEAD
    frame: the block sits outside the lead-only branch, so a call site scoped
    one level in emits nothing here while every lead-framed test still passes.
    """
    import io
    from unittest.mock import patch

    import session_init

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))
    monkeypatch.setattr(Path, "home", lambda: home)
    stdin_data = json.dumps({"source": source})

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
         patch("sys.stdout", new_callable=io.StringIO) as captured:
        try:
            session_init.main()
        except SystemExit as exc:
            assert exc.code == 0

    raw = captured.getvalue().strip()
    assert raw, "session_init emitted nothing at all"
    payload = json.loads(raw)
    return (
        payload.get("hookSpecificOutput", {}).get("additionalContext", ""),
        payload.get("systemMessage", ""),
    )


def test_session_init_emits_the_block_for_a_worktree_session(monkeypatch, tmp_path):
    """The whole feature, through its real call site.

    RED WHEN the block is scoped into the lead branch, when the store stops
    being home-pinned, or when the byte-0 role marker is displaced by an
    insertion at the front.
    """
    main_root = tmp_path / "project"
    worktree = main_root / ".worktrees" / "feat-x"
    worktree.mkdir(parents=True)
    _write(
        tmp_path / ".claude" / "pact-backlog",
        "demo.json",
        _backlog(main_root, items=[_item(title="SEEDED BACKLOG ITEM", status="active")]),
    )

    context, _ = _drive_session_init(monkeypatch, tmp_path, worktree, "startup")

    assert "SEEDED BACKLOG ITEM" in context, (
        "the backlog block did not reach a worktree session's context"
    )
    assert context.startswith("YOUR PACT ROLE:"), (
        "the block displaced the byte-0 role marker"
    )


def test_the_alert_channel_is_gated_on_the_launch_source(monkeypatch, tmp_path):
    """`alert` reaches the user on startup and resume, and NOT on compact,
    while `context` carries the loud text on all three.

    This is a SEPARATE property from the channel asymmetry, and the channel
    arms do not reach it: deleting `source in ("startup", "resume")` from the
    call site leaves every channel assertion intact and ships a systemMessage
    on every compaction. Measured before this arm existed — the whole file
    stayed green under exactly that mutation.

    RED WHEN the source gate is deleted (compact gains a systemMessage) or
    widened the other way (startup loses one). Both directions are asserted,
    since a gate stuck OFF and a gate stuck ON are different defects and an
    arm checking one is blind to the other.
    """
    project = tmp_path / "project"
    project.mkdir()
    # A corrupt store makes the loud path fire, which is what puts a value in
    # the alert channel for the gate to act on.
    _write(tmp_path / ".claude" / "pact-backlog", "demo.json", "{ not json at all")

    for source in ("startup", "resume"):
        context, system_message = _drive_session_init(
            monkeypatch, tmp_path, project, source
        )
        assert "PACT backlog" in context, f"{source}: context lost the loud text"
        assert "PACT backlog" in system_message, (
            f"{source}: the user was not told about a corrupt backlog"
        )

    context, system_message = _drive_session_init(
        monkeypatch, tmp_path, project, "compact"
    )
    assert "PACT backlog" in context, "compact: context lost the loud text"
    assert "PACT backlog" not in system_message, (
        "compact emitted a systemMessage; the source gate is not firing"
    )
