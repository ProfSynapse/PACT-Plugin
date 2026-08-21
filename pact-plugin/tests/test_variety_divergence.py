"""
GC-immune regression suite for the wrap-up Q5 coverage denominator + the
coverage-exceeds-unity tripwire (epic #972, children #971/#963).

This file is the dedicated home for the pure helpers in
shared/variety_divergence.py that back the §4 Orchestration Retrospective
Q5 (variety divergence):

  - extract_dispatch_coverage(dispatch_site_events) — derives BOTH Q5 terms
    from ONE pass over ONE list. The DENOMINATOR is the existence of each
    `dispatch_site` event; the NUMERATOR is the resolvable stamps within
    those same events. Because every element of `variety_totals` comes from
    an event that also incremented `total`, coverage > 1.0 is structurally
    impossible rather than merely unobserved.

  - the coverage_exceeds_unity early-return in compute_variety_divergence —
    a non-clamping advisory tripwire: when stamped > total it returns
    reason="coverage_exceeds_unity", surfaced=False, coverage left UNCLAMPED.
    It is now UNREACHABLE from the Q5 path (see above) and is retained only
    as defense-in-depth for a caller that assembles the two terms by hand.

The predecessor denominator — a 3-argument helper counting
agent_dispatch + review_dispatch.reviewers + deduped remediation — was
RETIRED when the denominator moved to the one-event topology. Its tests are
deleted rather than ported: they encoded 3-marker dedup semantics that have
no referent here, and porting them would have manufactured meaning. The
properties that survive the change of subject are re-expressed below and in
test_session_journal.py (arc-scoping), NOT dropped.

Non-vacuity: extract_dispatch_coverage is a NET-NEW symbol, so a source-only
revert removes it entirely (ImportError / collection error, not a clean
assertion fail). The behavioural guards that DO fail cleanly are the
absent-vs-malformed partition and the structural `stamped <= total` bound,
both asserted over arbitrary input below.

GC-immune: every fixture is a synthetic journal event built via
session_journal.make_event — zero dependence on the GC-reaped task store.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.session_journal import make_event  # noqa: E402
from shared.variety_divergence import (  # noqa: E402
    compute_variety_divergence,
    extract_dispatch_coverage,
    extract_final_dispatch_coverage,
    resolve_arc_start,
)


# =============================================================================
# Fixture builders — faithful journal-event shapes (see
# _REQUIRED_FIELDS_BY_TYPE / _OPTIONAL_FIELDS_BY_TYPE in session_journal.py)
# =============================================================================

_TS = "2026-06-15T12:00:00Z"


class TestExtractDispatchCoverage:
    """The replacement denominator. Both Q5 terms, one pass, one list.

    These are the behavioural guards that replace the retired 3-marker
    tests. The partition they pin — ABSENT stamp vs PRESENT-but-unresolvable
    stamp — is the one thing the old helper had no concept of, because a
    marker either existed or it did not.
    """

    STAMPED = {"task_id": "1", "variety": {"total": 9}}
    ABSENT = {"task_id": "2"}
    MALFORMED = {"task_id": "3", "variety": {"total": "junk"}}
    DIMENSION_SUM = {
        "task_id": "4",
        "variety": {"novelty": 2, "scope": 2, "uncertainty": 2, "risk": 2},
    }

    def test_denominator_counts_event_existence_not_stamp_presence(self):
        """The whole point of the one-event topology: an un-stamped dispatch
        is still a dispatch SITE, so it lowers coverage instead of vanishing
        from the denominator along with its stamp."""
        _totals, total, _malformed = extract_dispatch_coverage(
            [self.STAMPED, self.ABSENT, self.MALFORMED]
        )
        assert total == 3

    def test_absent_stamp_is_a_coverage_gap_not_a_malformed_stamp(self):
        """An absent stamp is an honest un-stamped dispatch — the gap
        coverage exists to surface. Folding it into `malformed` would leave
        the ratio unchanged while reporting a normal gap as a producer
        defect, which trains readers to ignore the malformed signal."""
        totals, total, malformed = extract_dispatch_coverage([self.ABSENT])
        assert totals == []
        assert total == 1
        assert malformed == [], (
            "a MISSING stamp and a MALFORMED stamp have different remedies "
            "and must never be merged"
        )

    def test_present_but_unresolvable_stamp_is_malformed(self):
        totals, total, malformed = extract_dispatch_coverage([self.MALFORMED])
        assert totals == []
        assert total == 1
        assert malformed == [self.MALFORMED]

    def test_dimension_sum_recovery_counts_as_stamped(self):
        """A stamp recovered through a non-canonical resolver candidate IS
        resolved; which candidate won is not this consumer's business.
        Counting it as malformed would record the dimension-sum recovery —
        20 events across 8 sessions — as a data-quality problem, inverting
        the fix that introduced it."""
        totals, _total, malformed = extract_dispatch_coverage(
            [self.DIMENSION_SUM]
        )
        assert totals == [8]
        assert malformed == []

    def test_one_unresolvable_stamp_costs_only_its_own_row(self):
        """Totality: the extraction is defined for every event the journal
        can hand it, so a single bad stamp cannot destroy the whole list."""
        totals, total, malformed = extract_dispatch_coverage(
            [self.STAMPED, self.MALFORMED, self.DIMENSION_SUM, self.ABSENT]
        )
        assert totals == [9, 8]
        assert total == 4
        assert len(malformed) == 1

    @pytest.mark.parametrize(
        "hostile",
        [None, "string", 42, {"not": "a list"}, object()],
    )
    def test_non_list_input_yields_the_empty_triple(self, hostile):
        assert extract_dispatch_coverage(hostile) == ([], 0, [])

    def test_non_dict_element_is_a_site_with_no_stamp(self):
        """It existed, so it counts as a site; it carries nothing resolvable.
        Never raises — this runs inside a wrap-up the session depends on."""
        totals, total, malformed = extract_dispatch_coverage(
            ["not-a-dict", None, self.STAMPED]
        )
        assert totals == [9]
        assert total == 3
        assert malformed == []


class TestCoverageExceedsUnityAdvisory:
    """The non-clamping coverage>1.0 tripwire in compute_variety_divergence."""

    def test_advisory_fires_when_stamped_exceeds_total(self):
        """Synthetic stamped > total (zero-residual under the real denominator,
        so it is exercised directly): reason set, surfaced=False, coverage
        left UNCLAMPED so the anomaly is visible."""
        result = compute_variety_divergence(
            feature_variety=8,
            dispatch_varieties=[8, 8, 8],  # stamped = 3
            total_pact_dispatch_count=2,  # total = 2 < stamped
        )
        assert result["reason"] == "coverage_exceeds_unity"
        assert result["coverage"] == pytest.approx(1.5)  # 3/2, UNCLAMPED
        assert result["coverage"] > 1.0
        assert result["surfaced"] is False

    def test_advisory_does_not_clamp_to_unity(self):
        """Explicit: the advisory does NOT clamp coverage to 1.0 — a clamp
        would HIDE the very denominator regression this tripwire exists to
        catch."""
        result = compute_variety_divergence(4, [12, 12], 1)  # stamped 2 > total 1
        assert result["reason"] == "coverage_exceeds_unity"
        assert result["coverage"] == pytest.approx(2.0)
        assert result["coverage"] != 1.0

    def test_advisory_fires_even_when_feature_variety_missing(self):
        """The tripwire precedes the feature_variety_missing fail-open, so it
        fires (delta=None) even with no feature variety — the broken
        denominator is surfaced regardless."""
        result = compute_variety_divergence(None, [8, 8, 8], 2)
        assert result["reason"] == "coverage_exceeds_unity"
        assert result["delta"] is None
        assert result["surfaced"] is False

    @pytest.mark.parametrize(
        "events",
        [
            pytest.param([], id="empty"),
            pytest.param([{"task_id": "1"}], id="one_unstamped"),
            pytest.param(
                [{"task_id": "1", "variety": {"total": 9}}], id="one_stamped"
            ),
            pytest.param(
                [
                    {"task_id": "1", "variety": {"total": 9}},
                    {"task_id": "2"},
                    {"task_id": "3", "variety": {"total": "junk"}},
                    {"task_id": "4", "variety": {"n": 1}},
                    "not-a-dict",
                ],
                id="mixed_including_hostile",
            ),
        ],
    )
    def test_advisory_is_unreachable_from_the_real_helper(self, events):
        """Complement, strengthened by the one-event topology: over terms
        produced by extract_dispatch_coverage the advisory can NEVER fire,
        because every stamped event also incremented the total. The old
        version proved zero-residual on ONE fixture; this proves it
        structurally, including on hostile input."""
        variety_totals, total, _malformed = extract_dispatch_coverage(events)
        assert len(variety_totals) <= total, (
            "coverage > 1.0 must be structurally impossible, not merely "
            "unobserved — a stamped event that did not increment the total "
            "would mean the two terms came from different populations"
        )
        result = compute_variety_divergence(6, variety_totals, total)
        assert result["reason"] != "coverage_exceeds_unity"
        assert result["coverage"] <= 1.0

    def test_advisory_silent_at_exact_unity_boundary_within_threshold(self):
        """The advisory fires on stamped > total (STRICT). At the exact
        boundary stamped == total (coverage EXACTLY 1.0) it must NOT fire —
        the normal divergence path runs. feature=8, dispatch=[8,8], total=2:
        mean=8, delta=0 → within_threshold, coverage 2/2=1.0. This pins the
        strict-`>` semantics; under a `>`→`>=` regression the advisory would
        fire here (reason='coverage_exceeds_unity') and this test fails."""
        result = compute_variety_divergence(
            feature_variety=8,
            dispatch_varieties=[8, 8],  # stamped = 2
            total_pact_dispatch_count=2,  # total = 2  → stamped == total
        )
        assert result["coverage"] == pytest.approx(1.0)
        assert result["reason"] != "coverage_exceeds_unity"
        assert result["reason"] == "within_threshold"
        assert result["surfaced"] is False

    def test_advisory_at_unity_boundary_does_not_suppress_real_divergence(self):
        """The sharper boundary case (the survivor the review found): at
        stamped == total a REAL divergence must still SURFACE — the advisory
        must not pre-empt it. feature=4, dispatch=[8,8], total=2: coverage 1.0,
        mean 8, delta 4 ≥ 2 → SURFACED undershot. A `>`→`>=` regression fires
        the advisory here (surfaced=False, reason='coverage_exceeds_unity'),
        SUPPRESSING the divergence → this test fails under that mutation."""
        result = compute_variety_divergence(
            feature_variety=4,
            dispatch_varieties=[8, 8],  # stamped = 2
            total_pact_dispatch_count=2,  # stamped == total
        )
        assert result["coverage"] == pytest.approx(1.0)
        assert result["surfaced"] is True
        assert result["reason"] is None
        assert result["direction"] == "undershot"


# =============================================================================
# resolve_arc_start — the --since arc-boundary resolver (#963)
# =============================================================================


class TestResolveArcStart:
    """resolve_arc_start(variety_assessed_events, feature_task_id): the LATEST
    variety_assessed.ts matching feature_task_id (the arc-start for --since),
    parse-not-lexical, fail-open None. Pure function, journal-event inputs."""

    def _va(self, task_id, ts):
        return make_event(
            "variety_assessed",
            task_id=task_id,
            variety={
                "novelty": 2,
                "scope": 2,
                "uncertainty": 2,
                "risk": 2,
                "total": 8,
            },
            ts=ts,
        )

    def test_returns_latest_ts_for_matching_feature_across_arcs(self):
        """The platform reuses task_ids across arcs, so the feature's id can
        match a PRIOR arc's variety_assessed too; the LATEST-ts match is the
        current arc. (Non-vacuity: a latest→earliest mutation returns the
        prior-arc ts and fails this.)"""
        events = [
            self._va("100", "2026-06-13T12:00:00Z"),  # prior arc
            self._va("100", "2026-06-14T12:00:00Z"),  # current arc
        ]
        assert resolve_arc_start(events, "100") == "2026-06-14T12:00:00Z"

    def test_filters_by_feature_task_id_ignoring_other_features(self):
        """A LATER variety_assessed for a DIFFERENT feature must NOT leak in —
        returns the matching feature's latest, not the global latest. (Proves
        the task_id filter is load-bearing.)"""
        events = [
            self._va("100", "2026-06-14T12:00:00Z"),
            self._va("200", "2026-06-15T12:00:00Z"),  # later, different feature
        ]
        assert resolve_arc_start(events, "100") == "2026-06-14T12:00:00Z"

    def test_cross_format_compared_by_instant_returns_original_string(self):
        """Cross-format (prior arc in +00:00, current in Z) is compared by
        PARSED instant; the RETURN is the original ts STRING of the max (passed
        verbatim to --since, which _ts_ge re-parses)."""
        events = [
            self._va("100", "2026-06-14T00:00:00+00:00"),  # earlier
            self._va("100", "2026-06-14T12:00:00Z"),  # later (current)
        ]
        assert resolve_arc_start(events, "100") == "2026-06-14T12:00:00Z"

    def test_returns_none_when_no_matching_feature(self):
        events = [self._va("200", "2026-06-14T12:00:00Z")]
        assert resolve_arc_start(events, "100") is None

    def test_returns_none_for_empty_events(self):
        assert resolve_arc_start([], "100") is None

    def test_skips_matching_event_missing_ts_keeps_valid_match(self):
        """A matching event with no `ts` is skipped; a remaining valid match
        wins. (Raw dict — make_event would auto-stamp a ts.)"""
        events = [
            self._va("100", "2026-06-14T12:00:00Z"),
            {"type": "variety_assessed", "task_id": "100", "variety": {"total": 8}},
        ]
        assert resolve_arc_start(events, "100") == "2026-06-14T12:00:00Z"

    def test_returns_none_when_only_match_missing_ts(self):
        events = [
            {"type": "variety_assessed", "task_id": "100", "variety": {"total": 8}},
        ]
        assert resolve_arc_start(events, "100") is None

    def test_returns_none_when_all_matches_unparseable(self):
        """Fail-open: matching entries whose ts is unparseable are skipped; if
        no parseable match remains → None (caller omits --since)."""
        events = [self._va("100", "garbage"), self._va("100", "also-bad")]
        assert resolve_arc_start(events, "100") is None

    def test_mixed_naive_and_aware_ts_does_not_crash_selects_aware_latest(self):
        """Regression: a sequence mixing a tz-AWARE ts ('...Z' → +00:00) with a
        tz-NAIVE-parseable one (a date-only '2026-06-16' → naive datetime via
        fromisoformat) must NOT raise TypeError ('can't compare offset-naive
        and offset-aware datetimes'). The `dt > latest_dt` compare lives INSIDE
        the try/except (mirroring _ts_ge), so the incomparable naive entry is
        SKIPPED, not fatal, and the latest tz-AWARE ts is returned.

        The date-only entry parses cleanly (it is NOT garbage) but is naive, so
        comparing it against an already-set AWARE latest is what raised — a
        parses-OK-but-incompatible probe, distinct from the unparseable case.
        Note the naive '2026-06-16' is date-wise LATER than both aware entries,
        so its being SKIPPED (not selected) is load-bearing: a regression that
        let it through would change the result.

        Structured assert-no-raise (catch → pytest.fail) so a pre-fix revert
        (compare moved back OUTSIDE the try) yields a deterministic FAILED, not
        a runtime ERROR that rtk's error-count-dropping summary could hide."""
        events = [
            self._va("100", "2026-06-14T12:00:00Z"),  # aware
            self._va("100", "2026-06-16"),  # naive (date-only) — the crasher
            self._va("100", "2026-06-15T12:00:00Z"),  # aware, the latest aware
        ]
        try:
            result = resolve_arc_start(events, "100")
        except TypeError as exc:  # pragma: no cover - the regression we guard
            pytest.fail(
                "resolve_arc_start raised on a mixed naive+aware ts sequence "
                f"(the try-scope regression resurfaced): {exc}"
            )
        assert result == "2026-06-15T12:00:00Z"


class TestExtractFinalDispatchCoverage:
    """The Q5 join: MEMBERSHIP from `dispatch_site`, VALUE from the latest
    `task_metadata_snapshot` of the same task.

    The defect this replaces: Q5 read the AS-DISPATCHED total, so a stamp
    revised after the dispatch was invisible to the calibration figure.

    Non-vacuity: `extract_final_dispatch_coverage` is a NET-NEW symbol, so a
    source-only revert removes it (ImportError at collection, not a clean
    assertion fail). The guards that DO fail cleanly are the non-member
    exclusion, the kept-member fallback, and the disjointness of the two
    counters, each asserted below on values that a broken implementation
    cannot reproduce by accident.
    """

    def _site(self, task_id, variety=None):
        """A `dispatch_site` event. `variety=None` means the key is ABSENT."""
        fields = {"task_id": task_id}
        if variety is not None:
            fields["variety"] = variety
        return make_event("dispatch_site", **fields)

    def _snap(self, task_id, metadata, ts=_TS):
        return make_event(
            "task_metadata_snapshot",
            task_id=task_id,
            metadata=metadata,
            ts=ts,
        )

    # -- The structural exclusion ------------------------------------------

    def test_non_member_snapshots_cannot_enter_the_distribution(self):
        """A snapshot for a task that NO dispatch_site names is unreachable,
        because the loop iterates the member list.

        The extras carry totals DISTINCT from each member value, which is
        what makes this arm able to FAIL: with a shared value, an
        implementation that admits non-members yields a list that looks
        correct. A REDIRECT that sourced membership from the snapshot stream
        would widen the population and break one-member-means-one-dispatch.
        """
        sites = [
            self._site("1", {"total": 9}),
            self._site("2", {"total": 10}),
        ]
        snapshots = [
            self._snap("1", {"variety": {"total": 9}}),
            self._snap("2", {"variety": {"total": 10}}),
            self._snap("90", {"variety": {"total": 15}}),  # non-member
            self._snap("91", {"variety": {"total": 16}}),  # non-member
        ]
        result = extract_final_dispatch_coverage(sites, snapshots)
        assert result["sites"] == 2
        assert len(result["variety_totals"]) <= result["sites"]
        assert sorted(result["variety_totals"]) == [9, 10]
        assert 15 not in result["variety_totals"]
        assert 16 not in result["variety_totals"]

    def test_member_with_no_snapshot_keeps_its_dispatch_site_value(self):
        """The opposite direction. An implementation that DROPS an
        un-snapshotted member passes the exclusion arm above and silently
        shrinks the denominator, which is the failure this design prevents.
        """
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], []
        )
        assert result["variety_totals"] == [9]
        assert result["sites"] == 1
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    # -- Which value wins --------------------------------------------------

    def test_snapshot_value_wins_and_the_member_counts_as_superseded(self):
        """The whole point of the join: the FINAL total, not the
        as-dispatched one. 9 and 11 sit in different bands, so a reader can
        see which value the distribution carries."""
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})],
            [self._snap("1", {"variety": {"total": 11}})],
        )
        assert result["variety_totals"] == [11]
        assert result["superseded"] == 1
        assert result["fallback_used"] == 0

    def test_agreeing_streams_do_not_count_as_superseded(self):
        """`superseded` counts DISAGREEMENT, not the presence of a snapshot.
        Counting each snapshot-sourced member would report the corrected
        defect as universal and make the counter useless."""
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})],
            [self._snap("1", {"variety": {"total": 9}})],
        )
        assert result["variety_totals"] == [9]
        assert result["superseded"] == 0
        assert result["fallback_used"] == 0

    def test_snapshot_reaches_the_nested_variety_score_candidate(self):
        """The snapshot side passes `metadata` as the resolver's SECOND
        argument, so the non-canonical `metadata["variety_score"]` candidate
        stays reachable.

        Non-vacuity: drop that argument and the snapshot resolves nothing,
        the member falls back to 9, and `fallback_used` becomes 1. So the
        two assertions below both move under that mutation.
        """
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})],
            [self._snap("1", {"variety_score": 12})],
        )
        assert result["variety_totals"] == [12]
        assert result["fallback_used"] == 0

    # -- The two counters --------------------------------------------------

    def test_fallback_and_superseded_are_disjoint(self):
        """A member that took the fallback has no second value to compare
        against, so it cannot reach `superseded`. A reader can add the two
        counts together without a double count.

        Member 1 is superseded. Members 2 and 3 take the fallback, one for
        each arm: an unresolvable snapshot, and no snapshot at all.
        """
        sites = [
            self._site("1", {"total": 9}),
            self._site("2", {"total": 10}),
            self._site("3", {"total": 11}),
        ]
        snapshots = [
            self._snap("1", {"variety": {"total": 13}}),
            self._snap("2", {"variety": {"total": "junk"}}),
        ]
        result = extract_final_dispatch_coverage(sites, snapshots)
        assert result["superseded"] == 1
        assert result["fallback_used"] == 2
        assert result["superseded"] + result["fallback_used"] <= result["sites"]
        assert sorted(result["variety_totals"]) == [10, 11, 13]

    def test_fallback_counts_arm_three_where_neither_stream_resolves(self):
        """`fallback_used` is "the final value did NOT come from a
        snapshot", which covers arm 3 as well as arm 2. Counting arm 2 alone
        answers a narrower question and keeps arm 3 unobserved."""
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": "junk"})],
            [self._snap("1", {"variety": {"total": "junk"}})],
        )
        assert result["variety_totals"] == []
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    # -- The latest-picker -------------------------------------------------

    def test_latest_snapshot_is_chosen_by_parsed_instant_not_by_position(self):
        """`make_event` stamps `ts` as `...Z` and `canonical_since()` emits
        `...+00:00`. A lexical compare is decided by the first byte after the
        seconds, and `+` (0x2B) sorts before `Z` (0x5A).

        The LATER instant is placed FIRST in the list, so a picker that takes
        the last element returns 11 and fails here.
        """
        snapshots = [
            self._snap(
                "1", {"variety": {"total": 12}}, ts="2026-06-15T00:00:00+00:00"
            ),
            self._snap(
                "1", {"variety": {"total": 11}}, ts="2026-06-14T12:00:00Z"
            ),
        ]
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], snapshots
        )
        assert result["variety_totals"] == [12]

    def test_equal_instant_tie_break_takes_the_later_element(self):
        """Journal events stamp `ts` at second granularity, so a tie is
        ordinary. LAST-WINS, because this function picks the FINAL value.
        `resolve_arc_start` keeps the FIRST of two equal instants, and it is
        correct for a different question: an arc BOUNDARY."""
        snapshots = [
            self._snap("1", {"variety": {"total": 11}}, ts=_TS),
            self._snap("1", {"variety": {"total": 12}}, ts=_TS),
        ]
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], snapshots
        )
        assert result["variety_totals"] == [12]

    def test_unparseable_and_missing_ts_snapshots_are_skipped(self):
        """Fail-open, mirroring `resolve_arc_start`. The usable snapshot
        wins rather than the whole member falling back."""
        snapshots = [
            self._snap("1", {"variety": {"total": 11}}, ts="not-a-timestamp"),
            self._snap("1", {"variety": {"total": 12}}, ts=""),
            self._snap("1", {"variety": {"total": 13}}, ts=_TS),
        ]
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], snapshots
        )
        assert result["variety_totals"] == [13]
        assert result["fallback_used"] == 0

    # -- Classification ----------------------------------------------------

    def test_absent_stamp_is_a_coverage_gap_and_a_junk_stamp_is_malformed(self):
        """The partition the old helper pins, ON THE FALLBACK PATH ONLY. The
        two findings have opposite remedies and are never merged.

        THE SNAPSHOT LIST IS EMPTY AND THAT IS DELIBERATE. DO NOT GIVE THIS
        ARM A NON-EMPTY ONE. With no snapshots each member takes the
        fallback, so this arm reaches the fallback partition and NOT the
        join. An earlier docstring here claimed the partition is preserved
        "through the join", which its fixture cannot show.

        THE EMPTY LIST IS LOAD-BEARING RATHER THAN INCIDENTAL. This arm is
        the only detector of the rule that `malformed` is classified from the
        value the join FINALLY uses rather than from the `dispatch_site`
        value alone. An implementation that classifies early agrees with a
        correct one for EVERY input that has no snapshots, so only a
        classify-early mutation separates them, and this arm is what catches
        it. Widening the fixture can take that detection to zero and the
        suite would stay green.

        THE JOIN PATH IS COVERED BY ITS OWN SIBLING, which is the arm
        directly below. Add to that one, not to this one.
        """
        absent = self._site("1")
        junk = self._site("2", {"total": "junk"})
        result = extract_final_dispatch_coverage([absent, junk], [])
        assert result["variety_totals"] == []
        assert result["sites"] == 2
        assert result["malformed"] == [junk]
        assert result["fallback_used"] == 2

    def test_a_resolving_snapshot_reports_the_dispatch_side_it_replaced(self):
        """THE SIBLING OF THE ARM ABOVE, on the path where the join RUNS.

        The two members here are the same two shapes as the arm above, an
        ABSENT stamp and a JUNK one, and each now has a snapshot that
        RESOLVES. That is the input the empty-list fixture cannot produce and
        it is where the two implementations diverge.

        The value is taken from the snapshot in each case, so `malformed`
        empties and `fallback_used` falls to zero. WITHOUT THE TWO COUNTERS
        BELOW that is all a reader would see, and a dispatch that carried no
        stamp would be indistinguishable from one that carried a good one.

        EACH SIDE IS ASSERTED. The counters alone would pass against an
        implementation that drops the members entirely, so the resolved
        totals are asserted to land in the distribution as well.
        """
        absent = self._site("1")
        junk = self._site("2", {"total": "junk"})
        absent_two = self._site("3")
        snapshots = [
            self._snap("1", {"variety": {"total": 9}}),
            self._snap("2", {"variety": {"total": 11}}),
            self._snap("3", {"variety": {"total": 7}}),
        ]
        result = extract_final_dispatch_coverage(
            [absent, junk, absent_two], snapshots
        )
        # The positive half: the members are kept and carry snapshot values.
        assert sorted(result["variety_totals"]) == [7, 9, 11]
        assert result["sites"] == 3
        # The join emptied the fallback-path terms.
        assert result["malformed"] == []
        assert result["fallback_used"] == 0
        # THE TWO COUNTS ARE ASYMMETRIC ON PURPOSE, 2 AGAINST 1, AND THE
        # ASYMMETRY IS THE WHOLE POINT. Equal expected values would constrain
        # the MULTISET of the two counts and NOT THE MAPPING from counter to
        # value, so a transposition of the two counters would map 1 and 1 onto
        # 1 and 1 and pass. No additional assertion on these two cells can
        # repair that, because the blindness lives in the VALUES rather than
        # in the number of assertions. With 2 and 1 a transposition reads 1
        # and 2, so this pins WHICH counter carries WHICH finding.
        assert result["late_stamped"] == 2
        assert result["dispatch_malformed"] == 1

    def test_a_dimension_revision_that_holds_the_total_is_counted(self):
        """A correction that moved dimensions and left the total is REPORTED.

        This is the shape measured on real session data: a stamp went from
        novelty 2 and risk 3 to novelty 3 and risk 2, and the total stayed
        11 on each side. A counter that compares TOTALS reads zero on it.

        The two totals agreeing is asserted here as well. Without that, an
        implementation that counted a MOVED total would also pass.
        """
        member = self._site(
            "1", {"novelty": 2, "scope": 3, "uncertainty": 3, "risk": 3, "total": 11}
        )
        snapshots = [
            self._snap(
                "1",
                {
                    "variety": {
                        "novelty": 3,
                        "scope": 3,
                        "uncertainty": 3,
                        "risk": 2,
                        "total": 11,
                    }
                },
            )
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [11]
        assert result["superseded"] == 0
        assert result["superseded_dimensions_only"] == 1
        assert result["dimensions_incomparable"] == 0

    def test_agreeing_vectors_are_not_a_dimension_revision(self):
        """The CONTROL for the arm above. Same shape, nothing revised.

        Without this arm, an implementation that counted every agreeing-total
        member as a dimension revision would pass the arm above.
        """
        stamp = {"novelty": 2, "scope": 3, "uncertainty": 3, "risk": 3, "total": 11}
        member = self._site("1", dict(stamp))
        snapshots = [self._snap("1", {"variety": dict(stamp)})]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [11]
        assert result["superseded"] == 0
        assert result["superseded_dimensions_only"] == 0
        assert result["dimensions_incomparable"] == 0

    def test_an_incomplete_vector_is_reported_not_absorbed(self):
        """A partial dimension vector cannot be compared, and it SAYS SO.

        The dispatch projection is tolerant of a partial stamp, so a member
        can carry a total and fewer than four dimensions. The totals agree
        here, so the member would otherwise read as full agreement that
        nothing measured.

        `superseded_dimensions_only` is asserted to be ZERO, which is what
        separates this from an implementation that treats a partial vector as
        a difference.
        """
        member = self._site("1", {"novelty": 2, "total": 11})
        snapshots = [
            self._snap(
                "1",
                {
                    "variety": {
                        "novelty": 3,
                        "scope": 3,
                        "uncertainty": 3,
                        "risk": 2,
                        "total": 11,
                    }
                },
            )
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [11]
        assert result["dimensions_incomparable"] == 1
        assert result["superseded_dimensions_only"] == 0
        assert result["superseded"] == 0

    def test_an_out_of_range_dimension_makes_the_vector_incomparable(self):
        """The dimension guard checks the RANGE, and not only the TYPE.

        A dimension of 9 is an int, so a type-only guard accepts it and the
        vector reads as complete. The two vectors then DIFFER and the member
        reads as a dimension revision, which this data cannot support.

        The two totals are equal here, so the member reaches the cell where
        the vector comparison decides the answer. The two counters are each
        asserted, because a type-only guard MOVES the member from one to the
        other, and an assertion on one alone would not see the move.
        """
        member = self._site(
            "1", {"novelty": 9, "scope": 3, "uncertainty": 3, "risk": 3, "total": 11}
        )
        snapshots = [
            self._snap(
                "1",
                {
                    "variety": {
                        "novelty": 2,
                        "scope": 3,
                        "uncertainty": 3,
                        "risk": 3,
                        "total": 11,
                    }
                },
            )
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [11]
        assert result["dimensions_incomparable"] == 1
        assert result["superseded_dimensions_only"] == 0

    def test_a_moved_total_is_superseded_and_not_a_dimension_revision(self):
        """The two superseded counters are DISJOINT, asserted on one member.

        The vectors differ here AND the total moved. The docstring argues
        that a moved total takes the member before any vector comparison
        runs, so a reader can add the two counts without a double count.
        This arm is that argument executed.
        """
        member = self._site(
            "1", {"novelty": 2, "scope": 3, "uncertainty": 3, "risk": 3, "total": 11}
        )
        snapshots = [
            self._snap(
                "1",
                {
                    "variety": {
                        "novelty": 3,
                        "scope": 3,
                        "uncertainty": 3,
                        "risk": 3,
                        "total": 12,
                    }
                },
            )
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [12]
        assert result["superseded"] == 1
        assert result["superseded_dimensions_only"] == 0
        assert result["dimensions_incomparable"] == 0

    # -- Hostile input -----------------------------------------------------

    @pytest.mark.parametrize(
        "hostile",
        [None, "string", 42, {"not": "a list"}, object()],
    )
    def test_non_list_members_yield_the_empty_result(self, hostile):
        """The empty result carries EVERY key the populated result carries.

        The equality is against a whole dict on purpose. A reader that pulls
        a counter off this result must find it here too, so a key added to
        the populated return and forgotten here would raise a KeyError in a
        wrap-up rather than in a test.
        """
        assert extract_final_dispatch_coverage(hostile, []) == {
            "variety_totals": [],
            "sites": 0,
            "malformed": [],
            "fallback_used": 0,
            "superseded": 0,
            "late_stamped": 0,
            "dispatch_malformed": 0,
            "superseded_dimensions_only": 0,
            "dimensions_incomparable": 0,
        }

    @pytest.mark.parametrize(
        "hostile",
        [None, "string", 42, {"not": "a list"}, object()],
    )
    def test_non_list_snapshots_leave_each_member_on_its_fallback(self, hostile):
        """The join degrades to the old behaviour rather than raising. This
        runs inside a wrap-up that the session depends on."""
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], hostile
        )
        assert result["variety_totals"] == [9]
        assert result["fallback_used"] == 1

    def test_non_dict_member_is_a_site_that_joins_to_nothing(self):
        """It existed, so it counts as a site. It carries nothing resolvable
        and it is not malformed, which mirrors `extract_dispatch_coverage`."""
        result = extract_final_dispatch_coverage(
            ["not-a-dict", None, self._site("1", {"total": 9})],
            [self._snap("1", {"variety": {"total": 11}})],
        )
        assert result["variety_totals"] == [11]
        assert result["sites"] == 3
        assert result["malformed"] == []
        assert result["fallback_used"] == 2

    def test_a_member_without_a_task_id_joins_to_nothing(self):
        """A `task_id` of None is skipped rather than keyed, so two events
        that each lack one cannot join to each other on the string "None"."""
        member = {"v": 1, "type": "dispatch_site", "variety": {"total": 9}}
        snapshots = [
            {
                "v": 1,
                "type": "task_metadata_snapshot",
                "metadata": {"variety": {"total": 14}},
                "ts": _TS,
            }
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [9]
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    # -- The join key ------------------------------------------------------
    #
    # EACH ARM BELOW FEEDS THE TWO STREAMS DISAGREEING VALUES, and that is
    # what makes the arm able to fail. The site carries 9 and the snapshot
    # carries 12, so a join that MISSES returns [9] with `fallback_used` 1,
    # and a join that HITS returns [12] with `fallback_used` 0. On agreeing
    # values the two outcomes are one list and the arm measures nothing.

    def test_an_int_snapshot_id_joins_a_str_member_id(self):
        """The `str()` normalize sits on the TWO sides of the join, so the
        streams align when one of them emits a bare int.

        DIRECTION MATTERS AND THIS IS THE FIRST OF TWO. Here the SNAPSHOT
        carries the int. An index that keys on the raw value cannot be found
        by a stringified member lookup, so this arm fails when the normalize
        is removed from the INDEX side alone, and also when it is removed
        from the two sides together.
        """
        member = self._site("7", {"total": 9})
        snapshots = [self._snap(7, {"variety": {"total": 12}})]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [12]
        assert result["fallback_used"] == 0
        assert result["superseded"] == 1

    def test_an_int_member_id_joins_a_str_snapshot_id(self):
        """The opposite direction, and it is a DIFFERENT condition.

        Here the MEMBER carries the int. A lookup that keys on the raw value
        misses a stringified index, so this arm fails when the normalize is
        removed from the two sides together. It PASSES when the normalize is
        removed from the index side alone, which is what separates the two
        defects rather than merging them into one finding.
        """
        member = self._site(7, {"total": 9})
        snapshots = [self._snap("7", {"variety": {"total": 12}})]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [12]
        assert result["fallback_used"] == 0
        assert result["superseded"] == 1

    def test_a_member_with_no_task_id_does_not_join_the_string_none_key(self):
        """`emit_task_metadata_snapshot` writes the id through
        `sanitize_path_component(str(task_id))`, so a snapshot for a task
        with no id lands on the LITERAL STRING "None". A member with no id
        must not join it.

        This is the collision the member-side None guard prevents, and it is
        a shape the emit path can produce rather than an adversarial one. The
        sibling arm above covers the case where NEITHER side carries an id.
        This arm covers the mixed case, where the guard is the only thing
        holding the two apart.
        """
        member = self._site(None, {"total": 9})
        snapshots = [self._snap("None", {"variety": {"total": 12}})]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [9]
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    def test_a_snapshot_with_no_task_id_does_not_join_the_string_none_key(self):
        """The mirror of the arm above, and the guard is on the other side.

        A snapshot that carries no id is skipped rather than keyed, so a
        member carrying the literal string "None" as its id cannot reach it.
        """
        member = self._site("None", {"total": 9})
        snapshots = [self._snap(None, {"variety": {"total": 12}})]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [9]
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    # -- The latest-picker -------------------------------------------------

    def test_equal_instant_z_and_offset_forms_are_ordered_as_instants(self):
        """THE TWO STAMPS NAME ONE INSTANT IN TWO SPELLINGS, which is the
        case a byte compare gets incorrect.

        `make_event` stamps `...Z` and `canonical_since()` emits `...+00:00`.
        `+` (0x2B) sorts before `Z` (0x5A), so a byte compare finds the
        `+00:00` element SMALLER than an equal-instant `Z` element and keeps
        the earlier one. Last-wins on an equal instant says the later element
        wins, so the correct answer is 12 and a byte compare returns 11.

        THE SIBLING ARM THAT NAMES THE PARSE CANNOT REACH THIS. It separates
        its two stamps by a DAY, and a byte compare orders different dates
        correctly, so it returns the same answer for a parsed compare and for
        a byte compare. Equal instants are the only inputs that discriminate
        the two.
        """
        snapshots = [
            self._snap(
                "1", {"variety": {"total": 11}}, ts="2026-06-15T12:00:00Z"
            ),
            self._snap(
                "1", {"variety": {"total": 12}}, ts="2026-06-15T12:00:00+00:00"
            ),
        ]
        result = extract_final_dispatch_coverage(
            [self._site("1", {"total": 9})], snapshots
        )
        assert result["variety_totals"] == [12]

    def test_the_only_snapshot_having_no_ts_sends_the_member_to_the_fallback(
        self,
    ):
        """A snapshot with no `ts` is SKIPPED, and it is not dated to an
        early instant and kept.

        THE SIBLING SKIP ARM CANNOT REACH THIS, because it puts a usable
        snapshot LAST and greatest, so a picker that keeps a ts-less snapshot
        at the epoch returns the same answer. Here the ts-less snapshot is
        the ONLY one, so keeping it changes the result from the fallback
        value to the snapshot value.
        """
        member = self._site("1", {"total": 9})
        snapshots = [self._snap("1", {"variety": {"total": 12}}, ts="")]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [9]
        assert result["fallback_used"] == 1
        assert result["superseded"] == 0

    def test_a_non_dict_snapshot_element_does_not_raise(self):
        """The docstring says the function is pure and does not raise. A
        snapshot LIST holding a non-dict element is the input that tests it.

        The sibling hostile arms pass a non-list `snapshot_events` and a
        non-dict MEMBER. Neither reaches the element read inside the snapshot
        loop, so this arm covers the one remaining shape. The usable snapshot
        sits after the junk, so the arm fails on a raise and also on a loop
        that abandons the rest of the list.
        """
        member = self._site("1", {"total": 9})
        snapshots = [
            "not-a-dict",
            42,
            None,
            self._snap("1", {"variety": {"total": 12}}),
        ]
        result = extract_final_dispatch_coverage([member], snapshots)
        assert result["variety_totals"] == [12]
        assert result["fallback_used"] == 0
        assert result["superseded"] == 1
