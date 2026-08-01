"""
Tests for the pin-comment repair BEYOND a single line and a single state.

Location: pact-plugin/tests/test_pin_comment_pipeline.py

Summary: the sibling file `test_pin_comment_dominance.py` owns the cross-oracle
property, which is quantified over ONE line and evaluated on ONE parse. This
file owns what that shape cannot reach:

  * the TWO-STATE predicate `compute_deny_reason`, which compares a pre-edit
    parse against a post-edit parse and denies when post is strictly worse;
  * the STALE marker path, which shares the module and was left alone;
  * multi-pin regions, where attribution walks backward over several pins;
  * malformed regions, where the parser promises to fail open;
  * `>` carriers that the enumerated alphabets could not express, such as an
    HTML fragment, an XML close tag and an angle-bracket generic;
  * an anti-exponential tripwire on the changed date field.

WHY A SIBLING FILE. The dominance file counts a corpus and asserts a floor on
it. The cases here build documents and read charges. Mixing them lowers the
signal of both, because a document fixture that fails takes the corpus counts
down with it.

NON-VACUITY. Tests below that CANNOT be red against the previous code are
named as no-change controls in their own docstrings. Their content is that the
repair leaves those cases alone, so a red there would mean the change did
something it promised not to do.

Used with: hooks/pin_caps.py.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))


STALE_MARKER = "<!-- STALE: Last relevant 2026-01-01 -->"


def two_pin_section(body_a, comment_b):
    """Build a two-pin body where pin B's comment sits in pin A's slice.

    `parse_pins(...)[0].body_chars` equals `len(body_a)` exactly when the
    strip removes pin B's comment in full.
    """
    return (
        "<!-- pinned: 2026-01-01 -->\n"
        f"### PinA\n{body_a}\n"
        f"{comment_b}\n"
        "### PinB\nshort\n"
    )


# ---------------------------------------------------------------------------
# `>` carriers.
#
# The enumerated alphabets in this arc were built from `a1-<>!,` plus a space.
# The carriers below hold characters and shapes that alphabet cannot express.
# Each one is a rationale a curator could realistically write in THIS
# repository, which documents markup grammars.
# ---------------------------------------------------------------------------

CARRIERS_WITH_GT = [
    "render <b>bold</b> inline",
    "ends with </tag> here",
    "the List<Map<K,V>> shape",
    "2 > 1 >= 0 > -1",
    "value >> 2 and 1 >> 0",
    "lambda x => x + 1",
    "quote: > cited line",
]

CARRIERS_WITHOUT_GT = [
    "see https://x.example/?a=1&b=2",
    "the rule — and its bound",
    "escape &gt; as an entity",
    "flow a → b then stop",
]


class TestPinCommentCarriers_Pipeline:
    """The trigger is ANY `>`, on shapes the enumerations could not express."""

    @pytest.mark.parametrize("carrier", CARRIERS_WITH_GT)
    def test_carrier_holding_a_greater_than_is_not_charged(self, carrier):
        from pin_caps import parse_pins

        body_a = "Pin A body, which the curator did not touch."
        comment = f"<!-- pinned: 2026-03-01, pin-size-override: {carrier} -->"
        pins = parse_pins(two_pin_section(body_a, comment))

        assert pins[0].body_chars == len(body_a), (
            f"pin A was charged {pins[0].body_chars} chars against a body of "
            f"{len(body_a)}. The excess is pin B's comment, which holds "
            f"{carrier!r}."
        )
        assert pins[1].date_comment == comment

    @pytest.mark.parametrize("carrier", CARRIERS_WITHOUT_GT)
    def test_carrier_without_a_greater_than_is_unaffected(self, carrier):
        """NO-CHANGE CONTROL. These shapes were never broken.

        They answer the other half of the question: the repair must not newly
        refuse a faithful rationale that carries a URL, an em-dash, an HTML
        entity or a Unicode arrow.
        """
        from pin_caps import parse_pins

        body_a = "Pin A body, which the curator did not touch."
        comment = f"<!-- pinned: 2026-03-01, pin-size-override: {carrier} -->"
        pins = parse_pins(two_pin_section(body_a, comment))

        assert pins[0].body_chars == len(body_a)
        assert pins[1].override_rationale == carrier

    def test_reconfirmed_clause_keeps_its_date_and_its_neighbour(self):
        """The reconfirmed shape fails BOTH oracles on the previous code.

        The pin lost its date attribution AND the neighbour was charged, so
        both halves belong in one assertion.
        """
        from pin_caps import parse_pins

        body_a = "Pin A body, which the curator did not touch."
        comment = ("<!-- pinned: 2026-03-01, reconfirmed: 2026-04-01 "
                   "because count > 2 -->")
        pins = parse_pins(two_pin_section(body_a, comment))

        assert pins[1].date_comment == comment
        assert pins[0].body_chars == len(body_a)


class TestPinCommentStale_Pipeline:
    """The STALE path shares the module and was deliberately left alone.

    `is_stale` reads the RAW body with `.search`, while `_extract_body_chars`
    works on a stripped copy. The widened strip therefore cannot reach the
    staleness signal. These tests pin that separation.
    """

    STALE_CASES = [
        ("marker alone", "body\n" + STALE_MARKER),
        ("date comment holding `>` then marker",
         "body\n<!-- pinned: 2026-01-01, a > b -->\n" + STALE_MARKER),
        ("unterminated opener holding `>` then marker",
         "body\n<!-- pinned: 2026-01-01, a > b\nmore\n" + STALE_MARKER),
        ("unterminated opener without `>` then marker",
         "body\n<!-- pinned: 2026-01-01 no close\nmore\n" + STALE_MARKER),
    ]

    @pytest.mark.parametrize(
        "label,body", STALE_CASES, ids=[c[0] for c in STALE_CASES]
    )
    def test_stale_signal_survives_the_widened_strip(self, label, body):
        """NO-CHANGE CONTROL on the signal. The charge test below discriminates."""
        from pin_caps import parse_pins

        pins = parse_pins(f"### P\n{body}\n")
        assert pins[0].is_stale is True, (
            f"the STALE marker stopped being seen for case {label!r}. "
            f"`is_stale` must read the RAW body, not the stripped copy."
        )

    def test_a_greater_than_comment_beside_a_stale_marker_is_not_charged(self):
        """Both managed markers must leave the curator's budget alone."""
        from pin_caps import parse_pins

        body = ("body\n"
                "<!-- pinned: 2026-01-01, a > b -->\n"
                f"{STALE_MARKER}")
        pins = parse_pins(f"### P\n{body}\n")

        assert pins[0].body_chars == len("body")
        assert pins[0].is_stale is True

    def test_stale_block_threshold_is_unchanged_by_greater_than_comments(self):
        """A region whose every comment holds `>` still reports stale overflow."""
        from pin_caps import PIN_STALE_BLOCK_THRESHOLD, check_stale_block, parse_pins

        region = ""
        for i in range(3):
            region += (
                f"<!-- pinned: 2026-0{i + 1}-01, note > {i} -->\n"
                f"### Pin {i}\nbody {i}\n{STALE_MARKER}\n"
            )
        pins = parse_pins(region)

        assert len(pins) == 3
        assert sum(p.is_stale for p in pins) >= PIN_STALE_BLOCK_THRESHOLD
        violation = check_stale_block(pins)
        assert violation is not None and violation.kind == "stale"


