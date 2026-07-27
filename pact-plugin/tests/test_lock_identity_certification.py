"""Certification of the lock-identity fix: the sidecar names what the write binds.

WHAT IS UNDER CERTIFICATION. `file_lock` keys its sidecar on

    target_file.parent.resolve() / f".{target_file.name}.lock"

in both twins (`hooks/shared/claude_md_manager.py`,
`skills/pact-memory/scripts/working_memory.py`). The PARENT is resolved so two
SPELLINGS of one directory produce one sidecar; the LEAF is deliberately NOT
resolved, because the write is `os.replace` — renameat(2) — which binds the
final component as a directory ENTRY without following it.

The superseded formula resolved the WHOLE target. Under a leaf symlink that
named a different directory than the write, and — because the write REPLACES
the leaf entry — the sidecar computed for one target path CHANGED ACROSS THE
WRITE. A mutual-exclusion primitive whose identity is a function of the state
it protects does not serialise that state. That is the defect closed here.

CERTIFICATION IS BIDIRECTIONAL. It is not enough to show the lock and write
agree; the property that IS real must be preserved:
  (a) lock and write cannot name different directories under a leaf symlink,
      and the sidecar is STABLE across the write;
  (b) two SPELLINGS of one directory still take ONE lock.

DELIBERATELY NOT CERTIFIED — two NAMES for one INODE (leaf symlink, hardlink)
do NOT collapse onto one sidecar, and no longer should. That property was
retired on purpose: a rename-based write destroys the alias relationship on
the first commit, so it protected a relationship that no longer exists. The
old formula never delivered it in general anyway — a hardlink pair is exactly
two names for one inode and never collapsed, because `resolve()` canonicalises
symlinks, not inodes. A test pinning it would certify a reversed decision.

--------------------------------------------------------------------------
TWO MEASURED FACTS ABOUT THE INSTRUMENTS, recorded because both invert the
intuitive choice and a later reader will otherwise "harden" them backwards.
--------------------------------------------------------------------------

1. PROVENANCE MUST USE `__module__`, NOT `inspect.getsourcefile()`.
   `file_lock` is `@contextmanager`-decorated, so what callers import is a
   wrapper. It would be natural to assume `__module__` reports the decorator
   and to reach for `getsourcefile()` as the more rigorous check. MEASURED,
   and it is the reverse:

     `__module__`            canonical 'shared.claude_md_manager'
                             skill     'working_memory'          -> DISCRIMINATES
     `inspect.getsourcefile` canonical contextlib.py
                             skill     contextlib.py             -> DOES NOT

   `functools.wraps` copies `__module__` through the decorator, so it is
   accurate. `getsourcefile()` resolves the wrapper's code object to
   contextlib.py for BOTH twins, while `_atomic_write_text` (undecorated)
   resolves to its real module — so a same-module guard built on it ABORTS on
   every LEGITIMATE pairing and "catches" the cross-module ones only by
   accident of that mismatch. It fails in both directions. Do not swap it in.

2. THE T-1 PARAGRAPH'S END ANCHOR IS NOT LOAD-BEARING. Including or excluding
   the trailing blank line yields the same sha256, because the extraction is
   rstripped. The START anchor and the token are what carry the extraction. A
   reader who later "tightens" the end anchor should know it was never doing
   work.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
import re
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
for _p in (
    _TESTS.parent / "hooks",
    _TESTS.parent / "skills" / "pact-memory" / "scripts",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PLUGIN_ROOT = _TESTS.parent
CANONICAL_REL = "hooks/shared/claude_md_manager.py"
TWIN_REL = "skills/pact-memory/scripts/working_memory.py"

# --- the T-1 CONTAINMENT precondition paragraph -----------------------------
# Reference values independently reproduced from BOTH twins at the commit that
# introduced the paragraph. The paragraph is a CONTRACT TERM: it states what
# the containment guard does and does not promise, and the write path is
# twinned, so the two copies must say the same thing.
T1_ANCHOR = "PRECONDITION."
T1_TOKEN = "IDENTITY, not POSITION"
T1_SHA256_PREFIX = "68e7297b2129978f"
T1_LENGTH = 672

# --- module provenance ------------------------------------------------------
CANONICAL_MODULE = "shared.claude_md_manager"
TWIN_MODULE = "working_memory"


def _load_twin(which: str):
    if which == "canonical":
        import shared.claude_md_manager as mod
        return mod, CANONICAL_MODULE
    import working_memory as mod
    return mod, TWIN_MODULE


_TWIN_PARAMS = ("canonical", "skill")


@pytest.fixture(params=_TWIN_PARAMS)
def twin(request):
    """One twin, plus the module name its functions must report.

    The twins are TWO INDEPENDENT LIVE DEFINITIONS -- `working_memory` defines
    its own `file_lock` and its own `_atomic_write_text` and cannot import from
    `claude_md_manager` at all (separate package). So a CROSS-MODULE pairing is
    silently constructible: take `file_lock` from one twin and
    `_atomic_write_text` from the other and you measure a combination
    production never runs.
    """
    mod, expected = _load_twin(request.param)
    return mod, expected


def assert_same_module(mod, expected_module: str) -> None:
    """L9 -- abort unless BOTH primitives come from the expected single module.

    ABORTS rather than warns, deliberately: a warning scrolls past in a
    12,000-test run and the green summary is what gets reported.

    Note what this bounds. The drift gates prove the two copies MATCH; this
    proves which one was MEASURED. Those are different claims, and only the
    second is at risk from a harness that imports across the twins.
    """
    fl_mod = mod.file_lock.__module__
    aw_mod = mod._atomic_write_text.__module__
    assert fl_mod == expected_module, (
        f"file_lock came from {fl_mod!r}, expected {expected_module!r} -- "
        f"this test is measuring a different twin than it names"
    )
    assert aw_mod == expected_module, (
        f"_atomic_write_text came from {aw_mod!r}, expected {expected_module!r}"
    )
    assert fl_mod == aw_mod, (
        f"CROSS-MODULE PAIRING: file_lock from {fl_mod!r} but "
        f"_atomic_write_text from {aw_mod!r} -- production never runs this "
        f"combination"
    )


def _extract_t1_paragraph(source: str) -> str:
    """Return the T-1 precondition paragraph, or "" if the anchor is absent.

    Anchored on the line beginning `PRECONDITION.` and terminated at the first
    blank line. Returns "" rather than raising, so the CALLER's non-emptiness
    assertion is what fails -- an extractor that raises would give a red test
    for a reason that reads like a broken test rather than a missing contract
    term.
    """
    lines = source.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if ln.strip().startswith(T1_ANCHOR)]
    if len(starts) != 1:
        return ""
    start = starts[0]
    end = start
    while end < len(lines) and lines[end].strip():
        end += 1
    return "".join(lines[start:end]).rstrip("\n")


def _atomic_write_docstring(rel: str) -> str:
    """Return `_atomic_write_text`'s docstring, via AST.

    WHY AST AND NOT A LINE SCAN. This region is the scope for the token
    assertion below, and a line-scan region would itself be an ANCHORED
    EXTRACTION -- i.e. a guard whose own failure mode is the one it exists to
    guard against. `ast` gets the docstring from the parser, so the region
    cannot drift out from under the assertion the way an anchor can.
    """
    tree = ast.parse(_read(rel))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_atomic_write_text":
            return ast.get_docstring(node, clean=False) or ""
    return ""


def _read(rel: str) -> str:
    return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")


# ===========================================================================
# L9 -- the provenance guard itself, proven able to fail
# ===========================================================================

class TestProvenanceGuardIsNotVacuous:
    """The L9 guard exists because a harness already made the cross-module
    mistake. A guard for that failure which cannot itself fail would be worse
    than no guard, because it would retire the concern."""

    def test_module_attribute_discriminates_the_twins(self):
        """The mechanism works. Recorded as a test rather than a comment so
        that a Python change making `__module__` non-discriminating (e.g. a
        decorator that stops using functools.wraps) fails HERE, loudly, rather
        than silently turning every provenance assertion into a tautology."""
        canonical, _ = _load_twin("canonical")
        skill, _ = _load_twin("skill")
        assert canonical.file_lock.__module__ == CANONICAL_MODULE
        assert skill.file_lock.__module__ == TWIN_MODULE
        assert canonical.file_lock.__module__ != skill.file_lock.__module__
        assert (
            canonical._atomic_write_text.__module__
            != skill._atomic_write_text.__module__
        )

    def test_guard_aborts_on_a_cross_module_pairing(self):
        """NEGATIVE CONTROL. Build the pairing production never runs and prove
        the guard rejects it. Without this, `assert_same_module` could be
        satisfied by any two functions from one import and would never fail."""
        canonical, _ = _load_twin("canonical")
        skill, _ = _load_twin("skill")

        class _Crossed:
            file_lock = staticmethod(canonical.file_lock)
            _atomic_write_text = staticmethod(skill._atomic_write_text)

        with pytest.raises(AssertionError):
            assert_same_module(_Crossed, CANONICAL_MODULE)

    def test_getsourcefile_is_not_a_usable_fallback(self):
        """Pins the measured fact in fact 1 of the module docstring, so the
        'more rigorous' swap fails instead of silently inverting the guard.

        `file_lock` is @contextmanager-wrapped, so its source file resolves to
        contextlib for BOTH twins while `_atomic_write_text` resolves to the
        real module. Any same-module check built on getsourcefile therefore
        rejects LEGITIMATE pairings.
        """
        canonical, _ = _load_twin("canonical")
        assert inspect.getsourcefile(canonical.file_lock).endswith("contextlib.py")
        assert inspect.getsourcefile(canonical._atomic_write_text).endswith(
            "claude_md_manager.py"
        )
        # The two disagree, which is why the naive same-file guard would abort
        # on a pairing that is in fact correct.
        assert inspect.getsourcefile(canonical.file_lock) != inspect.getsourcefile(
            canonical._atomic_write_text
        )

    def test_assert_same_module_accepts_each_real_twin(self, twin):
        """Positive control paired with the abort case above: the guard admits
        exactly the two pairings production actually runs."""
        mod, expected = twin
        assert_same_module(mod, expected)


# ===========================================================================
# The T-1 twin-parity gate -- the only enforcement that will exist
# ===========================================================================

class TestT1PreconditionParity:
    """The nine-line CONTAINMENT precondition must be byte-identical in both
    twins.

    WHY THIS GATE EXISTS. Both twin drift gates STRIP docstrings --
    `_extract_body` describes itself as "docstring-tolerant, logic-pinning" --
    so nothing mechanical catches divergence between the two copies of this
    paragraph. Before this gate the only check that had ever run was a one-off
    manual byte-compare. This replaces a person with a mechanism.

    NARROW BY DESIGN: this paragraph's parity ONLY, never full docstring
    equality. The existing gates' tolerance is deliberate -- the twins'
    docstrings legitimately differ, each pointing at the other -- and widening
    it as a side-effect of this gate would be a regression dressed as rigour.

    THE VACUITY HAZARD THIS CLASS IS BUILT AGAINST. An extractor anchored on
    something that later moves returns EMPTY from BOTH copies, and `"" == ""`
    passes green while measuring nothing -- which would leave the contract term
    exactly as unprotected as it was before, while LOOKING covered. That
    converts a known gap into an unknown one, which is worse than no gate. So
    emptiness, content, length, digest and uniqueness are all asserted, and the
    comparison is proven able to fail.
    """

    def test_paragraph_extracts_non_empty_from_both_twins(self):
        for rel in (CANONICAL_REL, TWIN_REL):
            para = _extract_t1_paragraph(_read(rel))
            assert para, f"T-1 paragraph extraction returned EMPTY from {rel}"

    def test_extraction_contains_the_distinctive_token(self):
        """Non-emptiness alone is satisfiable by the wrong span. The token must
        be in the EXTRACTION, not merely somewhere in the file."""
        for rel in (CANONICAL_REL, TWIN_REL):
            para = _extract_t1_paragraph(_read(rel))
            assert T1_TOKEN in para, (
                f"extraction from {rel} does not contain {T1_TOKEN!r} -- the "
                f"anchor selected the wrong span"
            )

    def test_anchor_and_token_are_unique_per_file(self):
        """Closes the NON-EMPTY FALSE POSITIVE.

        Non-empty and token-present are BOTH satisfiable by an extractor that
        selected the wrong span, if the anchor ever duplicates. A false
        positive terminates the search before a false negative can fire and
        hands you something that feels like success. Uniqueness is what closes
        it -- measured 1 and 1 at the time this gate was written, asserted
        rather than assumed to stay so.

        THE TWO ASSERTIONS HAVE DIFFERENT SCOPES ON PURPOSE. The TOKEN count is
        scoped to `_atomic_write_text`'s docstring; the ANCHOR count is
        WHOLE-FILE. That is not an oversight and must not be "tidied" into
        symmetry.

        The anchor assertion mirrors an invariant the EXTRACTOR genuinely has:
        `_extract_t1_paragraph` searches the WHOLE FILE and returns "" unless it
        finds exactly one anchor. An assertion mirroring an extractor invariant
        must carry the EXTRACTOR's scope, not the region's -- scope it to the
        docstring while the extractor stays whole-file and you get a silent
        disagreement, where a second anchor elsewhere makes the extractor return
        "" (reddening the non-empty test) while this assertion reports fine.

        COUPLING, because it is invisible from either side alone: IF ANYONE EVER
        SCOPES THE EXTRACTOR'S SEARCH, THE ANCHOR ASSERTION MUST MOVE WITH IT.
        """
        for rel in (CANONICAL_REL, TWIN_REL):
            src = _read(rel)
            anchors = [
                ln for ln in src.splitlines() if ln.strip().startswith(T1_ANCHOR)
            ]
            assert len(anchors) == 1, (
                f"{rel} has {len(anchors)} {T1_ANCHOR!r} anchors; the extractor "
                f"can no longer identify the paragraph unambiguously"
            )
            # SCOPED TO THE DOCSTRING, DELIBERATELY ASYMMETRIC WITH THE
            # ANCHOR ASSERTION ABOVE -- see the coupling note in this test's
            # docstring. Whole-file counting made a legitimate CROSS-REFERENCE
            # elsewhere in the module (`# See the "IDENTITY, not POSITION"
            # precondition ...`) redden this gate while the paragraph was
            # byte-identical and the digest matched: a false alarm on exactly
            # the kind of cross-reference this codebase models as good practice.
            doc = _atomic_write_docstring(rel)
            assert doc, f"{rel}: _atomic_write_text docstring not found"
            assert doc.count(T1_TOKEN) == 1, (
                f"{rel} has {doc.count(T1_TOKEN)} occurrences of the token IN "
                f"THE DOCSTRING; it is no longer distinctive enough to validate "
                f"the extraction"
            )

    def test_paragraph_matches_the_reference_digest_and_length(self):
        """Pins the CONTENT, not just parity. Two copies could match each other
        while both having drifted from the accepted wording.

        THIS ASSERTION IS THE LOAD-BEARING WRONG-SPAN EXCLUSION. DO NOT DELETE
        IT AS DUPLICATIVE OF THE TOKEN CHECK -- that is the exact simplification
        an adversarial review measured to be wrong. Of five adversarial
        docstrings crafted to impersonate this paragraph, FOUR satisfied all
        three of the cheap guards (non-emptiness, distinctive token, anchor
        uniqueness). Only the digest and length excluded them. The cheap guards
        look like the substantive checks and are the weaker ones.

        WHAT THE CHEAP GUARDS BUY, since they are not redundant either: the
        digest is SELF-CERTIFYING AT THE MOMENT IT IS RE-BASELINED. When the
        paragraph is legitimately reworded someone updates the reference to
        whatever the extractor returned -- and at that instant the digest
        cannot detect a broken extractor; it gets pinned TO the wrong span and
        confirms it forever after. The token and anchor checks are independent
        of the reference value and are the only guards still standing during a
        re-pin. So: the digest catches drift, the cheap guards protect the
        update. Removing either leaves a window.
        """
        for rel in (CANONICAL_REL, TWIN_REL):
            para = _extract_t1_paragraph(_read(rel))
            digest = hashlib.sha256(para.encode("utf-8")).hexdigest()
            assert len(para) == T1_LENGTH, f"{rel}: length {len(para)}"
            assert digest.startswith(T1_SHA256_PREFIX), f"{rel}: sha256 {digest[:16]}"

    def test_paragraph_is_byte_identical_across_the_twins(self):
        canonical = _extract_t1_paragraph(_read(CANONICAL_REL))
        twin = _extract_t1_paragraph(_read(TWIN_REL))
        assert canonical and twin, "guarded by the non-empty test above"
        assert canonical == twin, (
            "T-1 CONTAINMENT precondition has DIVERGED between the twins. It is "
            "a contract term on a twinned write path; both copies must state "
            "the same promise. Update both in the SAME commit."
        )

    def test_comparison_reddens_when_one_copy_is_mutated(self):
        """NON-VACUITY, by mutation rather than by argument.

        Proves the equality assertion above can actually fail. Mutation is
        IN-MEMORY -- the file on disk is never touched -- so this cannot leave
        the tree dirty if it fails midway.
        """
        canonical = _extract_t1_paragraph(_read(CANONICAL_REL))
        mutated = canonical.replace(T1_TOKEN, "POSITION, not IDENTITY", 1)
        assert mutated != canonical, "the mutation did not change anything"
        twin = _extract_t1_paragraph(_read(TWIN_REL))
        assert mutated != twin, (
            "a mutated paragraph still compares equal to the twin -- the "
            "equality assertion cannot detect divergence"
        )

    def test_extractor_returns_empty_when_the_anchor_moves(self):
        """The specific vacuity mode, proven detectable.

        If the anchor is reworded the extractor returns "" -- and the
        non-emptiness test above is what turns that into a RED. This asserts
        the extractor really does collapse to "" rather than silently returning
        a neighbouring paragraph, which would be the non-empty false positive.
        """
        src = _read(CANONICAL_REL)
        without_anchor = src.replace(T1_ANCHOR, "REWORDED.", 1)
        assert _extract_t1_paragraph(without_anchor) == "", (
            "extractor returned a non-empty span after the anchor was removed "
            "-- it is selecting something other than the intended paragraph"
        )


# ===========================================================================
# L7 -- the existing drift gates must pass unmodified
# ===========================================================================

class TestExistingDriftGatesUnmodified:
    """L7 proves the copies match. It does NOT prove either copy was measured
    -- that is L9's job, and conflating them is how a suite certifies a
    function it never called."""

    @pytest.mark.parametrize(
        "gate",
        [
            "TestFileLockTwinCopyDrift",
            "test_lock_timeout_constants_match",
            "TestAtomicWriteTwinCopyDrift",
        ],
    )
    def test_named_drift_gate_still_exists_in_test_staleness(self, gate):
        """Pins that the three gates the design relies on are still present and
        named as the design names them. If one is renamed or removed, the
        parity argument this suite leans on has quietly lost a leg."""
        src = (_TESTS / "test_staleness.py").read_text(encoding="utf-8")
        assert re.search(rf"\b{re.escape(gate)}\b", src), (
            f"{gate} is no longer present in test_staleness.py -- the "
            f"twin-parity argument depends on it"
        )


# ===========================================================================
# Behavioural core -- L1/L2/L3/L4
#
# L8 IS NOT CERTIFIED BY A TEST IN THIS FILE, AND THAT IS A DELIBERATE
# ABSTENTION RATHER THAN AN OVERSIGHT. It is recorded here because every other
# obligation is traceable to a docstring, and an obligation named in a banner
# but claimed by nothing reads as a gap.
#
# L8 asks that the failure-log site is unchanged in behaviour. It is covered BY
# INHERITANCE: that site carries its OWN leaf `is_symlink()` guard inside the
# lock and pre-creates its parent before taking it, so on the only topology
# where the two formulas differ -- a symlinked leaf -- the write is refused
# under BOTH, and the site can create no directory either way. Its existing
# tests pass untouched.
#
# STATE THE STRENGTH HONESTLY: that is weaker than L1-L4, which are certified
# directly here. Inheritance is an argument that the site cannot be affected,
# not a measurement that it was not. If the failure-log site ever loses its own
# leaf guard or stops pre-creating its parent, this obligation silently becomes
# uncovered and nothing in this file will notice.
#
# DERIVATION, and it is named here so a reader can tell it from the scratch
# harness used during the fix: the sidecar is taken from the path PRODUCTION
# ACTUALLY OPENS, never recomputed in the test. Recomputation is the trap --
# a test that re-implements the formula compares its own arithmetic to itself
# and agrees on every topology regardless of what production does.
#
# SELECTION KEYS ON WHICH CALL, NEVER ON PATH SHAPE. Filtering for `.lock` or
# a leading dot would reinstate the very naming assumption this exercise
# removes, so `file_lock`'s single open is taken positionally and the count is
# asserted rather than searched.
#
# THE PATCH WINDOW IS GLOBAL AND THEREFORE NARROW. `import os` binds one
# module object process-wide -- there is no per-module `os` to instrument, so
# routing the patch "through" a twin is not possible and not required. What
# selects the twin is WHICH `file_lock` is invoked inside the window; the L9
# provenance assert is what attributes the observation. Patch, call, restore
# in a `finally`, so unrelated opens cannot land in the record.
# ===========================================================================

class _OpenRecorder:
    """Records every `os.open` in a narrow window, with `fstat` AT OPEN TIME.

    fstat must happen while the fd is open -- `_atomic_write_text` closes its
    descriptors before returning, so a later stat would fail or, worse,
    silently describe a different object.
    """

    def __init__(self):
        self.calls = []

    def __enter__(self):
        import os as _os
        self._os = _os
        self._real = _os.open

        def spy(path, flags, mode=0o777, *, dir_fd=None, **kw):
            if dir_fd is None:
                fd = self._real(path, flags, mode, **kw)
            else:
                fd = self._real(path, flags, mode, dir_fd=dir_fd, **kw)
            try:
                st = _os.fstat(fd)
                ident = (st.st_dev, st.st_ino)
            except OSError:  # pragma: no cover - defensive
                ident = None
            self.calls.append({
                "path": str(path),
                "is_dir_open": bool(flags & _os.O_DIRECTORY),
                "top_level": dir_fd is None,
                "ident": ident,
            })
            return fd

        _os.open = spy
        return self

    def __exit__(self, *exc):
        self._os.open = self._real
        return False


def derive_sidecar_from_production(mod, target):
    """Return the sidecar path PRODUCTION opened. Never recomputed.

    Asserts exactly one open and RAISES otherwise -- no fallback and no
    guessing which open is the sidecar. If `file_lock` ever opens more than
    one file, this must go red rather than silently pick.
    """
    rec = _OpenRecorder()
    with rec:
        with mod.file_lock(target):
            pass
    opens = rec.calls
    assert len(opens) == 1, (
        f"file_lock performed {len(opens)} os.open calls, expected exactly 1; "
        f"the single-open premise this derivation rests on has changed: "
        f"{[o['path'] for o in opens]}"
    )
    return Path(opens[0]["path"])


def derive_write_parent_ident(mod, target, content, root):
    """Return (st_dev, st_ino) of the directory the WRITE binds into.

    STRUCTURAL discriminator, deliberately not positional: the parent open is
    the unique call that is both O_DIRECTORY and top-level (`dir_fd is None`).
    The ancestry walk's opens all pass `dir_fd`, and the temp-file open is not
    O_DIRECTORY. Selecting "the first O_DIRECTORY open" would also work today
    but depends on call ORDER; this depends on call SHAPE and so survives a
    reordering of the walk.

    Returns None when the parent could not be opened at all (dangling parent),
    which is a real outcome and must not be faked.
    """
    rec = _OpenRecorder()
    with rec:
        try:
            mod._atomic_write_text(target, content, root)
        except Exception:
            pass  # refusal/failure is a legitimate outcome for some topologies
    parents = [c for c in rec.calls if c["is_dir_open"] and c["top_level"]]
    if not parents:
        return None
    assert len(parents) == 1, (
        f"expected exactly one top-level O_DIRECTORY open (the write's "
        f"parent); found {len(parents)}: {[p['path'] for p in parents]}"
    )
    return parents[0]["ident"]


def _dir_ident(path: Path):
    import os as _os
    st = _os.stat(str(path))
    return (st.st_dev, st.st_ino)


def _dirs(root: Path):
    return {p for p in root.rglob("*") if p.is_dir()}


def _topology(kind, root: Path):
    """Build one of the six named topologies. Returns (project, target)."""
    import os as _os
    proj = root / "proj"
    outside = root / "outside"
    proj.mkdir()
    if kind == "plain":
        (proj / ".claude").mkdir()
        return proj, proj / ".claude" / "CLAUDE.md"
    if kind == "leaf-out-existing":
        outside.mkdir()
        (outside / "victim.md").write_text("VICTIM\n", encoding="utf-8")
        (proj / ".claude").mkdir()
        tgt = proj / ".claude" / "CLAUDE.md"
        _os.symlink(str(outside / "victim.md"), str(tgt))
        return proj, tgt
    if kind == "leaf-out-dangling":
        (proj / ".claude").mkdir()
        tgt = proj / ".claude" / "CLAUDE.md"
        _os.symlink(str(root / "gone" / "deep" / "victim.md"), str(tgt))
        return proj, tgt
    if kind == "parent-out-existing":
        outside.mkdir()
        _os.symlink(str(outside), str(proj / ".claude"), target_is_directory=True)
        return proj, proj / ".claude" / "CLAUDE.md"
    if kind == "parent-out-dangling":
        _os.symlink(str(root / "nodir"), str(proj / ".claude"),
                    target_is_directory=True)
        return proj, proj / ".claude" / "CLAUDE.md"
    if kind == "two-leg":
        outside.mkdir()
        (proj / "real.md").write_text("IN-PROJECT\n", encoding="utf-8")
        _os.symlink(str(outside), str(proj / ".claude"), target_is_directory=True)
        _os.symlink(str(proj / "real.md"), str(outside / "CLAUDE.md"))
        return proj, proj / ".claude" / "CLAUDE.md"
    raise AssertionError(f"unknown topology {kind}")



def _assert_points_outside(link: Path, proj: Path, label: str) -> None:
    """Assert a symlink's DESTINATION is outside the project.

    SYMLINK-NESS IS NOT OUT-NESS, and the difference is load-bearing. A
    precondition that checks only "is a symlink, is dangling" is satisfied by a
    degraded fixture pointing IN-PROJECT at a path whose parent exists -- under
    which the superseded formula creates ZERO directories, so the L3 DoS
    regression test PASSES and can no longer fail for the reason it exists.

    That is the failure `assert_topology_constructed` was written to prevent,
    one level deeper: the guard against fixture rot was itself under-specified.

    Uses `os.readlink` rather than `resolve()` because these destinations are
    frequently DANGLING, and `resolve()` on a dangling link would not tell us
    where it was aiming. The destination is made absolute against the link's own
    directory so a relative symlink is judged by where it actually points.

    DO NOT lean on production to reject a degraded fixture on the suite's
    behalf: `file_lock` calls `mkdir(parents=True)` and will happily create a
    missing `.claude` itself, so a degraded `plain` case is masked by PRODUCTION
    rather than caught by the test.
    """
    dest = Path(os.readlink(str(link)))
    if not dest.is_absolute():
        dest = (link.parent / dest)
    proj_resolved = proj.resolve()
    # `os.path.realpath` and NOT `normpath`: the destination is frequently
    # DANGLING, but its existing ANCESTORS still need resolving or the two
    # sides of the comparison are spelled differently and it silently never
    # matches. On macOS a tmp path is /var/... while proj.resolve() yields
    # /private/var/..., so a normpath-only comparison accepts an in-project
    # destination -- MEASURED: it did, and the degraded fixture sailed through.
    # realpath is non-strict: it resolves the existing prefix and leaves the
    # absent tail lexical, which is exactly what a dangling link needs.
    dest_norm = Path(os.path.realpath(str(dest)))
    assert not (
        dest_norm == proj_resolved or proj_resolved in dest_norm.parents
    ), (
        f"{label}: symlink points IN-PROJECT ({dest_norm}) -- the topology is "
        f"degenerate and the test would pass for the wrong reason"
    )


def assert_topology_constructed(kind, proj: Path, target: Path) -> None:
    """FIXTURE PRECONDITION -- fail if the defective topology was not built.

    THIS IS A DIFFERENT GUARD FROM A CODE MUTATION, and a suite can pass one
    while being wide open on the other:

        mutate the CODE     -> does the assertion catch a broken fix?
                               -> REGRESSION cover
        degrade the FIXTURE -> does the assertion catch a test that has
                               stopped testing? -> NON-VACUITY cover

    The exposure here is specific and permanent. If a setup silently stops
    building its symlink, the topology becomes benign and "the sidecar does
    not flip across the write" is TRUE FOR THE WRONG REASON -- forever, with
    no code change to blame and nothing ever failing to prompt an
    investigation. MEASURED before this guard existed: the stability test
    passed on a degenerate plain-file fixture, having never read the topology
    at all.

    The measurement lane got this property by ACCIDENT -- it compared against
    an unfixed base tree, which is a fixture guaranteed to still exhibit the
    defect, so a degenerate setup showed up as the base going quiet. A
    shipping suite has no second tree, so it has to buy the property
    deliberately. This is that purchase.
    """
    claude_dir = proj / ".claude"
    if kind == "plain":
        assert not claude_dir.is_symlink(), "plain: .claude should be a real dir"
        assert claude_dir.is_dir(), "plain: .claude should already EXIST as a dir"
        assert not target.is_symlink(), "plain: leaf should be a real file path"
        return
    if kind == "leaf-out-existing":
        assert target.is_symlink(), "leaf-out-existing: leaf is NOT a symlink"
        dest = Path(os.readlink(str(target)))
        assert dest.exists(), "leaf-out-existing: destination should exist"
        assert proj.resolve() not in dest.resolve().parents, (
            "leaf-out-existing: leaf does not point OUTSIDE the project"
        )
        return
    if kind == "leaf-out-dangling":
        assert target.is_symlink(), "leaf-out-dangling: leaf is NOT a symlink"
        assert not target.exists(), "leaf-out-dangling: destination should be absent"
        _assert_points_outside(target, proj, "leaf-out-dangling")
        return
    if kind == "parent-out-existing":
        assert claude_dir.is_symlink(), "parent-out-existing: .claude is NOT a symlink"
        assert claude_dir.exists(), "parent-out-existing: destination should exist"
        _assert_points_outside(claude_dir, proj, "parent-out-existing")
        return
    if kind == "parent-out-dangling":
        assert claude_dir.is_symlink(), "parent-out-dangling: .claude is NOT a symlink"
        assert not claude_dir.exists(), "parent-out-dangling: should be dangling"
        _assert_points_outside(claude_dir, proj, "parent-out-dangling")
        return
    if kind == "two-leg":
        assert claude_dir.is_symlink(), "two-leg: .claude (leg 1) is NOT a symlink"
        _assert_points_outside(claude_dir, proj, "two-leg leg 1")
        outside_entry = Path(os.readlink(str(claude_dir))) / "CLAUDE.md"
        assert outside_entry.is_symlink(), "two-leg: leg 2 is NOT a symlink"
        assert outside_entry.resolve() == (proj / "real.md").resolve(), (
            "two-leg: leg 2 does not point back INTO the project"
        )
        return
    raise AssertionError(f"unknown topology {kind}")


SIX_TOPOLOGIES = [
    "plain", "leaf-out-existing", "leaf-out-dangling",
    "parent-out-existing", "parent-out-dangling", "two-leg",
]


class TestSidecarAgreesWithTheWrite:
    """L1/L2 -- the sidecar names the directory the write binds into."""

    @pytest.mark.parametrize("kind", SIX_TOPOLOGIES)
    def test_sidecar_directory_is_the_directory_the_write_binds(
        self, tmp_path, twin, kind
    ):
        """L1. Compared by (st_dev, st_ino), NEVER by string equality -- string
        equality would also hide a userspace-vs-kernel resolution disagreement,
        which is the class of defect this whole arc is about."""
        mod, expected_module = twin
        assert_same_module(mod, expected_module)

        proj, target = _topology(kind, tmp_path)
        assert_topology_constructed(kind, proj, target)
        sidecar = derive_sidecar_from_production(mod, target)
        write_ident = derive_write_parent_ident(mod, target, "PAYLOAD\n", proj)

        if write_ident is None:
            # Dangling parent: the write cannot open a parent at all, so there
            # is no identity to agree with. Assert that rather than fabricate
            # agreement -- and assert the sidecar's directory is likewise
            # absent, which is the honest form of "they agree".
            assert kind == "parent-out-dangling", (
                f"{kind}: the write established no parent, which was only "
                f"expected on the dangling-parent row"
            )
            return
        assert _dir_ident(sidecar.parent) == write_ident, (
            f"{kind}: sidecar directory {sidecar.parent} does not name the "
            f"same kernel object as the directory the write binds into"
        )

    def test_sidecar_is_stable_across_the_write(self, tmp_path, twin):
        """L2. Under the superseded formula this flipped across the write,
        because the sidecar was a function of the leaf and the write replaces
        the leaf entry."""
        mod, expected_module = twin
        assert_same_module(mod, expected_module)

        proj, target = _topology("leaf-out-existing", tmp_path)
        assert_topology_constructed("leaf-out-existing", proj, target)
        before = derive_sidecar_from_production(mod, target)
        mod._atomic_write_text(target, "PAYLOAD\n", proj)
        # The write must have COMPLETED -- otherwise "unchanged" is trivially
        # true and this test measures nothing (the sidecar cannot move if
        # nothing happened).
        assert not target.is_symlink(), "write did not complete: leaf still a symlink"
        assert target.read_text(encoding="utf-8") == "PAYLOAD\n"
        after = derive_sidecar_from_production(mod, target)
        assert before == after, (
            f"sidecar MOVED across the write: {before} -> {after}. Lock "
            f"identity is a function of the state it protects."
        )

    def test_two_spellings_of_one_directory_take_one_lock(self, tmp_path, twin):
        """The property that IS real, and must be preserved (direction b)."""
        import os as _os
        mod, expected_module = twin
        assert_same_module(mod, expected_module)

        real = tmp_path / "real"
        (real / ".claude").mkdir(parents=True)
        alias = tmp_path / "alias"
        _os.symlink(str(real), str(alias), target_is_directory=True)

        # READ THIS BEFORE ADDING CASE OR UNICODE VARIANTS TO THIS TEST.
        #
        # The property is MUTUAL EXCLUSION. It is verified here by PATH-STRING
        # EQUALITY, which is a STRICTER PROXY than the property -- sound only
        # for the case built above, where `resolve()` collapses a directory
        # symlink alias to one string.
        #
        # It does NOT generalise. A case-variant (`Proj` vs `proj`) and an
        # NFC/NFD pair are the SAME kernel object reached by DIFFERENT strings,
        # so the two derived sidecar paths differ while `samefile` is True and
        # `flock` serialises on the inode regardless -- mutual exclusion is
        # fully intact and this assertion would nonetheless FAIL.
        #
        # So widening this test with those rows produces a RED THAT IS THE
        # INSTRUMENT'S FAULT, and the natural repair -- deleting the rows you
        # just added -- discards correct coverage to silence a wrong check. To
        # cover them, assert `samefile` on the two sidecars, or actual `flock`
        # exclusion (hold via one spelling, attempt via the other). NOT path
        # equality.
        #
        # THE PRECEDENT THAT WILL TEMPT YOU IS ONE FILE AWAY:
        # test_containment_certification.py has case-variant and NFD-variant
        # tests for the neighbouring containment property, where they are
        # correct. Copying that pattern here without changing the assertion is
        # the specific mistake this comment exists to prevent.
        via_real = derive_sidecar_from_production(mod, real / ".claude" / "CLAUDE.md")
        via_alias = derive_sidecar_from_production(mod, alias / ".claude" / "CLAUDE.md")
        assert via_real == via_alias, (
            "two SPELLINGS of one directory produced different sidecars"
        )

    def test_two_names_for_one_inode_do_NOT_collapse(self, tmp_path, twin):
        """RETIRED PROPERTY, pinned as retired rather than left ambiguous.

        A hardlink pair is two names for one inode. They deliberately do NOT
        share a sidecar: a rename-based write destroys the alias relationship
        on the first commit, so collapsing them would protect a relationship
        that no longer exists. The superseded formula did not deliver this
        either -- resolve() canonicalises symlinks, not inodes.

        Do NOT "fix" this into an equality assertion. Doing so would re-certify
        a decision that was reversed on purpose.
        """
        import os as _os
        mod, expected_module = twin
        assert_same_module(mod, expected_module)

        d = tmp_path / "proj" / ".claude"
        d.mkdir(parents=True)
        a = d / "CLAUDE.md"
        a.write_text("x\n", encoding="utf-8")
        b = d / "ALIAS.md"
        _os.link(str(a), str(b))
        assert a.stat().st_ino == b.stat().st_ino, "fixture is not a hardlink pair"

        assert derive_sidecar_from_production(mod, a) != \
            derive_sidecar_from_production(mod, b)


class TestDirectoryCreationCeiling:
    """L3/L4 -- the DoS-relevant axis. Every 'creates nothing' assertion is
    paired with a positive control in the SAME harness, because an empty
    created-set is equally produced by a harness that never ran."""

    def test_positive_control_dangling_parent_DOES_create_directories(
        self, tmp_path, twin
    ):
        """The control. If this does not create directories, the snapshot
        machinery is not observing creation and every zero below is worthless.
        This row creates dirs under BOTH schemes -- it is untouched by the fix
        and belongs to a separately-tracked residual."""
        mod, expected_module = twin
        assert_same_module(mod, expected_module)
        proj, target = _topology("parent-out-dangling", tmp_path)
        assert_topology_constructed("parent-out-dangling", proj, target)
        before = _dirs(tmp_path)
        try:
            with mod.file_lock(target):
                pass
        except OSError:
            pass
        assert _dirs(tmp_path) - before, (
            "the dangling-PARENT control created NO directories -- the "
            "snapshot cannot observe creation, so the zero-assertions below "
            "would prove nothing"
        )

    def test_dangling_leaf_creates_zero_directories(self, tmp_path, twin):
        """L3 -- the directory-creation DoS vector the fix CLOSES. Under the
        superseded formula this created the whole dangling chain as real
        directories at an attacker-chosen path."""
        mod, expected_module = twin
        assert_same_module(mod, expected_module)
        proj, target = _topology("leaf-out-dangling", tmp_path)
        assert_topology_constructed("leaf-out-dangling", proj, target)
        before = _dirs(tmp_path)
        with mod.file_lock(target):
            pass
        assert _dirs(tmp_path) - before == set(), (
            f"dangling-leaf topology created directories: "
            f"{_dirs(tmp_path) - before}"
        )

    def test_two_leg_sidecar_is_byte_zero_and_creates_no_directory(
        self, tmp_path, twin
    ):
        """L4 -- pins the ACCEPTED residual at its measured size, so a future
        change that widens it fails here."""
        mod, expected_module = twin
        assert_same_module(mod, expected_module)
        proj, target = _topology("two-leg", tmp_path)
        assert_topology_constructed("two-leg", proj, target)
        before = _dirs(tmp_path)
        sidecar = derive_sidecar_from_production(mod, target)
        assert _dirs(tmp_path) - before == set(), "two-leg created a directory"
        assert sidecar.stat().st_size == 0, (
            f"two-leg sidecar is {sidecar.stat().st_size} bytes, expected 0"
        )
