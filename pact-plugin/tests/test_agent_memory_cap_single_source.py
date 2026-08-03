"""Single-source pin for the agent-memory index limits.

The plugin states the agent-memory index limits in exactly ONE place, and every
other mention points at that rule instead of repeating the numbers. The purpose
is that a future correction is a one-line edit and not a sweep.

Until now that constraint was carried only by a sentence addressed to future
editors inside the rule itself — a convention, with no mechanism behind it.
These tests are the mechanism for the failure mode the convention names: a
second site that restates the limits.

WHY THIS PIN IS VALUE-AGNOSTIC. It counts the UNIT vocabulary and never the
numbers. The limits are platform constants that this repository cannot read, so
a test that pinned their values would assert only that the text matches itself,
and would have to be edited on the very day someone correctly updates them. By
counting the unit instead:

  * a correct update of the values at the single source leaves this GREEN,
    because nothing else has to change;
  * a SECOND site that restates the limits turns it RED, because the duplicate
    is exactly what must be removed;
  * deletion of the rule while a pointer still aims at it turns it RED.

BOUND, stated rather than implied — and NARROWED, because the previous bound was
walked through. This pin once matched only the unit VOCABULARY, so a restatement
spelled "25KB" or "25,000 characters" was invisible to it. That bound was
disclosed in this docstring, and a second statement of the ceiling reached the
tree through it anyway. A STATED BOUND IS NOT A CONTROL. The subject-tainted arm
below closes the spelling gap for any statement that names the index file.

WHAT REMAINS OUTSIDE, so the next reader does not have to rediscover it. A
restatement that both invents a spelling AND never names the index file is still
invisible. The LINE cap is deliberately unpinned: its vocabulary collides with
unrelated documentation, and the auto-memory table row states it a second time.
And nothing here says whether the stated limits are CORRECT — no test in this
repository can, because none of them reads the platform bundle.
"""
import re
from collections import namedtuple
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent

# The single source, and the file whose table points at it.
SINGLE_SOURCE = "skills/pact-agent-teams/SKILL.md"
REFERRER = "skills/pact-memory/SKILL.md"

# Unit vocabulary of the size ceiling.
#
# AN EARLIER VERSION OF THIS COMMENT WAS WRONG, and the error is worth keeping
# visible because of what it cost. It said the two auto-memory carriers "state a
# limit for a DIFFERENT memory system and are deliberately out of scope here".
# Both carriers in fact state a limit for the SAME artifact this rule governs,
# and one of them was a second statement of this very ceiling — spelled "25KB",
# which the vocabulary arm cannot see. The wrong justification is why the
# exclusion read as principled through three separate reviews: a false reason in
# a test is worse than no reason, because it stops the next reader looking.
#
# WHAT THIS FILE DELIBERATELY DOES NOT SETTLE: whether the two memory
# directories share one platform constant. No test in this repository reads the
# platform bundle, so that question cannot be answered from here. The arms below
# assert only what is measurable — how many times the shipped tree STATES a size
# ceiling for the index.
#
# This arm is RETAINED rather than replaced. It is keyed on vocabulary, so it
# still catches a restatement that never names the index file, which the
# subject-tainted arm below cannot see. Neither arm contains the other.
UNIT_TOKENS = ["UTF-16", "code unit"]

