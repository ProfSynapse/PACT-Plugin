"""Drift detection for the two marker helpers twinned into `working_memory`.

THE TWO BODIES: `marker_line_span` and `_narrow_to_memory_region`, held in
`hooks/shared/pin_markers.py` (canonical) and copied into
`skills/pact-memory/scripts/working_memory.py`.

WHY A COPY AND NOT AN IMPORT, taken from the copy itself: the production entry
`cli.py` puts ONLY the skill root on `sys.path`, and `tests/conftest.py` puts
`hooks/` on it. So an import there RESOLVES BELOW PYTEST AND RAISES FROM THE
CLI, which is the failure direction that ships green.

WHY THIS FILE EXISTS. MEASURED, NOT ASSUMED: no gate covered either body on
either side. Four behaviour-preserving renames, one for each of the four
bodies, left the full suite at its baseline count with zero failures, while
four behaviour-CHANGING controls on the same bodies reddened 89, 4, 88 and 4
tests. So the bodies were live and no gate saw a source change. The two
source docstrings that claimed a gate held them have since been corrected.

=====================================================================
THE ARITY IS TWO, AND IT IS TWO FOR A REASON WORTH WRITING DOWN
=====================================================================

The measurement above needed FOUR mutants, because each body is its own
mutation SITE and each needs its own run. A GATE DOES NOT MUTATE. IT
COMPARES, AND A COMPARISON IS SYMMETRIC: one assertion covers a change on
either side, because a change on either side breaks the same equality.

MEASURED BEFORE THIS FILE WAS WRITTEN, for each of the two functions:
    hooks mutated vs skills clean  -> not equal
    hooks clean   vs skills mutated -> not equal
So TWO comparisons cover four bodies. A four-arm gate would carry two
REDUNDANT arms, and a redundant arm is not free: it doubles the maintenance
and it makes a later reader believe two independent things are guarded.

This matches the convention in `test_staleness.py`, where each twinned
function carries ONE body comparison and the two-subject case is ONE
parametrized test.

=====================================================================
THE EXTRACTOR IS THE PARSING KIND, AND THAT IS A TRAP WARNING
=====================================================================

`_narrow_to_memory_region` has a MULTI-LINE SIGNATURE. A line-counting
extractor drops a fixed number of leading lines, so it leaves the parameter
lines and then the docstring in what it calls the body, AND THE TWO COPIES
THEN READ AS DIFFERENT. The two docstrings differ ON PURPOSE, because the
skills-side copy states only what is local.

SO A GATE BUILT ON A COUNTING EXTRACTOR IS RED ON ARRIVAL, AND THE NATURAL
REPAIR FOR THAT RED IS TO FORCE THE TWO DOCSTRINGS EQUAL, WHICH ERASES THE
LOCAL-ONLY CONTENT THE SKILLS COPY EXISTS TO CARRY. The second test below
pins that hazard as an executable fact, so a later author who swaps the
extractor reads the cause rather than reaches for the destructive repair.

WHAT THIS FILE DOES NOT COVER. The SESSION boundary prefix is a twinned
CONSTANT rather than a twinned body, and it carries its own equality gate
plus a derivation arm in `test_working_memory_parser.py`. A constant needs a
value comparison and a body needs a source comparison, so it is not in scope
here and it does not need to be.
"""

from __future__ import annotations

import inspect
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).parent.parent / "skills" / "pact-memory" / "scripts")
)

# THE EXTRACTOR COMES FROM ITS SINGLE DEFINITION AND IS NOT COPIED HERE.
# A second copy of an extractor is the same defect this file guards, one
# level up. If that class is renamed, this lookup raises and the failure is
# loud, which is the correct direction.
#
# BIND THE MODULE AND NOT THE CLASS. MEASURED: `from tests.test_staleness
# import TestSanitizePromptFieldTwinCopyDrift` puts a `Test*` name in THIS
# module, so pytest COLLECTS THAT CLASS AGAIN HERE. The file then reported
# seven tests where three are written, and the four borrowed ones ran twice
# for each session. A module binding carries no collectable name.
from tests import test_staleness as _staleness

_extract_body = _staleness.TestSanitizePromptFieldTwinCopyDrift._extract_body

