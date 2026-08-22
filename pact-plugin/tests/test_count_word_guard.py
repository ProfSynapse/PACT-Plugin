"""A count word in prose is bound to a count the code produces.

WHY THIS MODULE IS AWAY FROM `test_variety_divergence.py`. That file pins the
BEHAVIOUR of `extract_final_dispatch_coverage`. This one pins a claim that
three DOCUMENTS make about that helper. The subjects are different, and a
reader who opens the arm file to learn what the join does must not meet a
markdown slicer.

THE SHAPE THIS GUARD EXISTS FOR HIT FOUR TIMES IN ONE CHANGE, each caught by a
person and by no gate: a count word against a table of a different size, `six
join counters` after a counter was added, `a dict of nine values` above TEN
bullets, and a nine-row table with the word nine three times. NO GATE READS A
COUNT WORD.

THE BINDING IS CODE-TO-DOCS AND NOT DOCS-TO-DOCS, and that is the whole design.
THE DERIVED SIDE is a CALL: `len()` and `set()` of what the helper returns at
run time. It moves when the code moves and no document can influence it. THE
READ SIDE is a slice of a document a person maintains by hand. The two sides
can disagree, and they DO disagree when somebody edits one alone, which is what
makes the comparison evidence rather than a tautology.

A COUNT ALONE IS NOT SUFFICIENT AND THE NAME SET IS WHY. Ten bullets stay ten
bullets when one key is RENAMED, so a count check passes on a rename. The name
set catches a rename, a duplicate and a drop, and it reads the same call.

THE INSTRUMENT CLASS HERE IS THE ONE THAT CAUSED THIS AUDIT: a pattern across
prose that returns a confident zero with no error. Three protections, and each
answers a defect measured on this branch:
  1. EACH REGION MARKER MUST APPEAR ACCURATELY ONE TIME. A marker that moved or
     was reworded makes the slice run to the wrong end, and the bullet count is
     then a confident wrong number. The count of markers is asserted, so that
     case RAISES rather than reports.
  2. A PLAIN-TOKEN CONTROL that is known present must be in the slice. If it is
     absent the slice is incorrect, so an empty region cannot read as a
     satisfied assertion.
  3. EACH PROSE PATTERN RUNS CASE-INSENSITIVELY AND MUST MATCH ACCURATELY ONE
     TIME. A ZERO MATCH IS A FAILURE AND NOT A PASS.

THE PATTERN IS TIGHT ON PURPOSE, and the presence assertion is what makes that
safe. The patterns anchor on the stable technical tokens rather than the prose
around them. A rewording that keeps those tokens keeps the match. A rewording
that DROPS them stops the match, and the presence assertion turns that into a
RED. That direction is deliberate: a sentence that no longer states a count is
a REAL change to the claim this guard holds, so the author must then restore the
count or remove the assertion on purpose. A LOOSE pattern gives the worse
outcome, because the guard passes on a document that says nothing while the
record reads as gated.

A COUNT WORD IS A WORD, AND AN UNMAPPED WORD RAISES. It does not skip and it
does not pass. An unmapped word is a new count style or a typo, and each must
reach a person. Silently passing on one is the vacuous-guard shape, which is
this defect one level up.

THE TWO PROTOCOL FILES ARE EACH READ. They carry the same region and a
byte-mirror gate compares them, so a single read would rest on that gate rather
than on this one. Reading each keeps this module standing on its own.

PRIOR ART IN THIS REPOSITORY: `test_canary_checklist_count.py` binds a checklist
count to what a script EMITS at run time, and records why a source-text count of
the same script is defective. This module takes the same rule, that the RUN is
the sound source, and its derived side is a call rather than a text scan.
"""
import re
from pathlib import Path

import pytest

from hooks.shared.variety_divergence import extract_final_dispatch_coverage

_REPO_ROOT = Path(__file__).parent.parent.parent
_PLUGIN = _REPO_ROOT / "pact-plugin"
_PROTOCOL_FILES = (
    _PLUGIN / "protocols" / "pact-variety.md",
    _PLUGIN / "protocols" / "pact-protocols.md",
)
_WRAP_UP = _PLUGIN / "commands" / "wrap-up.md"

# The region rule, stated adjacent to the number it produces: ONE BULLET FOR
# EACH RETURNED KEY, matched on a leading dash-backtick, counted BETWEEN the
# `**Terms.**` line and the `**Two relation types` line.
_REGION_START = "**Terms.** One pass of the pure helper"
_REGION_END = "**Two relation types are in one key set"
_BULLET_RE = re.compile(r"^- `([a-z_]+)`", re.MULTILINE)

# The count words. Each pattern anchors on the stable technical tokens.
_TERMS_COUNT_RE = re.compile(r"returns a dict of (\w+) values", re.IGNORECASE)
_ALIKE_COUNT_RE = re.compile(r"cannot treat all (\w+) alike", re.IGNORECASE)

# The plain-token control: known present in the region, so an empty slice
# cannot read as a satisfied assertion.
_REGION_CONTROL = "extract_final_dispatch_coverage"

# The wrap-up region and its counting rule: a backticked name followed by the
# words `is the number`, counted between the count-word phrase and the
# `State with these counts` line.
_WRAPUP_COUNT_RE = re.compile(
    r"Report the (\w+) join counters here as well", re.IGNORECASE
)
_WRAPUP_END = "State with these counts"
_WRAPUP_NAME_RE = re.compile(r"`([a-z_]+)`\s+is the number")

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
}


