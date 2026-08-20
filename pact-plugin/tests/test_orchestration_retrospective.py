"""
Tests for orchestration retrospective in wrap-up.md.

Tests cover:
1. Orchestration Retrospective section exists
2. Four assessment questions defined
3. pact-memory save convention documented
4. Estimation pattern question documented
5. Q5/Q6 journal-read hardening
6. Q5/Q6 extractions are total (no direct-indexing comprehension)
7. Q5's recovery path depends on the dimension-sum resolver candidate
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from shared.teachback_schema import resolve_variety_total  # noqa: E402
from shared.variety_divergence import (  # noqa: E402
    extract_dispatch_coverage,
    extract_final_dispatch_coverage,
)

WRAPUP_PATH = Path(__file__).parent.parent / "commands" / "wrap-up.md"


@pytest.fixture
def q5():
    """The Q5 question line, module-scoped for the classes that execute the
    expression it carries."""
    return _question_line(
        WRAPUP_PATH.read_text(encoding="utf-8"), "5. **Variety divergence**"
    )


@pytest.fixture
def q6():
    return _question_line(
        WRAPUP_PATH.read_text(encoding="utf-8"),
        "6. **Variety acknowledgment signals**",
    )


class TestOrchestrationRetrospective:
    """Tests for orchestration retrospective in wrap-up command."""

    @pytest.fixture
    def wrapup_content(self):
        return WRAPUP_PATH.read_text(encoding="utf-8")

    def test_retrospective_section_exists(self, wrapup_content):
        assert "Orchestration Retrospective" in wrapup_content

    def test_variety_accuracy_question(self, wrapup_content):
        assert "Variety accuracy" in wrapup_content

    def test_phase_efficiency_question(self, wrapup_content):
        assert "Phase efficiency" in wrapup_content

    def test_specialist_fit_question(self, wrapup_content):
        assert "Specialist fit" in wrapup_content

    def test_estimation_pattern_question(self, wrapup_content):
        assert "Estimation pattern" in wrapup_content

    def test_memory_save_convention(self, wrapup_content):
        assert "orchestration_calibration" in wrapup_content


def _backticked_expression(line, prefix):
    """Return the single inline-backticked code span in `line` that starts with
    `prefix`. The retrospective questions carry their extraction code inline, so
    this lifts the ACTUAL documented expression out of the instruction rather
    than restating it in the test — a restatement would drift from the markdown
    silently and pin nothing."""
    for span in re.findall(r"`([^`]+)`", line):
        if span.startswith(prefix):
            return span
    raise AssertionError(f"no backticked expression starting with {prefix!r}")


def _run_extraction(expressions, events, snapshot_events=None):
    """Execute the documented extraction chain against `events` and return the
    resulting namespace.

    `exec` is the point, not a shortcut: wrap-up.md is executed by an LLM at
    runtime, so the only way to pin the instruction's BEHAVIOUR (rather than
    grep its wording) is to run the expression the file actually carries. The
    input is repo-controlled markdown.

    ACCEPTS A SEQUENCE, and that is load-bearing since the Q5 join. The join
    carries the helper CALL and the unpack as two separate backticked spans,
    so a lift of the unpack alone execs a statement that reads nothing from
    `events` and raises NameError. Running the spans IN ORDER pins the whole
    documented path rather than one line of it.

    `snapshot_events` defaults to EMPTY, which exercises the fallback arm: a
    member with no snapshot keeps its `dispatch_site` value. A caller that
    means to pin the snapshot-sourced arm passes its own list.
    """
    if isinstance(expressions, str):
        expressions = [expressions]
    namespace = {
        "events": events,
        "snapshot_events": [] if snapshot_events is None else snapshot_events,
        "resolve_variety_total": resolve_variety_total,
        "extract_dispatch_coverage": extract_dispatch_coverage,
        "extract_final_dispatch_coverage": extract_final_dispatch_coverage,
    }
    for expression in expressions:
        # noqa: S102 — repo-controlled instruction text
        exec(expression, namespace)  # noqa: S102
    return namespace


def _question_line(content, prefix):
    """Return the single wrap-up.md line beginning with `prefix` (each
    retrospective question is one long markdown line). Asserting WITHIN the
    specific question line is stronger than a whole-file substring grep."""
    for line in content.splitlines():
        if line.lstrip().startswith(prefix):
            return line
    raise AssertionError(f"question line not found for prefix {prefix!r}")


class TestRetroReadHardening:
    """#966 (docs-only): wrap-up Q5/Q6 journal-read guidance hardening — the
    explicit single-JSON-array parse, the output-masking bans, the Q5
    masked-empty re-read guard, and the Q6 fallback-on-zero that prevents a
    fabricated 0% signal rate from a masked/crashed read.

    These are STRUCTURAL (prose) assertions: they detect REMOVAL or
    rewording-away of the hardening instruction, but cannot prove an LLM
    obeys it at runtime — a known vacuity limit of prose tests, documented
    as a residual risk in the TEST HANDOFF. They are the appropriate
    coverage for a docs-only change whose logic is not extracted to code.
    """

    @pytest.fixture
    def wrapup_content(self):
        return WRAPUP_PATH.read_text(encoding="utf-8")

    @pytest.fixture
    def q5(self, wrapup_content):
        return _question_line(wrapup_content, "5. **Variety divergence**")

    @pytest.fixture
    def q6(self, wrapup_content):
        return _question_line(wrapup_content, "6. **Variety acknowledgment signals**")

    # --- Q5 read-mechanics hardening ---

    def test_q5_states_single_json_array_parse(self, q5):
        assert "SINGLE JSON array" in q5
        assert "json.loads(output)" in q5

    def test_q5_warns_against_line_by_line_parse(self, q5):
        assert "do NOT parse line-by-line" in q5

    def test_q5_bans_output_masking_pipes(self, q5):
        # the three constructs that mask a parse crash as emptiness
        assert "2>/dev/null" in q5
        assert "|| echo" in q5
        assert "`head`" in q5

    def test_q5_masked_empty_guard_precedes_omission_conclusion(self, q5):
        # the re-read guard must appear, and gate the omission conclusion
        assert "masked-empty guard" in q5
        assert "re-read the raw" in q5
        assert "session-journal.jsonl" in q5
        # RE-ANCHORED, strength unchanged. The landmark was the omission
        # note's old wording, "pre-dates per-dispatch stamping" -- which
        # asserted a CAUSE the reader cannot verify and which is false in
        # both branches: a session predating the emit and a session whose
        # emit path is broken produce the same journal signature. The note
        # now states what was OBSERVED, so the landmark moves with it.
        # Identical assertion shape: same three guard requirements, same
        # single ordering check, one substituted landmark string.
        assert "no dispatch sites recorded" in q5
        # ordering: the guard must precede the OMISSION conclusion
        assert q5.index("masked-empty guard") < q5.index(
            "no dispatch sites recorded"
        )

    def test_q5_denominator_comes_from_the_one_pass_helper(self, q5):
        """Successor to the retired-helper pin. The NEGATIVE half is the
        load-bearing one: it is what fails if someone reinstates
        `count_task_b_dispatch_sites` in the prose, which would leave the
        retirement silently incomplete.

        The positive half names `extract_final_dispatch_coverage` since the
        Q5 join: MEMBERSHIP continues to come from the `dispatch_site`
        stream, and the VALUE comes from the latest `task_metadata_snapshot`
        of the same task."""
        assert "extract_final_dispatch_coverage" in q5
        assert "count_task_b_dispatch_sites" not in q5, (
            "the retired 3-marker helper must not be named in Q5 — a "
            "reinstated mention means the denominator was not actually moved"
        )

    def test_q5_denominator_argument_is_the_resolvable_count_not_the_site_count(
        self, q5
    ):
        """THE FORBIDDEN-DENOMINATOR RULE, as an assertion instead of prose.

        Q5 marks `sites` FORBIDDEN as the third argument to
        `compute_variety_divergence`, because passing it revives the coverage
        ratio this question no longer reports. Until this pin that rule was
        carried by prose alone: a future edit could swap the argument back and
        nothing in the suite would go red.

        SCOPED TO THE DOCUMENTED CALL SPAN, which is what makes it a pin
        rather than decoration. Both obvious alternatives are unfalsifiable
        for this purpose, and the occupancy counts are why -- do not loosen
        this to either of them:

        - A line-wide `"sites" not in q5` is RED TODAY against correct prose.
          `sites` occurs SEVEN times on the Q5 line as a legitimately
          reported COUNT; the token is forbidden in one position, not on the
          line.
        - A bare `"len(variety_totals)" in <file>` cannot fail for the reason
          it claims. That literal occurs FOUR times in wrap-up.md, so the
          sample-output region alone satisfies it and the call could be
          changed to `sites` with the pin still green.

        The FULL call expression occurs exactly ONCE in the file, so lifting
        it is the one form that observes the argument this rule governs.
        Verified alongside it: the prefix `compute_variety_divergence(`
        selects exactly one backticked span, and correctly EXCLUDES the bare
        no-paren mention inside the FORBIDDEN sentence itself.

        Read the call out of the markdown rather than restating it, for the
        same reason `_backticked_expression` exists: a restatement drifts from
        the instruction silently and pins nothing.

        MUTATION THAT REDDENS: change the third argument in wrap-up.md from
        `len(variety_totals)` to `sites`.
        """
        call = _backticked_expression(q5, "compute_variety_divergence(")

        assert call.endswith("len(variety_totals))"), (
            "Q5's divergence call must take len(variety_totals) as its third "
            "argument -- the number of dispatches carrying a RESOLVABLE "
            f"stamp. Got: {call!r}"
        )
        assert "sites" not in call, (
            "`sites` has been passed to compute_variety_divergence. That "
            "revives the coverage ratio Q5 no longer reports, by making the "
            "denominator every recorded dispatch site rather than the ones "
            "whose stamp resolves. `sites` is a reported COUNT, never a "
            f"denominator. Got: {call!r}"
        )

    def test_q5_reads_the_dispatch_site_stream(self, q5):
        """The denominator is the dispatch_site event's EXISTENCE. Reading the
        old variety-independent markers for Q5 would rebuild the two-population
        split the one-event topology exists to remove."""
        assert "--type dispatch_site" in q5
        for retired_marker in ("--type agent_dispatch", "--type review_dispatch",
                               "--type remediation"):
            assert retired_marker not in q5

    def test_q5_derives_the_numerator_from_no_separate_stream(self, q5):
        """The coupling risk MOVED when the helper made `stamped <= total` an
        identity: the identity is internal to the helper and cannot stop a
        CONSUMER bypassing it. A future edit could take `total` from
        `extract_dispatch_coverage` while re-deriving the numerator from its
        own `dispatch_variety` read — the original two-population defect,
        verbatim, one level out.

        Keyed on the READ COMMAND, not the bare string, and that is
        deliberate: `dispatch_variety` must stay NAMEABLE as the Class-1
        cross-check witness. The pin is on it not being a RATIO INPUT.

        MUTATION THAT REDDENS: add a `read --type dispatch_variety` to Q5.
        """
        assert "--type dispatch_variety" not in q5, (
            "Q5 has reacquired its own dispatch_variety read. Both ratio "
            "terms must come from the single extract_dispatch_coverage pass; "
            "a second stream is how the numerator and denominator drift onto "
            "different populations. Naming dispatch_variety as the Class-1 "
            "cross-check witness is fine — READING it as a ratio input is not."
        )

    def test_q5_arc_scoped_with_since(self, q5):
        assert "Arc scope (current feature only)" in q5
        assert "--since" in q5

    # --- Q6 structural safety (no explicit re-read guard; rests on the
    #     parse bans + fallback-on-zero) ---

    def test_q6_states_single_json_array_parse(self, q6):
        assert "SINGLE JSON array" in q6
        assert "json.loads(output)" in q6

    def test_q6_bans_output_masking_pipes(self, q6):
        assert "2>/dev/null" in q6
        assert "|| echo" in q6
        assert "`head`" in q6

    def test_q6_fallback_on_zero_prevents_fabricated_signal_rate(self, q6):
        """The structural guarantee that a masked/crashed read (which yields
        zero teachback_ack events) cannot be reported as a real 0% signal
        rate: Q6 falls back to the task store ONLY when the journal yields
        zero teachback_ack events (#966 noted a masked read corrupting Q6 to
        0% vs a true 44%)."""
        assert "zero `teachback_ack` events" in q6
        assert "fall back to the legacy" in q6

    def test_q6_arc_scoped_with_since(self, q6):
        assert "--since" in q6

    def test_q6_carries_masked_empty_reread_guard(self, q6):
        """Q6 now MIRRORS Q5's explicit masked-empty re-read guard (the
        follow-up that closes the Q5/Q6 asymmetry): a masked/crashed
        teachback_ack read must be re-confirmed against the raw journal before
        any conclusion, so it cannot be reported as a real 0% cargo-cult
        signal rate (#966 noted a masked read corrupting Q6 to 0% vs a true
        44%). The guard must precede the fallback-on-zero branch."""
        assert "Masked-empty guard" in q6
        assert "re-read the raw" in q6
        assert "session-journal.jsonl" in q6
        assert "genuinely absent" in q6
        assert "0% signal rate" in q6
        # ordering: the re-read guard precedes the fallback-on-zero clause
        assert q6.index("Masked-empty guard") < q6.index("fall back to the legacy")


class TestTotalExtraction:
    """Both retrospective extractions must be TOTAL — defined for every event
    the journal can hand them — rather than aborting on the first bad one.

    Both questions used a direct-indexing comprehension, so a single event
    missing its key raised `KeyError` and destroyed the WHOLE list, not just
    that event. The blast radius is the session, not the row: measured
    2026-07-28 over 2254 journals, 20 `dispatch_variety` events lacked a usable
    `variety['total']`, and they sat in 8 sessions holding 289 events between
    them.

    These are STRUCTURAL (prose) assertions with the vacuity limit the sibling
    class documents: they detect the guard being removed or reworded away, but
    cannot prove an LLM obeys it at runtime. The negative halves are the
    load-bearing ones — they fail if a direct-indexing form is reinstated.
    """

    @pytest.fixture
    def wrapup_content(self):
        return WRAPUP_PATH.read_text(encoding="utf-8")

    @pytest.fixture
    def q5(self, wrapup_content):
        return _question_line(wrapup_content, "5. **Variety divergence**")

    @pytest.fixture
    def q6(self, wrapup_content):
        return _question_line(wrapup_content, "6. **Variety acknowledgment signals**")

    def test_q5_sources_both_terms_through_the_shared_helper(self, q5):
        """C-6 moved the resolver call INSIDE `extract_dispatch_coverage`, so
        Q5 no longer names it. The guarantee it carried — that the total is
        resolved rather than direct-indexed — did not go away; it moved into
        code, and is pinned behaviourally by
        `test_variety_divergence.py::TestExtractDispatchCoverage`. A prose pin
        satisfiable by an import line is weaker than a behavioural one.

        The helper is `extract_final_dispatch_coverage` since the Q5 join,
        and the behavioural pin moved with it, to
        `test_variety_divergence.py::TestExtractFinalDispatchCoverage`."""
        assert "extract_final_dispatch_coverage" in q5
        assert "shared.variety_divergence" in q5

    def test_q5_does_not_direct_index_the_total(self, q5):
        """The negative half: `[e["variety"]["total"] for e in events]` is the
        shape that aborts the whole comprehension on one malformed stamp."""
        assert '["variety"]["total"]' not in q5
        assert "for e in events]" not in q5

    def test_q5_sample_keys_the_two_delta_forms_off_surfaced(self, wrapup_content):
        """The rendering must key off the returned `surfaced` flag rather than
        re-deriving the verdict from `delta`. A renderer that decides for
        itself when a delta is worth surfacing reimplements the threshold, and
        the two copies drift silently — the reader sees a confident verdict
        that the computation never reached.

        AIMED AT THE SAMPLE BLOCK, NOT THE QUESTION LINE, and that is load-
        bearing: the flag is what SEPARATES the two forms, so the property
        lives where the forms are declared. The question line names `surfaced`
        only as one dict key among seven, and a pin there would assert a
        membership that survives every rendering mistake this guards against.

        SCOPE: structural (prose), with the vacuity limit this class documents
        — it detects the keying being dropped or reworded away, not an LLM
        disobeying it at run time. The behavioural half (that
        `compute_variety_divergence` sets `surfaced` correctly) is pinned in
        `test_per_dispatch_variety.py` and `test_variety_divergence.py`.

        MUTATION THAT REDDENS: strip `surfaced=True` / `surfaced=False` from
        the two form headers, leaving them separated by the delta wording
        alone — i.e. a sample that renders regardless of the flag.
        """
        headers = [
            line for line in wrapup_content.splitlines()
            if line.startswith("**SURFACED**") or line.startswith("**IN BAND**")
        ]
        assert len(headers) == 2, (
            "expected exactly one SURFACED and one IN BAND form header in the "
            f"Q5 sample block, found {len(headers)}: {headers}"
        )
        surfaced_header = next(h for h in headers if h.startswith("**SURFACED**"))
        in_band_header = next(h for h in headers if h.startswith("**IN BAND**"))
        assert "`surfaced=True`" in surfaced_header, (
            "the SURFACED form no longer declares `surfaced=True`. Without it "
            "the sample tells a renderer to decide from `delta` alone, which "
            "is the threshold reimplemented in prose."
        )
        assert "`surfaced=False`" in in_band_header, (
            "the IN BAND form no longer declares `surfaced=False`. The two "
            "forms are then separated by wording rather than by the flag the "
            "computation actually returns."
        )

    def test_q6_guards_the_flag_extraction(self, q6):
        assert "isinstance(e.get(\"rationale_articulates_this_dispatch\"), str)" in q6

    def test_q6_does_not_direct_index_the_flag(self, q6):
        assert "for e in events]" not in q6

    def test_q6_excludes_unreadable_acks_from_both_terms(self, q6):
        """Counting an unreadable ack in the denominator but not the numerator
        dilutes the rate toward "no concern" — the direction that hides the
        signal Q6 exists to surface."""
        assert "total_teachbacks = len(flags)" in q6
        assert "len(events) - len(flags)" in q6

    def test_q6_does_not_divide_when_no_flag_is_readable(self, q6):
        """`len(flags)` can be 0 while `events` is non-empty — a divisor the
        previous `len(events)` form could never produce."""
        assert "total_teachbacks > 0" in q6


class TestQ5ExtractionDependsOnTheDimensionSumCandidate:
    """The Q5 EXTRACTION PATH — the expression wrap-up.md actually carries —
    rests on `resolve_variety_total`'s FOURTH candidate (the four-dimension
    sum) and on no other.

    Measured 2026-07-28 across 2254 session journals: of the 20 `dispatch_variety`
    events lacking a usable `variety['total']`, 20 recover — and 0 are
    recoverable through candidate 2 (`score`) or candidate 3
    (`metadata.variety_score`). The malformed shape in the wild is exactly the
    four dimensions with no total.

    These RUN the documented expression rather than calling the resolver
    directly, and the distinction is the whole point. The resolver's own
    dimension-sum tests already exist in `test_teachback_schema.py`, so a test
    that calls `resolve_variety_total(...)` here would re-pin THEIR guard under
    a Q5 name and leave the extraction path unpinned. Executing the expression
    couples the candidate to this consumer: removing candidate 4 breaks these,
    and so does reverting the expression to a direct `variety['total']` index.

    Dropping candidate 4 fails DARK — the resolver returns `None` rather than
    raising, so the events vanish from the numerator and coverage drops with
    nothing to attribute it to.
    """

    # The malformed stamp exactly as it appears in the journal corpus: the four
    # dimensions, no total, no score. Candidates 1 and 2 cannot fire on it, and
    # candidate 3 reads a metadata argument the Q5 expression never passes — so
    # a recovery here can only have come from the dimension sum.
    CORPUS_MALFORMED_EVENT = {
        "task_id": "2",
        "variety": {"novelty": 2, "scope": 2, "uncertainty": 2, "risk": 2},
    }
    CANONICAL_EVENT = {"task_id": "1", "variety": {"total": 9}}

    @pytest.fixture
    def q5_expression(self, q5):
        """The documented chain, IN ORDER: the helper call, then the unpack.

        Q5 carries the join as two spans. Lifting the unpack alone runs a
        statement that reads nothing from `events`, so the pair is the unit
        that pins the extraction path.
        """
        return [
            _backticked_expression(q5, "coverage = "),
            _backticked_expression(q5, "variety_totals, "),
        ]

    def test_higher_candidates_cannot_fire_on_the_corpus_shape(self):
        """Fixture control. Without it, a shape that candidate 1 resolved would
        pass every test below while proving nothing about candidate 4."""
        variety = self.CORPUS_MALFORMED_EVENT["variety"]
        assert "total" not in variety
        assert "score" not in variety
        assert resolve_variety_total({}, {"variety_score": 8}) == 8, (
            "candidate 3 is live, so its silence below is the Q5 expression "
            "not passing metadata — not the candidate being gone"
        )

    def test_extraction_recovers_the_corpus_malformed_stamp(self, q5_expression):
        namespace = _run_extraction(
            q5_expression, [self.CANONICAL_EVENT, self.CORPUS_MALFORMED_EVENT]
        )
        assert namespace["variety_totals"] == [9, 8], (
            "the four-dimension sum is the ONLY path by which the 20 malformed "
            "stamps in the dispatch_site corpus reach Q5's numerator; drop "
            "candidate 4 and this returns [9], silently, with no exception"
        )

    def test_extraction_survives_an_unresolvable_event(self, q5_expression):
        """The C-1 defect itself: ONE bad event used to destroy the whole list.
        A stamp that no candidate can resolve must cost only its own row."""
        events = [
            {"task_id": "1", "variety": {"novelty": 2}},  # partial: unresolvable
            self.CANONICAL_EVENT,
            {"task_id": "3"},                              # no variety key at all
            "not-a-dict",                                  # not even an object
        ]
        assert _run_extraction(q5_expression, events)["variety_totals"] == [9]

    def test_extraction_is_empty_not_raising_when_nothing_resolves(
        self, q5_expression
    ):
        events = [{"task_id": "1", "variety": {}}, {"task_id": "2"}]
        assert _run_extraction(q5_expression, events)["variety_totals"] == []


class TestQ6ExtractionSurvivesAnUnreadableAck:
    """The Q6 flag extraction, run the same way and for the same reason.

    Measured 2026-07-28: 616 `teachback_ack` events, 0 missing the flag — the
    journal schema types that key `str`, which is why. So this guard is
    defense-in-depth against a shape the corpus has not yet produced, which is
    exactly when it is cheap to add.
    """

    @pytest.fixture
    def q6_expression(self, q6):
        return _backticked_expression(q6, "flags = ")

    def test_extraction_drops_only_the_unreadable_acks(self, q6_expression):
        events = [
            {"task_id": "1", "rationale_articulates_this_dispatch": "yes"},
            {"task_id": "2"},                                        # key absent
            {"task_id": "3", "rationale_articulates_this_dispatch": None},
            {"task_id": "4", "rationale_articulates_this_dispatch": "no"},
            "not-a-dict",
        ]
        assert _run_extraction(q6_expression, events)["flags"] == ["yes", "no"]

    def test_extraction_is_empty_not_raising_when_no_flag_is_readable(
        self, q6_expression
    ):
        """`len(flags) == 0` with `events` non-empty is the divisor the previous
        `len(events)` form could never produce — the case Q6's prose must (and
        does) tell the reader not to divide by."""
        assert _run_extraction(q6_expression, [{"task_id": "1"}])["flags"] == []
