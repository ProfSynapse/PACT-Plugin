"""#956 Component A — handoff_ordering_gate.py PreToolUse WARN gate.

The NUDGE half of the #956 fix: when the lead's TaskUpdate(status="completed")
lands on a HANDOFF-expecting task whose metadata.handoff is not yet on disk, the
gate surfaces an ACTIONABLE advisory (additionalContext) so the lead does
handoff-then-complete. It NEVER denies — the backstop guarantees the emit; this
gate only nudges.

These tests cover the both-modes matrix rows M1-M6 (lead vs teammate frame) plus
the gate's fail-OPEN contract on every error path, and a main()-level integration
proving the exit-0 + additionalContext (NOT permissionDecision) output shape.

Drives the gate via _evaluate(input_data) (the logic entry) with a real on-disk
task.json so read_task_json resolves; is_lead keys on agent_type (the only
tmux-safe discriminator). The pact_context fixture pre-sets the context path so
the gate's internal init() is a no-op against it.
"""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import handoff_ordering_gate as gate  # noqa: E402

TEAM = "test-team"
LEAD = "PACT:pact-orchestrator"
TEAMMATE = "pact-devops-engineer"
HANDOFF = {"decisions": ["x"], "produced": ["f.py"]}


def _seed_task(tmp_path, team, task_id, **fields):
    tasks_dir = tmp_path / ".claude" / "tasks" / team
    tasks_dir.mkdir(parents=True, exist_ok=True)
    payload = {"id": task_id, **fields}
    (tasks_dir / f"{task_id}.json").write_text(json.dumps(payload), encoding="utf-8")


# Default team member set the dispatch-variety predicate resolves against.
# REAL owners are BARE names; the team config maps each bare name to its
# pact-* agentType — the resolution the corrected gate predicate performs.
_DEFAULT_MEMBERS = [
    {"name": "backend-coder", "agentType": "pact-backend-coder"},
    {"name": "test-engineer", "agentType": "pact-test-engineer"},
    {"name": "secretary", "agentType": "pact-secretary"},
    {"name": "explorer", "agentType": "general-purpose"},  # SOLO_EXEMPT (non-pact)
]


def _seed_team_config(tmp_path, monkeypatch, team, members=None):
    """Make the corrected gate predicate resolvable in-test:
      (a) write ~/.claude/teams/{team}/config.json so pact_context._iter_members
          resolves bare owners → agentType, and
      (b) seed a plugin root with agents/pact-*.md for each member's pact-*
          agentType + point the context's plugin_root at it + clear the
          registry cache so is_registered_pact_specialist resolves (in
          production the live agents/ dir is found; in-test the glob needs a
          seeded plugin root, mirroring test_dispatch_gate._seed_plugin).
    Forces HOME/.claude resolution by clearing CLAUDE_CONFIG_DIR."""
    import shared.dispatch_helpers as dh
    import shared.pact_context as ctx_module

    members = _DEFAULT_MEMBERS if members is None else members
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    team_dir = tmp_path / ".claude" / "teams" / team
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "config.json").write_text(
        json.dumps({"members": members}), encoding="utf-8",
    )

    # Seed the specialist registry: one agents/pact-*.md per pact-* agentType.
    plugin_root = tmp_path / "plugin"
    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for m in members:
        at = m.get("agentType", "")
        if isinstance(at, str) and at.startswith("pact-"):
            (agents_dir / f"{at}.md").write_text(
                f"---\nname: {at}\n---\n", encoding="utf-8",
            )
    monkeypatch.setattr(ctx_module, "get_plugin_root", lambda: str(plugin_root))
    dh._specialist_registry.cache_clear()


def _complete_update(task_id, *, agent_type=LEAD, metadata=None):
    """A TaskUpdate(status=completed). `metadata` (if given) is the INCOMING
    update metadata (e.g. a bundled handoff)."""
    tool_input = {"taskId": task_id, "status": "completed"}
    if metadata is not None:
        tool_input["metadata"] = metadata
    payload = {"tool_name": "TaskUpdate", "tool_input": tool_input}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    return payload