# --- the subject-tainted size-cap arm --------------------------------------
# Keyed on the SHAPE of a size statement about the index rather than on the
# words chosen for it, so the spelling no longer decides the verdict.
#
# THE NUMBER IS A WILDCARD, deliberately. Pinning the value would assert only
# that the text matches itself, and would have to be edited on the very day
# someone correctly updates the platform constant.
#
# THE SUBJECT TAINT IS WHAT MAKES THE SHAPE USABLE. A bare numeral-plus-size-unit
# sweep matches 96 lines across the shipped surfaces — hook buffer sizes, n8n
# documentation, telegram limits, the pact-memory CLI. Requiring the line to name
# the index file reduces that to the statements about this index and nothing
# else. Measured across the shipped surfaces, not estimated.
#
# THE SIZE ALPHABET EXCLUDES LINE UNITS, and that is a separation rather than
# an omission. The two caps are distinct axes with distinct counts, so merging
# their alphabets would make a line-only restatement and a size-only
# restatement indistinguishable in a single tally. The line cap has its own
# pattern immediately below.
SIZE_UNIT = (
    r"(?:UTF-16\s+code\s+units?|code\s+units?|characters?|chars?"
    r"|bytes?|[KMG]i?B)"
)
SIZE_CAP_RE = re.compile(r"\d[\d,\.]*\s*" + SIZE_UNIT, re.IGNORECASE)

# The LINE cap, added once the tree could support it. It was withheld from the
# first pass of this repair because a third statement of the constant still
# stood in the auto-memory table row, so this arm would have been red against
# correct text. With that row converted to a pointer the sweep returns one site,
# and the arm is admissible. THE ALPHABET IS DELIBERATELY NARROW: bare
# "N lines". Widening it to prose forms buys nothing measurable and spends the
# false-positive budget that makes the subject taint work.
LINE_CAP_RE = re.compile(r"\d[\d,\.]*\s*lines?\b", re.IGNORECASE)

# The two axes of the same ceiling. Both are subject-tainted and
# number-wildcard; they differ only in the unit alphabet, so a new axis is one
# entry rather than a new test. Pinning only the size axis would leave the line
# axis in exactly the state this repair exists to fix.
CapAxis = namedtuple("CapAxis", "pattern examples")
CAP_AXES = {
    "size": CapAxis(
        SIZE_CAP_RE, "'25KB', '25,000 characters' and '25,000 UTF-16 code units'"
    ),
    "line": CapAxis(LINE_CAP_RE, "'200 lines' and 'the first 250 lines'"),
}

SUBJECT_TOKEN = "MEMORY.md"

# The pointer, and the heading it must resolve to.
POINTER_TOKEN = "index-upkeep rule"
RULE_HEADING = "Index upkeep"

# --- the memory-block selection rule (see the second docstring block below) ---
SELECTOR_FILE = SINGLE_SOURCE
# The discriminator, backtick-anchored and deliberately WITHOUT a tilde.
DISCRIMINATOR = "`.claude/agent-memory/`"
# The bare form the discriminator must never be reduced to.
BARE_DISCRIMINATOR = "`agent-memory/`"
EXPECTED_SELECTOR_SITES = 2

TEXT_SUFFIXES = {".md", ".py", ".json", ".sh", ".txt", ".yaml", ".yml"}
SKIP_DIR_PARTS = {"__pycache__", ".pytest_cache"}


def _is_test_module(rel):
    """True for a test module, wherever it lives.

    Two test modules sit OUTSIDE `tests/`, inside the skill directories
    themselves. A directory-only exclusion would leave them in the instruction
    population, where a future test that quotes the limits would read as a
    second statement of them.
    """
    return rel.name.startswith("test_") and rel.suffix == ".py"


def _instruction_files():
    """Every shipped instruction file under the plugin, excluding test code.

    Deliberately filesystem-based rather than git-based: these tests must give
    the same answer inside a hermetic export, which has no `.git`.
    """
    out = []
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(PLUGIN_ROOT)
        if SKIP_DIR_PARTS & set(rel.parts):
            continue
        if rel.parts and rel.parts[0] == "tests":
            continue
        if _is_test_module(rel):
            continue
        out.append(path)
    return out


def _sites(token):
    """Every `relpath:lineno` at which `token` occurs, case-insensitively."""
    needle = token.lower()
    hits = []
    for path in _instruction_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if needle in line.lower():
                hits.append(f"{path.relative_to(PLUGIN_ROOT)}:{lineno}")
    return hits


