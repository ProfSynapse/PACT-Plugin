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

BOTH CAPS ARE PINNED — the size axis and the line axis, each with its own unit
alphabet. An earlier version of this docstring said the line cap was
deliberately unpinned, and gave two reasons. The first was real and is now
SUPERSEDED: the line vocabulary did collide with unrelated documentation, and
the collision was solved by NARROWING that alphabet to a bare "N lines" rather
than by abandoning the axis. The second stopped being true when the auto-memory
table row became a pointer. Read the comment above LINE_CAP_RE for the alphabet
that shipped.

WHAT REMAINS OUTSIDE, so the next reader does not have to rediscover it, and
WIDER than the superseded paragraph implied. A restatement is invisible when it
uses a spelling outside the alphabet OR when it never names the index file —
ONE of the two is enough, and the earlier text required both. The predicate
reads ONE LINE AT A TIME, so a ceiling whose subject and numeral sit on
different lines is invisible unless the subject-free unit arm happens to catch
it. The arms count NUMERIC restatements, so a statement that a ceiling exists
without giving a figure is out of scope by design — a pointer states no value
and cannot duplicate one. And the shape the arms match is
subject-plus-numeral-plus-unit, which a line can satisfy WITHOUT restating the
ceiling, so this guard can also flag correct text.

PART OF THAT IS ASSERTED RATHER THAN MERELY STATED, and the split matters
because this docstring has been wrong before. KNOWN_MISSES at the end of this
module carries one spelling outside each of the two alphabets. KNOWN_OVER_BLOCKS
carries a line that matches the shape without restating the ceiling. Both go RED
if the predicate ever improves past them, so those two clauses cannot rot here
unnoticed. THE REST OF THE PARAGRAPH ABOVE IS PROSE — the unnamed-subject half,
and the one-line-at-a-time limit, are enforced by nothing. A reader who needs
either of them held should convert it the same way rather than trust this
wording.

