"""The two HANDOFF schema advisories wired into task_lifecycle_gate:

  handoff_schema_invalid_at_completion — lead-side, at the completing write
  handoff_schema_invalid_at_write_time — author-side, at their own write

EVERY ARM HERE IS A POSITIVE CONTROL OR ITS PAIRED NEGATIVE. A schema advisory
that never fires is indistinguishable from a green suite, so each SILENT row
sits beside a FIRES row built from the same fixture.

Both advisories key on a handoff that is PRESENT. Nothing here fires on a
completion carrying no handoff at all: signal completions, session briefings
and other exempt work legitimately store none, and "may this owner complete
without a HANDOFF?" is a question this gate does not answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import task_lifecycle_gate as tlg  # noqa: E402
from fixtures.emitter import VALID_HANDOFF  # noqa: E402

TEAM = "pact-test"
LEAD = "PACT:pact-orchestrator"

# The case issue #1543 reports: legacy-spelled and otherwise perfect.
LEGACY_HANDOFF = {
    "produced": ["src/auth.ts"],
    "key_decisions": ["Used JWT"],
    "uncertainty": [],
    "integration": ["UserService"],
    "open_questions": [],
}


@pytest.fixture
def emit_events(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(tlg, "append_event", lambda e: events.append(e) or True)
    return events


def _completed(*, subject="devops: implement", owner="devops", handoff=VALID_HANDOFF,
               task_type=None):
    """TaskUpdate(status=completed) post-state, as the lead's acceptance."""
    metadata: dict = {}
    if handoff is not None:
        metadata["handoff"] = handoff
    if task_type is not None:
        metadata["type"] = task_type
    return {
        "tool_name": "TaskUpdate",
        "agent_type": LEAD,
        "tool_input": {"taskId": "42", "status": "completed"},
        "tool_response": {
            "task": {
                "id": "42",
                "subject": subject,
                "owner": owner,
                "metadata": metadata,
            }
        },
    }


def _write(handoff):
    """A non-completed metadata TaskUpdate — the author's own write."""
    metadata = {} if handoff is None else {"handoff": handoff}
    return {
        "tool_name": "TaskUpdate",
        "agent_type": LEAD,
        "tool_input": {"taskId": "42", "metadata": metadata},
        "tool_response": {},
    }


def _rules(payload, tmp_path, monkeypatch, pact_context):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    pact_context(team_name=TEAM, session_id="s1")
    return [rule for rule, _ in tlg.evaluate_lifecycle(payload)]


class TestCompletionTimeSchema:
    def test_fires_on_legacy_spelling(self, tmp_path, monkeypatch, pact_context,
                                      emit_events):
        rules = _rules(_completed(handoff=LEGACY_HANDOFF), tmp_path, monkeypatch,
                       pact_context)
        assert "handoff_schema_invalid_at_completion" in rules

    def test_legacy_handoff_still_emits(self, tmp_path, monkeypatch, pact_context,
                                        emit_events):
        """One advisory, ZERO LOSS, zero blockage. A legacy-spelled handoff is
        a dict like any other, so the journal event still lands."""
        _rules(_completed(handoff=LEGACY_HANDOFF), tmp_path, monkeypatch, pact_context)
        assert len(emit_events) == 1

    def test_silent_on_the_repos_valid_fixture(self, tmp_path, monkeypatch,
                                               pact_context, emit_events):
        rules = _rules(_completed(), tmp_path, monkeypatch, pact_context)
        assert "handoff_schema_invalid_at_completion" not in rules


class TestWriteTimeSchema:
    def test_fires_on_legacy_spelling(self, tmp_path, monkeypatch, pact_context):
        rules = _rules(_write(LEGACY_HANDOFF), tmp_path, monkeypatch, pact_context)
        assert "handoff_schema_invalid_at_write_time" in rules

    def test_silent_on_valid_handoff(self, tmp_path, monkeypatch, pact_context):
        rules = _rules(_write(VALID_HANDOFF), tmp_path, monkeypatch, pact_context)
        assert "handoff_schema_invalid_at_write_time" not in rules

    def test_silent_when_no_handoff_key(self, tmp_path, monkeypatch, pact_context):
        """A teammate writing only intentional_wait is not writing a HANDOFF.
        This silence is also what keeps the two-run advisory-equality pin in
        test_per_write_adversarial_matrix green."""
        rules = _rules(_write(None), tmp_path, monkeypatch, pact_context)
        assert "handoff_schema_invalid_at_write_time" not in rules
