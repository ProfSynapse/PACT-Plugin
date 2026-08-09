"""
Presence pins for the import-bar cause in the memory-repair package.

Location: pact-plugin/tests/test_import_bar_cause_presence.py

WHAT THIS PROVES, AND IT IS NARROW ON PURPOSE. Each module in the
memory-repair package that states the import bar also carries the sentence
that forbids an audit of which call is safe. That sentence is the only one
that stops a reader treating the bar as a DISTANCE to be measured rather than
a rule to keep, and it was dropped once with nothing to catch it.

WHAT A GREEN HERE DOES NOT MEAN. Read this before you trust it.

  * It does NOT check that the surrounding prose is true. No test can read a
    natural-language cause for truth.
  * It does NOT catch an incorrect cause ADDED elsewhere, in this package or
    outside it. The population is derived from the files that state the bar,
    so a new file that states nothing about it is invisible here.
  * It proves the PRESENCE of two sentences, and nothing more.

THE POPULATION HAS THREE PARTS, AND EACH COVERS A FAILURE THE OTHERS MISS.

  1. The DERIVATION reaches a carrier written later, on the day it arrives.
  2. `MINIMUM_CARRIERS` refuses SHRINKAGE for the carriers known today. A
     derived population can shrink: rename the subject phrase in one file and
     that file leaves the set, after which its copy of a required sentence is
     deletable with each arm green.
  3. `EXEMPT_MODULES` extends part 2 to files nobody has written yet, which
     fixed names cannot reach. A module leaves the population only by a
     declared line, and not by a rename that reads as tidying.

An arm that asserts ONE member proves the set is not empty and proves nothing
about the rest. Non-emptiness and completeness are different properties.

THE FAILURE DIRECTION IS DELIBERATE. A legitimate reword trips these tests,
so they fail toward a FALSE ALARM and somebody must look. The pin to avoid is
the one that goes stale in silence. This is its opposite.

TO CHANGE ANY CONSTANT IN THIS FILE, STATE A CAUSE. The rule is stated over
the CLASS and not over a list of names, on purpose. Each module-level constant
here sets what the arms require, or which files the arms cover, so each one
weakens the guard if it changes for no reason. A list of names would go stale
the moment a constant is added, and a reader who trusts the list then learns a
rule narrower than the one that must hold.

If you update a constant to agree with new prose, or to quiet a red, and you
give no cause, this file becomes a MIRROR of the thing it guards, and its
green stops meaning anything. That covers the required sentences, the subject
phrase the population is derived from, and each set of file names.

MATCHING IS WHITESPACE-INSENSITIVE BY NECESSITY. Each guarded sentence wraps
across lines in the file that carries it, so a line-oriented search or a
literal comparison cannot find it even when it is present. Flatten first.

Used by: pytest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "scripts" / "memory_repair"

# The anti-permission clause. Its absence is the defect this file exists for.
REQUIRED_CAUSE_CLAUSE = (
    "This rule holds so that nobody must audit which call is safe."
)

# The obligation that reaches an edit to an EXISTING module, not new ones only.
REQUIRED_PACKAGE_OBLIGATION = (
    "Keep each module here, and each module added later, the same way."
)

# A module "states the import bar" when it names the guarded package. This
# derives the population from the property, so a third carrier file added
# later is covered on the day it arrives.
BAR_SUBJECT = "pact-memory scripts package"

# THE FLOOR, AND THE DERIVATION ALONE IS NOT ENOUGH WITHOUT IT. A derived
# population can SHRINK. Delete the subject phrase from one carrier and that
# file leaves the population, after which its copy of the required sentence is
# deletable with each arm below green. So the derivation supplies GROWTH and
# this floor refuses SHRINKAGE. Neither half covers the other.
#
# To remove a name from this floor, state a cause, as for the two sentence
# constants above. A name removed to quiet a red turns the floor into a report
# of the current population, which is the same mirror failure.
MINIMUM_CARRIERS = frozenset({"__init__.py", "shred_detect.py"})

# MODULES THAT DO NOT HAVE TO STATE THE BAR. Empty today, and that is the
# point: each .py file in this package must state the bar, or appear here.
#
# The floor above protects the carriers known when it was written. It cannot
# protect a carrier written later, because its names are fixed. This closes
# that gap from the other side: a file leaves the population ONLY by an entry
# here, which is a visible line in a diff, rather than by a rename of the
# subject phrase, which reads as tidying and is what defeated the derivation.
#
# To add a name here, state a cause. A name added to quiet a red is the mirror
# failure again. A KNOWN CARRIER CANNOT ESCAPE THIS WAY: MINIMUM_CARRIERS is
# checked separately, so an exemption for one of those names goes red anyway.
EXEMPT_MODULES: frozenset = frozenset()


def flatten(text: str) -> str:
    """Collapse all whitespace runs to single spaces.

    A guarded sentence wraps across lines, so it is not a contiguous substring
    of any single line. This is what makes the comparison find it.
    """
    return re.sub(r"\s+", " ", text)


def modules_stating_the_bar(package_dir: Path) -> list[Path]:
    """Return each .py file in `package_dir` whose text names the guarded package."""
    return sorted(
        path
        for path in package_dir.glob("*.py")
        if BAR_SUBJECT.lower() in flatten(path.read_text(encoding="utf-8")).lower()
    )


class TestTheInstrumentIsLive:
    """Non-vacuity. An empty population agrees with every assertion below."""

    def test_package_dir_holds_python_files(self):
        assert PACKAGE_DIR.is_dir(), f"package directory absent: {PACKAGE_DIR}"
        assert list(PACKAGE_DIR.glob("*.py")), (
            f"no .py files under {PACKAGE_DIR} — the glob broke, and every "
            f"per-module assertion below would pass over an empty set."
        )

    def test_each_known_carrier_stays_in_the_derived_population(self):
        """The floor. Non-emptiness is not enough, because COMPLETENESS is the
        property at issue.

        An arm that asserts one member proves the set is not empty and proves
        nothing about the rest. Drop a second carrier out of the derivation and
        such an arm keeps passing while coverage halves. This asserts each
        known carrier is IN the derived population, so a file cannot leave it
        in silence.
        """
        present = {path.name for path in modules_stating_the_bar(PACKAGE_DIR)}
        gone = sorted(MINIMUM_CARRIERS - present)
        assert not gone, (
            f"{gone} no longer name the guarded package, so they left the "
            f"derived population and their copy of the required sentence is "
            f"now unguarded. Either the docstring was rewritten, or the "
            f"subject phrase {BAR_SUBJECT!r} changed. Do not repair this by "
            f"removing a name from MINIMUM_CARRIERS without a stated cause."
        )

    def test_each_module_states_the_bar_or_is_declared_exempt(self):
        """The population covers files nobody has written yet.

        MINIMUM_CARRIERS holds fixed names, so it cannot reach a carrier added
        later. This reaches it: a new .py file must state the bar, or take a
        line in EXEMPT_MODULES. A file then leaves the population only by a
        visible declaration, and not by a rename of the subject phrase.
        """
        on_disk = {path.name for path in PACKAGE_DIR.glob("*.py")}
        stating = {path.name for path in modules_stating_the_bar(PACKAGE_DIR)}
        silent = sorted(on_disk - stating - EXEMPT_MODULES)
        assert not silent, (
            f"{silent} do not name the guarded package. Add the import-bar "
            f"paragraph to each, or add the name to EXEMPT_MODULES with a "
            f"stated cause. A module outside the population carries none of "
            f"the sentences the arms below require."
        )

    def test_the_flatten_finds_a_wrapped_sentence(self):
        """A control on the matcher itself, not on the files it reads."""
        wrapped = "This rule holds so that\n    nobody must audit which\n    call is safe."
        assert REQUIRED_CAUSE_CLAUSE not in wrapped
        assert REQUIRED_CAUSE_CLAUSE in flatten(wrapped)


class TestTheCauseClauseIsPresent:
    """The population is BOTH carrier files, and it is derived rather than listed."""

    def test_each_module_stating_the_bar_carries_the_cause_clause(self):
        missing = [
            path.name
            for path in modules_stating_the_bar(PACKAGE_DIR)
            if REQUIRED_CAUSE_CLAUSE not in flatten(path.read_text(encoding="utf-8"))
        ]
        assert not missing, (
            f"{missing} state the import bar but omit the clause that forbids "
            f"an audit of which call is safe. Without it, 'one call away' reads "
            f"as a DISTANCE, and a maintainer concludes they may import so long "
            f"as they audit which functions resolve a path. Required sentence: "
            f"{REQUIRED_CAUSE_CLAUSE!r}"
        )

    def test_the_package_docstring_carries_the_obligation(self):
        """The obligation is package-scoped, so its population is `__init__.py` alone."""
        text = flatten((PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8"))
        assert REQUIRED_PACKAGE_OBLIGATION in text, (
            f"the package docstring lost the obligation that binds a future "
            f"editor. A description of an invariant does not command its "
            f"preservation. Required sentence: {REQUIRED_PACKAGE_OBLIGATION!r}"
        )


class TestTheRefutedCauseStaysOut:
    """The one negative arm here, and its bound is the spellings named.

    This does NOT detect a new incorrect cause in new words. It detects the
    return of the exact claim that shipped, which is worth catching because a
    revert or a bad merge reintroduces the original bytes rather than a
    paraphrase.
    """

    @pytest.mark.parametrize(
        "refuted",
        [
            "an import is a write",
            "EXECUTES code that creates the live store",
            "runs code that creates the live store",
            "safe to import",
        ],
    )
    def test_a_refuted_spelling_does_not_return(self, refuted):
        for path in PACKAGE_DIR.glob("*.py"):
            text = flatten(path.read_text(encoding="utf-8"))
            assert refuted.lower() not in text.lower(), (
                f"{path.name} carries {refuted!r} again. That claim was measured "
                f"incorrect: no call that creates a directory or resolves a path "
                f"runs at import time in the guarded package."
            )