And nothing here says whether the stated limits are CORRECT — no test in this
repository can, because none of them reads the platform bundle.
"""
import os
import re
import subprocess
from collections import namedtuple
from functools import lru_cache
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
#
# THE SPELLED-OUT UNIT NAMES ARE INCLUDED, and they were measured before they
# were added. "kilobytes" is ordinary English and `[KMG]i?B` cannot match inside
# it, so a cap written that way was invisible. The addition costs NOTHING on
# either side: the untainted sweep is unchanged at 112 and the tainted count
# unchanged at 1, and it opens no new class of false positive, because a
# non-restatement written as "grew by 3 kilobytes" is the same class the
# alphabet already admitted as "grew by 3 KB".
SIZE_UNIT = (
    r"(?:UTF-16\s+code\s+units?|code\s+units?|characters?|chars?"
    r"|(?:kilo|mega|giga|kibi|mebi)-?bytes?|bytes?|[KMG]i?B)"
)
SIZE_CAP_RE = re.compile(r"\d[\d,\.]*[-\s]*" + SIZE_UNIT, re.IGNORECASE)

# The LINE cap, added once the tree could support it. It was withheld from the
# first pass of this repair because a third statement of the constant still
# stood in the auto-memory table row, so this arm would have been red against
# correct text. With that row converted to a pointer the sweep returns one site,
# and the arm is admissible.
#
# THE REVERSED ORDER IS MATCHED THROUGH A CLOSED LIST OF CONNECTIVES, and the
# shape of that decision is the important part. An earlier version of this
# comment said widening to prose forms "buys nothing measurable"; that was
# wrong, because the platform's OWN phrasing of this cap puts the numeral AFTER
# the unit word ("lines after 200 will be truncated") and the bare form cannot
# see it.
#
# WHAT WAS MEASURED, and it reversed the obvious choice. The general widening —
# the unit word, then up to three words, then a numeral — accepts EVERY line
# citation: "see line 12", "delete lines 5 and 6", "lines 1 to 3". Measured on
# CONSTRUCTED inputs it took 6 of 6 such sentences, and 13 of the 14 lines it
# matches in the shipped tree are line-number citations rather than caps. A
# corpus count could not reveal that, because it measures what the tree ALREADY
# contains, never what a pattern would newly ACCEPT.
#
# So the widening is an ALLOWLIST of the connectives a ceiling is stated with,
# not a general shape. That direction is deliberate: the ways to STATE a cap are
# few and enumerable, while the ways to write a non-cap sentence with a numeral
# near "lines" are unbounded. Bounding the small side is the only side that can
# be bounded. It fails toward a MISS rather than toward a false positive, and
# every known miss is recorded in KNOWN_MISSES below rather than left silent.
#
# THE SEPARATOR IS `[-\s]*` RATHER THAN `\s*` so the HYPHENATED-ADJECTIVE form
# is caught: "a 200-line ceiling", "a 25-KB cap". Ordinary English, and the
# trailing `\b` does not save you because the break is on the far side of the
# number. An independent enumeration found this family and nothing else that
# was worth the budget. MEASURED COST: the widening adds 31 matches to the
# UNTAINTED sweep (28 size, 3 line), every one a hyphenated adjective in a code
# comment, and NONE of them is in a file that mentions the index file at all --
# so the tainted count is unchanged at one site per axis. The taint absorbed
# the whole cost.
#
# WHAT THIS COUNTS, and the distinction is load-bearing: NUMERIC restatements of
# the ceiling, not every statement that a ceiling exists. A pointer states no
# value, so it cannot duplicate one, and the arms are right to ignore it. This
# PR converted several numeric cap statements into pointer-shaped ones, so the
# guard is deliberately blind to the shape they were converted INTO -- including
# the auto-memory row that now reads as a pointer.
LINE_CONNECTIVE = (
    r"(?:after|beyond|past|over|above|up\s+to|and"
    r"|are\s+capped\s+at|is\s+capped\s+at|are\s+limited\s+to)"
)
LINE_CAP_RE = re.compile(
    r"\d[\d,\.]*[-\s]*lines?\b"
    r"|\blines?\b\s+" + LINE_CONNECTIVE + r"\s+\d[\d,\.]*",
    re.IGNORECASE,
)

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

# THE SUBJECT MATCH IS CASE-INSENSITIVE BUT ANCHORED, and both halves are
# load-bearing in opposite directions.
#
# Case-insensitive, because a plain substring test missed `Memory.md` and
# `memory.md` while the count arms reported green — the taint is what gates
# BOTH axes, so a case variant disarmed the whole guard.
#
# Anchored, because the plugin ships a `-memory.md` filename family:
# `commands/prune-memory.md` contains the token as a suffix. A case-insensitive
# substring test readmits every line naming that command file, and such a line
# carrying any numeral next to a unit would be counted as a statement of this
# ceiling. The lookbehind rejects a preceding word character or hyphen, so the
# command file cannot satisfy the subject while the index still can. Both
# directions are pinned by the probe tables below; neither is assumed.
SUBJECT_RE = re.compile(r"(?<![\w-])" + re.escape(SUBJECT_TOKEN), re.IGNORECASE)

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


# --- the untracked subtraction ---------------------------------------------
# WHY GIT IS CONSULTED AT ALL, in a walk that stays deliberately
# filesystem-based. A stale directory left behind by earlier work entered the
# walk and reddened the count arms, while `git status` reported clean the whole
# time. Nothing in the normal view of the repository could explain the failure.
# The population is meant to be the SHIPPED tree, so anything git does not
# track is subtracted from it. The SOURCE is unchanged; only an exclusion is
# added, and only where there is a repository to ask.
#
# THE SUBTRACTION SET IS THE COMPLEMENT OF TRACKED, NEVER AN ENUMERATION OF
# UNTRACKED. That distinction is the whole correctness of this module, and the
# obvious spelling is the wrong one. MEASURED, on a constructed repository
# carrying one file of each class:
#
#   * `git ls-files --others --exclude-standard` returns ONLY the plain
#     untracked file. It excludes IGNORED files by design, and it does not
#     descend into a nested repository at all.
#   * `git ls-files --others` adds the ignored file, and collapses a nested
#     worktree to a single directory entry with a trailing slash — so a
#     membership test on file paths still never matches the files inside it.
#   * the complement of `git ls-files` catches all three.
#
# BOTH INVISIBLE CLASSES ARE LIVE IN THIS REPOSITORY. `.gitignore` carries
# `.worktrees/` with no leading slash, so that pattern matches at ANY depth,
# and this project does nearly all of its work in worktrees. A stale one is
# therefore ignored AND a nested repository at the same time — which is exactly
# why `git status` stayed clean. A subtraction built on `--others` would have
# shipped green while removing a class of file that was never the problem.
#
# THE COMPLEMENT FORM IS ALSO IMMUNE TO THE USER'S GLOBAL EXCLUDES FILE, which
# `--exclude-standard` reads. Two people with different `core.excludesFile`
# settings get the same population here. They would not, under the other form.
def _git(root, *args):
    """Run a read-only git query under `root`.

    The user's git config is INHERITED rather than neutralised, deliberately.
    A hermetic config is right when a test BUILDS a repository, and the helper
    beside the synthetic probes below does exactly that. It is wrong here: the
    only settings that could matter to `ls-files` are the ownership allowances
    in `safe.directory`, and discarding those would turn a normal checkout into
    a hard error for no gain. Nothing this function reads depends on the ignore
    rules, because it never asks about them.
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )


@lru_cache(maxsize=None)
def _tracked_relpaths(root=PLUGIN_ROOT):
    """Paths git tracks under `root`, or None when `root` is in no repository.

    THREE OUTCOMES, AND COLLAPSING ANY TWO OF THEM REINSTATES THE DEFECT:

      * NO REPOSITORY -> None, meaning "subtract nothing". The walk then
        returns exactly what it always did, which is what keeps this module
        working inside a hermetic export that has no `.git`.
      * A REPOSITORY, QUERY SUCCEEDS -> the tracked set.
      * A REPOSITORY, QUERY FAILS -> raise.

    THE THIRD OUTCOME IS WHY THIS IS NOT WRITTEN AS A `try`. "There is no
    repository here" and "I could not ask git" are different facts with the
    same convenient answer, and an exception handler gives both of them the
    empty subtraction set. A transient git failure would then silently restore
    the original defect, in the one tree where it has already happened once,
    with nothing in the output to say so. So the no-repository case is reached
    only by a POSITIVE determination, and every other failure raises.

    CACHED, so that one pytest session sees ONE population. Without the cache
    a suite that runs while somebody stages a file could answer two calls from
    two different git states, and the population arms would disagree with each
    other for a reason no reader could reconstruct.
    """
    probe = _git(root, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None

    listing = _git(root, "ls-files", "-z")
    if listing.returncode != 0:
        raise RuntimeError(
            f"{root} is inside a git work tree, but `git ls-files` failed with "
            f"status {listing.returncode}: {listing.stderr.strip()!r}. This is "
            f"NOT treated as an empty subtraction set on purpose — that would "
            f"silently readmit untracked files to the instruction population, "
            f"which is the defect this subtraction exists to prevent."
        )

    tracked = frozenset(entry for entry in listing.stdout.split("\0") if entry)
    if not tracked:
        raise RuntimeError(
            f"{root} is inside a git work tree, but git tracks NOTHING under "
            f"it. Subtracting the complement of an empty set would empty the "
            f"instruction population and make every count arm in this module "
            f"vacuous, so this raises instead. The likely cause is a repository "
            f"that encloses this directory without covering it — a home "
            f"directory under version control, with the plugin installed "
            f"beneath it. If that is your setup, the population cannot be "
            f"filtered by git here and this subtraction needs a way to say so."
        )
    return tracked


def _is_test_module(rel):
    """True for a test module, wherever it lives.

    Two test modules sit OUTSIDE `tests/`, inside the skill directories
    themselves. A directory-only exclusion would leave them in the instruction
    population, where a future test that quotes the limits would read as a
    second statement of them.
    """
    return rel.name.startswith("test_") and rel.suffix == ".py"


def _instruction_files(root=PLUGIN_ROOT):
    """Every shipped instruction file under the plugin, excluding test code.

    `root` IS A PARAMETER SO THE PROBES BELOW CAN ASSERT ON THE POPULATION
    ITSELF rather than on the helper that feeds it. A test that asserted
    `_tracked_relpaths` returned the right set would be pinned to TODAY'S
    mechanism: rewrite the subtraction to enumerate untracked files instead,
    and such a test has to be rewritten too, so it could be made to pass by
    the same edit that broke the guard. Driving the real population keeps the
    assertions true of any mechanism that claims to do this job.


    THE SOURCE IS DELIBERATELY THE FILESYSTEM RATHER THAN GIT: these tests must
    give the same answer inside a hermetic export, which has no `.git`. That
    sentence is unchanged and still governs. What is now QUALIFIED is that git
    is consulted for EXCLUSION where a repository exists — untracked entrants
    are subtracted, because the population is meant to be the shipped tree and
    a stale untracked directory once reddened this module while `git status`
    reported clean. Where there is no repository the subtraction set is empty
    and this returns precisely what it always returned. See the block above
    `_tracked_relpaths` for why the subtraction is a COMPLEMENT of tracked and
    not an enumeration of untracked.
    """
    tracked = _tracked_relpaths(root)
    out = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if SKIP_DIR_PARTS & set(rel.parts):
            continue
        if tracked is not None and str(rel) not in tracked:
            continue
        if rel.parts and rel.parts[0] == "tests":
            continue
        if _is_test_module(rel):
            continue
        out.append(path)
    assert out, (
        "the instruction-file population is EMPTY. Every count arm in this "
        "module asserts a site count, so an empty population makes the whole "
        "file assert things about nothing — and a vacuous pass is "
        "byte-identical to a real one. Either the walk no longer reaches the "
        "plugin tree, or the untracked subtraction removed everything."
    )
    return out


def _walked_text_files(root=PLUGIN_ROOT):
    """The SUPERSET the filter self-check measures `kept` against.

    Everything the walk reaches that could be an instruction file, with the
    untracked subtraction applied and NONE of the exclusion rules. Those rules
    stay re-derived at the call site, because a self-check that calls the
    helpers under test proves only that the files exist.

    EXTRACTED SO THE SUBTRACTION HERE CAN BE ASSERTED. While this was a local
    inside the test, deleting its subtraction left the suite at 40 passed on a
    clean tree — and a clean tree is the only state CI runs in. A bound that
    only a comment defends is not defended.
    """
    tracked = _tracked_relpaths(root)
    return [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in TEXT_SUFFIXES
        and not (SKIP_DIR_PARTS & set(p.relative_to(root).parts))
        and (tracked is None or str(p.relative_to(root)) in tracked)
    ]


def _directories_holding_shipped_text(root=PLUGIN_ROOT):
    """Top-level directory names holding at least one shipped text file.

    The independent oracle for the reach of the population: derived from the
    DIRECTORY LISTING rather than from `_instruction_files`, so a narrowing is
    visible whichever directory it drops.

    EXTRACTED FOR THE SAME REASON AS THE SUPERSET ABOVE, and this one had the
    sharper failure. With the subtraction deleted here and one stale untracked
    directory present, the arm that consumes this went red with
    `assert not ['stale_leftover']` — the original defect, moved one test down,
    which is exactly what the comment predicted and nothing asserted.
    """
    tracked = _tracked_relpaths(root)
    out = set()
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "tests" or entry.name in SKIP_DIR_PARTS:
            continue
        if any(
            f.is_file()
            and f.suffix in TEXT_SUFFIXES
            and not (SKIP_DIR_PARTS & set(f.relative_to(root).parts))
            and not _is_test_module(f.relative_to(root))
            and (tracked is None or str(f.relative_to(root)) in tracked)
            for f in entry.rglob("*")
        ):
            out.add(entry.name)
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


def _names_subject(line):
    """True when the line names the index file, in any case, as its own token."""
    return bool(SUBJECT_RE.search(line))


def _states_cap(line, pattern):
    """THE predicate. One definition, used by the walk AND by the probes below.

    Kept separate so the probe table exercises the real conjunction rather than
    a copy of it. A copy passes forever once the two drift: measured, a version
    of `_cap_sites` that ignored SUBJECT_TOKEN and hardcoded the literal left
    every probe green, because the probes were re-deriving the rule instead of
    calling it. A self-check that re-derives its own rule cannot falsify it.
    """
    return _names_subject(line) and bool(pattern.search(line))


# --- the declared exception ------------------------------------------------
# WHY A DECLARATION RATHER THAN A CLEVERER PREDICATE. The arms match
# subject-plus-numeral-plus-unit, and a line can satisfy that shape while
# stating something else entirely: a PER-ENTRY limit, a MEASUREMENT, an EXAMPLE
# cost, a BUDGET. Those four share NO vocabulary, so no word list separates
# them. That was measured rather than assumed: a negative lookahead for
# "each/per ... entry" silenced the two per-entry lines it was written for and
# left four others of the same class standing. The distinguisher is the semantic
# ROLE of the numeral — is this figure THE ceiling of the index, or some other
# quantity that happens to sit beside the index's name — and a regular
# expression cannot read a role.
#
# So this module does not try to. A line that carries the shape without
# restating the ceiling is DECLARED here. The declaration IS the human
# judgement the predicate cannot make, and it lands in review as a visible
# one-line addition rather than as a silent widening of the pattern.
#
# KEYED ON THE EXACT LINE TEXT, DELIBERATELY. Edit the line and the declaration
# stops matching, so the guard flags it again and the judgement is re-made by
# whoever changed it. A declaration keyed on a line NUMBER would drift the
# moment anything above it moved, and would then exempt a line nobody judged.
#
# EMPTY TODAY, and that is the honest state: no shipped line currently carries
# the shape without restating the ceiling. The mechanism is asserted anyway by
# the arm below, which drives it with a synthetic table, so an empty production
# list cannot make the machinery vacuous.
DECLARED_NON_RESTATEMENTS = ()


def _is_declared(rel, line, declarations=DECLARED_NON_RESTATEMENTS):
    """True when this exact line, at this exact path, is a declared exception."""
    return (str(rel), line.strip()) in declarations


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
        rel = path.relative_to(PLUGIN_ROOT)
        for lineno, line in enumerate(text.splitlines(), 1):
            if _states_cap(line, pattern) and not _is_declared(rel, line):
                hits.append(f"{rel}:{lineno}")
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
        f"tree. TWO DOORS, and pick by what the line actually says. If it "
        f"RESTATES the ceiling, replace it with a pointer to the rule at "
        f"{SINGLE_SOURCE}. If it carries the shape WITHOUT restating the ceiling "
        f"— a per-entry limit, a measurement, an example cost — then it is not a "
        f"duplicate and the predicate cannot tell: declare it in "
        f"DECLARED_NON_RESTATEMENTS by path and exact text. Do NOT widen the "
        f"pattern to exclude it; that is how the alphabet rots. "
        f"A count of ZERO means the rule was deleted, or that "
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
    # THE SUBTRACTION IS APPLIED TO THE SUPERSET TOO, and it has to be. This
    # is what `kept` is measured against, so on a raw filesystem walk the two
    # halves below would reason about two different populations: Half 1 could
    # report a filter as live on the evidence of an untracked file that Half 2
    # can never see. That subtraction is asserted by
    # `test_the_superset_oracle_excludes_untracked_entrants`, not merely
    # described here.
    #
    # SHARING THE SOURCE DOES NOT COST THE INDEPENDENCE THIS ARM RELIES ON.
    # What must not be shared is the FILTER RULES — they are re-derived
    # literally below, never by calling `_instruction_files`. The population
    # SOURCE was always shared: it was `PLUGIN_ROOT.rglob("*")` written out on
    # both sides before, and it is that walk minus the subtraction now.
    rels = [p.relative_to(PLUGIN_ROOT) for p in _walked_text_files()]
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
# constant and a probe stops matching, so alphabet NON-REGRESSION stops being an
# editorial property and becomes an asserted one.
#
# WHAT THIS TABLE CANNOT DO, stated because an earlier version of this comment
# claimed the opposite and claimed it in the direction that stops a reader
# looking. It cannot assert that the alphabet is SUFFICIENT. Every entry here is
# asserted to be DETECTED, so by construction every entry lies INSIDE the
# current alphabet, and no entry can represent a spelling the alphabet does not
# already cover. The table pins the alphabet against SHRINKING. It says nothing
# about whether the alphabet was wide enough to begin with, and a green run here
# is not evidence that it was. KNOWN_MISSES below carries that half, and it is
# an enumeration rather than a proof.
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
        "Your `MEMORY.md` index has a 25-KB cap.",
        # Case variant. Pins the case-insensitive half of the subject match.
        "Your `Memory.md` index is capped at 25,000 characters.",
        # Spelled-out unit. Was a KNOWN_MISS until the alphabet was widened.
        "Keep `MEMORY.md` under 25 kilobytes.",
    ),
    "line": (
        "Only the first 200 lines of `MEMORY.md` auto-load.",
        "Your `MEMORY.md` index is truncated to the first 250 lines.",
        "Your `MEMORY.md` index has a 200-line ceiling.",
        # THE PLATFORM'S OWN PHRASING, numeral AFTER the unit word. Was a
        # KNOWN_MISS until the reversed-order connectives were admitted.
        "`MEMORY.md` is always loaded into your conversation context - lines "
        "after 200 will be truncated, so keep the index concise.",
    ),
}

