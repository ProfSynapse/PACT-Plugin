"""#1507 resume team-realign — comprehensive TEST-phase matrix for branch-3 census.

After a clean end-session, ``claude --resume <old-id>`` provisions a NEW team +
task store under a NEW id while every hook frame still carries the OLD session
id; the OLD team config is reaped, so #989's identity-match cannot align and
``dispatch_gate`` denied every spawn (#1507). The fix (fork b) is a branch-3
census in ``_resolve_aligned_team_name``: when identity-match failed, the
persisted team's config is ABSENT, and the session journal shows prior team
ACTIVITY, the single LIVE re-provisioned team (config ``leadSessionId`` != the
persisted id + sibling ``tasks/<dir>/`` mtime within
``RESUME_CENSUS_RECENCY_SECONDS``) wins; zero or >= 2 candidates fail safe to
the stale default. Convergence persists via the EXISTING marker-writer
write-back; the gate's stale-team remedy texts now name the measured manual
repoint.

This file owns the plan's Test-phase matrix (docs/plans/
1507-resume-team-realign-plan.md, cells i-xi) at the GATE level, end-to-end
through ``dispatch_gate.main()`` wherever the plan's assertion is a gate
decision, plus resolver-level legs where the cell pins a predicate directly.
The resolver-coder's focused verification lives in
``test_team_name_detect_align.py`` section 14 (TestBranch3ResumeCensus); the
standing both-modes merge gate lives in ``test_team_name_resolution_both_modes.py``
(sibling files — this file adds the #1507 scenario family without polluting
either).

Assertions are CONTRACT-FIRST (resolved team / gate decision / message
markers), never fork-internals. Non-vacuity by store placement: in every ALLOW
cell the owner's task is seeded ONLY under the team the cell must resolve, so
an ALLOW is reachable only via the intended resolution path. mtime
determinism: every "fresh" store in this file is left at CREATION time —
inside the 900 s window on any conceivable clock — with no clock-relative
arithmetic; the aged-store arm (``os.utime``-pinned mtimes) lives in the
sibling's section 14 (test_team_name_detect_align.py).

COUNTER-TEST-BY-REVERT (source-only; the fix commits bundle source with their
own focused tests, so a whole-commit revert would mask). MEASURED (before the
i-b Desktop leg was xfailed per the lead ruling; the xfail does not change
the FAIL counts — an xfailed cell reports xfailed, not failed):
  git checkout 1c722640^ -- pact-plugin/hooks/shared/pact_context.py
    -> {6 failed, 1 xfailed, 9 passed}: the six census-dependent cells
       {i, i-b incident-shape, viii, ix (2 legs), x} FAIL; i-b Desktop-shape
       reports xfailed (it is xfail-red on the fixed tree too — the accepted
       branch-2 dead-dir residual, see that test's docstring). Cells
       ii/v/vi/vii stay GREEN (fail-safe arms whose pass-condition does not
       require the census to exist); iii/iv stay GREEN (empty-SSOT /
       identity-match are pre-existing branches the census must not
       disturb); xi stays GREEN (its text comes from 6c676bbb).
  git checkout 6c676bbb^ -- pact-plugin/hooks/dispatch_gate.py
    -> {2 failed, 1 xfailed, 13 passed}: the two message-marker cells
       {ii, xi} FAIL; i-b Desktop reports xfailed (resolution axis
       untouched).
  Restore: git checkout HEAD -- <path>; git diff --quiet -- <path> exits 0.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

_SUPPRESS_EXPECTED = {"suppressOutput": True}
_NAME = "tester"

# ── Ids / names: the OLD (persisted, reaped) world vs the NEW (live) one ──────
# OLD_SID is the session id every hook frame carries (the platform model: the
# OLD id remains the SESSION id; the NEW id is the TEAM provisioning id).
OLD_SID = "0001639f-a74f-41c4-bd0b-93d9d206e7f7"
OLD_TEAM = "session-0001639f"          # persisted-but-reaped stale default
# The NEW team's provisioning id + the two dir-naming shapes it can take.
NEW_SID = "aaaa1111-2222-4333-8444-555566667777"
NEW_TEAM_ID8 = "session-aaaa1111"      # CLI naming (the #1507 incident shape)
NEW_UUID_DIR = NEW_SID                 # bare full UUID (Desktop composition)
# A second live candidate (the ambiguity arm) + a foreign concurrent session.
AMBIG_SID = "beefbeef-1111-4222-8333-444455556666"
AMBIG_TEAM = "session-beefbeef"
FOREIGN_SID = "cafe1234-5678-4abc-9def-0123456789ab"
FOREIGN_TEAM = "session-cafe1234"
# A tmux-shaped spawn-frame id (topology axis — != the lead/persisted id).
TMUX_FRAME_SID = "ffff8888-bbbb-4ccc-9ddd-eeeeeeeeeeee"

# Message markers (contract-first; the exact constants live in
# dispatch_gate.py — these substrings are the STABLE contract each text owns).
_CAUSE2_RECOVERY_MARKER = (
    "Recovery: set team_name in the OLD session's pact-session-context.json"
)
_HINT_MARKER = "Working recovery"
_STALE_BLOCK_MARKER = "stale session block"
_ENUMERATION_HEADER = "DIAGNOSIS — this gate did not OBSERVE"
_FORBIDDEN_INERT_PHRASES = (
    "bootstrap ritual rewrites",
    "bootstrap also rewrites",
    "rewrites those records",
)


# ── seeding helpers (self-contained; modeled on the sibling files) ───────────


def _seed_plugin(plugin_root: Path, agents=("pact-architect",)):
    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for stem in agents:
        (agents_dir / f"{stem}.md").write_text(f"---\nname: {stem}\n---\n")


def _write_context(monkeypatch, tmp_path, plugin_root, *, team_name,
                   session_id):
    """Persist the SSOT context and point _context_path at it (caches cleared,
    init stubbed so dispatch_gate.main cannot re-derive the path from the
    spawn frame's own session_id)."""
    import shared.pact_context as ctx_module

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ctx_path = tmp_path / "pact-session-context.json"
    ctx_path.write_text(
        json.dumps(
            {
                "team_name": team_name,
                "session_id": session_id,
                "project_dir": str(tmp_path / "project"),
                "plugin_root": str(plugin_root),
                "started_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ctx_module, "_context_path", ctx_path)
    monkeypatch.setattr(ctx_module, "_cache", None)
    monkeypatch.setattr(ctx_module, "init", lambda input_data: None)
    import shared.dispatch_helpers as dh
    dh._specialist_registry.cache_clear()
    return ctx_path


def _seed_team_store(config_root, *, team_name, lead_session_id, members=(),
                     tasks=()):
    """Platform-shaped team store under a CONFIG ROOT (the dir
    get_claude_config_dir() resolves to — tmp/.claude for the default-root
    worlds, the scratch root itself for the CLAUDE_CONFIG_DIR cell):
    teams/{team}/config.json (name + leadSessionId + members) plus
    tasks/{team}/*.json task files."""
    team_dir = config_root / "teams" / team_name
    team_dir.mkdir(parents=True, exist_ok=True)
    config = {"name": team_name, "members": [{"name": m} for m in members]}
    if lead_session_id is not None:
        config["leadSessionId"] = lead_session_id
    (team_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    tasks_dir = config_root / "tasks" / team_name
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for i, (owner, status) in enumerate(tasks):
        (tasks_dir / f"task_{i}.json").write_text(
            json.dumps({"id": str(i), "owner": owner, "status": status}),
            encoding="utf-8",
        )
    return team_dir


def _seed_dead_team_dir(tmp_path, *, team_name, with_inboxes=True):
    """A REAPED team dir: present on disk with the half-formed witness but NO
    config.json (the end-session reaper removes config while the dir survives).
    This is the adversarial substrate — its inboxes/ satisfies branch-2's
    witness whenever the dir is named with the bare OLD session uuid."""
    team_dir = tmp_path / ".claude" / "teams" / team_name
    team_dir.mkdir(parents=True, exist_ok=True)
    if with_inboxes:
        (team_dir / "inboxes").mkdir(exist_ok=True)
    assert not (team_dir / "config.json").exists()
    return team_dir


def _seed_session_journal(monkeypatch, tmp_path, event_types):
    """Write the session journal at the dir get_session_dir() points at (the
    branch-3 witness's read location), one event per given type. Must run
    AFTER _write_context (the session dir derives from the persisted
    context)."""
    import shared.pact_context as ctx_module

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    session_dir = Path(ctx_module.get_session_dir())
    session_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"v": 1, "type": t, "ts": "2026-08-24T00:00:00Z"})
        for t in event_types
    ]
    (session_dir / "session-journal.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return session_dir


def _make_spawn(team_name_arg="ignored-by-platform"):
    """A specialist spawn frame; the team_name arg is platform-ignored, kept
    deliberately wrong so it can never be the resolution source."""
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "spawn-frame-session",
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": "pact-architect",
            "name": _NAME,
            "team_name": team_name_arg,
            "prompt": "Standard mission. Check TaskList for tasks assigned to you.",
        },
    }


def _run_dispatch(spawn, capsys):
    from dispatch_gate import main
    with patch("sys.stdin", io.StringIO(json.dumps(spawn))):
        with pytest.raises(SystemExit) as exc:
            main()
    out = capsys.readouterr().out.strip()
    return exc.value.code, (json.loads(out) if out else {})


def _reset_aligned_cache():
    import shared.pact_context as ctx_module
    ctx_module._aligned_cache = None


def _seed_census_world(monkeypatch, tmp_path, *, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID, journal_events=("task_claimed",),
                       with_journal=True, tasks=((_NAME, "pending"),)):
    """The canonical #1507 world: OLD team config REAPED (dir absent), the
    live re-provisioned team present with a fresh task store carrying the
    owner's task (non-vacuity: an ALLOW is reachable ONLY by resolving the
    live team), and a lived-session journal for the branch-3 witness."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(
        monkeypatch, tmp_path, plugin_root,
        team_name=OLD_TEAM, session_id=OLD_SID,
    )
    _reset_aligned_cache()
    _seed_team_store(
        tmp_path / ".claude", team_name=live_team,
        lead_session_id=live_lead_sid, members=(), tasks=tasks,
    )
    # The stale team is FULLY reaped: neither its config nor its dir exists.
    assert not (tmp_path / ".claude" / "teams" / OLD_TEAM).exists()
    if with_journal:
        _seed_session_journal(monkeypatch, tmp_path, list(journal_events))
    return plugin_root


# ══════════════════════════════════════════════════════════════════════════════
# (i) THE REALIGN CELL — reaped old config + single fresh candidate + lived
#     journal -> census returns the live team; the gate ALLOWs.
# ══════════════════════════════════════════════════════════════════════════════


def test_i_census_resolves_live_team_gate_allows(tmp_path, monkeypatch, capsys):
    """CELL i — the #1507 incident shape end-to-end: persisted OLD team +
    OLD session id, old team config reaped, the live re-provisioned team
    (session-<new8> naming, NEW leadSessionId, fresh task store holding the
    owner's task) + a lived journal. The census realigns, get_team_name()
    returns the LIVE team, and the gate ALLOWs. NON-VACUITY: the task lives
    ONLY under the live team; a resolver that stayed on the stale default
    would MISS the store and DENY."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID)
    code, out = _run_dispatch(_make_spawn(team_name_arg="wrong-team"), capsys)
    assert code == 0, "census must realign to the live re-provisioned team"
    assert out == _SUPPRESS_EXPECTED
    # Load-bearing: the owner's task exists ONLY under the live team.
    assert (tmp_path / ".claude" / "tasks" / NEW_TEAM_ID8).exists()
    assert not (tmp_path / ".claude" / "tasks" / OLD_TEAM).exists()


# ══════════════════════════════════════════════════════════════════════════════
# (i-b) ADVERSARIAL DEAD DIR — branch-2's witness satisfied by a DEAD dir
# ══════════════════════════════════════════════════════════════════════════════


def test_i_b_dead_incident_shaped_dir_never_resolved(tmp_path, monkeypatch,
                                                     capsys):
    """CELL i-b (incident shape) — the reaped OLD team dir SURVIVES on disk
    (session-<old8> naming) with inboxes/ but no config.json, while the live
    re-provisioned team is the sole census candidate. The resolution must be
    the LIVE team (or at minimum the stale default) — NEVER the dead dir's
    name. Branch-2 cannot hijack here: it anchors on teams/<bare-old-uuid>/,
    and the dead dir is named session-<old8>. NON-VACUITY: the owner's task
    lives only under the live team, so the ALLOW proves the resolution landed
    there."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID)
    _seed_dead_team_dir(tmp_path, team_name=OLD_TEAM, with_inboxes=True)
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 0, (
        "dead session-<old8> dir must not block the census realign"
    )
    import shared.pact_context as ctx_module
    assert ctx_module.get_team_name() == NEW_TEAM_ID8
    assert ctx_module.get_team_name() != OLD_TEAM


@pytest.mark.xfail(
    reason=(
        "Accepted residual (lead ruling, follow-up #1509): the world needs "
        "TWO unobserved platform behaviors to co-occur — bare-uuid remnant "
        "naming AND inboxes/ surviving end-session. Measured remnants are "
        "session-<id8>-named with file-edits.json (branch-2 never matches "
        "them); PACT's own reaper rmtrees whole dirs. Branch-2 returns the "
        "dead name before the census runs. The unguarded liveness conjunct "
        "is REJECTED (silent sticky foreign-team alignment in the "
        "live-but-idle config-less world); the guarded branch-2 override "
        "sketch lives in #1509. strict=True is the deliberate tripwire: when "
        "#1509 lands, this XPASSes and the suite REDDENS, forcing the "
        "un-xfail-and-turn-green step that issue's acceptance requires."
    ),
    strict=True,
)
def test_i_b_dead_desktop_shaped_uuid_dir_never_resolved(
    tmp_path, monkeypatch, capsys
):
    """CELL i-b (Desktop composition shape) — the reaped OLD team dir is named
    with the BARE OLD full uuid and carries inboxes/ (branch-2's config-less
    witness is SATISFIED by a DEAD dir), while the live re-provisioned team is
    the sole census candidate. PLAN CONTRACT (Test-phase table, i-b): the
    resolution must be the live team or the stale default — NEVER the dead
    dir's name. MEASURED RED on the landed code (branch-2 fires on the dead
    substrate and returns the dead name before the census), ruled an ACCEPTED
    RESIDUAL: reachability requires (a) bare-uuid dir naming (Desktop
    2.1.177 shape) AND (b) inboxes/ surviving end-session to CO-OCCUR — both
    unobserved on this platform (5 config-less remnants measured at the zai
    teams root: all session-<id8>-named, all file-edits.json, ZERO inboxes/,
    ZERO bare-uuid; session_end's reaper is ^pact--scoped whole-dir rmtree,
    so PACT itself cannot leave this half-corpse). The xfail pins the
    contract against future platform change and tracks follow-up #1509
    (guarded branch-2 override: fire branch-2 only when own tasks are fresh
    OR the census has no unique candidate — preserves matrix v and every
    census-empty #989 pin). The plainly-fresh-tasks liveness conjunct was
    REJECTED: in the live-but-idle config-less world it would fall through
    branch-2 to the census, silently align to a concurrent FOREIGN team, and
    the write-back would make that sticky — a worse hole than this deny,
    which at least self-diagnoses with the manual-repoint remedy."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID)
    _seed_dead_team_dir(tmp_path, team_name=OLD_SID, with_inboxes=True)
    import shared.pact_context as ctx_module
    resolved = ctx_module.get_team_name()
    assert resolved != OLD_SID, (
        f"resolver returned the DEAD dir name {resolved!r} — branch-2's "
        "witness was satisfied by the reaped Desktop-shaped old team dir"
    )
    # Live team or stale default are both acceptable per the plan contract;
    # the dead name is the only forbidden outcome.
    assert resolved in (NEW_TEAM_ID8, OLD_TEAM)


# ══════════════════════════════════════════════════════════════════════════════
# (ii) AMBIGUOUS CENSUS — two fresh candidates -> stale default + honest deny
# ══════════════════════════════════════════════════════════════════════════════


def test_ii_two_candidates_stale_default_and_new_remedy(tmp_path, monkeypatch,
                                                        capsys):
    """CELL ii — two live candidates (two simultaneous broken resumes) ->
    AMBIGUOUS -> the stale default stands and the gate DENIES with
    no_task_assigned. The deny carries the enumeration's cause-(2) remedy
    naming the MEASURED recovery (edit pact-session-context.json); none of the
    falsified inert 'bootstrap ritual' phrases may appear (this leg has no
    CLAUDE.md, so the stale block is silent and the enumeration is the sole
    appended diagnosis)."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID, tasks=())  # stale store: no task
    _seed_team_store(tmp_path / ".claude", team_name=AMBIG_TEAM,
                     lead_session_id=AMBIG_SID, members=(), tasks=())
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 2, "ambiguous census must fail safe to a deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "no Task assigned" in reason
    # The NEW remedy names the measured manual repoint...
    assert _CAUSE2_RECOVERY_MARKER in reason
    # ...and no inert bootstrap-ritual claim survives anywhere in the deny.
    for phrase in _FORBIDDEN_INERT_PHRASES:
        assert phrase not in reason, f"inert remedy phrase leaked: {phrase!r}"


# ══════════════════════════════════════════════════════════════════════════════
# (iii) EMPTY-SSOT SECURITY GATE — census must sit BEHIND the short-circuit
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("frame_sid", [OLD_SID, TMUX_FRAME_SID],
                         ids=["in-process", "tmux"])
def test_iii_empty_ssot_fails_closed_with_census_inputs(tmp_path, monkeypatch,
                                                        capsys, frame_sid):
    """CELL iii — the empty-SSOT fail-closed gate, extended with the #1507
    census's OWN inputs: an empty persisted team_name plus a fully-seeded live
    re-provisioned team and a lived journal. Identity-match AND the census are
    both unreachable on the empty path — get_team_name() returns '' and the
    gate DENIES team_name_unavailable in BOTH topologies. The census must
    never recover a team from an empty SSOT (that would over-reach the
    security gate pinned by test_empty_ssot_team_fails_closed_both_modes)."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name="", session_id=OLD_SID)
    _reset_aligned_cache()
    _seed_team_store(tmp_path / ".claude", team_name=NEW_TEAM_ID8,
                     lead_session_id=NEW_SID, members=(),
                     tasks=((_NAME, "pending"),))
    _seed_session_journal(monkeypatch, tmp_path, ["task_claimed"])
    import shared.pact_context as ctx_module
    assert ctx_module.get_team_name() == ""
    spawn = _make_spawn()
    spawn["session_id"] = frame_sid
    code, out = _run_dispatch(spawn, capsys)
    assert code == 2, f"empty SSOT must fail-closed (frame_sid={frame_sid})"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "session team_name is unavailable" in reason


# ══════════════════════════════════════════════════════════════════════════════
# (iv) #989 SAME-ID PATH + INTERFERENCE — identity-match OUTRANKS the census
# ══════════════════════════════════════════════════════════════════════════════


def test_iv_identity_match_outranks_census(tmp_path, monkeypatch, capsys):
    """CELL iv — the #989 world (persisted id == a real dir's leadSessionId,
    dir NAMED with the bare full uuid) with a census candidate ALSO present
    and every census trigger conjunct satisfied (stale fallback config absent,
    lived journal, fresh foreign store). Identity-match must win: resolution
    is the SAME-ID full-uuid dir, never the census candidate. NON-VACUITY:
    the owner's task lives only under the same-id dir."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name=OLD_TEAM, session_id=OLD_SID)
    _reset_aligned_cache()
    # The same-id divergent dir (#989): bare full uuid, config carries the
    # PERSISTED id, owner's task lives here.
    _seed_team_store(tmp_path / ".claude", team_name=OLD_SID, lead_session_id=OLD_SID,
                     members=(), tasks=((_NAME, "pending"),))
    # A census candidate that WOULD win if the census ran first.
    _seed_team_store(tmp_path / ".claude", team_name=NEW_TEAM_ID8,
                     lead_session_id=NEW_SID, members=(), tasks=())
    _seed_session_journal(monkeypatch, tmp_path, ["task_claimed"])
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 0, "identity-match must resolve before the census"
    import shared.pact_context as ctx_module
    assert ctx_module.get_team_name() == OLD_SID


# ══════════════════════════════════════════════════════════════════════════════
# (v) ORDERING — branch-2's config-less witness fires BEFORE the census
# ══════════════════════════════════════════════════════════════════════════════


def test_v_branch2_witness_preempts_census(tmp_path, monkeypatch, capsys):
    """CELL v — the legitimate branch-2 substrate (a config-less OWN-session
    dir: teams/<old-uuid>/ with inboxes/, the #989 Desktop/SDK shape) with a
    census candidate also live. Branch-2 must resolve FIRST (its return
    preempts the census), so the resolution is the own-session substrate —
    the census candidate is never consulted. NON-VACUITY: the owner's task
    lives only under the branch-2 dir; if the census had won, the gate would
    read the candidate's empty store and DENY."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name=OLD_TEAM, session_id=OLD_SID)
    _reset_aligned_cache()
    # Branch-2 substrate: config-less, inboxes witness, task store under the
    # SAME name the branch-2 return addresses (the bare OLD uuid).
    _seed_dead_team_dir(tmp_path, team_name=OLD_SID, with_inboxes=True)
    tasks_dir = tmp_path / ".claude" / "tasks" / OLD_SID
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "task_0.json").write_text(
        json.dumps({"id": "0", "owner": _NAME, "status": "pending"}),
        encoding="utf-8",
    )
    # The census candidate that would win if ordering were inverted.
    _seed_team_store(tmp_path / ".claude", team_name=NEW_TEAM_ID8,
                     lead_session_id=NEW_SID, members=(), tasks=())
    _seed_session_journal(monkeypatch, tmp_path, ["task_claimed"])
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 0, "branch-2 must preempt the census on own-substrate"
    import shared.pact_context as ctx_module
    assert ctx_module.get_team_name() == OLD_SID


# ══════════════════════════════════════════════════════════════════════════════
# (vi) COLD-START GUARD — fresh journal + foreign fresh candidate -> NO align
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "journal_events",
    [[], ["variety_assessed"]],
    ids=["no-journal", "journal-without-team-activity"],
)
def test_vi_fresh_journal_never_aligns_to_foreign_candidate(
    tmp_path, monkeypatch, capsys, journal_events
):
    """CELL vi — THE cold-start guard, gate-level: a FRESH session's journal
    (absent, or carrying only non-activity events) plus a concurrently ACTIVE
    foreign session as the SOLE fresh candidate. Without the journal witness
    the unambiguous-only rule alone would mis-align to the foreign team and
    the write-back would make it sticky; the witness kills the census.
    NON-VACUITY: the owner's task lives ONLY under the foreign candidate, so
    an ALLOW would PROVE mis-alignment — the deny is the guard observable."""
    _seed_census_world(
        monkeypatch, tmp_path, live_team=FOREIGN_TEAM,
        live_lead_sid=FOREIGN_SID, journal_events=journal_events,
        with_journal=bool(journal_events),
    )
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 2, (
        "fresh journal + sole foreign candidate must NOT align (witness)"
    )
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "no Task assigned" in reason


# ══════════════════════════════════════════════════════════════════════════════
# (vii) POST-CONVERGENCE STABILITY — persisted winner's config exists -> inert
# ══════════════════════════════════════════════════════════════════════════════


def test_vii_post_convergence_stable_with_foreign_candidate(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """CELL vii — after the write-back converges (persisted team_name = the
    census winner, whose config EXISTS), the census trigger's config-absent
    conjunct is false and the census is INERT — no flicker — even with a
    fresh foreign candidate present (the concurrent-session world). The
    resolution stays on the persisted winner and the gate ALLOWs. NON-VACUITY:
    the owner's task lives only under the winner."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name=NEW_TEAM_ID8, session_id=OLD_SID)
    _reset_aligned_cache()
    # The winner's own config EXISTS (post-convergence shape) — identity-match
    # still misses (NEW leadSessionId != persisted OLD id) but the census
    # trigger is false, so the fail-safe default (the winner) stands.
    _seed_team_store(tmp_path / ".claude", team_name=NEW_TEAM_ID8,
                     lead_session_id=NEW_SID, members=(),
                     tasks=((_NAME, "pending"),))
    _seed_team_store(tmp_path / ".claude", team_name=FOREIGN_TEAM,
                     lead_session_id=FOREIGN_SID, members=(), tasks=())
    _seed_session_journal(monkeypatch, tmp_path, ["task_claimed"])
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 0, "post-convergence resolution must stay on the winner"
    import shared.pact_context as ctx_module
    assert ctx_module.get_team_name() == NEW_TEAM_ID8


# ══════════════════════════════════════════════════════════════════════════════
# (viii) SCRATCH ROOT — census reads ONLY $CLAUDE_CONFIG_DIR, never default
# ══════════════════════════════════════════════════════════════════════════════


def test_viii_scratch_root_no_default_root_leakage(tmp_path, monkeypatch,
                                                   capsys):
    """CELL viii (spec Verification 4) — under CLAUDE_CONFIG_DIR at a scratch
    root, the census and witness read ONLY that root's teams/tasks/journal. A
    DECOY candidate seeded under the DEFAULT root (tmp/.claude — what the
    resolution would read if it ignored the env var) carries an even-fresher
    config+tasks store: on any default-root leakage the census would resolve
    the DECOY (whose task store is absent here), not the scratch candidate.
    The ALLOW + resolved-team assertion prove the scratch root was the only
    root read."""
    scratch = tmp_path / "scratch-root"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(scratch))
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name=OLD_TEAM, session_id=OLD_SID)
    _reset_aligned_cache()
    # The LIVE candidate under the SCRATCH root (owner's task lives here).
    _seed_team_store(scratch, team_name=NEW_TEAM_ID8,
                     lead_session_id=NEW_SID, members=(),
                     tasks=((_NAME, "pending"),))
    # The journal witness must also resolve under the scratch root.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import shared.pact_context as ctx_module
    session_dir = Path(ctx_module.get_session_dir())
    assert str(scratch) in str(session_dir), (
        "session dir must derive from CLAUDE_CONFIG_DIR when set"
    )
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session-journal.jsonl").write_text(
        json.dumps({"v": 1, "type": "task_claimed",
                    "ts": "2026-08-24T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    # The DECOY under the DEFAULT root: config + fresh tasks dir, no owner
    # task. Fresh mtime so it would WIN the census on leakage.
    _seed_team_store(tmp_path / ".claude", team_name="session-decoy",
                     lead_session_id="d0c0aaaa-1111-4222-8333-444455556666",
                     members=(), tasks=())
    code, out = _run_dispatch(_make_spawn(), capsys)
    assert code == 0, "census must resolve the SCRATCH-root candidate"
    assert ctx_module.get_team_name() == NEW_TEAM_ID8
    assert ctx_module.get_team_name() != "session-decoy"


# ══════════════════════════════════════════════════════════════════════════════
# (ix) COMPOSITION — both divergences at once, both spawn-frame topologies
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("frame_sid,mode",
                         [(OLD_SID, "in-process"),
                          (TMUX_FRAME_SID, "tmux")])
def test_ix_composition_both_divergences_both_topologies(
    tmp_path, monkeypatch, capsys, frame_sid, mode
):
    """CELL ix — the full composition: persisted OLD id, old config reaped,
    the live team dir NAMED with the bare NEW full uuid AND carrying the NEW
    leadSessionId (dir-name divergence AND id divergence at once — #1507 on
    top of #989), across BOTH spawn-frame topologies (frame id == the
    persisted/lead id, and !=). The resolver keys on the PERSISTED id (never
    the acting frame's), so the census realigns identically in both modes.
    NON-VACUITY: the owner's task lives only under the live dir."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_UUID_DIR,
                       live_lead_sid=NEW_SID)
    spawn = _make_spawn(team_name_arg="wrong-team")
    spawn["session_id"] = frame_sid
    # Per-leg cache reset: the aligned cache would bleed across legs in this
    # same-process harness.
    _reset_aligned_cache()
    code, out = _run_dispatch(spawn, capsys)
    assert code == 0, f"census must compose both divergences ({mode})"
    assert out == _SUPPRESS_EXPECTED
    assert not (tmp_path / ".claude" / "tasks" / OLD_TEAM).exists()
    assert (tmp_path / ".claude" / "tasks" / NEW_UUID_DIR).exists()


# ══════════════════════════════════════════════════════════════════════════════
# (x) MALFORMED-CONFIG CANDIDATE STANCE — a config MISSING leadSessionId
# ══════════════════════════════════════════════════════════════════════════════


def test_x_config_missing_leadsessionid_counts_as_candidate(
    tmp_path, monkeypatch
):
    """CELL x — the resolver's candidate predicate is the LITERAL spec
    (``leadSessionId != session_id`` — NO non-empty requirement), so a config
    whose leadSessionId key is MISSING (``data.get`` -> None != the persisted
    id) COUNTS as a census candidate whenever its tasks store is fresh. This
    test ASSERTS that implemented stance and records it (resolver-coder's
    open question #1): the stance is acceptable because it is bounded by the
    unambiguous-only rule, the journal witness, and the recency window — a
    malformed sibling can only WIN when it is the sole fresh candidate of a
    lived session whose persisted team config is reaped, i.e. a world where
    returning the stale default denies every spawn anyway. If a future change
    tightens the predicate (e.g. requires a non-string-safe, present,
    non-empty leadSessionId), flip this test WITH it — the stance is pinned,
    not endorsed."""
    plugin_root = tmp_path / "plugin"
    _seed_plugin(plugin_root)
    _write_context(monkeypatch, tmp_path, plugin_root,
                   team_name=OLD_TEAM, session_id=OLD_SID)
    _reset_aligned_cache()
    # The malformed candidate: config.json EXISTS but carries NO
    # leadSessionId key; fresh sibling tasks store.
    _seed_team_store(tmp_path / ".claude", team_name=NEW_TEAM_ID8, lead_session_id=None,
                     members=(), tasks=())
    _seed_session_journal(monkeypatch, tmp_path, ["task_claimed"])
    import shared.pact_context as ctx_module
    resolved = ctx_module._resolve_aligned_team_name(
        OLD_SID, teams_dir=str(tmp_path / ".claude" / "teams"),
        default=OLD_TEAM,
    )
    assert resolved == NEW_TEAM_ID8


# ══════════════════════════════════════════════════════════════════════════════
# (xi) COMPOSITE-DENY COHERENCE — stale block + Working-recovery hint
# ══════════════════════════════════════════════════════════════════════════════


def test_xi_stale_block_and_working_recovery_coexist_scoped(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """CELL xi (auditor note) — when the stale-block detector fires ALONGSIDE
    the ambiguous-census deny, the composite reason carries BOTH diagnoses,
    each scoped to ITS OWN records with no contradiction inside one message:
      * the stale-block WARNING (about the CLAUDE.md 'Current Session' block —
        its 'completing bootstrap will rewrite them' claim is TRUE for the
        CLAUDE.md records it names), and
      * the re-align HINT (about pact-session-context.json — the measured
        working recovery, leaving session_id/journal untouched).
    The composer is A-xor-B by construction: with the incumbent fired the
    rule-⑧ enumeration is NOT also appended, so the message carries exactly
    one remedy path per record-type, not two competing instructions. Fixture:
    CLAUDE.md records a PREVIOUS session's id while the acting frame carries
    the current one (the session_init-crash overlap world where the detector
    was designed to fire) on top of the ambiguous-census stale world."""
    _seed_census_world(monkeypatch, tmp_path, live_team=NEW_TEAM_ID8,
                       live_lead_sid=NEW_SID, tasks=())
    _seed_team_store(tmp_path / ".claude", team_name=AMBIG_TEAM,
                     lead_session_id=AMBIG_SID, members=(), tasks=())
    # The stale-block trigger: project CLAUDE.md whose Resume line records a
    # PREVIOUS session id, with the acting frame carrying a different one.
    project_dir = tmp_path / "project"
    (project_dir / ".claude").mkdir(parents=True, exist_ok=True)
    prev_sid = "11112222-3333-4444-8555-666677778888"
    (project_dir / ".claude" / "CLAUDE.md").write_text(
        "# PACT Framework and Managed Project Memory\n\n"
        "## Current Session\n"
        f"- Resume: `claude --resume {prev_sid}`\n"
        f"- Team: `session-11112222`\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))
    spawn = _make_spawn()
    spawn["session_id"] = OLD_SID  # != recorded prev_sid -> mismatch fires
    code, out = _run_dispatch(spawn, capsys)
    assert code == 2
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    # BOTH diagnoses present, each naming its own record surface...
    assert _STALE_BLOCK_MARKER in reason
    assert "CLAUDE.md" in reason                      # stale-block's surface
    assert _HINT_MARKER in reason                     # the hint's marker
    assert "pact-session-context.json" in reason      # the hint's surface
    assert "journal continuity" in reason             # the hint's constraint
    # ...and the composer did NOT also append the enumeration (A-xor-B), so
    # no second, competing remedy block rides in the same message.
    assert _ENUMERATION_HEADER not in reason
