"""A PRIMARY frame with no ``--agent`` must keep the orchestrator ladder.

THE DEFECT THESE ARMS CLOSE. ``classify_session_role`` returns "unknown" when
``agent_type`` is ABSENT, and its own docstring names what that covers: "a
non-PACT / no-``--agent`` primary frame". A role gate that SUPPRESSES the
orchestrator ladder for "unknown" therefore suppresses it for every user who
runs plain ``claude``. That user is not told to bootstrap, so the bootstrap
marker is never stamped, so ``bootstrap_gate`` (PreToolUse, no matcher key,
runs on EVERY tool call) denies Edit, Write and Agent. The user reads that as a
total tool-load failure.

THE SUPPRESSION ALSO CANNOT REACH THE FRAMES IT WAS BUILT FOR, WHICH IS WHY
THESE ARMS ASSERT A RESTORE RATHER THAN A NARROWING. Its stated target was
subagent frames that received the orchestrator instructions. MEASURED, with the
parameter beside the count. POPULATION: 166 files matching ``subagents/*.jsonl``
for one team session. 13 of them carry a SessionStart record, and those records
hold 70 SessionStart entries. EVERY ONE of the 70 has ``type == "attachment"``
and carries the LEAD session id, not a subagent session id: the set of distinct
session ids across all 70 has exactly ONE member and it is the lead. They are
the LEAD's own hook output, which the platform attaches into the transcripts of
the sidechains that are live at that moment. Those frames classify "lead", so
they take the lead branch in either version, and a gate keyed on "unknown"
cannot change one byte of them. NO SUBAGENT FRAME REACHES THIS HOOK: 150 of the
166 files hold no SessionStart record of any kind.

WHAT THE NOTICE IS FOR, AND WHY IT IS ADDITIVE. ``_UNKNOWN_ROLE_NOTICE`` tells
an operator who MEANT to launch the orchestrator and forgot the flag. That cue
is worth keeping. It is emitted BESIDE the ladder, never in place of it,
because the cost of withholding the ladder is a denied user and the cost of the
notice is a few hundred bytes.

THE ARMING PROBLEM THESE ARMS ANSWER. ``session_init`` is fail-open by
contract, so a hook that emits nothing and a hook that ran and correctly said
nothing produce the same bytes, which are none. AN ARM THAT ASSERTS ONLY AN
ABSENCE CANNOT SEPARATE THOSE TWO STATES. Every arm below asserts a PRESENCE
and an ABSENCE together, so the absence half is measured inside a run that
provably reached the emission point.
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_HOOKS = Path(__file__).parent.parent / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import session_init  # noqa: E402
from session_init import _build_safety_net_context, _UNKNOWN_ROLE_NOTICE  # noqa: E402

LADDER = "YOUR PACT ROLE: orchestrator."
BOOTSTRAP = 'Skill("PACT:bootstrap")'
TEAMMATE_MARKER = "YOUR PACT ROLE: teammate."
_SESSION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_PROJECT_DIR = "/tmp/pact-primary-frame-ladder"

# The four lifecycle sources a primary frame can arrive with. `clear` is listed
# because it is the WORST cell and the one an author is most likely to skip:
# session_init sets `is_marker_reset = source == "clear"` and then ERASES the
# bootstrap marker on that path. A primary `clear` frame with no ladder loses
# the marker AND the instruction that would rebuild it.
PRIMARY_SOURCES = ("startup", "resume", "compact", "clear")


def _run_main(frame, source, monkeypatch, tmp_path):
    """Drive the real ``session_init.main()`` and return its additionalContext.

    Heavy collaborators are stubbed. THE ROLE GATE IS NOT STUBBED: the frame
    carries the agent type the classifier reads, so the branch under test is
    the branch the hook takes in production.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", _PROJECT_DIR)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    stdin_data = json.dumps({"session_id": _SESSION_ID, "source": source, **frame})
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
         patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        with pytest.raises(SystemExit) as exc:
            session_init.main()
    assert exc.value.code == 0
    raw = mock_stdout.getvalue().strip()
    if not raw:
        return ""
    return json.loads(raw).get("hookSpecificOutput", {}).get("additionalContext", "")