# Near-misses. Each carries a unit OR the subject, never both as a cap claim.
NON_DETECTIONS = (
    "The webhook payload is capped at 8 MB.",
    "- **WORKFLOW_GUIDE.md** (200 lines) - Workflow management",
    "Your `MEMORY.md` index is the file the platform loads at session start.",
    # The anchor's negative control. This line carries the token as a SUFFIX of
    # a shipped command file and a numeral next to a line unit, so a
    # case-insensitive SUBSTRING subject test would count it as a statement of
    # this ceiling. Pinned, not assumed: drop the lookbehind and this fires.
    "`prune-memory.md` reads the first 40 lines of the pin block.",
    # LINE CITATIONS. These are what the reversed-order arm must NOT readmit,
    # and they are the reason it is a closed list of connectives rather than a
    # general "unit word, then a numeral" shape: the general form took all
    # three of these, and 13 of the 14 lines it matches in the shipped tree are
    # citations exactly like them.
    "See `MEMORY.md` line 12 for the pointer format.",
    "Delete `MEMORY.md` lines 5 and 6.",
    "The `MEMORY.md` header occupies lines 1 to 3.",
)

_PROBE_CASES = [(a, p) for a, ps in DETECTION_PROBES.items() for p in ps]

# ---------------------------------------------------------------------------
# The bounds, as assertions rather than as prose
# ---------------------------------------------------------------------------
# A BOUND WRITTEN AS PROSE GOES STALE IN SILENCE, and this module has paid for
# that twice: a docstring paragraph disclosed a hole and a duplicate walked
# through it, then a second paragraph kept asserting a superseded reason across
# three reviews. Both tables below therefore pin CURRENT behaviour, not desired
# behaviour, so that the day someone changes the predicate CI tells them the
# bound moved instead of leaving the prose to rot.
#
# HOW TO RESOLVE A FAILURE HERE. These are the only tests in this file that go
# RED on an IMPROVEMENT. If one fails, the predicate got better: move the entry
# to DETECTION_PROBES or to NON_DETECTIONS and delete it from here. Do not widen
# the entry to make it pass again.
#
# NEITHER TABLE MAY GROW SILENTLY. An addition is a statement that the guard is
# weaker than the last reader believed, and it belongs in review as such.