TWINNED = ("marker_line_span", "_narrow_to_memory_region")


def _pair(name):
    """Return the (canonical, copy) function objects for `name`."""
    import shared.pin_markers as canonical
    import working_memory as copy

    return getattr(canonical, name), getattr(copy, name)


class TestMarkerHelperTwinCopyDrift:
    """The executable bodies of the two marker helpers stay byte-identical."""

    @pytest.mark.parametrize("name", TWINNED)
    def test_marker_helper_bodies_are_identical(self, name):
        """ONE comparison for each function, and it covers a change on either
        side, because equality is symmetric.
        """
        canonical_fn, copy_fn = _pair(name)
        canonical_body = _extract_body(canonical_fn)
        copy_body = _extract_body(copy_fn)

        # NON-VACUITY, TWO LEGS. An extractor that returned "" for each input
        # would make the comparison below trivially true, and an extractor
        # that left the signature in would compare the wrong text.
        assert canonical_body, f"{name}: the extracted canonical body is empty"
        assert copy_body, f"{name}: the extracted copy body is empty"
        assert not canonical_body.lstrip().startswith("def "), (
            f"{name}: the extractor left the SIGNATURE in the body, so this "
            "comparison is about the wrong text"
        )

        assert canonical_body == copy_body, (
            f"{name}: THE TWO COPIES OF THIS BODY HAVE DRIFTED.\n"
            "The copy in working_memory.py must stay byte-identical to the "
            "canonical one in hooks/shared/pin_markers.py. CHANGE THE TWO "
            "TOGETHER.\n"
            "DO NOT CLOSE THIS BY EDITING A DOCSTRING. The extractor drops "
            "the docstring, so a docstring difference cannot produce this "
            "red. The two docstrings differ on purpose.\n"
            f"canonical:\n{canonical_body}\n\ncopy:\n{copy_body}"
        )


class TestTheExtractorMustParseRatherThanCountLines:
    """A counting extractor reports a difference that is not a difference.

    THIS PINS THE TRAP AS AN EXECUTABLE FACT. Without it, a later author who
    swaps the extractor for the two line-counting ones in `test_staleness.py`
    gets a red on arrival, reads the two docstrings as the cause, and forces
    them equal, deleting the local-only content of the skills-side copy.
    """

    @staticmethod
    def _counting_extract(func) -> str:
        """The shape of a line-counting extractor: drop the `def` line and
        the docstring block, by COUNT rather than by parse."""
        source = textwrap.dedent(inspect.getsource(func))
        lines = source.split("\n")[1:]
        if lines and lines[0].lstrip().startswith('"""'):
            end = next(
                i for i, line in enumerate(lines[1:], 1)
                if line.rstrip().endswith('"""')
            )
            lines = lines[end + 1:]
        return textwrap.dedent("\n".join(lines)).strip()

    def test_the_counting_shape_reports_a_difference_the_parser_does_not(self):
        """The multi-line signature is what separates the two extractors.

        NON-VACUITY IS THE WHOLE POINT HERE: this test is meaningful only
        while the PARSING extractor says the two bodies AGREE. So it asserts
        that first, and the counting result second.
        """
        canonical_fn, copy_fn = _pair("_narrow_to_memory_region")

        assert _extract_body(canonical_fn) == _extract_body(copy_fn), (
            "the parsing extractor already reports a difference, so this "
            "test cannot show that the counting one is the weaker instrument"
        )

        counted_canonical = self._counting_extract(canonical_fn)
        counted_copy = self._counting_extract(copy_fn)

        assert counted_canonical != counted_copy, (
            "THE COUNTING EXTRACTOR NOW AGREES WITH THE PARSING ONE for "
            "`_narrow_to_memory_region`, so the trap this test documents has "
            "gone. That happens when the MULTI-LINE SIGNATURE becomes a "
            "single line, or when the two docstrings become equal.\n"
            "IF THE DOCSTRINGS WERE MADE EQUAL, THAT IS THE DEFECT: the "
            "skills-side copy carries local-only content on purpose. Restore "
            "it. If the signature was re-wrapped, retire this test rather "
            "than weaken the gate above it."
        )
