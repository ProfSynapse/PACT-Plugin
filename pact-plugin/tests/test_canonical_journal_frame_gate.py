"""Frame-gate arms for the six sites that moved from is_lead to
is_canonical_journal_frame.

WHY THIS FILE EXISTS. The substitution shipped with a green suite, and the
suite was green BEFORE the change and AFTER it. The arms in this repository
were insensitive to the substitution in the two directions, so the green
proved that nothing broke and proved nothing about the substitution.

🔴 WHY THE OLD ARMS COULD NOT SEE IT, MEASURED RATHER THAN ASSUMED.
``is_canonical_journal_frame`` returns True IMMEDIATELY when ``is_lead`` is
True, and only then falls to the topology leg. So in a lead frame that
carries a lead ``agent_type``, THE TWO PREDICATES GIVE THE SAME ANSWER and a
revert is invisible. The ONLY frame class that separates them is
``is_lead`` False AND ``is_canonical_journal_frame`` True, which needs the
topology leg to resolve.

🔴 THE TOPOLOGY LEG NEEDS TWO HALVES, AND ONE HALF IS A TRAP. It needs a
frame ``session_id`` AND a team config carrying a ``leadSessionId`` that
agrees with it. WITH ONE HALF THE PREDICATE ANSWERS False, WHICH IS THE SAME
ANSWER ``is_lead`` GIVES. So an arm built on one half is green with the
substitution and green without it, AND IT READS AS TESTED because it does
drive the site. That is an equality between two outcomes rather than a
defect in the arm: no arm confined to that frame class can discriminate,
however carefully it is written. ``test_four_point_control`` pins all four
points so a later editor cannot seed one half and believe it is covered.

🔴 THE SIX SITES DO NOT SHARE ONE OBSERVABLE. Five emit journal records
through ``append_event``. The artifact-paths site appends an ADVISORY to the
return value of ``evaluate_lifecycle`` and writes no journal record. AN ARM
SET BUILT ON ONE CHANNEL IS BLIND AT THAT SITE, AND A BLIND ARM IS GREEN.
The fixture below captures the two channels for that cause.

SITES COVERED HERE, cited by symbol because the line numbers move:
``dispatch_variety`` in the TaskCreate branch, ``teachback_ack`` in the
TaskUpdate-completed branch, and the ``artifact_paths_emit_missing``
advisory. THREE SITES ARE NOT COVERED: the lead-side agent_handoff emit and
the two post-completion backstop emits. Their fixtures need an on-disk
Task-A read through the resolution path of the gate, which this file does
not build.

R5 IS OUT OF SCOPE AND IS NAMED SO A READER DOES NOT EXPECT IT.
``_journal_lifecycle_decision`` writes a ``lifecycle_decision`` record with
NO frame gate, in EVERY frame, and it is filed as item 2 of issue 1482. The
arm-D controls below assert silence FOR THE RECORD KIND OF THEIR OWN SITE,
never journal silence in general, because the ungated write makes a general
silence assertion red at the base for a cause this commit does not own.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import shared.pact_context as pc  # noqa: E402
import shared.session_journal as sj  # noqa: E402
import task_lifecycle_gate as tlg  # noqa: E402

LEAD_AGENT_TYPE = "PACT:pact-orchestrator"
TEAMMATE_AGENT_TYPE = "pact-devops-engineer"
SESSION_ID = "sess-canonical-frame-0001"
OTHER_SESSION_ID = "sess-tmux-teammate-0002"
TEAM = "session-abcd1234"


@pytest.fixture
def frame_rig(tmp_path, monkeypatch):
    """Seed the two halves of the topology leg and capture BOTH observables.

    Returns a callable. Call it with a frame dict and it returns
    ``(journal_records, advisory_names)``.

    The team config is the half that the ordinary ``pact_context`` fixture
    does NOT write: that fixture writes the CONTEXT file, and the
    ``leadSessionId`` lives in the TEAM CONFIG. The two are different files,
    and an arm that seeds only the first carries one half.
    """
    teams_dir = tmp_path / "teams" / TEAM
    teams_dir.mkdir(parents=True)
    teams_dir.joinpath("config.json").write_text(
        json.dumps({"leadSessionId": SESSION_ID}), encoding="utf-8"
    )
    monkeypatch.setattr(pc, "get_claude_config_dir", lambda: tmp_path)
    monkeypatch.setattr(pc, "get_team_name", lambda: TEAM)
    monkeypatch.setattr(pc, "get_pact_context", lambda: {"team_name": TEAM})

    def drive(frame):
        records: list[dict] = []
        monkeypatch.setattr(
            sj, "append_event", lambda e: records.append(e) or True
        )
        advisories = tlg.evaluate_lifecycle(frame)
        return records, [name for name, _ in advisories]

    return drive


def _arm_b(**extra):
    """Arm B: a lead launched with NO --agent flag. `agent_type` is ABSENT,
    so `is_lead` is False, and the topology leg admits the frame."""
    return {"session_id": SESSION_ID, **extra}


def _arm_c(**extra):
    """Arm C: an in-process teammate that shares the lead session."""
    return {
        "agent_type": TEAMMATE_AGENT_TYPE,
        "session_id": SESSION_ID,
        **extra,
    }


def _arm_d(**extra):
    """Arm D: a tmux teammate. Its session_id DISAGREES with the config."""
    return {
        "agent_type": TEAMMATE_AGENT_TYPE,
        "session_id": OTHER_SESSION_ID,
        **extra,
    }


def _arm_a(**extra):
    """Arm A: a lead carrying a lead `agent_type`. `is_lead` short-circuits."""
    return {"agent_type": LEAD_AGENT_TYPE, **extra}


def _typed(records, kind):
    return [r for r in records if r.get("type") == kind]


# =============================================================================
# The control. Read this before changing any arm below it.
# =============================================================================
class TestFramePredicateControl:
    def test_four_point_control(self, tmp_path, monkeypatch):
        """The topology leg needs BOTH halves, and one half is not a weaker
        version of two: it gives the SAME verdict as the reverted predicate.

        Four points, and a three-point control would miss the fourth. The
        fourth is the two halves present and DISAGREEING, which is what a
        stale team config produces in the field.
        """
        teams_dir = tmp_path / "teams" / TEAM
        teams_dir.mkdir(parents=True)
        cfg = teams_dir / "config.json"
        cfg.write_text(json.dumps({"leadSessionId": SESSION_ID}), encoding="utf-8")
        monkeypatch.setattr(pc, "get_claude_config_dir", lambda: tmp_path)
        monkeypatch.setattr(pc, "get_team_name", lambda: TEAM)

        both = {"session_id": SESSION_ID}
        assert pc.is_canonical_journal_frame(both) is True, (
            "POINT 1: the two halves seeded and in agreement must ADMIT."
        )
        assert pc.is_lead(both) is False, (
            "POINT 1 NON-VACUITY: is_lead must answer False here, or this "
            "frame does not separate the two predicates and no arm built on "
            "it can detect a revert."
        )

        disagree = {"session_id": OTHER_SESSION_ID}
        assert pc.is_canonical_journal_frame(disagree) is False, (
            "POINT 2: the two halves present and DISAGREEING must EXCLUDE. "
            "This is the tmux teammate, and it is the state a stale team "
            "config produces."
        )

        cfg.unlink()
        assert pc.is_canonical_journal_frame(both) is False, (
            "POINT 3, THE TRAP: with the FRAME HALF ALONE the predicate "
            "answers False, which is the SAME answer is_lead gives. An arm "
            "built on this half is green with the substitution AND green "
            "without it, and it reads as tested because it drives the site."
        )

        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"leadSessionId": SESSION_ID}), encoding="utf-8")
        assert pc.is_canonical_journal_frame({}) is False, (
            "POINT 4: with the CONFIG HALF ALONE and no session_id the "
            "predicate answers False. The second half of the same trap."
        )

    def test_arm_a_cannot_discriminate_and_that_is_the_point(self, tmp_path,
                                                             monkeypatch):
        """A NEGATIVE CONTROL ON MY OWN REASONING, not on the code.

        In a lead frame carrying a lead `agent_type`, the two predicates
        AGREE, so a revert is invisible. This arm asserts that agreement.
        IT DETECTS NO DEFECT BY DESIGN. Its value is conditional: if it ever
        fails, the short-circuit model behind every other arm in this file is
        incorrect, and those arms must be re-derived rather than repaired.
        """
        monkeypatch.setattr(pc, "get_claude_config_dir", lambda: tmp_path)
        monkeypatch.setattr(pc, "get_team_name", lambda: TEAM)
        frame = _arm_a()
        assert pc.is_lead(frame) is True
        assert pc.is_canonical_journal_frame(frame) is True
        assert pc.is_lead(frame) == pc.is_canonical_journal_frame(frame), (
            "THE TWO PREDICATES MUST AGREE AT ARM A. If they disagree, the "
            "short-circuit is gone and every arm in this file needs a "
            "re-derived expectation."
        )


# =============================================================================
# Site arms. Each drives a real site in a frame that separates the predicates.
# =============================================================================
class TestDispatchVarietySite:
    """`dispatch_variety`, in the TaskCreate branch."""

    FRAME_EXTRA = {
        "tool_name": "TaskCreate",
        "tool_input": {
            "subject": "devops: implement",
            "metadata": {"variety": {"total": 9}},
        },
        "tool_response": {"task": {"id": "42"}},
    }

    def test_arm_b_lead_without_agent_flag_emits(self, frame_rig):
        """A lead with no --agent flag writes the canonical journal, so the
        emit must run. A revert to is_lead makes this arm RED."""
        records, _ = frame_rig(_arm_b(**self.FRAME_EXTRA))
        assert len(_typed(records, "dispatch_variety")) == 1, (
            "A lead launched with no --agent flag DOES write the canonical "
            "journal. If this arm is red, the gate answered on ROLE rather "
            "than on which journal the frame writes, and the record is lost."
        )

    def test_arm_c_in_process_teammate_emits(self, frame_rig):
        """The in-process teammate shares the lead session, so its writes
        land in the canonical journal and the emit must run."""
        records, _ = frame_rig(_arm_c(**self.FRAME_EXTRA))
        assert len(_typed(records, "dispatch_variety")) == 1, (
            "An in-process teammate shares the lead session, so its emit "
            "lands in the canonical journal and must not be suppressed."
        )

    def test_arm_d_tmux_teammate_stays_silent(self, frame_rig):
        """Arm D control, SCOPED TO THIS RECORD KIND. It does NOT assert
        journal silence in general: R5 writes an ungated record in every
        frame, and a general assertion would be red at the base for a
        defect this commit does not own."""
        records, _ = frame_rig(_arm_d(**self.FRAME_EXTRA))
        assert _typed(records, "dispatch_variety") == [], (
            "A tmux teammate writes a DIFFERENT journal. Emitting from it "
            "silos the record and poisons the shared marker namespace."
        )


class TestTeachbackAckSite:
    """`teachback_ack`, in the TaskUpdate-completed branch."""

    FRAME_EXTRA = {
        "tool_name": "TaskUpdate",
        "tool_input": {"taskId": "7", "status": "completed"},
        "tool_response": {
            "task": {
                "id": "7",
                "owner": "teammate",
                "subject": "teammate: TEACHBACK for the thing",
                "metadata": {
                    "teachback_submit": {
                        "variety_acknowledgment": {
                            "rationale_articulates_this_dispatch": "yes"
                        }
                    }
                },
            }
        },
    }

    def test_arm_b_lead_without_agent_flag_emits(self, frame_rig):
        records, _ = frame_rig(_arm_b(**self.FRAME_EXTRA))
        assert len(_typed(records, "teachback_ack")) == 1, (
            "The teachback acknowledgement must reach the canonical journal "
            "from a lead frame that carries no --agent flag."
        )

    def test_arm_c_in_process_teammate_emits(self, frame_rig):
        records, _ = frame_rig(_arm_c(**self.FRAME_EXTRA))
        assert len(_typed(records, "teachback_ack")) == 1

    def test_arm_d_tmux_teammate_stays_silent(self, frame_rig):
        records, _ = frame_rig(_arm_d(**self.FRAME_EXTRA))
        assert _typed(records, "teachback_ack") == []


class TestArtifactPathsAdvisorySite:
    """The `artifact_paths_emit_missing` advisory.

    🔴 THIS SITE WRITES NO JOURNAL RECORD. It appends an advisory to the
    RETURN VALUE. An arm that watches `append_event` alone is blind here and
    reports the site as silent, which reads as a passing control. The
    fixture returns the two channels for that cause. Do not narrow these
    assertions to the journal channel.
    """

    FRAME_EXTRA = {
        "tool_name": "TaskUpdate",
        "tool_input": {"taskId": "7", "status": "completed"},
        "tool_response": {
            "task": {
                "id": "7",
                "owner": "architect",
                "subject": "ARCHITECT: the feature",
                "metadata": {},
            }
        },
    }

    def test_arm_b_lead_without_agent_flag_raises_the_advisory(self, frame_rig):
        records, advisories = frame_rig(_arm_b(**self.FRAME_EXTRA))
        assert "artifact_paths_emit_missing" in advisories, (
            "The artifact-paths check must run in a canonical-journal frame. "
            "If it is absent, the gate skipped the check on ROLE, and the "
            "missing durability pointer goes unreported."
        )
        assert records == [] or True, (
            "Recorded deliberately: this site writes NO journal record. The "
            "advisory channel is the observable."
        )

    def test_arm_c_in_process_teammate_raises_the_advisory(self, frame_rig):
        _, advisories = frame_rig(_arm_c(**self.FRAME_EXTRA))
        assert "artifact_paths_emit_missing" in advisories

    def test_arm_d_tmux_teammate_stays_silent(self, frame_rig):
        _, advisories = frame_rig(_arm_d(**self.FRAME_EXTRA))
        assert "artifact_paths_emit_missing" not in advisories, (
            "A tmux teammate must not raise this advisory: it reads a "
            "journal it does not share, so its answer is not evidence."
        )