# Statements of the ceiling the predicate does NOT see today.
KNOWN_MISSES = {
    # THE CONNECTIVE BEFORE THE UNIT WORD, not after it. The reversed-order arm
    # is an allowlist of connectives that follow "lines", so a sentence that
    # puts the connective FIRST is outside it. Both entries this table used to
    # carry are now DETECTED and have moved to DETECTION_PROBES; this one
    # replaces them and is a real, current hole rather than a placeholder.
    "line": (
        "`MEMORY.md` is truncated past line 200.",
    ),
}

# Correct text that is NOT a restatement of the ceiling and IS flagged today.
# The predicate matches subject-plus-numeral-plus-unit on one line, which a
# sentence can satisfy while stating something else entirely: a PER-ENTRY
# limit, a measurement, or an example. The first entry is the platform's own
# index-discipline sentence, so this is not a hypothetical cost.
KNOWN_OVER_BLOCKS = (
    "`MEMORY.md` is an index, not a memory - each entry should be one line, "
    "under ~150 characters.",
    "Each `MEMORY.md` entry should be one line, under 150 characters.",
)

_MISS_CASES = [(a, t) for a, ts in KNOWN_MISSES.items() for t in ts]


def test_population_reaches_every_directory_a_duplicate_has_appeared_in():
    """The walk itself can narrow, and the count arms cannot see it.

    Measured: restricting `_instruction_files()` to `skills/` leaves the count
    at one, because the single source lives there — while a duplicate under
    `agents/` becomes invisible. That is not hypothetical. The only real
    duplicate this pin has ever caught was at agents/pact-orchestrator.md:581.
    """
    tops = {
        rel.parts[0]
        for rel in (p.relative_to(PLUGIN_ROOT) for p in _instruction_files())
        if rel.parts
    }
    for required in ("agents", "skills"):
        assert required in tops, (
            f"the instruction population no longer reaches {required!r}; it "
            f"covers {sorted(tops)}. A cap statement added there would be "
            f"invisible to every arm in this file while the counts stay at one. "
            f"If a directory was deliberately dropped, say which and why."
        )

    # THE NAMED PAIR ABOVE IS A FLOOR, NOT THE PROPERTY. It closes the one
    # narrowing that was measured and nothing else: a walk cut to agents+skills
    # satisfies it while commands/, protocols/, hooks/ and templates/ — all
    # instruction surfaces — drop out unseen. The expectation below is derived
    # from the DIRECTORY LISTING instead of from the population function, so it
    # is an independent oracle rather than a second spelling of the same rule,
    # and any narrowing is visible whichever directory it drops.
    # THE SUBTRACTION APPLIES TO THIS ORACLE TOO, AND OMITTING IT WOULD
    # RELOCATE THE DEFECT RATHER THAN FIX IT. This one walks a PER-ENTRY
    # subtree instead of the plugin root, so it is the site a mechanical edit
    # skips. If `_instruction_files` subtracted untracked entrants and this did
    # not, an untracked directory holding a single .md file would enter
    # `expected`, could never enter `tops`, and THIS ARM would go red — the
    # same unexplainable local failure as before, moved one test down. That is
    # asserted by `test_the_directory_oracle_ignores_a_stale_untracked_dir`
    # rather than left to this comment, which is all that guarded it before.
    expected = _directories_holding_shipped_text()
    unreached = sorted(expected - tops)
    assert not unreached, (
        f"the instruction population no longer reaches {unreached}; it covers "
        f"{sorted(tops)}. Each of those directories holds at least one shipped "
        f"text file, so a cap statement added there would be invisible to every "
        f"arm in this file while the counts stay at one. If a directory was "
        f"deliberately dropped, exclude it here by name with a comment saying "
        f"why, rather than letting the walk narrow silently."
    )