def _cap_sites(pattern):
    """Every `relpath:lineno` stating a ceiling for the index, ANY spelling.

    A line qualifies when it names the index file AND carries a numeral next to
    a unit from the given alphabet. Both conditions are load-bearing: the
    numeral-plus-unit shape alone matches 96 unrelated lines across the shipped
    surfaces, and the subject alone matches every mention of the index.
    """
    hits = []
    for path in _instruction_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if SUBJECT_TOKEN in line and pattern.search(line):
                hits.append(f"{path.relative_to(PLUGIN_ROOT)}:{lineno}")
    return hits


@pytest.mark.parametrize("axis", sorted(CAP_AXES), ids=sorted(CAP_AXES))
def test_cap_stated_exactly_once_in_any_spelling(axis):
    """The spelling-agnostic arm. A count of 0 fails loudly rather than passing."""
    sites = _cap_sites(CAP_AXES[axis].pattern)
    assert len(sites) == 1, (
        f"the index {axis} ceiling must be STATED on exactly ONE line across the "
        f"shipped instruction surfaces; found {len(sites)}: {sites}. This arm is "
        f"spelling-agnostic on purpose — {CAP_AXES[axis].examples} all count as "
        f"statements of the same ceiling, because a duplicate "
        f"in a novel spelling is exactly how a second statement last reached this "
        f"tree. If you added a site, replace it with a pointer to the rule at "
        f"{SINGLE_SOURCE}. A count of ZERO means the rule was deleted, or that "
        f"{SUBJECT_TOKEN!r} no longer names the index file — fix the predicate, "
        f"do not delete this test."
    )


@pytest.mark.parametrize("axis", sorted(CAP_AXES), ids=sorted(CAP_AXES))
def test_cap_site_is_the_single_source(axis):
    """The one statement must live in the file the pointer sends readers to."""
    sites = _cap_sites(CAP_AXES[axis].pattern)
    assert len(sites) == 1, f"expected one {axis}-cap statement, found {sites}"
    assert sites[0].startswith(SINGLE_SOURCE + ":"), (
        f"the {axis} ceiling is stated at {sites[0]}, but {REFERRER} sends readers "
        f"to {SINGLE_SOURCE}. Move the rule back, or re-point the pointer and "
        f"update SINGLE_SOURCE here."
    )


def test_each_population_filter_removes_something():
    """Self-check on the OUTPUT of the population function, not on a copy of its rules.

    Both halves matter, and the second is the one that is easy to get wrong.
    Each rule must have something to remove (otherwise it is inert), AND
    `_instruction_files()` must actually have removed it. Re-deriving a rule
    here and asserting that it matches something proves only that the FILES
    exist — it says nothing about whether the population function applied the
    rule, so a broken filter would pass. The leak checks below therefore use
    literal predicates against the KEPT set, never the helpers under test.
    """
    all_text = [
        p
        for p in PLUGIN_ROOT.rglob("*")
        if p.is_file()
        and p.suffix in TEXT_SUFFIXES
        and not (SKIP_DIR_PARTS & set(p.relative_to(PLUGIN_ROOT).parts))
    ]
    rels = [p.relative_to(PLUGIN_ROOT) for p in all_text]
    kept = {p.relative_to(PLUGIN_ROOT) for p in _instruction_files()}
    assert kept, "the instruction-file population is empty"

    # Half 1: each rule has something to bite on.
    assert [r for r in rels if r.parts and r.parts[0] == "tests"], (
        "there is nothing under tests/, so the directory exclusion is inert"
    )
    assert [
        r
        for r in rels
        if r.name.startswith("test_")
        and r.suffix == ".py"
        and not (r.parts and r.parts[0] == "tests")
    ], (
        "no test module lives outside tests/, so the name exclusion is inert. "
        "If that is now true of this repository, delete the rule rather than "
        "leave it in place doing nothing."
    )

    # Half 2: the population function actually applied each rule.
    leaked_dir = sorted(str(r) for r in kept if r.parts and r.parts[0] == "tests")
    assert not leaked_dir, (
        f"the tests/ directory exclusion is a no-op: {len(leaked_dir)} file(s) "
        f"under tests/ reached the instruction population, e.g. {leaked_dir[:3]}. "
        f"Every occupancy count in this file is unreliable until that is fixed."
    )
    leaked_name = sorted(
        str(r) for r in kept if r.name.startswith("test_") and r.suffix == ".py"
    )
    assert not leaked_name, (
        f"the test_*.py name exclusion is a no-op: {len(leaked_name)} test "
        f"module(s) reached the instruction population, e.g. {leaked_name[:3]}. "
        f"A test that quotes the limits would then read as a second statement "
        f"of them."
    )