class TestPrimaryFrameKeepsTheLadder:
    """The live emission path, driven through ``main()``."""

    @pytest.mark.parametrize("source", PRIMARY_SOURCES)
    def test_primary_frame_keeps_the_ladder_and_the_bootstrap_directive(
        self, source, monkeypatch, tmp_path
    ):
        """THE ARM THAT CLOSES THE REGRESSION, one cell for each source.

        SEPARATION: the emitted block must be non-empty first, so a dead build
        path fails on that assertion rather than on the ladder assertion. Then
        BOTH the marker and the bootstrap directive are asserted, because the
        marker alone does not make a lead bootstrap.
        """
        out = _run_main({}, source, monkeypatch, tmp_path)
        assert out, (
            f"a primary frame (source={source!r}, no agent_type) emitted NO "
            f"additionalContext at all. That is the not-delivered state rather "
            f"than the declined state: the run did not reach the emission point."
        )
        assert LADDER in out, (
            f"a PRIMARY frame (source={source!r}, no agent_type) lost the "
            f"orchestrator marker. A user who runs plain `claude` classifies "
            f"'unknown', so suppressing the ladder for 'unknown' suppresses it "
            f"for that user, who is then denied Edit/Write/Agent by "
            f"bootstrap_gate because no bootstrap marker is ever stamped."
        )
        assert BOOTSTRAP in out, (
            f"a PRIMARY frame (source={source!r}) kept the role marker but lost "
            f"the bootstrap directive. The marker alone does not cause a "
            f"bootstrap, so the marker is never stamped and the deny stands."
        )

    @pytest.mark.parametrize("source", PRIMARY_SOURCES)
    def test_primary_frame_also_keeps_the_unknown_role_notice(
        self, source, monkeypatch, tmp_path
    ):
        """The notice is ADDITIVE, not a replacement.

        SEPARATION: the ladder is the presence half that proves this run took
        the restored branch, so a green here cannot come from a build that
        suppressed the ladder and emitted the notice alone.
        """
        out = _run_main({}, source, monkeypatch, tmp_path)
        assert LADDER in out, (
            "the ladder is missing, so this arm cannot show that the notice "
            "rides BESIDE it rather than in place of it"
        )
        assert _UNKNOWN_ROLE_NOTICE in out, (
            f"a primary frame (source={source!r}) lost the unknown-role notice. "
            f"An operator who meant to pass `--agent` loses the only cue that "
            f"is delivered on a channel a transcript keeps."
        )

    def test_an_unrecognized_source_still_keeps_the_ladder(
        self, monkeypatch, tmp_path
    ):
        """THE FAILURE DIRECTION ON AN UNKNOWN INPUT, ARMED.

        The source ladder has a final else-branch for a `source` value it does
        not recognize. A future platform that adds a FIFTH source value lands
        there, and it MUST land on the restore side. This arm exists so that a
        later edit cannot quietly move the unrecognized branch to the suppress
        side: the value below is not one of the four the ladder names, so it
        reaches that branch by construction.

        SEPARATION: the run must emit something first, then the ladder and the
        bootstrap directive are asserted together, and the branch is confirmed
        by its own diagnostic sentence.
        """
        out = _run_main({}, "a-source-nobody-has-added-yet", monkeypatch, tmp_path)
        assert out, "the unrecognized-source branch emitted NO additionalContext"
        assert "unrecognized session source" in out, (
            "this run did not reach the unrecognized-source branch, so the "
            "assertions below measure a different branch than the one named"
        )
        assert LADDER in out, (
            "an unrecognized `source` value lost the orchestrator marker. The "
            "failure direction on an unknown input must be RESTORE, so a "
            "future platform source value cannot deny a user."
        )
        assert BOOTSTRAP in out, (
            "the unrecognized-source branch kept the marker and lost the "
            "bootstrap directive, so no marker is stamped and the deny stands"
        )

    def test_lead_frame_is_unchanged(self, monkeypatch, tmp_path):
        """THE ARM THAT BOUNDS THE FIX. A lead frame must not move."""
        out = _run_main(
            {"agent_type": "PACT:pact-orchestrator"}, "startup", monkeypatch, tmp_path
        )
        assert out, "a lead frame emitted NO additionalContext at all"
        assert LADDER in out, "a LEAD frame lost its orchestrator instructions"
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "a lead frame received the unknown-role notice, so the lead branch "
            "now falls through to the primary-frame branch"
        )

    def test_teammate_frame_is_unchanged(self, monkeypatch, tmp_path):
        """THE OTHER BOUND. A teammate must gain neither the ladder nor the
        notice. If this fix were too wide, a teammate would self-identify as
        the orchestrator, which is the defect the teammate branch exists for."""
        out = _run_main(
            {"agent_type": "some-teammate-name"}, "startup", monkeypatch, tmp_path
        )
        assert LADDER not in out, (
            "a teammate frame received the orchestrator instructions"
        )
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "a teammate frame received the unknown-role notice, so the teammate "
            "branch now falls through to the primary-frame branch"
        )


