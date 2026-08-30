"""
Smoke tests for dispatch_gate.py — #662 PreToolUse matcher='Agent' hook.

NOT comprehensive coverage — that lives in the TEST phase / Commit-4
follow-up. These cases are the minimum-viable surface that proves the
gate's structural contract:

  1. Happy-path ALLOW (registered specialist, valid name, matching team,
     task assigned, short prompt with TaskList reference)
  2. name_required DENY: empty name=
  3. team_name_required DENY: empty team_name=
  4. name_reserved_token DENY: reserved name (`team-lead`)
  5. SOLO_EXEMPT carve-out: subagent_type='general-purpose' → ALLOW
  6. Module-load fail-closed counter-test: subprocess invocation of a
     COPIED hooks tree whose shared.dispatch_helpers raises ImportError
     → DENY output includes hookEventName + exit 2

The fail-closed counter-test runs in a subprocess per PR #660 R2
discipline: NEVER pop shared.* from sys.modules in the test process.
Sabotage runs in a subprocess so the test process's import state stays
clean.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))


_SUPPRESS_EXPECTED = {"suppressOutput": True}
_TEAM = "pact-test"
_NAME = "tester"


# ─── helpers ───────────────────────────────────────────────────────────────


def _make_input(subagent_type="pact-architect", name=_NAME, team_name=_TEAM,
                prompt="Standard mission. Check TaskList for tasks assigned to you."):
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "test-session",
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": subagent_type,
            "name": name,
            "team_name": team_name,
            "prompt": prompt,
        },
    }


def _run_main(input_data, capsys):
    """Invoke dispatch_gate.main() in-process. Returns (exit_code, stdout_json)."""
    from dispatch_gate import main

    with patch("sys.stdin", io.StringIO(json.dumps(input_data))):
        with pytest.raises(SystemExit) as exc_info:
            main()

    captured = capsys.readouterr()
    out = captured.out.strip()
    return exc_info.value.code, json.loads(out) if out else {}


def _setup_session(monkeypatch, tmp_path, plugin_root: Path, team_name=_TEAM):
    """Wire pact_context to point at a tmp session, set HOME so
    has_task_assigned + _team_member_names read tmp dirs.
    """
    import shared.pact_context as ctx_module

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    ctx_path = tmp_path / "pact-session-context.json"
    ctx_path.write_text(json.dumps({
        "team_name": team_name,
        "session_id": "test-session",
        "project_dir": str(tmp_path / "project"),
        "plugin_root": str(plugin_root),
        "started_at": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(ctx_module, "_context_path", ctx_path)
    monkeypatch.setattr(ctx_module, "_cache", None)

    # Override init() so re-init from hook stdin doesn't overwrite our path.
    monkeypatch.setattr(ctx_module, "init", lambda input_data: None)

    # Clear the registry cache so each test sees the freshly-built plugin_root.
    import shared.dispatch_helpers as dh
    dh._specialist_registry.cache_clear()


def _seed_plugin(plugin_root: Path, agents=("pact-architect",)):
    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for stem in agents:
        (agents_dir / f"{stem}.md").write_text("---\nname: " + stem + "\n---\n")


def _seed_team(home: Path, team_name=_TEAM, members=(), tasks=()):
    """Write fake team config + canonical tasks store.

    config.json under ``HOME/.claude/teams/{team_name}/`` (read by
    ``_team_member_names``); tasks under ``HOME/.claude/tasks/{team_name}/``
    (the canonical store per ``shared/task_utils.py``, read by
    ``has_task_assigned`` after the path-alignment fix).
    """
    team_dir = home / ".claude" / "teams" / team_name
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "config.json").write_text(json.dumps({
        "team_name": team_name,
        "members": [{"name": m} for m in members],
    }), encoding="utf-8")
    tasks_dir = home / ".claude" / "tasks" / team_name
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for i, (owner, status) in enumerate(tasks):
        (tasks_dir / f"task_{i}.json").write_text(json.dumps({
            "id": str(i),
            "owner": owner,
            "status": status,
        }), encoding="utf-8")


# ─── tests ─────────────────────────────────────────────────────────────────


def test_allow_happy_path(tmp_path, monkeypatch, capsys):
    """Registered specialist, valid name, matching team, task assigned,
    short prompt with TaskList reference → ALLOW (suppressOutput, exit 0).
    """
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root, agents=("pact-architect",))
    _setup_session(monkeypatch, tmp_path, plugin_root)
    _seed_team(tmp_path, members=(), tasks=((_NAME, "pending"),))

    code, out = _run_main(_make_input(), capsys)
    assert code == 0
    assert out == _SUPPRESS_EXPECTED


def test_deny_empty_name(tmp_path, monkeypatch, capsys):
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _setup_session(monkeypatch, tmp_path, plugin_root)

    code, out = _run_main(_make_input(name=""), capsys)
    assert code == 2
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "name= parameter is required" in hso["permissionDecisionReason"]


def test_empty_team_name_arg_resolves_via_ssot(tmp_path, monkeypatch, capsys):
    """#979: an EMPTY team_name arg no longer DENYs. Rule ③'s team_name-presence
    check was dropped — the platform-ignored caller arg is never a path
    component — so the gate resolves the session team from the SSOT
    (get_team_name() → 'pact-test') and ALLOWs when that team carries the
    owner's task. Mirrors test_dispatch_gate.test_missing_team_name_arg_resolves_via_ssot."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _setup_session(monkeypatch, tmp_path, plugin_root)
    _seed_team(tmp_path, members=(), tasks=((_NAME, "pending"),))

    code, out = _run_main(_make_input(team_name=""), capsys)
    assert code == 0
    assert out == _SUPPRESS_EXPECTED