@pytest.mark.parametrize("token", UNIT_TOKENS, ids=UNIT_TOKENS)
def test_size_ceiling_unit_stated_exactly_once(token):
    sites = _sites(token)
    assert len(sites) == 1, (
        f"the size-ceiling unit {token!r} must occur on exactly ONE line across "
        f"the shipped instruction surfaces; found {len(sites)}: {sites}. "
        f"The limits are stated once, at {SINGLE_SOURCE}, and every other mention "
        f"must refer to that rule rather than repeat the numbers — otherwise a "
        f"future correction becomes a sweep instead of a one-line edit. If you "
        f"added a second site, delete it and point at the rule instead. If you "
        f"deliberately MOVED the rule, update SINGLE_SOURCE here and re-point "
        f"the table row in {REFERRER}."
    )


@pytest.mark.parametrize("token", UNIT_TOKENS, ids=UNIT_TOKENS)
def test_single_source_is_the_file_the_pointer_names(token):
    """The one site must live in the file the cross-reference sends readers to.

    A move that keeps the count at one but relocates the rule would leave the
    pointer in the other file aiming at nothing.
    """
    sites = _sites(token)
    assert len(sites) == 1, f"expected one site for {token!r}, found {sites}"
    assert sites[0].startswith(SINGLE_SOURCE + ":"), (
        f"the single statement of {token!r} is at {sites[0]}, but {REFERRER} "
        f"sends readers to {SINGLE_SOURCE}. Move the rule back, or re-point the "
        f"pointer and update SINGLE_SOURCE here."
    )


# ---------------------------------------------------------------------------
# The meta-arm: the pin's own constants
# ---------------------------------------------------------------------------
# THE ARMS ABOVE COUNT SITES; NOTHING ABOVE CHECKS THAT THE PREDICATE CAN STILL
# SEE A SITE. SUBJECT_TOKEN, SIZE_UNIT and LINE_CAP_RE are bare literals, and
# narrowing any of them is SILENT: measured, `SUBJECT_TOKEN` narrowed to
# "`MEMORY.md` index" leaves every arm green while the guard's reach has
# collapsed, because the single source still matches and the count is still one.
# Only a narrowing that matches NOTHING drives the count to zero and fires.
# SUBJECT_TOKEN is the worst of the three: one literal gating BOTH axes.
#
# The remedy is a table of statements the predicate MUST recognise. Narrow any
# constant and a probe stops matching, so alphabet completeness stops being an
# editorial property and becomes an asserted one.
#
# WHY A PROBE TABLE RATHER THAN A MUTATION HARNESS. A test that mutated these
# constants and re-ran the predicate would RE-DERIVE THE RULE IT IS CHECKING,
# which is the vacuity this very file shipped in its first version. Mutation is
# how this table is CERTIFIED, not what ships.
#
# THE NEGATIVE HALF IS NOT DECORATION. Without it this arm is a one-way
# ratchet: every failure argues for a broader alphabet and nothing argues back,
# until the subject taint is dropped and the 96 unrelated matches return.
#
# RESIDUAL, stated because a bound left implicit reads as a guarantee: this
# table is itself unguarded — a future editor can delete a probe. The regress
# does not close, it TERMINATES WHERE REVIEW CAN SEE IT. Narrowing a regex
# character class is invisible in review; deleting a plain-English sentence
# from a list is not.
DETECTION_PROBES = {
    "size": (
        "Your `MEMORY.md` index auto-loads only the first 25KB.",
        "Your `MEMORY.md` index is capped at 25,000 characters.",
        "`MEMORY.md` is truncated to the first 25,000 UTF-16 code units.",
    ),
    "line": (
        "Only the first 200 lines of `MEMORY.md` auto-load.",
        "Your `MEMORY.md` index is truncated to the first 250 lines.",
    ),
}

