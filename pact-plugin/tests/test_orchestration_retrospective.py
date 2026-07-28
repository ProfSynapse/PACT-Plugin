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


def _run_extraction(expression, events):
    """Execute a documented extraction expression against `events` and return
    the resulting namespace.

    `exec` is the point, not a shortcut: wrap-up.md is executed by an LLM at
    runtime, so the only way to pin the instruction's BEHAVIOUR (rather than
    grep its wording) is to run the expression the file actually carries. The
    input is repo-controlled markdown.
    """
    namespace = {"events": events, "resolve_variety_total": resolve_variety_total}
    exec(expression, namespace)  # noqa: S102 — repo-controlled instruction text
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

    def test_q5_masked_empty_guard_precedes_predates_conclusion(self, q5):
        # the re-read guard must appear, and gate the "pre-dates" conclusion
        assert "masked-empty guard" in q5
        assert "re-read the raw" in q5
        assert "session-journal.jsonl" in q5
        # the unique OMISSION-note phrasing (distinct from the earlier
        # GC-problem mention "wrongly reports 'pre-dates stamping'")
        assert "pre-dates per-dispatch stamping" in q5
        # ordering: the guard must precede the pre-dates OMISSION conclusion
        assert q5.index("masked-empty guard") < q5.index(
            "pre-dates per-dispatch stamping"
        )

    def test_q5_denominator_uses_count_helper_not_len_agent_dispatch(self, q5):
        assert "count_task_b_dispatch_sites" in q5

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

    def test_q5_resolves_the_total_through_the_shared_accessor(self, q5):
        assert "resolve_variety_total" in q5
        assert "shared.teachback_schema" in q5

    def test_q5_does_not_direct_index_the_total(self, q5):
        """The negative half: `[e["variety"]["total"] for e in events]` is the
        shape that aborts the whole comprehension on one malformed stamp."""
        assert '["variety"]["total"]' not in q5
        assert "for e in events]" not in q5

    def test_q5_reports_the_dropped_count(self, q5):
        """An unresolvable stamp lowers coverage exactly like an un-stamped
        dispatch, so without the count a data-quality problem reads as a
        compliance gap."""
        assert "len(events) - len(dispatch_varieties)" in q5

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
        return _backticked_expression(q5, "dispatch_varieties = ")

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
        assert namespace["dispatch_varieties"] == [9, 8], (
            "the four-dimension sum is the ONLY path by which the 20 malformed "
            "dispatch_variety events in the corpus reach Q5's numerator; drop "
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
        assert _run_extraction(q5_expression, events)["dispatch_varieties"] == [9]

    def test_extraction_is_empty_not_raising_when_nothing_resolves(
        self, q5_expression
    ):
        events = [{"task_id": "1", "variety": {}}, {"task_id": "2"}]
        assert _run_extraction(q5_expression, events)["dispatch_varieties"] == []


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
