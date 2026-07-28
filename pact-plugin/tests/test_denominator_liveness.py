"""The denominator liveness checks, and the promoted journal-emit seam.

Three surfaces, one commit:

1. `append_event_checked` — promoted from a PRIVATE helper in
   task_lifecycle_gate to shared, so dispatch_gate can reach it. It had only
   INCIDENTAL coverage through its callers, which vanishes silently when
   those callers change; these are its first direct tests.
2. `check_denominator_liveness` — Check A. A PURE HELPER, not markdown prose:
   this whole rebuild exists because a Q5 term was prose-emitted, and prose
   does not fail. A predicate in `wrap-up.md` could not be unit-tested,
   could not be mutation-proven, and could not redden when someone edited the
   paragraph around it.
3. `count_emit_skips` — Check B's consumer-side count.

The through-line is ONE MECHANISM, TWO CONSUMERS: a `journal_emit_skipped`
event reads as emit-site loss to Check B, and as "my own witness was dropped"
to Check A. The tests that matter most are the ones proving the second
consumer can actually see it, because that failure is silent — Check A would
keep reporting healthy while blind to its own degradation.
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
from shared.variety_divergence import (  # noqa: E402
    LIVENESS_ALIVE,
    LIVENESS_DEAD,
    LIVENESS_INCONCLUSIVE,
    check_denominator_liveness,
    count_emit_skips,
)

EXEMPT = frozenset({"pact-secretary"})


def decision(subagent_type):
    return {"type": "dispatch_decision", "subagent_type": subagent_type}


def site(n=1):
    return [{"type": "dispatch_site", "task_id": str(i)} for i in range(n)]


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
# Check A — binary liveness
# =============================================================================
class TestCheckA:
    def test_dead_when_sites_empty_and_a_specialist_spawned(self):
        r = check_denominator_liveness([], [decision("pact-backend-coder")], [], EXEMPT)
        assert r["state"] == LIVENESS_DEAD
        assert r["dispatch_sites"] == 0 and r["witness_spawns"] == 1

    def test_alive_when_sites_present(self):
        r = check_denominator_liveness(site(2), [decision("pact-backend-coder")], [], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE

    def test_alive_when_nothing_was_dispatched_at_all(self):
        """The common healthy case: no sites AND no countable spawns. Most
        real sessions dispatch nothing, so tripping here would make the check
        useless noise."""
        r = check_denominator_liveness([], [], [], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE

    def test_raw_counts_and_NO_ratio(self):
        """The ratio was never the signal (0.20-4.00 on the corpus, useless);
        the witness was chosen for being degenerate. A ratio key would invite
        exactly the tunable threshold this check does not have."""
        r = check_denominator_liveness([], [decision("pact-backend-coder")], [], EXEMPT)
        assert set(r) == {"state", "dispatch_sites", "witness_spawns", "witness_skips"}
        assert not any("ratio" in k or "coverage" in k for k in r)


class TestCheckAWitnessFilter:
    """The correction. Unfiltered, the specified predicate trips in 117
    legitimately-empty sessions; filtered, 5. dispatch_decision fires on EVERY
    spawn, including the bootstrap secretary's — 248 of 856 events."""

    @pytest.mark.parametrize("st", ["pact-secretary"])
    def test_teachback_exempt_spawn_is_NOT_a_witness(self, st):
        r = check_denominator_liveness([], [decision(st)], [], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE, "the secretary must not trip Check A"
        assert r["witness_spawns"] == 0

    @pytest.mark.parametrize("st", ["Explore", "general-purpose", "fork",
                                    "claude-code-guide", "", None, 7])
    def test_non_pact_spawn_is_NOT_a_witness(self, st):
        r = check_denominator_liveness([], [decision(st)], [], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE
        assert r["witness_spawns"] == 0

    def test_the_filter_DISCRIMINATES(self):
        """The arm that makes the correction observable. A bootstrap-only
        session — secretary spawn, no dispatch sites — is the exact shape that
        false-fired 117 times. If the exemption leg is dropped this reddens;
        without this arm, the corrected and uncorrected predicates agree on
        every other case here and the fix would be untested."""
        bootstrap_only = [decision("pact-secretary")]
        assert check_denominator_liveness([], bootstrap_only, [], EXEMPT)["state"] == LIVENESS_ALIVE
        # and the same session WITH a real specialist must still trip
        real = bootstrap_only + [decision("pact-test-engineer")]
        assert check_denominator_liveness([], real, [], EXEMPT)["state"] == LIVENESS_DEAD

    def test_exempt_set_is_threaded_not_hardcoded(self):
        """Check A's exclusion set must come from the same SSOT as the emit
        predicate; if they diverge the witness mis-aims silently."""
        r = check_denominator_liveness([], [decision("pact-backend-coder")], [],
                                       frozenset({"pact-backend-coder"}))
        assert r["state"] == LIVENESS_ALIVE


class TestCheckAInconclusive:
    """A liveness check that knows its witness is lossy must not return
    'alive' — and must not return 'dead' either, because a dropped witness
    makes BOTH readings untrustworthy."""

    def test_witness_skip_yields_INCONCLUSIVE_not_alive(self):
        r = check_denominator_liveness(site(2), [decision("pact-backend-coder")],
                                       [skip("dispatch_decision")], EXEMPT)
        assert r["state"] == LIVENESS_INCONCLUSIVE
        assert r["witness_skips"] == 1

    def test_witness_skip_OVERRIDES_a_would_be_dead_verdict(self):
        r = check_denominator_liveness([], [decision("pact-backend-coder")],
                                       [skip("dispatch_decision")], EXEMPT)
        assert r["state"] == LIVENESS_INCONCLUSIVE, (
            "a dropped witness makes the DEAD reading untrustworthy too"
        )

    def test_a_NON_witness_skip_does_not_make_it_inconclusive(self):
        """A lost dispatch_site is emit-site loss for Check B — it does not
        impugn Check A's witness. Treating every skip as witness degradation
        would make Check A useless the moment any emit was lost."""
        r = check_denominator_liveness(site(2), [decision("pact-backend-coder")],
                                       [skip("dispatch_site")], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE
        assert r["witness_skips"] == 0

    def test_INCONCLUSIVE_is_a_CHECK_A_verdict_not_a_COVERAGE_reason(self):
        """THE SEPARATION THIS COMMIT MUST NOT LOSE.

        INCONCLUSIVE is a sibling of `denominator_stream_dead` on Check A's
        own verdict. It must NEVER appear as a `reason` from
        `compute_variety_divergence`, because the two answer different
        questions over different inputs: coverage never reads the
        `dispatch_decision` stream at all.

        If it leaked into the coverage enum, a dropped WITNESS would suppress
        a perfectly good coverage ratio — one stream's degradation silently
        invalidating a measurement it does not feed. That is the conflation,
        and separating the verdicts is the fix."""
        from shared.variety_divergence import compute_variety_divergence

        cases = [
            (12, [11, 12], 2),      # ordinary surfaced path
            (12, [], 0),            # no dispatch sites
            (12, [], 5),            # zero coverage
            (None, [11], 1),        # feature variety missing
            (12, [11, 12, 13], 1),  # more stamps than sites
        ]
        for feature, totals, count in cases:
            r = compute_variety_divergence(feature, totals, count)
            assert r.get("reason") != LIVENESS_INCONCLUSIVE
            assert r.get("reason") != LIVENESS_DEAD

    def test_a_witness_drop_does_NOT_disturb_the_coverage_figure(self):
        """The concrete thing the separation protects. `zero_coverage` is the
        ONLY reason carrying surfaced=True — the loudest legitimate reading
        this metric produces — and it is precisely what a mis-placed
        INCONCLUSIVE would swallow. Coverage is computed from the
        dispatch_site stream alone, so a degraded witness must leave it
        untouched; the liveness verdict reports the degradation separately."""
        from shared.variety_divergence import compute_variety_divergence

        coverage = compute_variety_divergence(12, [], 5)
        assert coverage["reason"] == "zero_coverage"
        assert coverage["surfaced"] is True

        # The witness is degraded in the same session ...
        liveness = check_denominator_liveness(
            site(5), [decision("pact-backend-coder")],
            [skip("dispatch_decision")], EXEMPT,
        )
        assert liveness["state"] == LIVENESS_INCONCLUSIVE
        # ... and the coverage figure is entirely unaffected by that.
        assert compute_variety_divergence(12, [], 5) == coverage


# =============================================================================
# THE GAP — executable, so it cannot be quietly forgotten
# =============================================================================
class TestTheUndisguisedGap:
    """A5's original concern WAS partial degradation, so this mitigation is
    strictly NARROWER than the concern that motivated it. Both assertions
    below are required: the second is the one that documents the hole."""

    def test_suppress_ALL_emits_goes_RED(self):
        decisions = [decision("pact-backend-coder") for _ in range(10)]
        r = check_denominator_liveness([], decisions, [], EXEMPT)
        assert r["state"] == LIVENESS_DEAD

    def test_suppress_N_PERCENT_stays_GREEN__THIS_IS_THE_GAP(self):
        """9 of 10 dispatch sites lost and Check A still reports ALIVE.

        This is not a defect in the check — it is the documented limit of a
        binary liveness test, asserted here so a future reader cannot mistake
        Check A for partial-loss coverage. If someone later builds partial
        detection, THIS TEST SHOULD FAIL and be rewritten; until then its
        passing is the honest statement that the gap is open."""
        decisions = [decision("pact-backend-coder") for _ in range(10)]
        r = check_denominator_liveness(site(1), decisions, [], EXEMPT)
        assert r["state"] == LIVENESS_ALIVE, (
            "documented gap: partial emit loss is invisible to this check"
        )


# =============================================================================
# Check B — consumer-side counting
# =============================================================================
class TestCheckB:
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