def _ctx(pact_context, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    pact_context(team_name=TEAM, session_id="s1", project_dir=str(tmp_path))


# =============================================================================
# M1 — HANDOFF-expecting task completed, handoff absent → advisory (lead) / none (teammate)
# =============================================================================
class TestM1WarnOnOrderingMistake:
    def test_lead_frame_warns(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},  # completed, NO handoff
        )
        advisory = gate._evaluate(_complete_update("42"))
        assert advisory is not None
        assert "no metadata.handoff yet" in advisory
        assert "42" in advisory and "devops" in advisory

    def test_teammate_frame_no_warn(self, tmp_path, monkeypatch, pact_context):
        """M1 dual-mode: identical fixture under a TEAMMATE frame (is_lead
        False) → no advisory. The advisory is for the lead who completes."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},
        )
        assert gate._evaluate(_complete_update("42", agent_type=TEAMMATE)) is None


# =============================================================================
# M2 — handoff already on disk → no warn
# =============================================================================
class TestM2HandoffAlreadyPresent:
    def test_no_warn_when_handoff_on_disk(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={"handoff": HANDOFF},
        )
        assert gate._evaluate(_complete_update("42")) is None


# =============================================================================
# M3 — teachback Task-A (exempt by subject) → no warn
# =============================================================================
class TestM3TeachbackExempt:
    def test_no_warn_on_teachback_subject(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "A",
            subject="devops: TEACHBACK for the thing", owner="devops",
            status="completed", metadata={},
        )
        assert gate._evaluate(_complete_update("A")) is None


# =============================================================================
# M4 — secretary task (exempt Surface 1, signal-type proxy) → no warn
# M5 — signal-task (exempt Surface 2) → no warn
# =============================================================================
class TestM4M5Exempt:
    @pytest.mark.parametrize("signal_type", ["blocker", "algedonic"])
    def test_no_warn_on_signal_task(self, tmp_path, monkeypatch, pact_context, signal_type):
        """M5: a signal task (completion_type=signal + type in {blocker,
        algedonic}) is self-complete-exempt → no handoff expected → no warn."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "S",
            subject="devops: raise blocker", owner="devops",
            status="completed",
            metadata={"completion_type": "signal", "type": signal_type},
        )
        assert gate._evaluate(_complete_update("S")) is None

    def test_warn_positive_control_non_signal(self, tmp_path, monkeypatch, pact_context):
        """Positive control for M5: the SAME fixture WITHOUT the signal
        metadata DOES warn — proving the suppression above is the exempt
        predicate firing, not a missing precondition."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "S",
            subject="devops: raise blocker", owner="devops",
            status="completed", metadata={},
        )
        assert gate._evaluate(_complete_update("S")) is not None


# =============================================================================
# M6 — bundled handoff+complete in one TaskUpdate → no warn
# =============================================================================
class TestM6BundledHandoffComplete:
    def test_no_warn_when_incoming_handoff_bundled(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},
        )
        # The completing TaskUpdate ALSO carries the handoff → no race.
        adv = gate._evaluate(_complete_update("42", metadata={"handoff": HANDOFF}))
        assert adv is None


# =============================================================================
# Scoping / fail-open contract
# =============================================================================
class TestScopingAndFailOpen:
    def test_non_completion_update_no_warn(self, tmp_path, monkeypatch, pact_context):
        """Only completion transitions are gated."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="pending", metadata={},
        )
        payload = {
            "tool_name": "TaskUpdate",
            "agent_type": LEAD,
            "tool_input": {"taskId": "42", "metadata": {"foo": "bar"}},  # no status=completed
        }
        assert gate._evaluate(payload) is None

    def test_no_owner_no_warn(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="",
            status="completed", metadata={},
        )
        assert gate._evaluate(_complete_update("42")) is None

    def test_missing_task_on_disk_no_warn(self, tmp_path, monkeypatch, pact_context):
        """No task file → read_task_json returns {} → bypass (fail-open)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        assert gate._evaluate(_complete_update("does-not-exist")) is None

    def test_non_taskupdate_tool_no_warn(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        payload = {"tool_name": "TaskCreate", "agent_type": LEAD, "tool_input": {}}
        assert gate._evaluate(payload) is None

    def test_empty_agent_type_no_warn(self, tmp_path, monkeypatch, pact_context):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},
        )
        assert gate._evaluate(_complete_update("42", agent_type="")) is None


# =============================================================================
# main() integration — exit-0 + additionalContext (NEVER permissionDecision)
# =============================================================================
class TestMainContract:
    def _run_main(self, monkeypatch, capsys, stdin_obj):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_obj)))
        with pytest.raises(SystemExit) as exc:
            gate.main()
        out = capsys.readouterr().out
        return exc.value.code, out

    def test_advisory_path_exits_zero_with_additional_context(
        self, tmp_path, monkeypatch, pact_context, capsys
    ):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},
        )
        code, out = self._run_main(monkeypatch, capsys, _complete_update("42"))
        assert code == 0, "WARN gate must ALWAYS exit 0 — never deny"
        parsed = json.loads(out)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert "additionalContext" in hso
        assert "permissionDecision" not in hso, "a WARN gate must NEVER emit a deny"

    def test_passthrough_path_suppresses_and_exits_zero(
        self, tmp_path, monkeypatch, pact_context, capsys
    ):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={"handoff": HANDOFF},  # already present → no warn
        )
        code, out = self._run_main(monkeypatch, capsys, _complete_update("42"))
        assert code == 0
        assert json.loads(out) == {"suppressOutput": True}

    def test_malformed_stdin_fails_open(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        with pytest.raises(SystemExit) as exc:
            gate.main()
        assert exc.value.code == 0
        assert json.loads(capsys.readouterr().out) == {"suppressOutput": True}


# =============================================================================
# main() through the REAL pact_context on-disk resolution (advisory path)
# =============================================================================
class TestMainRealContextResolution:
    """The other main() tests (TestMainContract) use the `pact_context`
    fixture, which monkeypatches `pact_context._context_path` to a pre-written
    file. Because `init()` early-returns when `_context_path is not None`, those
    tests SKIP the gate's real session-context resolution chain — the path
    `init(input_data)` resolves from `input_data.session_id` + CLAUDE_PROJECT_DIR,
    then `get_pact_context()` reads the on-disk pact-session-context.json to
    recover `team_name`, then `read_task_json(task_id, team_name)`.

    This test deliberately does NOT use the `pact_context` fixture. It writes a
    REAL on-disk context via `pact_context.write_context(...)`, leaves
    `_context_path`/`_cache` UNSET (None) so `init()` performs the genuine
    resolution, and drives `main()` end-to-end for the POSITIVE-advisory path.
    It proves team_name resolution from real disk reaches the warn branch — not
    just the pre-injected-path shortcut. (Non-vacuity: if the advisory path or
    the real context resolution is broken, team_name resolves empty, the gate
    bypasses, and the additionalContext assertion fails.)
    """

    def test_advisory_path_through_real_on_disk_context(
        self, tmp_path, monkeypatch, capsys
    ):
        import shared.pact_context as pc

        sid = "real-ctx-session-001"
        project_dir = str(tmp_path / "PACT-Plugin")  # basename slug == "PACT-Plugin"

        # Filesystem isolation: every Path.home() (write_context, init's path
        # builder, read_task_json) resolves under tmp_path.
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # CLAUDE_PROJECT_DIR is the OTHER half of init()'s path resolution.
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", project_dir)

        # Write the REAL on-disk session-context file at the session-scoped path.
        # Start from clean module state so write_context resolves freshly.
        monkeypatch.setattr(pc, "_context_path", None)
        monkeypatch.setattr(pc, "_cache", None)
        pc.write_context(TEAM, sid, project_dir)

        # CRITICAL: write_context populates `_cache` (and `_context_path`). Reset
        # BOTH to None so the gate's init()/get_pact_context() must perform the
        # genuine on-disk resolution rather than hitting the warm cache — that
        # resolution chain is exactly what this test exists to exercise.
        monkeypatch.setattr(pc, "_context_path", None)
        monkeypatch.setattr(pc, "_cache", None)

        # Seed the on-disk task: completed, HANDOFF-expecting (owner, no handoff).
        _seed_task(
            tmp_path, TEAM, "42",
            subject="devops: CODE the thing", owner="devops",
            status="completed", metadata={},
        )

        # Frame carries agent_type (is_lead reads it directly) AND session_id
        # (init() reads it to resolve the context path). No pre-set _context_path.
        frame = _complete_update("42", agent_type=LEAD)
        frame["session_id"] = sid

        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(frame)))
        with pytest.raises(SystemExit) as exc:
            gate.main()
        out = capsys.readouterr().out

        assert exc.value.code == 0, "WARN gate must ALWAYS exit 0 — never deny"
        parsed = json.loads(out)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert "additionalContext" in hso, (
            "the advisory must fire through the REAL on-disk context resolution "
            "(team_name recovered from the written pact-session-context.json); a "
            "missing advisory means the resolution chain or the warn branch broke"
        )
        assert "42" in hso["additionalContext"] and "devops" in hso["additionalContext"]
        assert "permissionDecision" not in hso, "a WARN gate must NEVER emit a deny"


# =============================================================================
# #865 dispatch-variety gate — the NEW branch (_evaluate_dispatch_variety),
# parallel to and independent of the #956 completion-ordering _evaluate.
# =============================================================================
#
# Composite-signature trigger: a TaskUpdate whose tool_input carries BOTH
# owner=pact-* AND a non-empty addBlockedBy in the SAME call (the terminal
# dispatch-wiring write). Fires (warn/deny/shadow per env-knob) ONLY when the
# linked Task B carries no resolvable metadata.variety. No misfire at
# TaskCreate(B) or partial-wiring; carve-outs preserved.
# =============================================================================


def _variety(total):
    """A resolvable D11 variety stamp at the given total."""
    return {
        "novelty": 2, "novelty_rationale": "x",
        "scope": 2, "scope_rationale": "x",
        "uncertainty": 2, "uncertainty_rationale": "x",
        "risk": 2, "risk_rationale": "x",
        "total": total,
    }


def _wiring_update(task_id, *, owner="backend-coder",
                   add_blocked_by=("A",), agent_type=LEAD):
    """A terminal dispatch-wiring TaskUpdate: owner + addBlockedBy in the SAME
    tool_input. owner is a BARE specialist name (the real shape) resolving via
    team config to a pact agentType. add_blocked_by=None / [] omits it
    (partial-wiring case)."""
    tool_input = {"taskId": task_id}
    if owner is not None:
        tool_input["owner"] = owner
    if add_blocked_by:
        tool_input["addBlockedBy"] = list(add_blocked_by)
    payload = {"tool_name": "TaskUpdate", "tool_input": tool_input}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    return payload


class TestDispatchVarietyTrigger:
    """The composite signature fires iff owner pact-* AND addBlockedBy are in
    the SAME tool_input AND the linked Task B has no resolvable variety."""

    def test_fires_on_wiring_write_unstamped_task_b(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """Terminal wiring write linking an unstamped Task B → advisory. The
        BARE-NAME-FIRES case: owner 'backend-coder' resolves via team config to
        agentType pact-backend-coder. This is the case that was DEAD under the
        old owner.startswith('pact-') predicate."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        adv = gate._evaluate_dispatch_variety(_wiring_update("42"))
        assert adv is not None and "metadata.variety" in adv

    def test_fires_reds_if_predicate_reverted_to_prefix(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """NON-VACUITY: the bare-name-fires case proves the gate is ALIVE only
        if it REDs under the reverted (dead) predicate. Simulate the revert by
        monkeypatching the predicate back to owner.startswith('pact-'): with a
        BARE owner that check is False → gate silent → adv is None. So the test
        above genuinely depends on the corrected resolution, not on the
        composite signature alone."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        # Revert: the dead prefix predicate on the BARE owner.
        monkeypatch.setattr(
            gate, "is_pact_specialist_owner",
            lambda owner, team_name: isinstance(owner, str)
            and owner.startswith("pact-"),
        )
        assert gate._evaluate_dispatch_variety(_wiring_update("42")) is None

    def test_silent_when_task_b_is_stamped(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """READ+VALIDATE: a stamped Task B → silent (the structural read is
        what makes the gate precise; it does NOT fire on the composite
        signature alone)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder",
                   metadata={"variety": _variety(12)})
        assert gate._evaluate_dispatch_variety(_wiring_update("42")) is None

    def test_silent_when_task_b_stamped_via_fallback(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """A non-canonical but resolvable stamp (score, no total) → silent.
        The gate uses the shared resolve_variety_total, so any shape that
        resolves at write/read time also satisfies the gate."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        v = _variety(0)
        v.pop("total")
        v["score"] = 9
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={"variety": v})
        assert gate._evaluate_dispatch_variety(_wiring_update("42")) is None

    def test_silent_when_owner_not_in_team_config(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """FAIL-OPEN: a bare owner that is NOT a known team member resolves to
        False → gate silent (never strands). The corrected predicate's
        unresolvable-owner floor."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="ghost-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", owner="ghost-coder")
        ) is None

    def test_silent_when_team_config_missing(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """FAIL-OPEN: no team config on disk → _iter_members returns [] →
        is_pact_specialist_owner False → gate silent. Consumer-wide-safe: an
        unresolvable config never strands a dispatch."""
        _ctx(pact_context, monkeypatch, tmp_path)
        # Deliberately do NOT seed team config.
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(_wiring_update("42")) is None


class TestDispatchVarietyNoMisfire:
    """The FIRST-OBSERVABLE-WRITE / no-misfire invariant: never fire at
    TaskCreate(B) or on a partial-wiring TaskUpdate."""

    def test_no_fire_on_taskcreate(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """A TaskCreate (different tool) never reaches the branch."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="pact-backend-coder", metadata={})
        payload = {
            "tool_name": "TaskCreate",
            "tool_input": {"subject": "impl foo", "owner": "pact-backend-coder",
                           "addBlockedBy": ["A"]},
            "agent_type": LEAD,
        }
        assert gate._evaluate_dispatch_variety(payload) is None

    def test_no_fire_on_owner_only_partial_wiring(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """owner set but NO addBlockedBy in the same call → not yet terminal
        → silent."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="pact-backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", add_blocked_by=None)
        ) is None

    def test_no_fire_on_addblockedby_only_partial_wiring(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """addBlockedBy set but NO owner in the same call → silent. This is
        the imPACT blocker-reassign / phase-task-blocking shape (scenario 12):
        every NON-dispatch addBlockedBy use is addBlockedBy-ONLY, so the
        composite never false-positives on it."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="pact-backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", owner=None)
        ) is None


class TestDispatchVarietyCarveOuts:
    """Carve-outs preserve R4's silence guarantees verbatim."""

    def test_silent_non_pact_owner(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """A SOLO_EXEMPT owner resolves to a NON-pact agentType
        (explorer→general-purpose) → is_pact_specialist_owner False → never
        fires (scenario 9: SOLO_EXEMPT agents have non-pact agentTypes, so the
        corrected predicate excludes them naturally — no explicit check)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="explorer", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", owner="explorer")
        ) is None

    def test_silent_teachback_subject(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """A Task-A teachback gate subject is exempt (is_teachback_subject).
        The bare owner RESOLVES (passes the trigger), so the subject carve-out
        is what suppresses it."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42",
                   subject="backend: TEACHBACK for the thing",
                   owner="backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(_wiring_update("42")) is None

    @pytest.mark.parametrize("signal_type", ["blocker", "algedonic"])
    def test_silent_signal_task(
        self, tmp_path, monkeypatch, pact_context, signal_type,
    ):
        """A signal task (completion_type=signal) is exempt via
        is_self_complete_exempt — auditor/blocker signal tasks carry no
        variety obligation. The bare 'auditor' owner RESOLVES to pact-auditor
        (passes the trigger), so the signal carve-out is what suppresses it."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM, members=[
            {"name": "auditor", "agentType": "pact-auditor"},
        ])
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="auditor",
                   metadata={"completion_type": "signal", "type": signal_type})
        assert gate._evaluate_dispatch_variety(_wiring_update(
            "42", owner="auditor")) is None

    def test_silent_secretary_owner(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """LOAD-BEARING carve-out: the secretary (pact-secretary) IS a
        registered specialist, so the bare 'secretary' owner PASSES the
        corrected trigger — meaning is_self_complete_exempt MUST suppress it.
        A secretary-owned wiring write with no variety → SILENT, NOT warn/deny.
        If the carve-out regressed, this would wrongly warn/deny a legit
        secretary dispatch."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="secretary", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", owner="secretary")
        ) is None

    def test_silent_teammate_frame(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """DUAL-MODE: a teammate frame emits nothing (is_lead structural
        discriminator). Short-circuits before owner resolution."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update("42", agent_type=TEAMMATE)
        ) is None


class TestDispatchVarietyPerfGuard:
    """F1 — the extra per-dispatch task-read is BOUNDED: read_task_json must
    NOT be called when the cheap in-memory guards (is_lead / owner-present /
    addBlockedBy-present / taskId-present) fail. Pins the cost-order so a future
    refactor cannot move the disk read ahead of the guards (which would add a
    disk hit to EVERY TaskUpdate in EVERY consumer session, not just genuine
    dispatch-wiring writes)."""

    def _spy_read_task_json(self, monkeypatch):
        """Replace gate.read_task_json with a call-counting spy. Patches the
        name in the GATE module namespace (where it is looked up via the
        module-level `from shared.task_utils import read_task_json`), NOT
        shared.task_utils (where it is defined) — patch-where-looked-up."""
        calls = []
        real = gate.read_task_json

        def _spy(task_id, team_name, *a, **k):
            calls.append((task_id, team_name))
            return real(task_id, team_name, *a, **k)

        monkeypatch.setattr(gate, "read_task_json", _spy)
        return calls

    @pytest.mark.parametrize(
        "frame_desc, frame_factory",
        [
            # is_lead guard: a teammate frame short-circuits first.
            ("teammate_frame",
             lambda: _wiring_update("42", agent_type=TEAMMATE)),
            # owner-absent guard (partial wiring).
            ("owner_absent",
             lambda: _wiring_update("42", owner=None)),
            # addBlockedBy-absent guard (partial wiring).
            ("addblockedby_absent",
             lambda: _wiring_update("42", add_blocked_by=None)),
            # taskId-absent guard.
            ("taskid_absent",
             lambda: {"tool_name": "TaskUpdate", "agent_type": LEAD,
                      "tool_input": {"owner": "backend-coder",
                                     "addBlockedBy": ["A"]}}),
        ],
    )
    def test_no_disk_read_when_cheap_guards_fail(
        self, tmp_path, monkeypatch, pact_context, frame_desc, frame_factory,
    ):
        """Each guard-failing frame must bypass read_task_json entirely."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        calls = self._spy_read_task_json(monkeypatch)
        gate._evaluate_dispatch_variety(frame_factory())
        assert calls == [], (
            f"read_task_json must NOT be called on {frame_desc} "
            f"(cheap guards short-circuit first); got {calls}"
        )

    def test_disk_read_happens_on_a_real_dispatch_wiring_write(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """Counter-case (proves the spy is wired): a genuine wiring write that
        passes every cheap guard DOES read the task — so the test above asserts
        a real short-circuit, not a dead spy."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        calls = self._spy_read_task_json(monkeypatch)
        gate._evaluate_dispatch_variety(_wiring_update("42"))
        assert calls == [("42", TEAM)], (
            f"a real dispatch wiring write must read the linked task once; "
            f"got {calls}"
        )


class TestDispatchVarietyBothModesMatrix:
    """F2 — the is_lead dual-mode discriminator as a single explicit matrix:
    a lead frame FIRES (advisory present); a teammate frame SUPPRESSES (None).
    Consolidates the previously-paired lead-fire / teammate-silent coverage
    into one parametrized case so the both-directions contract reads as a unit.
    """

    @pytest.mark.parametrize(
        "mode, agent_type, expect_fires",
        [
            ("in_process_lead", LEAD, True),
            ("tmux_teammate", TEAMMATE, False),
        ],
    )
    def test_is_lead_matrix(
        self, tmp_path, monkeypatch, pact_context, mode, agent_type,
        expect_fires,
    ):
        """Same unstamped bare-owner wiring write under each frame role:
        lead → advisory; teammate → silent (is_lead structural branch)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        adv = gate._evaluate_dispatch_variety(
            _wiring_update("42", agent_type=agent_type)
        )
        if expect_fires:
            assert adv is not None and "metadata.variety" in adv, (
                f"{mode}: lead frame must fire the advisory; got {adv!r}"
            )
        else:
            assert adv is None, (
                f"{mode}: teammate frame must suppress (is_lead False); "
                f"got {adv!r}"
            )


class TestDispatchVarietyMalformedType:
    """F3 — a variety value of the WRONG TYPE (list / string, not a dict) at
    the gate: resolve_variety_total returns None for it, so the gate treats it
    as the missing-stamp gap and FIRES. Closes the one un-probed malformed
    shape (the dict-shaped malformed cases are covered by the R4 split tests)."""

    @pytest.mark.parametrize(
        "bad_variety",
        [
            pytest.param(["not", "a", "dict"], id="variety_is_list"),
            pytest.param("twelve", id="variety_is_string"),
            pytest.param(12, id="variety_is_bare_int"),
        ],
    )
    def test_fires_on_non_dict_variety(
        self, tmp_path, monkeypatch, pact_context, bad_variety,
    ):
        """A non-dict metadata.variety does not resolve to a total → the gate
        fires the missing-stamp advisory (never crashes, never silently
        passes)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={"variety": bad_variety})
        adv = gate._evaluate_dispatch_variety(_wiring_update("42"))
        assert adv is not None and "metadata.variety" in adv, (
            f"a non-dict variety ({bad_variety!r}) must fire the missing-stamp "
            f"advisory; got {adv!r}"
        )


class TestDispatchVarietyEnvKnobModes:
    """main()-level: PACT_DISPATCH_VARIETY_MODE selects warn / deny / shadow.
    The module reads the knob at import; monkeypatch the resolved constant."""

    def _run_main(self, monkeypatch, capsys, stdin_obj):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_obj)))
        with pytest.raises(SystemExit) as exc:
            gate.main()
        return exc.value.code, capsys.readouterr().out

    def _seed_unstamped(self, tmp_path, monkeypatch):
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})

    def test_warn_mode_additional_context_exit_zero(
        self, tmp_path, monkeypatch, pact_context, capsys,
    ):
        _ctx(pact_context, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "DISPATCH_VARIETY_MODE", "warn")
        self._seed_unstamped(tmp_path, monkeypatch)
        code, out = self._run_main(monkeypatch, capsys, _wiring_update("42"))
        assert code == 0
        hso = json.loads(out)["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert "additionalContext" in hso
        assert "permissionDecision" not in hso

    def test_deny_mode_permission_decision_exit_two(
        self, tmp_path, monkeypatch, pact_context, capsys,
    ):
        """deny mode → permissionDecision:"deny" + exit 2 (the sole
        fail-CLOSED path). Source-proven honor; opt-in only."""
        _ctx(pact_context, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "DISPATCH_VARIETY_MODE", "deny")
        self._seed_unstamped(tmp_path, monkeypatch)
        code, out = self._run_main(monkeypatch, capsys, _wiring_update("42"))
        assert code == 2
        hso = json.loads(out)["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"
        assert hso["hookEventName"] == "PreToolUse"

    def test_shadow_mode_suppresses(
        self, tmp_path, monkeypatch, pact_context, capsys,
    ):
        """shadow mode → no additionalContext, no deny (journal-only
        telemetry; here it suppresses)."""
        _ctx(pact_context, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "DISPATCH_VARIETY_MODE", "shadow")
        self._seed_unstamped(tmp_path, monkeypatch)
        code, out = self._run_main(monkeypatch, capsys, _wiring_update("42"))
        assert code == 0
        assert json.loads(out) == {"suppressOutput": True}

    def test_deny_mode_does_not_deny_stamped_task_b(
        self, tmp_path, monkeypatch, pact_context, capsys,
    ):
        """Even in deny mode, a STAMPED Task B is never denied — the
        structural read gates the deny. Counter-pin against a deny-on-every-
        wiring-write regression."""
        _ctx(pact_context, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "DISPATCH_VARIETY_MODE", "deny")
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder",
                   metadata={"variety": _variety(12)})
        code, out = self._run_main(monkeypatch, capsys, _wiring_update("42"))
        assert code == 0
        assert json.loads(out) == {"suppressOutput": True}

    @pytest.mark.parametrize("env_value, expected", [
        ("deny", "deny"),
        ("DENY", "deny"),       # case-folded
        (" deny ", "deny"),     # whitespace-stripped
        ("Deny", "deny"),
        (" shadow\t", "shadow"),
        ("warn", "warn"),
        ("", "deny"),           # empty → the DECLARED default
        ("bogus", "deny"),      # unknown → the DECLARED default
        ("denY ", "deny"),
    ])
    def test_env_knob_strip_lower_normalization(
        self, monkeypatch, env_value, expected,
    ):
        """The PACT_DISPATCH_VARIETY_MODE read normalizes with .strip().lower()
        BEFORE the membership check, then falls back to the option's DECLARED
        default for anything not in the allowed set. NON-TAUTOLOGICAL: reloads
        the module under the real env value so it exercises the actual
        os.environ read + normalize + fallback (not the already-resolved
        constant).

        WHAT THE FALLBACK ROWS NOW ASSERT, because their polarity inverted when
        this gate was armed: they used to prove "an unrecognised token cannot
        accidentally ENABLE enforcement". The declared default is now `deny`, so
        what they prove instead is the property that survives the flip — an
        unrecognised token resolves to the DECLARED DEFAULT and to nothing else.
        It is never derived from the token and never lands outside the allowed
        set. The consumer-facing consequence is real and is the reason these
        rows are kept rather than deleted: a MISSPELLED opt-down (`warm`,
        `Warnn`) still enforces, so a consumer who means to opt down must spell
        it correctly and read the resolver's stderr line.

        The 'warn' row is the discriminator: if the fallback ever stopped
        consulting the registry and hardcoded a mode, that row and the fallback
        rows could not both hold."""
        import importlib
        monkeypatch.setenv("PACT_DISPATCH_VARIETY_MODE", env_value)
        reloaded = importlib.reload(gate)
        try:
            assert reloaded.DISPATCH_VARIETY_MODE == expected
        finally:
            # Restore the module's default-env resolution for sibling tests.
            monkeypatch.delenv("PACT_DISPATCH_VARIETY_MODE", raising=False)
            importlib.reload(gate)

    def test_deny_mode_fails_open_when_evaluation_raises(
        self, tmp_path, monkeypatch, pact_context, capsys,
    ):
        """ADVERSARIAL fail-OPEN invariant: in DENY mode, an exception inside
        _evaluate_dispatch_variety must NOT brick the TaskUpdate — main()
        catches it, sets variety_gap=None, and falls through to suppress
        (exit 0), NEVER exit-2/deny. The deny is fail-CLOSED only on a
        CONFIRMED missing stamp, never on evaluation uncertainty. A consumer-
        wide deny gate that denied on its own crash would strand every
        legitimate dispatch wiring write whenever the evaluator hit a malformed
        frame — strictly worse than the gap it guards."""
        _ctx(pact_context, monkeypatch, tmp_path)
        monkeypatch.setattr(gate, "DISPATCH_VARIETY_MODE", "deny")
        self._seed_unstamped(tmp_path, monkeypatch)

        def _boom(_input_data):
            raise RuntimeError("simulated evaluator crash")

        monkeypatch.setattr(gate, "_evaluate_dispatch_variety", _boom)
        code, out = self._run_main(monkeypatch, capsys, _wiring_update("42"))
        assert code == 0, "deny mode must fail-OPEN (exit 0) on evaluator crash"
        parsed = json.loads(out)
        assert "permissionDecision" not in parsed.get(
            "hookSpecificOutput", {}
        ), "a crash must never produce a deny verdict"


# =============================================================================
# is_pact_specialist_owner — the corrected-predicate resolution helper.
# Direct unit coverage of the bare owner → agentType → registry resolution +
# the fail-CLOSED-to-False contract (which composes to gate fail-OPEN).
# =============================================================================
class TestIsPactSpecialistOwner:
    def test_true_for_bare_specialist_owner(self, tmp_path, monkeypatch):
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("backend-coder", TEAM) is True

    def test_true_for_secretary_owner(self, tmp_path, monkeypatch):
        """pact-secretary IS a registered specialist → True. (The gate's
        is_self_complete_exempt carve-out, NOT this helper, suppresses it.)"""
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("secretary", TEAM) is True

    def test_false_for_solo_exempt_owner(self, tmp_path, monkeypatch):
        """explorer→general-purpose is a NON-pact agentType (no
        agents/general-purpose.md) → False."""
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("explorer", TEAM) is False

    def test_false_for_unknown_owner(self, tmp_path, monkeypatch):
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("ghost", TEAM) is False

    def test_false_for_missing_team_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("backend-coder", TEAM) is False

    def test_false_for_empty_inputs(self):
        from shared.dispatch_helpers import is_pact_specialist_owner
        assert is_pact_specialist_owner("", TEAM) is False
        assert is_pact_specialist_owner("backend-coder", "") is False
        assert is_pact_specialist_owner(None, TEAM) is False

    def test_false_and_never_raises_on_iter_members_exception(self, monkeypatch):
        """The bare-except fail-closed wrap: if _iter_members raises (e.g. the
        get_claude_config_dir→Path.home RuntimeError seam that ESCAPES
        _iter_members' own typed except), the helper returns False and never
        propagates — so the gate fail-OPENS rather than crashing."""
        import shared.pact_context as ctx_module
        from shared.dispatch_helpers import is_pact_specialist_owner

        def _raise(team_name, teams_dir=None):
            raise RuntimeError("simulated config-dir resolution failure")

        monkeypatch.setattr(ctx_module, "_iter_members", _raise)
        assert is_pact_specialist_owner("backend-coder", TEAM) is False


# =============================================================================
# The disk/incoming OVERLAY — the cardinal over-block fix.
# =============================================================================
def _wiring_update_with_metadata(task_id, metadata, **kw):
    """A wiring write that ALSO carries metadata — the atomic wire+stamp."""
    payload = _wiring_update(task_id, **kw)
    payload["tool_input"]["metadata"] = metadata
    return payload


class TestDispatchVarietyReadsTheIncomingWrite:
    """THE CARDINAL CASE. `TaskUpdate(B, owner=..., addBlockedBy=[A],
    metadata={"variety": {...}})` wires and stamps in ONE call. At PreToolUse
    the stamp is in the write and not yet on disk, so a disk-only read REFUSES
    a faithful single command — which for a control that can deny is the
    failure that must never ship.

    MUTATION THAT REDDENS: in `_evaluate_dispatch_variety`, replace
    `merged_variety_stamp(tool_input, task)` with the disk-only read
    (`task.get("metadata", {}).get("variety")`). Every test in this class
    flips to an advisory. That is the base behaviour, measured.
    """

    def test_atomic_wire_and_stamp_is_SILENT(
        self, tmp_path, monkeypatch, pact_context,
    ):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        adv = gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"variety": _variety(12)}),
        )
        assert adv is None, (
            "a wiring write CARRYING a complete variety stamp was refused — "
            f"this is the cardinal over-block: {adv!r}"
        )

    def test_atomic_stamp_survives_a_task_with_no_metadata_key(
        self, tmp_path, monkeypatch, pact_context,
    ):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder")
        assert gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"variety": _variety(12)}),
        ) is None

    def test_atomic_stamp_via_the_variety_score_sibling(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """The non-canonical spelling resolve_variety_total documents as
        candidate 3. Reaching it needs the overlay to hand the resolver a DICT
        rather than None — the resolver early-returns on a non-dict `variety`
        and never consults the sibling."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"variety_score": 12}),
        ) is None

    def test_a_ONE_KEY_restamp_does_not_flip_a_stamped_task_to_unstamped(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """The LEVEL pin at the gate. Under a metadata-level merge the
        incoming `{"novelty": 4}` replaces the whole disk variety, nothing
        resolves, and a correctly-stamped dispatch is refused."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={"variety": _variety(12)})
        assert gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"variety": {"novelty": 4}}),
        ) is None

    def test_STILL_DENIES_when_neither_side_carries_a_stamp(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """The other direction, and the reason the overlay is not a hole: an
        incoming metadata that carries no variety leaves the gate firing."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={})
        assert gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"handoff": {"produced": ["f"]}}),
        ) is not None

    def test_an_incoming_write_that_JUNKS_the_only_resolving_key_denies(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """The single new deny this overlay opens, asserted so it is a decision
        rather than a surprise. The write itself destroys the stamp — post-write
        the task holds `{"total": "x"}` — so the refusal is truthful, and the
        message sends the caller to the VALUES rather than to the field list."""
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        _seed_task(tmp_path, TEAM, "42", subject="impl foo",
                   owner="backend-coder", metadata={"variety": {"total": 12}})
        adv = gate._evaluate_dispatch_variety(
            _wiring_update_with_metadata("42", {"variety": {"total": "x"}}),
        )
        assert adv is not None and "does NOT resolve" in adv


class TestDispatchVarietyDiagnosisSplit:
    """ABSENT vs PRESENT-BUT-UNRESOLVABLE. One trigger, two messages, because
    the remedies are opposite: 'write the block' versus 'the block you wrote
    does not resolve'. NOT a carve-out — both still fire.

    MUTATION THAT REDDENS: make `_variety_stamp_attempted` return a constant.
    Either the absent tests or the unresolvable tests go red, whichever
    constant is chosen.
    """

    def _adv(self, tmp_path, monkeypatch, pact_context, disk, incoming=None):
        _ctx(pact_context, monkeypatch, tmp_path)
        _seed_team_config(tmp_path, monkeypatch, TEAM)
        kw = {"subject": "impl foo", "owner": "backend-coder"}
        if disk is not None:
            kw["metadata"] = disk
        _seed_task(tmp_path, TEAM, "42", **kw)
        frame = (_wiring_update("42") if incoming is None
                 else _wiring_update_with_metadata("42", incoming))
        return gate._evaluate_dispatch_variety(frame)

    @pytest.mark.parametrize("disk,incoming", [
        pytest.param({}, None, id="no_metadata_content"),
        pytest.param(None, None, id="no_metadata_key"),
        pytest.param({}, {"handoff": {}}, id="incoming_without_variety"),
    ])
    def test_nothing_written_says_ADD_the_block(
        self, tmp_path, monkeypatch, pact_context, disk, incoming,
    ):
        adv = self._adv(tmp_path, monkeypatch, pact_context, disk, incoming)
        assert adv is not None
        assert "no metadata.variety stamp at all" in adv
        assert "does NOT resolve" not in adv

    @pytest.mark.parametrize("disk,incoming", [
        pytest.param({"variety": {}}, None, id="empty_variety_dict"),
        pytest.param({"variety": "12"}, None, id="variety_is_a_string"),
        pytest.param({"variety": {"total": 99}}, None, id="total_out_of_range"),
        pytest.param({"variety": {"total": True}}, None, id="total_is_a_bool"),
        pytest.param({"variety": {"total": "12"}}, None, id="total_is_a_string"),
        pytest.param({"variety_score": "x"}, None, id="sibling_is_junk"),
        pytest.param({}, {"variety": {}}, id="incoming_empty_variety"),
    ])
    def test_something_written_says_RE_READ_the_values(
        self, tmp_path, monkeypatch, pact_context, disk, incoming,
    ):
        adv = self._adv(tmp_path, monkeypatch, pact_context, disk, incoming)
        assert adv is not None
        assert "does NOT resolve" in adv
        assert "no metadata.variety stamp at all" not in adv, (
            "a consumer who DID stamp is being told to add the block — that "
            "sends them hunting for a missing field instead of at the values"
        )

    def test_BOTH_states_still_deny(
        self, tmp_path, monkeypatch, pact_context,
    ):
        """The non-carve-out. If the unresolvable branch is ever softened into
        a pass, this is what reddens."""
        absent = self._adv(tmp_path, monkeypatch, pact_context, {})
        unresolvable = self._adv(
            tmp_path, monkeypatch, pact_context, {"variety": {"total": 99}})
        assert absent is not None and unresolvable is not None
        assert absent != unresolvable, "the two states must not share a message"
