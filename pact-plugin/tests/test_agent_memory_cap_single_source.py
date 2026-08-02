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

BOUND, stated rather than implied. A restatement that avoids the unit vocabulary
altogether (for example "25,000 characters") is invisible to this pin. The pin
narrows the failure mode; it does not close it. It also says nothing about
whether the stated limits are CORRECT — no test in this repository can, because
none of them reads the platform bundle.
"""
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent

# The single source, and the file whose table points at it.
SINGLE_SOURCE = "skills/pact-agent-teams/SKILL.md"
REFERRER = "skills/pact-memory/SKILL.md"

# Unit vocabulary of the size ceiling. Neither token is used by the two
# auto-memory carriers, which state a limit for a DIFFERENT memory system and
# are deliberately out of scope here.
UNIT_TOKENS = ["UTF-16", "code unit"]

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