def test_deny_reserved_name(tmp_path, monkeypatch, capsys):
    """Reserved name 'team-lead' would shadow the routing literal — DENY."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _setup_session(monkeypatch, tmp_path, plugin_root)

    code, out = _run_main(_make_input(name="team-lead"), capsys)
    assert code == 2
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "reserved-token" in hso["permissionDecisionReason"]


def test_solo_exempt_carve_out(tmp_path, monkeypatch, capsys):
    """subagent_type='general-purpose' bypasses the gate even without
    name/team_name — research agents legitimately spawn solo.
    """
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _setup_session(monkeypatch, tmp_path, plugin_root)

    code, out = _run_main(
        _make_input(subagent_type="general-purpose", name="", team_name=""),
        capsys,
    )
    assert code == 0
    assert out == _SUPPRESS_EXPECTED


def test_fail_closed_module_load(tmp_path):
    """Module-load fail-closed counter-test: sabotage shared.dispatch_helpers
    inside a COPY of the hooks tree, then invoke the COPIED dispatch_gate.py
    as a subprocess.
    Expect: exit 2, stdout JSON with hookEventName + permissionDecision='deny'.

    Subprocess isolation per PR #660 R2 discipline — NEVER pop shared.*
    from sys.modules in the test process.

    RUNNING THE COPIED SCRIPT IS THE MECHANISM. Python puts the script's own
    directory at sys.path[0], so invoking the copied gate makes the copied —
    and therefore sabotaged — `shared` package the one that resolves, on
    every interpreter. The whole hooks/ tree is copied rather than just
    shared/, so any __file__-relative resolution inside the gate stays
    structurally honest.

    THE EARLIER SHAPE WAS INERT BELOW 3.11. It ran the REAL gate and relied
    on PYTHONSAFEPATH=1 to suppress the sys.path[0] auto-insert so that a
    PYTHONPATH pointing at the sabotage would win. PYTHONSAFEPATH arrived in
    3.11: on 3.9 it is ignored, the real hooks/shared/ wins, the fail-closed
    branch is never reached, and this arm fails at the exit-code assertion.
    Do NOT repair that by relaxing the assertion — the gate is not failing
    open, it was never being exercised.

    PYTHONSAFEPATH is cleared from the child's environment for the same
    reason it used to be set: an ambient PYTHONSAFEPATH=1 would suppress the
    sys.path[0] insert this mechanism depends on.
    """
    import shutil

    repo_hooks = Path(__file__).parent.parent / "hooks"
    hooks_copy = tmp_path / "hooks"
    # Copy the whole tree so every OTHER submodule (pact_context,
    # session_journal, ...) imports normally from the copy.
    shutil.copytree(
        repo_hooks, hooks_copy, ignore=shutil.ignore_patterns("__pycache__")
    )
    # Overwrite ONLY dispatch_helpers.py with a forced-raise stub so the
    # `from shared.dispatch_helpers import ...` line in dispatch_gate.py
    # fires the wrapped except BaseException → _emit_load_failure_deny.
    (hooks_copy / "shared" / "dispatch_helpers.py").write_text(
        "raise ImportError('sabotage: forced module-load failure')\n"
    )

    env = os.environ.copy()
    env.pop("PYTHONSAFEPATH", None)

    proc = subprocess.run(
        [sys.executable, str(hooks_copy / "dispatch_gate.py")],
        input=json.dumps({
            "hook_event_name": "PreToolUse",
            "session_id": "test",
            "tool_name": "Agent",
            "tool_input": {},
        }),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert proc.returncode == 2, (
        f"expected exit 2, got {proc.returncode}. stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}"
    )
    out = json.loads(proc.stdout.strip())
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "load failure" in hso["permissionDecisionReason"].lower() \
        or "module imports" in hso["permissionDecisionReason"].lower()


def test_redaction_in_journal(tmp_path, monkeypatch, capsys):
    """Credential redaction verification: prompt containing a credential pattern is
    redacted in the journal-written form. The user-facing
    permissionDecisionReason is unaffected (verbatim prompt fragment is
    kept for dispatcher debugging).

    We trigger team_name_required (empty team_name) so the gate DENIES, then read the
    captured journal event to confirm prompt_redacted contains
    [REDACTED] and NOT the original sk-... token.
    """
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _setup_session(monkeypatch, tmp_path, plugin_root)

    captured_events = []

    def _capture_append(event):
        captured_events.append(event)
        return True

    # Patching the shared seam alone is sufficient and complete: the gate
    # emits through append_event_checked, which funnels here, so there is no
    # module-local append_event in dispatch_gate left to patch.
    import shared.session_journal as sj
    monkeypatch.setattr(sj, "append_event", _capture_append)

    # Split via Python adjacent-string-literal concatenation so the
    # repo-root pre-commit secret-scanner regex
    # ``["']sk-[a-zA-Z0-9]{20,}["']`` does NOT match this test fixture.
    # Runtime value is identical to the joined literal.
    secret = "sk" "-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
    prompt = f"Embedded credential: {secret} please ignore. Check TaskList."
    code, _out = _run_main(
        _make_input(team_name="", prompt=prompt),
        capsys,
    )
    assert code == 2
    assert captured_events, "expected a journal event to be captured"
    event = captured_events[-1]
    assert event["type"] == "dispatch_decision"
    assert "[REDACTED]" in event["prompt_redacted"]
    assert secret not in event["prompt_redacted"]