# Near-misses. Each carries a unit OR the subject, never both as a cap claim.
NON_DETECTIONS = (
    "The webhook payload is capped at 8 MB.",
    "- **WORKFLOW_GUIDE.md** (200 lines) - Workflow management",
    "Your `MEMORY.md` index is the file the platform loads at session start.",
)

_PROBE_CASES = [(a, p) for a, ps in DETECTION_PROBES.items() for p in ps]


@pytest.mark.parametrize(
    "axis,probe",
    _PROBE_CASES,
    ids=[f"{a}{i}" for a, ps in DETECTION_PROBES.items() for i in range(len(ps))],
)
def test_predicate_detects_every_canonical_spelling(axis, probe):
    """Narrow any constant and one of these stops matching."""
    assert SUBJECT_TOKEN in probe, (
        f"the subject taint {SUBJECT_TOKEN!r} no longer matches a canonical "
        f"statement of the ceiling: {probe!r}. Narrowing the taint disarms BOTH "
        f"axes at once while the count arms stay green, because the single "
        f"source still matches and the count is still one. Widen it back, or "
        f"retire the probe with a comment saying why it is no longer canonical."
    )
    assert CAP_AXES[axis].pattern.search(probe), (
        f"the {axis} alphabet no longer matches a canonical statement of the "
        f"ceiling: {probe!r}. A duplicate written this way would now be "
        f"invisible to the {axis} arm while it reports green. Restore the "
        f"missing unit, or retire the probe with a comment saying why."
    )


@pytest.mark.parametrize(
    "text", NON_DETECTIONS, ids=[f"near{i}" for i in range(len(NON_DETECTIONS))]
)
def test_predicate_ignores_near_misses(text):
    """The other direction: a widened alphabet must not readmit unrelated text."""
    hit = [
        axis
        for axis, spec in CAP_AXES.items()
        if SUBJECT_TOKEN in text and spec.pattern.search(text)
    ]
    assert not hit, (
        f"{hit} now match text that does not state the index ceiling: {text!r}. "
        f"An alphabet widened to fix a missed spelling has readmitted unrelated "
        f"content; a bare numeral-plus-unit sweep matches 96 lines across the "
        f"shipped surfaces, and the subject taint is what excludes them. Narrow "
        f"the change, do not delete this case."
    )


def test_index_upkeep_pointer_resolves_to_a_rule_that_exists():
    """Regression pin for a dangling cross-reference.

    The pointer and its target live in different files and can drift apart
    independently: this branch carried the pointer for two commits before the
    rule it names existed.
    """
    referrer = (PLUGIN_ROOT / REFERRER).read_text(encoding="utf-8")
    target = (PLUGIN_ROOT / SINGLE_SOURCE).read_text(encoding="utf-8")
    assert POINTER_TOKEN in referrer, (
        f"{REFERRER} no longer points at the index-upkeep rule. If the pointer "
        f"was removed on purpose, remove this test with it."
    )
    assert RULE_HEADING in target, (
        f"{REFERRER} points at the {POINTER_TOKEN!r} in {SINGLE_SOURCE}, but that "
        f"file has no {RULE_HEADING!r} rule. The pointer dangles: restore the "
        f"rule, or remove the pointer."
    )


