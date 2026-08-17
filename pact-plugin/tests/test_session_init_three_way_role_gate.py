"""The session-start role gate must consume all THREE classifier values.

WHAT WENT WRONG. `classify_session_role` returns "lead", "teammate" or
"unknown". Both emitters of the orchestrator instructions consumed TWO of the
three: `if frame_role == "teammate": ... else: <orchestrator ladder>`. A LEAD
frame and an UNKNOWN frame took the same branch and emitted the same bytes, so
a frame of unknown role was handed the instructions that do the most damage in
the wrong hands.

MEASURED, with the parameter beside the count. Population: the 155 files
matching `subagents/*.jsonl` for one team session. 13 of those frames fired a
compact SessionStart, and 13 of 13 received the orchestrator instructions. The
branch that emits them needs an ABSENT agent type to be reached, so those
frames classified as "unknown".

WHY A LEAD KEEPS ITS LADDER, and it is measured rather than argued: `is_lead`
returned true for this session, proven by the session context file, which no
frame can write without passing an `is_lead` gate.

THE ARMING PROBLEM THESE ARMS ANSWER. `session_init` is fail-open by contract:
an error must not block a session start. So a hook that emits nothing and a
hook that ran and correctly said nothing produce the same bytes, which are
none. AN ARM THAT ASSERTS ONLY AN ABSENCE CANNOT SEPARATE THOSE TWO STATES,
and it passes when the build path dies for a cause it was not written to catch.
EVERY ARM BELOW ASSERTS A PRESENCE AND AN ABSENCE TOGETHER. The presence half
is what proves the run reached the emission point, so the absence half then
means the branch declined rather than that the run died.
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
TEAMMATE_MARKER = "YOUR PACT ROLE: teammate."
_SESSION_ID = "11111111-2222-3333-4444-555555555555"
_PROJECT_DIR = "/tmp/pact-three-way-gate"


def _run_main(frame, monkeypatch, tmp_path):
    """Drive the real `session_init.main()` and return its additionalContext.

    Heavy collaborators are stubbed. THE ROLE GATE IS NOT STUBBED: the frame
    below carries the agent type the classifier reads, so the branch under test
    is the one the hook takes in production.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", _PROJECT_DIR)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    stdin_data = json.dumps({"session_id": _SESSION_ID, "source": "startup", **frame})
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


class TestMainSiteThreeWay:
    """The live emission path, driven through `main()`."""

    def test_lead_frame_keeps_the_ladder(self, monkeypatch, tmp_path):
        """THE ARM THAT PROTECTS THE PRODUCT. A lead frame must still receive
        its bootstrap instructions. SEPARATION: the emitted block is non-empty
        AND carries the ladder, so a dead run fails the first assertion rather
        than passing the second by accident."""
        out = _run_main({"agent_type": "PACT:pact-orchestrator"}, monkeypatch, tmp_path)
        assert out, (
            "a lead frame emitted NO additionalContext at all. This is the "
            "not-delivered state, not the declined state: the run did not "
            "reach the emission point."
        )
        assert LADDER in out, (
            "a LEAD frame lost its orchestrator instructions. The three-way "
            "gate must keep the lead branch intact: the lead resolves through "
            "is_lead on its own evidence, which is what makes this safe."
        )

    def test_unknown_frame_gets_no_ladder_and_a_note(self, monkeypatch, tmp_path):
        """THE ARM THAT CLOSES THE DEFECT, and it carries its own non-vacuity.
        SEPARATION: the note is the PRESENCE half, so the absence of the ladder
        is measured inside a run that provably reached the emission point. With
        the note dropped, a dead run would satisfy the absence half alone."""
        out = _run_main({}, monkeypatch, tmp_path)
        assert out, (
            "an unknown frame emitted NO additionalContext at all, so this arm "
            "cannot tell a correct decline from a dead build path."
        )
        assert _UNKNOWN_ROLE_NOTICE in out, (
            "the unknown branch emitted no note. Without it the absence "
            "assertion below is unfalsifiable in a fail-open hook."
        )
        assert LADDER not in out, (
            "an UNKNOWN frame received the orchestrator instructions. That is "
            "the defect: the gate consumed two of three classifier values and "
            "sent unknown down the lead branch."
        )

    def test_teammate_frame_gets_neither_the_ladder_nor_the_note(
        self, monkeypatch, tmp_path
    ):
        """The teammate branch must not change. SEPARATION: the run is proven
        live by the SystemExit(0) plus a parsed output envelope in `_run_main`,
        and the two absences are asserted together so a shift of the teammate
        frame into either sibling branch reddens."""
        out = _run_main({"agent_type": "some-teammate-name"}, monkeypatch, tmp_path)
        assert LADDER not in out, (
            "a teammate frame received the orchestrator instructions"
        )
        assert _UNKNOWN_ROLE_NOTICE not in out, (
            "a teammate frame received the unknown-role note, so the teammate "
            "branch now falls through to the unknown branch"
        )


class TestSafetyNetThreeWay:
    """The exception path. `_build_safety_net_context` is pure, so each case is
    driven directly. THE FOUR INPUTS ARE FOUR CASES: None is not the string
    'unknown'. None means the classifier did not run. 'unknown' means it ran
    and found no role."""

    def test_lead_keeps_the_ladder(self):
        out = _build_safety_net_context("session-x", "lead")
        assert out, "the safety net returned an empty string for a lead frame"
        assert LADDER in out, "the safety net stopped delivering the lead ladder"

    def test_teammate_keeps_its_own_marker(self):
        out = _build_safety_net_context("session-x", "teammate")
        assert TEAMMATE_MARKER in out, "the teammate safety-net marker is gone"
        assert LADDER not in out, "a teammate frame received the lead ladder"

    def test_unknown_gets_the_note_and_no_ladder(self):
        out = _build_safety_net_context("session-x", "unknown")
        assert _UNKNOWN_ROLE_NOTICE in out, (
            "the unknown safety-net branch emitted no note, so the absence "
            "assertion below cannot separate a decline from an empty return"
        )
        assert LADDER not in out, (
            "an unknown frame received the lead ladder from the safety net"
        )
        assert TEAMMATE_MARKER not in out, (
            "an unknown frame was labelled a teammate, which claims a role the "
            "classifier did not find"
        )

    def test_none_is_ruled_separately_from_unknown(self):
        """None and 'unknown' are DIFFERENT facts and get DIFFERENT text. A
        reader debugging an early-window failure must be able to tell that the
        role was never resolved rather than resolved-empty."""
        out = _build_safety_net_context("session-x", None)
        assert out, "the safety net returned an empty string for an unresolved frame"
        assert "before the session role was resolved" in out, (
            "the unresolved-frame case lost its distinguishing sentence, so it "
            "can no longer be told apart from the resolved-empty case"
        )
        assert LADDER not in out, (
            "an unresolved frame received the lead ladder. An earlier comment "
            "called that a known no-regression default. It is the misroute."
        )
        assert _build_safety_net_context("session-x", None) != \
            _build_safety_net_context("session-x", "unknown"), (
            "the None case and the 'unknown' case now emit identical text, so "
            "the two have been collapsed into one"
        )