# ---------------------------------------------------------------------------
# The subtraction, asserted against a constructed repository
# ---------------------------------------------------------------------------
# THE SHIPPED TREE CANNOT ASSERT ANY OF THIS. Every file under this plugin is
# tracked, so the subtraction removes NOTHING here — measured, 512 walked text
# files and 512 tracked, difference zero. A green suite in this repository is
# therefore consistent with a subtraction that works, and equally consistent
# with one that is completely broken. The classes it must remove do not exist
# in the tree, so they have to be built.
#
# THE FOURTH CASE IS THE NON-VACUITY ANCHOR, and it is not decoration: three
# assertions that things are ABSENT are all satisfied by a function that
# returns nothing at all. A tracked file must SURVIVE for the other three to
# mean anything.


def _bgit(root, *args):
    """Build-side git, with the user's config neutralised.

    The opposite choice from `_git`, and deliberate in both directions. This
    one CREATES repositories, so it must not inherit a signing key, a hook
    path or a default branch name from whoever runs the suite. `_git` only
    reads an existing repository, where neutralising the global config would
    discard the `safe.directory` allowances a normal checkout may depend on.
    """
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", *args],
        cwd=str(root),
        capture_output=True,
        check=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        },
    )


def _repo_carrying_every_class(root):
    """A repository holding one file of each class the walk can meet.

    Returned in the order: tracked, plain untracked, ignored, nested worktree.

    THE NESTED FILE IS A COPY OF THE TRACKED ONE, on purpose. That is the
    shape of the original failure rather than a convenient stand-in: a stale
    worktree holds a whole second copy of the tree, so every statement counted
    once in the shipped files is counted twice, and the count arms go red
    against text nobody touched.
    """
    (root / "skills").mkdir(parents=True)
    _bgit(root, "init")
    _bgit(root, "config", "user.email", "t@e")
    _bgit(root, "config", "user.name", "T")
    (root / "skills" / "tracked.md").write_text("shipped\n", encoding="utf-8")
    (root / ".gitignore").write_text(".worktrees/\nignored/\n", encoding="utf-8")
    _bgit(root, "add", "skills/tracked.md", ".gitignore")
    _bgit(root, "commit", "-m", "seed")

    (root / "skills" / "plain.md").write_text("untracked\n", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored" / "hidden.md").write_text("ignored\n", encoding="utf-8")
    _bgit(root, "worktree", "add", "--detach", ".worktrees/stale")

    return (
        "skills/tracked.md",
        "skills/plain.md",
        "ignored/hidden.md",
        ".worktrees/stale/skills/tracked.md",
    )


def test_subtraction_removes_every_class_of_untracked_entrant(tmp_path):
    """All three classes, not just the one the obvious spelling catches.

    DRIVEN THROUGH `_instruction_files`, so this asserts the POPULATION and
    not the helper behind it. Any rewrite of the subtraction has to satisfy
    these four facts, whatever mechanism it uses to reach them.
    """
    root = tmp_path / "plugin"
    tracked_rel, plain_rel, ignored_rel, nested_rel = _repo_carrying_every_class(root)
    population = {str(p.relative_to(root)) for p in _instruction_files(root)}

    assert tracked_rel in population, (
        f"the TRACKED file {tracked_rel!r} is not in the population. Without "
        f"this the three exclusion assertions below are satisfied by an empty "
        f"set, and this arm would certify a subtraction that removes "
        f"everything. Population was: {sorted(population)}"
    )
    for label, rel in (
        ("a plain untracked file", plain_rel),
        ("an IGNORED file", ignored_rel),
        ("a file inside a NESTED WORKTREE", nested_rel),
    ):
        assert rel not in population, (
            f"{label} reached the instruction population: {rel!r}. The "
            f"subtraction set must be the COMPLEMENT of tracked. If the "
            f"subtraction was rewritten to enumerate untracked files "
            f"positively with `git ls-files --others`, this is the failure: "
            f"that spelling omits ignored files under `--exclude-standard`, "
            f"and it never descends into a nested repository under any "
            f"spelling. Both classes are live in this project, whose "
            f"`.gitignore` carries an unanchored `.worktrees/`."
        )


def test_the_superset_oracle_excludes_untracked_entrants(tmp_path):
    """The filter self-check's SUPERSET carries the subtraction too.

    Deleting it there left the suite green on a clean tree, because a clean
    tree has no untracked text files for it to admit. The damage is not a red
    test: Half 1 of that self-check would report an exclusion rule as LIVE on
    the evidence of a file Half 2 can never see, so the two halves would
    measure two different populations and agree by accident.
    """
    root = tmp_path / "plugin"
    tracked_rel, plain_rel, ignored_rel, nested_rel = _repo_carrying_every_class(root)
    superset = {str(p.relative_to(root)) for p in _walked_text_files(root)}

    assert tracked_rel in superset, (
        f"the tracked file {tracked_rel!r} is missing from the superset, so "
        f"the three exclusions below are satisfied by an empty set. Superset "
        f"was: {sorted(superset)}"
    )
    for rel in (plain_rel, ignored_rel, nested_rel):
        assert rel not in superset, (
            f"{rel!r} reached the SUPERSET that the filter self-check measures "
            f"`kept` against. That check would then compare a git-filtered "
            f"population against an unfiltered superset, and its two halves "
            f"would be reasoning about different file sets."
        )


def test_the_directory_oracle_ignores_a_stale_untracked_dir(tmp_path):
    """The reach oracle carries the subtraction too, and this is the sharp one.

    Without it, a stale untracked directory holding ONE markdown file enters
    `expected`, can never enter `tops`, and the reach arm fails with the name
    of a directory git has never heard of. That is the original defect exactly
    — an unexplainable local red while `git status` reports clean — relocated
    from the population function into its oracle.
    """
    root = tmp_path / "plugin"
    _repo_carrying_every_class(root)
    stale = root / "stale_leftover"
    stale.mkdir()
    (stale / "left_behind.md").write_text("residue\n", encoding="utf-8")

    reached = _directories_holding_shipped_text(root)

    assert "skills" in reached, (
        f"the directory holding the tracked file is missing from the oracle, "
        f"so the assertion below is satisfied by an empty set. Oracle "
        f"returned: {sorted(reached)}"
    )
    assert "stale_leftover" not in reached, (
        f"a stale UNTRACKED directory reached the directory oracle: "
        f"{sorted(reached)}. The arm that consumes this subtracts `tops` — "
        f"built from the population, which excludes untracked files — from "
        f"this set, so the directory would show up as 'no longer reached' and "
        f"redden the suite against a tree nobody changed."
    )


def test_no_repository_means_the_subtraction_is_empty(tmp_path):
    """The hermetic-export branch, which CI otherwise never executes.

    Every run in this project happens inside a work tree, so the no-repository
    path would ship unexercised and would first be tried by a user. The walk
    must still answer, and answer with everything it finds.
    """
    export = tmp_path / "export" / "skills"
    export.mkdir(parents=True)
    (export / "shipped.md").write_text("shipped\n", encoding="utf-8")

    assert _tracked_relpaths(tmp_path / "export") is None, (
        "a directory in no repository did not return None, so the subtraction "
        "would filter an exported tree against some enclosing repository's "
        "index and could empty the population. None is what keeps this module "
        "working where there is no `.git`."
    )


def test_a_partially_tracked_tree_narrows_the_population_silently(tmp_path):
    """A RECORDED BOUND ON THE SUBTRACTION. RED here means it got better.

    A work tree where git answers successfully but tracks only SOME of the
    plugin means the population narrows with NO signal: the set is non-empty,
    so nothing raises, and every count arm still sees the single source.

    WHY THIS IS RECORDED RATHER THAN CLOSED, and it is a judgement rather than
    a shrug. The obvious control is an anchor — assert some known file is in
    the tracked set. That is a heuristic wearing a control's clothes here,
    because it witnesses only the files it names, and the failure it must
    catch is that some UNNAMED subset went untracked. Worse, the two cases are
    the SAME OBSERVATION: `walk minus tracked` is non-empty both when a file
    is legitimately untracked, which is the normal state this whole change
    exists to handle, and when the tree is partially covered. No predicate
    reads from here separates them.

    WHAT IS ALREADY COVERED, so the residual is not overstated. A tree that
    tracks NOTHING under the root raises, by the arm above. A tree that loses
    the single source drives every count arm to zero, which fails loudly. A
    tree that loses `agents/` or `skills/` entirely trips the named-pair floor
    in the reach arm. What is left uncovered is a partially-tracked tree that
    drops some OTHER instruction directory whole.

    IF THIS GOES RED, the subtraction learned to tell the two apart. Move the
    finding into an asserted control and delete this arm. Do not weaken it.
    """
    root = tmp_path / "plugin"
    _repo_carrying_every_class(root)
    (root / "commands").mkdir()
    (root / "commands" / "untracked_surface.md").write_text("x\n", encoding="utf-8")

    population = {str(p.relative_to(root)) for p in _instruction_files(root)}

    assert "commands/untracked_surface.md" not in population, (
        "the fixture no longer represents a partially-covered tree; this arm "
        "would then record a bound that does not exist."
    )
    assert "commands" not in _directories_holding_shipped_text(root), (
        "a whole instruction directory that git does not track is now VISIBLE "
        "to the reach oracle. THAT IS AN IMPROVEMENT, NOT A FAILURE. The "
        "subtraction can apparently distinguish a partially-tracked tree from "
        "an ordinary untracked file, which this module records as impossible "
        "from here. Convert the finding into a real control and delete this arm."
    )


def test_the_rejected_spelling_still_misses_two_of_the_three_classes(tmp_path):
    """A recorded bound on git, in the idiom of KNOWN_MISSES. RED = relaxed.

    This pins the MEASUREMENT that chose the complement form over the obvious
    one, so the reason cannot rot into prose that nobody re-derives. If git
    ever makes `--others --exclude-standard` cover ignored files or descend
    into nested repositories, this goes red and the constraint has relaxed —
    move the finding, do not weaken the production helper to match.
    """
    root = tmp_path / "plugin"
    _, plain_rel, ignored_rel, nested_rel = _repo_carrying_every_class(root)

    others = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert plain_rel in others, (
        f"the one class this spelling was ever able to see is missing from "
        f"{others}. The fixture is broken, not the finding."
    )
    for label, rel in (("the ignored", ignored_rel), ("the nested-worktree", nested_rel)):
        assert rel not in others, (
            f"`git ls-files --others --exclude-standard` now reports {label} "
            f"file {rel!r}. THAT IS AN IMPROVEMENT IN GIT, NOT A FAILURE HERE. "
            f"It removes one of the two reasons this module derives the "
            f"subtraction set by complement. Record the change; do not treat "
            f"this as licence to enumerate untracked files positively, since "
            f"the complement form is also what makes the population "
            f"independent of the user's global excludes file."
        )


@pytest.mark.parametrize(
    "axis,probe",
    _PROBE_CASES,
    ids=[f"{a}{i}" for a, ps in DETECTION_PROBES.items() for i in range(len(ps))],
)
def test_predicate_detects_every_canonical_spelling(axis, probe):
    """Narrow any constant and one of these stops matching."""
    assert _states_cap(probe, CAP_AXES[axis].pattern), (
        f"the predicate no longer recognises a canonical statement of the "
        f"ceiling: {probe!r}. Something in SUBJECT_TOKEN, the {axis} alphabet, "
        f"or _states_cap itself has narrowed, and a duplicate written this way "
        f"would now be invisible while the count arms report green.\n"
    )
    assert _names_subject(probe), (
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
        if _states_cap(text, spec.pattern)
    ]
    assert not hit, (
        f"{hit} now match text that does not state the index ceiling: {text!r}. "
        f"An alphabet widened to fix a missed spelling has readmitted unrelated "
        f"content; a bare numeral-plus-unit sweep matches 96 lines across the "
        f"shipped surfaces, and the subject taint is what excludes them. Narrow "
        f"the change, do not delete this case."
    )


@pytest.mark.parametrize(
    "axis,text",
    _MISS_CASES,
    ids=[f"miss-{a}{i}" for a, ts in KNOWN_MISSES.items() for i in range(len(ts))],
)
def test_known_miss_is_still_missed(axis, text):
    """A stated bound, asserted. RED here means the guard IMPROVED.

    This is the half DETECTION_PROBES structurally cannot carry: every probe
    there is asserted to be detected, so none of them can stand for a spelling
    the alphabet does not cover.
    """
    assert not _states_cap(text, CAP_AXES[axis].pattern), (
        f"the {axis} predicate now SEES a spelling this module records as a "
        f"known miss: {text!r}. That is an improvement, not a failure. Move "
        f"this entry into DETECTION_PROBES and delete it from KNOWN_MISSES, so "
        f"the recorded bound matches the guard that ships. Do not edit the "
        f"string to make this pass."
    )


@pytest.mark.parametrize(
    "text",
    KNOWN_OVER_BLOCKS,
    ids=[f"over{i}" for i in range(len(KNOWN_OVER_BLOCKS))],
)
def test_known_over_block_still_over_blocks(text):
    """The opposite bound, asserted. RED here also means the guard IMPROVED.

    These lines state a PER-ENTRY limit rather than the index ceiling, and the
    guard counts them as restatements. Until the predicate can tell the two
    apart, a shipped instruction file carrying one of them turns the count arms
    red against correct text.
    """
    hit = [
        axis for axis, spec in CAP_AXES.items() if _states_cap(text, spec.pattern)
    ]
    assert hit, (
        f"the predicate no longer flags {text!r}, which this module records as "
        f"CORRECT TEXT that the guard wrongly counts as a duplicate. THIS RED "
        f"MEANS THE GUARD BECAME MORE CORRECT, NOT LESS. That line carries the "
        f"index file and a numeral beside a unit WITHOUT restating the ceiling, "
        f"and until now it was counted as a second statement of the cap. DO NOT "
        f"REVERT THE PREDICATE CHANGE THAT CAUSED THIS: reverting restores a "
        f"false positive and turns the suite green again, so nothing would tell "
        f"you afterwards that you undid a real fix. Move this entry into "
        f"NON_DETECTIONS and delete it from KNOWN_OVER_BLOCKS. Do not edit the "
        f"string to make this pass."
    )


def test_a_declaration_suppresses_exactly_its_own_line():
    """The declared-exception machinery, driven by a SYNTHETIC table.

    DELIBERATELY NOT DRIVEN BY THE PRODUCTION TABLE, which is empty. An empty
    allowlist makes every assertion about it vacuously true, so the mechanism
    would ship unasserted and would first be exercised on the day someone
    depended on it. Passing the table as an argument is what makes that
    impossible.
    """
    line = "Each `MEMORY.md` entry should be one line, under 150 characters."
    table = (("agents/example.md", line),)

    assert _states_cap(line, CAP_AXES["size"].pattern), (
        "the fixture line no longer carries the shape, so this arm would pass "
        "vacuously; pick a line the predicate still flags."
    )
    assert _is_declared("agents/example.md", line, table), (
        "a declaration did not suppress its own line. DECLARED_NON_RESTATEMENTS "
        "is keyed on (path, exact stripped text) — check the key shape."
    )
    assert not _is_declared("agents/other.md", line, table), (
        "a declaration suppressed the same text at a DIFFERENT path. The key "
        "must include the path, or one judgement would exempt every copy."
    )
    assert not _is_declared("agents/example.md", line + " Plus more.", table), (
        "a declaration suppressed an EDITED line. The key must be the exact "
        "text, so that changing the line forces the judgement to be re-made."
    )


def test_every_declaration_is_live():
    """A declaration for a line that no longer exists is a rotting exemption.

    VACUOUS WHILE THE TABLE IS EMPTY, and that is stated rather than hidden.
    It arms itself the moment a first declaration is added, which is the moment
    it starts to matter.
    """
    for rel, text in DECLARED_NON_RESTATEMENTS:
        path = PLUGIN_ROOT / rel
        assert path.is_file(), (
            f"DECLARED_NON_RESTATEMENTS names {rel}, which does not exist. A "
            f"declaration outliving its file silently exempts any future line "
            f"with the same text. Delete the entry."
        )
        lines = [
            ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        ]
        assert text in lines, (
            f"DECLARED_NON_RESTATEMENTS declares a line that is no longer in "
            f"{rel}: {text!r}. Delete the entry — the judgement it carried was "
            f"about a line that has gone."
        )
        assert any(
            _states_cap(text, spec.pattern) for spec in CAP_AXES.values()
        ), (
            f"DECLARED_NON_RESTATEMENTS declares {text!r} in {rel}, but no arm "
            f"would flag that line anyway. The declaration is inert: delete it, "
            f"or the table will read as though the guard is noisier than it is."
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