# ---------------------------------------------------------------------------
# The memory-block selection rule
# ---------------------------------------------------------------------------
# An agent's context carries TWO instruction blocks offering a memory
# directory, at different paths, with byte-identical second sentences, neither
# mentioning the other and neither stating precedence. The selection rule tells
# the agent which one to follow. It appears at both deferral sites, verbatim:
# the site read at spawn and the site read at wrap-up. The duplication is
# deliberate — an agent saving a learning is not re-reading the start-up step,
# and a missed cross-reference is the failure the rule exists to prevent.
#
# TWO PROPERTIES OF THE PREDICATE ARE LOAD-BEARING AND NEITHER IS EVIDENT FROM
# READING IT. Both are the kind a future editor "tidies" away, leaving text
# that reads better and a predicate that no longer works.
#
# 1. NO TILDE. The delivered path is EXPANDED, so `~/.claude/agent-memory/` is
#    not a substring of anything an agent holds and a tilde predicate NEVER
#    FIRES. The tilde is correct in the DESCRIPTION sentence beside it, which
#    describes rather than selects. The two spellings sit on the same line on
#    purpose, which is why these tests slice the selector SENTENCE out of the
#    line: a line-level tilde assertion would be red against correct text.
#
# 2. THE FULL `.claude/` PREFIX, which looks like padding and is not. It
#    contributes nothing to discrimination — the discriminating component is
#    `agent-memory` — so the tempting edit is to strip it for brevity. That
#    edit reintroduces a real collision. Project directories are keyed by a
#    SLUG, and a slug is the filesystem path with `/` replaced by `-`; a
#    repository under an `agent-memory` path therefore yields, for example,
#    `.claude/projects/-Users-me-Sites-agent-memory/memory/`. The bare form
#    matches that project path and MISROUTES the agent; the full form does not.
#    The general reason is stronger than the example: a slug cannot contain
#    `/`, and the full form contains two, so it can only ever match a real
#    directory path and is immune to slug collision BY CONSTRUCTION. Keep the
#    prefix. It is a false-positive guard, not a discriminator.
#
# WHY THIS IS NOT THE PIN VERIFICATION D FORBIDS. D forbids pinning the cap
# sentence because that asserts a PLATFORM CONSTANT matches itself: it would
# pass forever, including on the day the constant changes, converting a visible
# limitation into an invisible one. These tests assert a PREDICATE'S SHAPE and
# contain no number. They stay GREEN when the platform constants change —
# correctly, because they never claimed anything about them — and go RED
# exactly when someone tidies the asymmetry away. Opposite failure direction.
# Do not delete these believing D forbids them.
#
# THE RESIDUAL, STATED RATHER THAN IMPLIED, because a bound left out is a
# bounded guarantee presented as an unbounded one. The discriminator is ITSELF
# a platform-determined path. If the platform relocated the agent-memory tree,
# or renamed `.claude/`, the rule would go stale and THESE TESTS WOULD STAY
# GREEN — structurally D's own objection, one level down. Two things bound it:
# the path is OBSERVED by every agent in its own context every session, unlike
# the cap, so staleness is discoverable in normal operation rather than
# undetectable in principle; and a stale discriminator matches NOTHING, so the
# agent falls back to the ambiguity that existed before the rule rather than
# being routed to the wrong directory. Fail-safe, not fail-open.
#
# WHAT THE FULL-STRING FORM COSTS, because it is a TRADE and not a free win.
# Asserting the whole `.claude/agent-memory/` couples this pin more tightly to
# the platform's config-root NAME than a bare `agent-memory` would, and so it
# WIDENS the silent-staleness surface described immediately above: rename
# `.claude/` and the rule goes stale while these tests stay green. That cost is
# accepted deliberately, because the alternative is worse in kind rather than
# in degree. A stale full form matches NOTHING and degrades to the ambiguity
# that existed before the rule; a stripped form plus a slug collision matches
# BOTH paths and actively misroutes. The trade is a slightly larger
# silent-staleness surface in exchange for removing an active-misroute
# surface. Anyone reopening this decision should re-derive that comparison
# rather than weigh the two failures as though they were the same kind.


