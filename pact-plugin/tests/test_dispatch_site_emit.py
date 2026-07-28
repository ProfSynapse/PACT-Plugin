"""dispatch_site — the hook-side emit that carries the coverage DENOMINATOR.

One event per dispatched Task-B, emitted at the owner-wiring TaskUpdate. The
event's EXISTENCE is a dispatch site; the OPTIONAL `variety` within it is the
numerator. Both terms come from one stream, which is what makes coverage > 1.0
structurally impossible rather than merely guarded.

WHY THE TaskUpdate BRANCH AND NOT BESIDE dispatch_variety: that emit lives in
the TaskCreate branch and keys on metadata.variety PRESENCE, because
TaskCreate(B) leaves owner empty — an owner-wiring predicate placed there would
return False forever and Q5 would stay dark with every test still green. These
tests pin the emit to the branch where an owner-wiring write is observable.

Each step of the evaluation order gets a negation test, because every one of
them fails SILENTLY: a wrong frame gate zeroes the population, a dropped
team_name precondition craters coverage while the number still renders, and a
missing dedup claim turns one dispatch into two sites. None of those produce an
exception or a red anywhere else.

Drives tlg.evaluate_lifecycle against a real on-disk team config, task store
and O_EXCL marker root, with tlg.append_event spied to capture events.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import task_lifecycle_gate as tlg  # noqa: E402
import shared.session_journal as sj  # noqa: E402

TEAM = "test-team"
LEAD = "PACT:pact-orchestrator"
TEAMMATE = "pact-devops-engineer"

MEMBERS = [
    {"name": "backend-coder", "agentType": "pact-backend-coder"},
    {"name": "auditor", "agentType": "pact-auditor"},
    {"name": "secretary", "agentType": "pact-secretary"},
    {"name": "explorer", "agentType": "general-purpose"},
]

# The 5 canonical keys the projection must keep. The *_rationale strings are
# calibration noise in a GC-immune journal and must be dropped.
CANONICAL = {"novelty", "scope", "uncertainty", "risk", "total"}

STAMP = {
    "novelty": 3, "novelty_rationale": "new shape",
    "scope": 2, "scope_rationale": "two files",
    "uncertainty": 2, "uncertainty_rationale": "closed spec",
    "risk": 4, "risk_rationale": "silent failure modes",
    "total": 11,
}


@pytest.fixture
def env(tmp_path, monkeypatch, pact_context):
    """Real team config + specialist registry + task store + marker root."""
    import shared.dispatch_helpers as dh
    import shared.pact_context as ctx

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    team_dir = tmp_path / ".claude" / "teams" / TEAM
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / "config.json").write_text(
        json.dumps({"leadSessionId": "s1", "members": MEMBERS}), encoding="utf-8"
    )

    plugin_root = tmp_path / "plugin"
    agents = plugin_root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    for m in MEMBERS:
        at = m["agentType"]
        if at.startswith("pact-"):
            (agents / f"{at}.md").write_text(f"---\nname: {at}\n---\n", "utf-8")
    monkeypatch.setattr(ctx, "get_plugin_root", lambda: str(plugin_root))
    dh._specialist_registry.cache_clear()

    pact_context(team_name=TEAM, session_id="s1", project_dir=str(tmp_path))
    return tmp_path


@pytest.fixture
def events(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(sj, "append_event", lambda e: captured.append(e) or True)
    return captured


def seed(tmp_path, task_id="42", subject="backend-coder: implement the thing",
         owner="backend-coder", metadata=None):
    d = tmp_path / ".claude" / "tasks" / TEAM
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}.json").write_text(json.dumps({
        "id": task_id, "subject": subject, "owner": owner,
        "metadata": metadata if metadata is not None else {},
    }), encoding="utf-8")


def wiring(task_id="42", *, owner="backend-coder", blockers=("41",),
           agent_type=LEAD, metadata=None, session_id=None):
    ti = {"taskId": task_id, "status": "in_progress"}
    if owner is not None:
        ti["owner"] = owner
    if blockers:
        ti["addBlockedBy"] = list(blockers)
    if metadata is not None:
        ti["metadata"] = metadata
    payload = {"tool_name": "TaskUpdate", "tool_input": ti}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    if session_id is not None:
        payload["session_id"] = session_id
    return payload


def sites(events):
    return [e for e in events if e.get("type") == "dispatch_site"]


class TestEmitsAtTheWiringWrite:
    def test_stamped_dispatch_emits_one_site_with_variety(self, env, events):
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring())
        s = sites(events)
        assert len(s) == 1
        assert s[0]["task_id"] == "42"
        assert set(s[0]["variety"]) == CANONICAL, "rationales must be dropped"
        assert s[0]["variety"]["total"] == 11

    def test_unstamped_dispatch_emits_a_site_with_NO_variety(self, env, events):
        """The coverage GAP. The event must still fire — it is the denominator
        — and `variety` must be ABSENT rather than empty or null, because
        absence is what the consumer reads as un-stamped."""
        seed(env, metadata={})
        tlg.evaluate_lifecycle(wiring())
        s = sites(events)
        assert len(s) == 1
        assert "variety" not in s[0]

    def test_incoming_stamp_in_the_same_write_is_not_missed(self, env, events):
        """If a lead stamps variety in the SAME update that wires the owner, a
        disk-only read would record an un-stamped site for a stamped dispatch
        — a false negative biasing coverage DOWN."""
        seed(env, metadata={})
        tlg.evaluate_lifecycle(wiring(metadata={"variety": STAMP}))
        s = sites(events)
        assert len(s) == 1 and s[0]["variety"]["total"] == 11

    def test_incoming_overlays_disk(self, env, events):
        seed(env, metadata={"variety": {**STAMP, "total": 4}})
        tlg.evaluate_lifecycle(wiring(metadata={"variety": {"total": 16}}))
        assert sites(events)[0]["variety"]["total"] == 16

    def test_partial_restamp_does_NOT_wipe_the_complete_disk_variety(
        self, env, events
    ):
        """The merge happens at the VARIETY-KEY level, not the metadata level,
        and the distinction is the whole safety of the overlay.

        A metadata-level `{**disk_md, **incoming_md}` would let a partial
        same-write re-stamp REPLACE the complete stamp wholesale: the four
        dimensions vanish, only the re-stamped key survives, and a
        correctly-stamped dispatch is recorded as a malformed one. That is the
        very false-negative the overlay was introduced to prevent, arriving by
        a different route. Here a one-key incoming stamp must overlay that key
        and leave the other four intact."""
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(metadata={"variety": {"risk": 1}}))
        v = sites(events)[0]["variety"]
        assert v["risk"] == 1, "the incoming key must win"
        assert set(v) == CANONICAL, "the other four dimensions must survive"
        assert v["novelty"] == 3 and v["total"] == 11


class TestEvaluationOrderNegations:
    """Every one of these fails silently in production. Each gets its own arm."""

    def test_non_canonical_frame_does_not_emit(self, env, events):
        """A tmux teammate frame (session_id != leadSessionId) writes a
        DIFFERENT journal; emitting there silos the event."""
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(
            wiring(agent_type=TEAMMATE, session_id="other-session")
        )
        assert sites(events) == []

    def test_class_3_lead_without_agent_type_STILL_emits(self, env, events):
        """THE ARM THAT MAKES THE FRAME-GATE CHOICE LOAD-BEARING.

        A lead launched without `--agent` carries NO agent_type, so is_lead is
        False — but its session_id IS the team's leadSessionId, so it writes
        the canonical journal and MUST emit. is_canonical_journal_frame
        survives this via its topology leg; is_lead does not.

        Without this arm the gate choice is untested: the tmux-teammate arm
        above is rejected by BOTH predicates, so swapping the gate to is_lead
        would leave the suite green while silently zeroing the entire
        population in exactly the frame the design named Class 3."""
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(agent_type=None, session_id="s1"))
        assert len(sites(events)) == 1, (
            "a no---agent lead writes the canonical journal and must emit"
        )

    def test_team_name_gate_holds_when_the_leg_that_subsumes_it_stops_blocking(
        self, env, events, monkeypatch
    ):
        """PINS A GUARD THAT IS OTHERWISE UNOBSERVABLE, by mutating what
        subsumes it.

        Step (2) — the team_name precondition — is strictly subsumed today by
        step (4)'s is_pact_specialist_owner, which also fails closed on an
        empty team. No ordinary input exists where step 2 rejects and step 4
        accepts, so simply deleting step 2 reddens nothing and a future reader
        sees a guard no test defends. Annotating that asks them to believe a
        comment; this makes the suite disagree with them instead.

        Forcing the SUBSUMING leg open isolates step 2 as the only thing left
        standing, so the arm reddens if step 2 is deleted AND it pins the
        subsumption assumption itself — if is_pact_specialist_owner ever stops
        failing closed, this keeps the guard honest rather than both going
        quiet together.

        The positive control matters: without it, an assertion of 'no emit'
        would pass even if the fixture could never emit at all."""
        seed(env, metadata={"variety": STAMP})
        monkeypatch.setattr(tlg, "is_pact_specialist_owner", lambda o, t: True)

        # POSITIVE CONTROL — subsuming leg forced open, team_name VALID:
        # the emit fires, proving this fixture can produce an event.
        tlg.evaluate_lifecycle(wiring())
        assert len(sites(events)) == 1, "control: fixture must be able to emit"

        # THE GUARDED CASE — team_name unresolvable. Only step (2) stands here.
        events.clear()
        monkeypatch.setattr(
            tlg.pact_context, "get_pact_context", lambda: {"team_name": ""}
        )
        tlg.evaluate_lifecycle(wiring("43"))
        assert sites(events) == [], (
            "an unresolvable team_name must stop the emit even when the "
            "specialist leg no longer blocks it"
        )

    def test_partial_wiring_owner_only_does_not_emit(self, env, events):
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(blockers=()))
        assert sites(events) == []

    def test_partial_wiring_blockers_only_does_not_emit(self, env, events):
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(owner=None))
        assert sites(events) == []

    def test_non_specialist_owner_does_not_emit(self, env, events):
        seed(env, owner="explorer", metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(owner="explorer"))
        assert sites(events) == []

    def test_owner_absent_from_team_config_does_not_emit(self, env, events):
        seed(env, owner="ghost", metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(owner="ghost"))
        assert sites(events) == []

    def test_teachback_task_a_does_not_emit(self, env, events):
        seed(env, subject="backend-coder: TEACHBACK for the thing",
             metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring())
        assert sites(events) == []

    def test_teachback_exempt_owner_does_not_emit(self, env, events):
        """The secretary is teachback-exempt: its task-system work is rote and
        skill-defined, so it is not a variety-eligible dispatch. Keying on
        is_teachback_exempt (NOT is_self_complete_exempt) is what makes this
        arm correct — the two answer different questions."""
        seed(env, owner="secretary", subject="secretary: harvest",
             metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring(owner="secretary"))
        assert sites(events) == []


class TestDedup:
    def test_two_owner_bearing_writes_yield_ONE_site(self, env, events):
        """Without the O_EXCL claim a repeat wiring write doubles the
        denominator: a correctly-stamped dispatch reads coverage 0.5."""
        seed(env, metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring())
        tlg.evaluate_lifecycle(wiring())
        assert len(sites(events)) == 1

    def test_distinct_tasks_are_not_deduped_against_each_other(self, env, events):
        seed(env, task_id="42", metadata={"variety": STAMP})
        seed(env, task_id="43", metadata={"variety": STAMP})
        tlg.evaluate_lifecycle(wiring("42"))
        tlg.evaluate_lifecycle(wiring("43"))
        assert {e["task_id"] for e in sites(events)} == {"42", "43"}

    def test_marker_key_constant_must_be_non_empty(self, env):
        """NON-VACUITY ON THE THIRD KEY COMPONENT — the pin that catches a
        future 'simplification' dropping the constant.

        already_emitted's degenerate guard FAIL-OPENS on an empty occupant: no
        marker is written, nothing raises, and dedup silently never fires while
        looking like it works. Every other dedup test would still pass. This
        arm asserts (a) the hazard is real, so the constant is load-bearing
        rather than decorative, and (b) the constant this module actually binds
        is not falsy.

        Asserted against the marker primitive directly, because the wrapper
        hard-binds the constant and therefore cannot express the broken case."""
        from shared.agent_handoff_marker import already_emitted

        # (a) the hazard: an empty occupant never suppresses.
        empty = [
            already_emitted(TEAM, "9001", "", namespace=".probe_ns")
            for _ in range(2)
        ]
        assert empty == [False, False], (
            "an empty occupant must fail open — if this ever starts deduping, "
            "the constant below is no longer load-bearing and this test should "
            "be re-derived rather than deleted"
        )

        # (b) what the module binds is not falsy, and does suppress.
        assert tlg._DISPATCH_SITE_MARKER_KEY, "marker key must be non-empty"
        real = [
            already_emitted(TEAM, "9002", tlg._DISPATCH_SITE_MARKER_KEY,
                            namespace=tlg.DISPATCH_SITE_MARKER_NAMESPACE)
            for _ in range(2)
        ]
        assert real == [False, True], "the bound constant must claim then dedup"

    def test_failed_write_rolls_the_claim_back(self, env, monkeypatch):
        """A claim whose write then failed must be released, or the site is
        suppressed forever with no journal entry to show for it."""
        seed(env, metadata={"variety": STAMP})
        monkeypatch.setattr(sj, "append_event", lambda e: False)
        tlg.evaluate_lifecycle(wiring())

        captured: list[dict] = []
        monkeypatch.setattr(sj, "append_event", lambda e: captured.append(e) or True)
        tlg.evaluate_lifecycle(wiring())
        assert len(sites(captured)) == 1, "rollback did not release the marker"


class TestAntiWidening:
    def test_signal_shaped_dispatch_STILL_emits(self, env, events):
        """TRIPWIRE. Signal-shaped dispatches are stamped 0-of-6 — a clean
        categorical zero that looks symmetric with the secretary's 0-of-51 and
        invites 'exempt them too'. Whether completion_type is a variety
        boundary is an UNRULED PROTOCOL QUESTION, and the current ruling is the
        opposite: auditor observation dispatches are genuine coverage gaps
        whose remedy is stamping, not exempting. This reddens if anyone adds a
        completion_type / metadata.type exemption to the emit."""
        seed(env, owner="auditor", subject="auditor: observe wave 2",
             metadata={"completion_type": "signal", "type": "blocker"})
        tlg.evaluate_lifecycle(wiring(owner="auditor"))
        s = sites(events)
        assert len(s) == 1, "a signal-shaped dispatch must COUNT as a site"
        assert "variety" not in s[0], "and it counts as an un-stamped one"