class TestPinCommentMultiPin_Pipeline:
    """Attribution walks BACKWARD over several pins, and must not overreach."""

    def test_every_pin_in_a_six_pin_region_is_charged_only_its_own_body(self):
        from pin_caps import parse_pins

        bodies = [f"{'body ' * 8}pin {i}" for i in range(6)]
        region = ""
        for i, body in enumerate(bodies):
            region += (
                f"<!-- pinned: 2026-01-0{i + 1}, reason a > b for pin {i} -->\n"
                f"### Pin {i}\n{body}\n"
            )
        pins = parse_pins(region)

        assert len(pins) == 6
        assert [p.body_chars for p in pins] == [len(b) for b in bodies], (
            "at least one pin was charged for a neighbouring pin's comment"
        )
        assert all(p.date_comment is not None for p in pins), (
            "a pin lost its date attribution, so its age degrades in silence"
        )

    def test_backward_walk_takes_the_nearest_comment_over_blank_lines(self):
        """Two comments, blank lines between. The NEAREST one must win."""
        from pin_caps import parse_pins

        nearest = "<!-- pinned: 2026-03-03, second > marker -->"
        region = (
            "<!-- pinned: 2026-01-01 -->\n"
            "### PinA\nbody A\n"
            "\n"
            "<!-- pinned: 2026-02-02, first > marker -->\n"
            "\n"
            f"{nearest}\n"
            "\n"
            "### PinB\nbody B\n"
        )
        pins = parse_pins(region)

        assert pins[1].date_comment == nearest
        assert pins[0].body_chars == len("body A")


