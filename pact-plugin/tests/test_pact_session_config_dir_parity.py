"""
Location: pact-plugin/tests/test_pact_session_config_dir_parity.py
Summary: Behavioural parity pin between the config-root resolver twin inside
         skills/pact-memory/scripts/pact_session.py and the authoritative
         resolver hooks/shared/paths.get_claude_config_dir().
Used by: the merge gate only — nothing imports this module.

WHY A TWIN EXISTS AT ALL: skill scripts cannot import the hooks package (a real
package boundary, documented repeatedly in working_memory.py), so pact_session
must reproduce the resolver contract rather than call it. The defect this pin
guards is therefore not the copy — it is the UNCOVERED copy. Nothing pinned
parity, so the copy drifted.

THE RESOLVER IS THE ORACLE. Every expected value below is COMPUTED by calling
get_claude_config_dir() under the same env and the same redirected home. None is
restated as a literal: a restatement would be a THIRD copy of the contract, free
to drift from both and capable of passing while the two it compares disagree.

The package boundary binds PRODUCTION code, not tests — tests/conftest.py puts
both trees on sys.path, so oracle and twin load in one interpreter, and both read
Path.home() at call time so one redirected home reaches both.

test_oracle_moves_with_env is what keeps the rest of this file from going
vacuous. If a future change makes get_claude_config_dir() ignore
$CLAUDE_CONFIG_DIR, oracle and twin agree on home/".claude" for every input and
every other arm here goes green against an unchanged broken twin.
"""
import json

import pytest

from scripts import pact_session
from shared.paths import get_claude_config_dir

# The clause set is the resolver's STATED PRECEDENCE (hooks/shared/paths.py),
# not a plausible-looking sample. The three UNSET clauses separate nothing —
# the contract's answer there IS home/".claude", which a home-hardcoded twin
# matches by coincidence. That is exactly their job: they are the control that
# shows the instrument is live. The five divergent clauses are the ones where
# correct and defective code actually differ, so they are the ones that can
# fail.
UNSET_CLAUSES = ("unset", "empty", "whitespace")
DIVERGENT_CLAUSES = ("tilde", "tilde_child", "abs_existing", "abs_missing", "relative")
ALL_CLAUSES = UNSET_CLAUSES + DIVERGENT_CLAUSES


@pytest.fixture
def apply_clause(tmp_path, monkeypatch):
    """Put $CLAUDE_CONFIG_DIR into exactly one precedence clause.

    The autouse `_isolate_config_root_to_tmp` fixture has already scrubbed the
    variable and redirected Path.home() to tmp_path, so "unset" needs no action
    and every config root built here is a SEPARATE tree from home — an anchor
    that lags on Path.home() lands somewhere no arm expects, rather than
    somewhere an arm happens to accept.
    """
    existing = tmp_path / "config-existing"
    existing.mkdir()
    values = {
        "empty": "",
        "whitespace": "   ",
        "tilde": "~",
        "tilde_child": "~/nested",
        "abs_existing": str(existing),
        # Honored even though it is never created — the resolver's contract is
        # explicit that only CONSUMERS fail open on a missing dir.
        "abs_missing": str(tmp_path / "config-never-created"),
        "relative": "rel-root",
    }

    def _apply(clause):
        if clause != "unset":
            monkeypatch.setenv("CLAUDE_CONFIG_DIR", values[clause])

    return _apply


@pytest.mark.parametrize("clause", ALL_CLAUSES)
def test_context_file_path_tracks_the_resolver(clause, apply_clause):
    """The session-context path must be anchored at the resolved config root."""
    apply_clause(clause)

    expected = (
        get_claude_config_dir()
        / "pact-sessions" / "proj" / "sid" / "pact-session-context.json"
    )

    assert pact_session._context_file_path("sid", "/somewhere/proj") == expected


def test_disk_discovery_tracks_the_resolver(tmp_path, monkeypatch):
    """Session discovery must GLOB the resolved config root, not home.

    A second, independently hardcoded site: a fix that re-anchors the path
    builder alone leaves this one reading the wrong tree, and every parametrized
    arm above still passes.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "relocated"))
    session_id = "session-abc"

    context_file = (
        get_claude_config_dir()
        / "pact-sessions" / "proj" / session_id / "pact-session-context.json"
    )
    context_file.parent.mkdir(parents=True)
    context_file.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")

    assert pact_session._resolve_context_on_disk(session_id) == session_id


def test_oracle_moves_with_env(tmp_path, monkeypatch):
    """The ORACLE itself must track $CLAUDE_CONFIG_DIR.

    Without this arm, a resolver that stopped honoring the variable would make
    every comparison in this file compare home/".claude" against home/".claude"
    — all green, against an unchanged broken twin, with no red anywhere.
    """
    unset_answer = get_claude_config_dir()

    first = tmp_path / "root-one"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(first))
    assert get_claude_config_dir() == first

    second = tmp_path / "root-two"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(second))
    assert get_claude_config_dir() == second

    assert unset_answer not in (first, second)