def _word_to_int(word, where):
    """Map a count word to an integer, or RAISE naming the word and the file.

    A DIGIT FORM IS ACCEPTED, because a future author can write `10` and that
    must not be a failure.

    AN UNMAPPED WORD RAISES. It does not skip and it does not pass. Silently
    passing on a word outside this map is the vacuous-guard shape, and it is
    the exact defect this module exists to prevent.
    """
    text = word.strip().lower()
    if text.isdigit():
        return int(text)
    if text in _NUMBER_WORDS:
        return _NUMBER_WORDS[text]
    raise AssertionError(
        f"count word {word!r} in {where} is outside the map in this module. "
        f"Add it to _NUMBER_WORDS, or correct the document. This guard does "
        f"NOT pass on a word it cannot read."
    )


def _one_match(pattern, text, where, what):
    """Return the one match, or FAIL. A zero match is a RED and not a pass."""
    found = pattern.findall(text)
    assert len(found) == 1, (
        f"{what} in {where}: expected accurately ONE match and found "
        f"{len(found)}. A zero here means the sentence was reworded away from "
        f"the tokens this guard reads, which is a REAL change to the claim. "
        f"Restore the count, or remove this assertion on purpose."
    )
    return found[0]


def _terms_region(path):
    """Slice the Terms region, with each marker asserted unique first."""
    text = path.read_text()
    for marker, name in ((_REGION_START, "start"), (_REGION_END, "end")):
        assert text.count(marker) == 1, (
            f"{path.name}: the region {name} marker appears "
            f"{text.count(marker)} times and must appear one time. The slice "
            f"cannot be taken, so this guard raises rather than report a "
            f"confident wrong number."
        )
    start = text.index(_REGION_START)
    end = text.index(_REGION_END)
    region = text[start:end]
    assert _REGION_CONTROL in region, (
        f"{path.name}: the plain-token control {_REGION_CONTROL!r} is absent "
        f"from the slice, so the slice is incorrect. An empty region must not "
        f"read as a satisfied assertion."
    )
    return text, region


def _derived():
    """THE DERIVED SIDE: a CALL, not a text scan. It moves with the code."""
    return extract_final_dispatch_coverage([], [])


@pytest.mark.parametrize("path", _PROTOCOL_FILES, ids=lambda p: p.name)
class TestTheProtocolCountWordsMatchTheHelper:
    """Each protocol file is read on its own, so this module does not rest on
    the byte-mirror gate that compares the two."""

    def test_the_terms_count_word_equals_the_returned_key_count(self, path):
        """R1 against the derived count."""
        text, _ = _terms_region(path)
        word = _one_match(_TERMS_COUNT_RE, text, path.name, "the Terms count word")
        assert _word_to_int(word, path.name) == len(_derived())

    def test_the_relation_types_count_word_equals_the_returned_key_count(self, path):
        """R3, the SECOND count word, in the `all WORD alike` line. It states
        the same quantity as the Terms line and it can go stale on its own."""
        text, _ = _terms_region(path)
        word = _one_match(_ALIKE_COUNT_RE, text, path.name, "the relation-types count word")
        assert _word_to_int(word, path.name) == len(_derived())

    def test_the_bullet_count_equals_the_returned_key_count(self, path):
        """R2. COUNTING RULE, stated adjacent to the number: one bullet for
        each returned key, matched on a leading dash-backtick, counted between
        the `**Terms.**` line and the `**Two relation types` line."""
        _, region = _terms_region(path)
        assert len(_BULLET_RE.findall(region)) == len(_derived())

    def test_the_bullet_names_are_the_returned_key_set(self, path):
        """R4, AND A COUNT CHECK CANNOT DO THIS. Ten bullets stay ten bullets
        when one key is RENAMED, so the three arms above pass on a rename.
        This one compares the SET, so it catches a rename, a duplicate and a
        drop, and it reads the same derived call."""
        _, region = _terms_region(path)
        names = _BULLET_RE.findall(region)
        assert len(names) == len(set(names)), f"{path.name}: a bullet name repeats"
        assert set(names) == set(_derived())


class TestTheWrapUpCounterNamesAreHelperKeys:
    """`wrap-up.md` states a count of the join counters it then defines.

    THE COUNT AND THE NAMES ARE EACH IN THE FILE, so comparing the two alone
    is a docs-to-docs tautology. THE MEMBERSHIP CHECK IS WHAT MAKES IT
    CODE-BOUND: each named counter must be a key the helper returns, so a
    rename or a drop in the helper reddens this class.
    """

    def _region(self):
        text = _WRAP_UP.read_text()
        word = _one_match(
            _WRAPUP_COUNT_RE, text, _WRAP_UP.name, "the join-counter count word"
        )
        tail = text[text.index("join counters here as well"):]
        assert _WRAPUP_END in tail, (
            f"{_WRAP_UP.name}: the region end marker {_WRAPUP_END!r} is absent "
            f"after the count word, so the slice cannot be taken."
        )
        return word, tail[: tail.index(_WRAPUP_END)]

    def test_the_named_counter_count_equals_the_count_word(self):
        """COUNTING RULE, stated adjacent to the number: a backticked name
        followed by the words `is the number`, counted between the count-word
        phrase and the `State with these counts` line. A plain count of
        backticked tokens in that region reads 11 and is incorrect, because the
        region also names `coverage`, `variety`, `dispatch_site` and a
        `len(malformed)` call."""
        word, region = self._region()
        names = _WRAPUP_NAME_RE.findall(region)
        assert len(names) == len(set(names)), "a counter name repeats"
        assert len(names) == _word_to_int(word, _WRAP_UP.name)

    def test_each_named_counter_is_a_key_the_helper_returns(self):
        """THE CODE BINDING. Without this the class above is a tautology."""
        _, region = self._region()
        names = set(_WRAPUP_NAME_RE.findall(region))
        assert names, "the counting rule selected no name, so the slice is incorrect"
        assert names <= set(_derived())