class TestPinCommentMalformed_Pipeline:
    """`parse_pins` promises fail-open. A malformed region must not raise."""

    MALFORMED = [
        ("unterminated comment, nothing after",
         "### P\nbody\n<!-- pinned: 2026-01-01, a > b\n", 1),
        ("comment with no heading after it",
         "### P\nbody\n<!-- pinned: 2026-01-01, a > b -->\n", 1),
        ("heading with no comment before it",
         "### P\nbody only\n### Q\nbody two\n", 2),
        ("comment before the first heading",
         "<!-- pinned: 2026-01-01, a > b -->\n### P\nbody\n", 1),
        ("empty region", "", 0),
        ("only a comment, no heading at all",
         "<!-- pinned: 2026-01-01, a > b -->\n", 0),
        ("closer with no opener", "### P\nbody --> tail\n", 1),
        ("opener inside prose, closer far away",
         "### P\nprose <!-- pinned: a > b more prose\nyet more\n--> tail\n", 1),
        ("nested openers, one closer",
         "### P\n<!-- pinned: <!-- pinned: x > y -->\n", 1),
        ("comment split across two lines",
         "### P\nbody\n<!-- pinned: 2026-01-01,\na > b -->\n", 1),
    ]

    @pytest.mark.parametrize(
        "label,region,expected_pins", MALFORMED, ids=[c[0] for c in MALFORMED]
    )
    def test_malformed_region_parses_without_raising(
        self, label, region, expected_pins
    ):
        """NO-CHANGE CONTROL on the pin count. The charge test below discriminates."""
        from pin_caps import parse_pins

        pins = parse_pins(region)
        assert len(pins) == expected_pins, (
            f"case {label!r} changed the pin count, which changes the count cap"
        )

    def test_a_trailing_comment_with_no_heading_is_still_stripped(self):
        """A pin whose comment has no following heading still loses it.

        This is the case that discriminates: the previous body class refused
        the `>` and charged the whole comment to the pin.
        """
        from pin_caps import parse_pins

        pins = parse_pins("### P\nbody\n<!-- pinned: 2026-01-01, a > b -->\n")
        assert pins[0].body_chars == len("body")