class TestSafetyNetPrimaryFrame:
    """The exception path. ``_build_safety_net_context`` is pure, so each case
    is driven directly."""

    def test_unknown_keeps_the_ladder_and_the_note(self):
        out = _build_safety_net_context("session-x", "unknown")
        assert out, "the safety net returned an empty string for an unknown frame"
        assert LADDER in out, (
            "the safety-net unknown branch withholds the orchestrator marker. "
            "A primary frame reaching the exception window is the same user as "
            "on the normal path and must not be denied."
        )
        assert BOOTSTRAP in out, (
            "the safety-net unknown branch kept the marker but dropped the "
            "bootstrap directive, so no marker is stamped and the deny stands"
        )
        assert _UNKNOWN_ROLE_NOTICE in out, (
            "the safety-net unknown branch lost the operator cue, which must "
            "ride BESIDE the ladder"
        )
        assert TEAMMATE_MARKER not in out, (
            "an unknown frame was labelled a teammate, which claims a role the "
            "classifier did not find"
        )

    def test_unresolved_role_keeps_the_ladder_and_its_own_diagnostic(self):
        """A frame that never classified STILL gets the tools.

        `frame_role is None` means the classifier DID NOT RUN, because the
        raise fired above the capture. The frame behind it is the same
        population as every other frame: mostly a primary user. Withholding
        the ladder there leaves the bootstrap marker unstamped and
        bootstrap_gate denies each tool call.

        THE STATED PRICE OF WITHHOLDING IT WAS A REACTIVE ROUTE, and the field
        report is evidence that route does not work: the reporter did not
        recover through the deny text, he rolled the plugin back.

        THE DIAGNOSTIC SENTENCE IS KEPT AND IS AN ADDITION OVER 4.6.34, WHICH
        HAD NO None BRANCH AT ALL. It is what keeps an unresolved frame
        separable from a resolved-empty one for a reader who debugs the early
        window. It rides BESIDE the ladder, never in place of it.
        """
        out = _build_safety_net_context("session-x", None)
        assert out, "the safety net returned an empty string for an unresolved frame"
        assert LADDER in out, (
            "an unresolved frame lost the orchestrator marker. The classifier "
            "not running says nothing about who the reader is, and the "
            "population behind that frame is mostly a primary user."
        )
        assert BOOTSTRAP in out, (
            "an unresolved frame kept the marker and lost the bootstrap "
            "directive, so no marker is stamped and the deny stands"
        )
        assert "before the session role was resolved" in out, (
            "the unresolved-frame case lost its distinguishing sentence, so a "
            "reader can no longer tell it from the resolved-empty case"
        )

    def test_unresolved_does_not_claim_the_unknown_role_fact(self):
        """None and 'unknown' stay DIFFERENT, and the difference is a fact.

        The unknown-role notice asserts that no `--agent` flag was recognized.
        For an unresolved frame the classifier did not run, so that fact was
        never established and the notice must NOT be emitted. Asserting it
        would claim more than the system knows, which is the one half of the
        original None argument that survives.
        """
        out = _build_safety_net_context("session-x", None)
        assert LADDER in out, (
            "the ladder is missing, so this arm cannot show what rides beside it"
        )
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "an unresolved frame received the unknown-role notice, which "
            "asserts a classifier result that was never computed"
        )
        assert _build_safety_net_context("session-x", None) != \
            _build_safety_net_context("session-x", "unknown"), (
            "the None case and the 'unknown' case now emit identical text, so "
            "the two have been collapsed into one"
        )

    def test_lead_is_unchanged(self):
        out = _build_safety_net_context("session-x", "lead")
        assert out, "the safety net returned an empty string for a lead frame"
        assert LADDER in out, "the safety net stopped delivering the lead ladder"
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "a lead frame received the unknown-role notice from the safety net"
        )

    def test_teammate_is_unchanged(self):
        out = _build_safety_net_context("session-x", "teammate")
        assert TEAMMATE_MARKER in out, "the teammate safety-net marker is gone"
        assert LADDER not in out, "a teammate frame received the lead ladder"
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "a teammate frame received the unknown-role notice"
        )
