"""Emit-skip accounting: the journal-emit seam and the count over what it
records.

Two surfaces, one mechanism:

1. `append_event_checked` — promoted from a PRIVATE helper in
   task_lifecycle_gate to shared, so dispatch_gate can reach it. It had only
   INCIDENTAL coverage through its callers, which vanishes silently when
   those callers change; these are its first direct tests. It is what turns a
   lost emit into a `journal_emit_skipped` record instead of silence.
2. `count_emit_skips` — the consumer-side count over those records, read by
   the wrap-up retrospective's Q5.

WHAT THIS PAIR DOES AND DOES NOT COVER, because the boundary is the whole
reason the pair exists. A skipped `dispatch_site` emit is a dispatch that
happened and left no sample, so the reported mean is over fewer dispatches
than occurred; these two surfaces are what let the consumer SAY SO instead of
reporting a quietly-thinned figure. But they see only emit loss that
successfully RECORDS a skip. An emit lost without leaving a
`journal_emit_skipped` event is invisible here too — smaller than the gap it
closes, and not zero.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.session_journal import (  # noqa: E402
    SKIP_CAUSE_RAISED,
    SKIP_CAUSE_RETURNED_FALSE,
    append_event_checked,
)
from shared.variety_divergence import count_emit_skips  # noqa: E402


def skip(skipped_type, cause=SKIP_CAUSE_RETURNED_FALSE):
    return {"type": "journal_emit_skipped", "skipped_type": skipped_type,
            "cause": cause}


# =============================================================================
# append_event_checked — the promoted seam's FIRST direct coverage
# =============================================================================
class TestPromotedSeam:
    @pytest.fixture
    def spy(self, monkeypatch):
        """Capture what reaches the journal, without touching a real one."""
        import shared.session_journal as sj
        written: list[dict] = []

        def fake(event):
            written.append(event)
            return not event.get("_fail")

        monkeypatch.setattr(sj, "append_event", fake)
        return written

    def test_success_returns_true_and_records_no_skip(self, spy):
        assert append_event_checked({"v": 1, "type": "x"}, "x") is True
        assert [e for e in spy if e.get("type") == "journal_emit_skipped"] == []

    def test_returned_false_records_a_skip_with_that_cause(self, spy):
        assert append_event_checked({"v": 1, "type": "x", "_fail": True}, "x") is False
        skips = [e for e in spy if e.get("type") == "journal_emit_skipped"]
        assert len(skips) == 1
        assert skips[0]["skipped_type"] == "x"
        assert skips[0]["cause"] == SKIP_CAUSE_RETURNED_FALSE

    def test_raise_records_a_DISTINCT_cause(self, monkeypatch):
        """RAISED must not collapse into RETURNED-FALSE. A writer defect and a
        schema rejection have different remedies; one 'failed' bucket rebuilds
        the ambiguity capturing the bool removed."""
        import shared.session_journal as sj
        written: list[dict] = []
        calls = {"n": 0}

        def fake(event):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("journal exploded")
            written.append(event)
            return True

        monkeypatch.setattr(sj, "append_event", fake)
        assert append_event_checked({"v": 1, "type": "x"}, "x") is False
        assert written[0]["cause"] == SKIP_CAUSE_RAISED
        assert written[0]["cause"] != SKIP_CAUSE_RETURNED_FALSE

    def test_task_id_recorded_when_given(self, spy):
        append_event_checked({"v": 1, "type": "x", "_fail": True}, "x", "42")
        assert spy[-1]["task_id"] == "42"

    def test_NO_RECURSION_when_the_skip_record_itself_fails(self, monkeypatch):
        """A failure-to-record-a-failure must TERMINATE, not retry into the
        substrate that just failed — otherwise the degraded case becomes the
        loudest thing in the journal. Every write fails here; the helper must
        return False, attempt the record at most once more, and not raise."""
        import shared.session_journal as sj
        calls = {"n": 0}

        def always_fail(event):
            calls["n"] += 1
            return False

        monkeypatch.setattr(sj, "append_event", always_fail)
        assert append_event_checked({"v": 1, "type": "x"}, "x") is False
        assert calls["n"] == 2, "one primary attempt + exactly one skip record"

    def test_hostile_task_id_is_bounded_and_sanitised(self, spy):
        append_event_checked({"v": 1, "type": "x", "_fail": True}, "x",
                             "a\x00b" + "Z" * 50000)
        rec = spy[-1]["task_id"]
        assert len(rec) < 3000 and "\x00" not in rec and "[truncated]" in rec

    def test_never_raises_even_when_stderr_is_dead(self, spy, monkeypatch):
        class Dead:
            def write(self, *a):
                raise OSError("stderr gone")

            def flush(self, *a):
                pass

        monkeypatch.setattr(sys, "stderr", Dead())
        assert append_event_checked({"v": 1, "type": "x", "_fail": True}, "x") is False


# =============================================================================
# count_emit_skips — consumer-side counting
# =============================================================================
class TestCountEmitSkips:
    def test_counts_by_type_and_cause(self):
        r = count_emit_skips([
            skip("dispatch_site"),
            skip("dispatch_site", SKIP_CAUSE_RAISED),
            skip("dispatch_decision"),
        ])
        assert r["total"] == 3
        assert r["by_type"] == {"dispatch_site": 2, "dispatch_decision": 1}
        assert r["by_cause"] == {SKIP_CAUSE_RETURNED_FALSE: 2, SKIP_CAUSE_RAISED: 1}

    def test_causes_stay_separate(self):
        """Collapsing RAISED into RETURNED-FALSE would rebuild one layer up
        the ambiguity the capture removed."""
        r = count_emit_skips([skip("dispatch_site", SKIP_CAUSE_RAISED)])
        assert list(r["by_cause"]) == [SKIP_CAUSE_RAISED]

    @pytest.mark.parametrize("bad", [None, "", 0, {"a": 1}, [None, 7, "x"]])
    def test_malformed_input_is_total_and_never_raises(self, bad):
        r = count_emit_skips(bad if isinstance(bad, list) else bad)
        assert r["total"] == 0

    def test_empty_is_zero_not_an_error(self):
        assert count_emit_skips([])["total"] == 0