class TestPinCommentTwoState_Pipeline:
    """`compute_deny_reason` compares TWO parses, not one.

    A per-line property cannot reach this predicate, because the quantity it
    compares does not exist until two documents have been parsed. An edit is
    denied when the post state is strictly worse than the pre state, so a
    LOWER pre-state charge is not a safety margin. It is a lower bar for the
    post state to clear.
    """

    PROSE1 = "Alpha prose that belongs to pin A. " * 37
    PROSE2 = "Beta prose that also belongs to pin A. " * 18
    PIN_B_COMMENT = "<!-- pinned: 2026-03-03 -->"

    def _region(self, stray):
        lines = ["<!-- pinned: 2026-01-01 -->", "### PinA", self.PROSE1]
        if stray is not None:
            lines.append(stray)
        lines += [self.PROSE2, self.PIN_B_COMMENT, "### PinB", "short"]
        return "\n".join(lines) + "\n"

    def _verdict(self, stray):
        from pin_caps import compute_deny_reason, parse_pins

        pre = parse_pins(self._region(stray))
        post = parse_pins(self._region(None))
        return compute_deny_reason(pre, post, "")

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "OPEN FINDING, reported and not yet dispositioned. The curator "
            "deletes a stray unterminated pin-comment opener, which removes "
            "characters and adds none, and the edit is DENIED. The widened "
            "strip reaches past the `>` to the next terminator, so the "
            "PRE-state charge falls, and the net-worse predicate then reads "
            "the unchanged post state as a regression. The previous code "
            "allowed this repair."
        ),
    )
    def test_repairing_a_stray_opener_is_not_denied(self):
        stray = "<!-- pinned: 2026-02-02, note > threshold"
        assert self._verdict(stray) is None, (
            "the curator's repair of their own file was denied. The edit only "
            "removes characters, so no pin grew."
        )

    def test_a_stray_opener_without_a_greater_than_denies_on_both_versions(self):
        """CONTROL, and it denies. That is the point.

        This case shares every ingredient with the one above EXCEPT the `>`.
        Without the `>` the previous body class also strips the region, so
        both code versions read the same pre-state and both deny. The deny is
        therefore not new, and the `>` is isolated as the one ingredient that
        makes the two verdicts diverge.
        """
        stray = "<!-- pinned: 2026-02-02, note above threshold"
        assert self._verdict(stray) is not None

    def test_removing_a_wellformed_comment_holding_a_greater_than_is_allowed(self):
        """The repair this change exists to make does NOT open a deny.

        A WELL-FORMED comment carrying a `>` is stripped by the new code and
        was charged by the old one. Deleting it lowers the charge on both, so
        no new deny appears. NO-CHANGE CONTROL, and it bounds the finding
        above to the malformed route.
        """
        stray = "<!-- pinned: 2026-02-02, note > threshold -->"
        assert self._verdict(stray) is None

    def test_a_non_pin_comment_opener_is_allowed_on_both_versions(self):
        """CONTROL. The strip needs the literal `pinned:` prefix.

        A stray opener that is not a pin comment is stripped by neither code
        version, so both read the same pre-state and both allow.
        """
        stray = "<!-- note: 2026-02-02, count > threshold"
        assert self._verdict(stray) is None


class TestPinCommentBacktracking_Pipeline:
    """An anti-exponential tripwire on the changed date field.

    NO-CHANGE CONTROL against the previous code, which is faster on these
    inputs. The guard is against a FUTURE edit that makes the alternation
    ambiguous, because the two branches are disjoint today and a run of
    characters therefore has exactly one decomposition.

    The budget is deliberately loose. Measured growth is quadratic and the
    worst case here costs tens of milliseconds, so a budget in seconds cannot
    flake, and an exponential would blow through it by orders of magnitude.
    """

    BUDGET_SECONDS = 5.0

    @pytest.mark.parametrize("length", [500, 1000, 2000])
    def test_interior_whitespace_run_stays_within_budget(self, length):
        from pin_caps import OVERRIDE_COMMENT_RE

        # An interior whitespace run survives `.strip()`, so this is the shape
        # the parser can actually receive. The trailing character closes it.
        line = "<!-- pinned:" + " " * length + "x"
        assert line.strip() == line

        started = time.perf_counter()
        OVERRIDE_COMMENT_RE.fullmatch(line)
        elapsed = time.perf_counter() - started

        assert elapsed < self.BUDGET_SECONDS, (
            f"a {len(line)}-char line took {elapsed:.3f}s. The date field is a "
            f"quantified alternation, so check whether its branches have "
            f"stopped being disjoint."
        )

    def test_many_unterminated_openers_stay_within_budget(self):
        from pin_caps import _DATE_COMMENT_RE

        body = ("<!-- pinned: a > b " * 400) + ("word " * 40)

        started = time.perf_counter()
        _DATE_COMMENT_RE.sub("", body)
        elapsed = time.perf_counter() - started

        assert elapsed < self.BUDGET_SECONDS, (
            f"a {len(body)}-char body took {elapsed:.3f}s to strip. Each "
            f"unterminated opener is a fresh start position for the scan."
        )