def _selector_slices():
    """Every sentence in the selector file that carries the discriminator.

    Returned as (line number, sentence). Slicing to the SENTENCE is what makes
    the no-tilde assertion meaningful: the description sentence on the same
    line legitimately carries a tilde, so a line-level assertion would be red
    against correct text.

    A broken slicer is caught rather than tolerated in both directions. Too
    wide (the whole line) drags the description tilde in and reddens the
    no-tilde assertion; too narrow (empty) fails the contains-discriminator
    assertion beside it.
    """
    import re

    text = (PLUGIN_ROOT / SELECTOR_FILE).read_text(encoding="utf-8")
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if DISCRIMINATOR not in line:
            continue
        for sentence in re.split(r'(?<=\.)\s+(?=[A-Z`“"*])', line):
            if DISCRIMINATOR in sentence:
                out.append((lineno, sentence))
    return out


def test_selection_rule_present_at_every_deferral_site():
    slices = _selector_slices()
    found = [ln for ln, _ in slices]
    assert len(slices) == EXPECTED_SELECTOR_SITES, (
        f"the memory-block selection rule must appear at exactly "
        f"{EXPECTED_SELECTOR_SITES} sites in {SELECTOR_FILE}; found {len(slices)} "
        f"at lines {found}. The rule is duplicated deliberately: one site is read "
        f"at spawn and the other at wrap-up, and this project has recorded that "
        f"agents do not follow cross-references reliably. Do NOT resolve a "
        f"failure here by replacing a site with a pointer to the other one. If a "
        f"site was legitimately added or removed, update EXPECTED_SELECTOR_SITES "
        f"with a comment naming which site and why."
    )


@pytest.mark.parametrize("index", range(EXPECTED_SELECTOR_SITES))
def test_selector_clause_carries_no_tilde(index):
    """The tilde belongs in the description sentence and NEVER in the selector."""
    slices = _selector_slices()
    assert index < len(slices), (
        f"expected {EXPECTED_SELECTOR_SITES} selector sites, found {len(slices)}"
    )
    lineno, clause = slices[index]
    assert DISCRIMINATOR in clause, (
        f"the slice taken at {SELECTOR_FILE}:{lineno} does not contain the "
        f"discriminator, so the no-tilde check below would pass vacuously. The "
        f"sentence splitter is broken, not the instruction text."
    )
    assert "~" not in clause, (
        f"the selection rule at {SELECTOR_FILE}:{lineno} contains a tilde: "
        f"{clause!r}. The delivered path is EXPANDED, so a tilde form is not a "
        f"substring of what an agent holds and the predicate would NEVER FIRE. "
        f"The tilde in the DESCRIPTION sentence beside this one is correct and "
        f"must stay; this asymmetry is deliberate. Do not harmonise them."
    )


def test_discriminator_keeps_its_claude_prefix():
    """`.claude/` is a false-positive guard, not padding. See the block above.

    Separable from the site-count assertion: adding a THIRD mention in the bare
    form leaves the count of full discriminators at two while reintroducing the
    collision, and only this assertion sees that.
    """
    text = (PLUGIN_ROOT / SELECTOR_FILE).read_text(encoding="utf-8")
    bare_sites = [
        lineno
        for lineno, line in enumerate(text.splitlines(), 1)
        if BARE_DISCRIMINATOR in line.replace(DISCRIMINATOR, "")
    ]
    assert not bare_sites, (
        f"{SELECTOR_FILE} uses the bare {BARE_DISCRIMINATOR} at line(s) "
        f"{bare_sites}. The `.claude/` prefix is NOT redundant padding: project "
        f"directories are keyed by a slug, a slug is the filesystem path with "
        f"'/' replaced by '-', so a repository under an `agent-memory` path "
        f"yields a project path the bare form MATCHES and misroutes the agent "
        f"to. The full form contains two slashes and a slug contains none, so it "
        f"can only match a real directory path. Restore the prefix."
    )
