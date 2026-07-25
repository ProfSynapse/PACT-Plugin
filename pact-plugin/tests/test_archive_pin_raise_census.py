"""Structural guard on archive_pin's verdict-context invariant.

    EACH FIELD IS PRESENT IFF THE FACT IT NAMES WAS ACTUALLY ESTABLISHED.

      `claude_md_path`  the file this run read       -- established at resolution
      `heading`         which pin                    -- established at location
      `delete_string`   a USABLE handle for the Edit -- established once the
                        block is sliced AND non-empty AND verbatim in source

WHY THIS IS A TEST AND NOT A ONE-OFF SCRIPT. The contract it guards was
previously stated only in a docstring, and that docstring was FALSE THE DAY
IT WAS WRITTEN -- it described what the author intended rather than what the
code did, which is exactly why nothing caught it. A docstring backed by a
tested invariant is a different artifact from one backed by intent; shipping
the invariant with only a scratchpad script behind it would reproduce the
original defect inside its own fix.

WHY IT IS DERIVED RATHER THAN A LIST. Three violating sites were originally
found by exercising three triggers. A hand-list contains only what someone
already noticed, so it cannot produce a case that refutes its own framing --
and the derived walk did exactly that: it surfaced TWO further post-resolution
sites that LOOK like the defect and are correct, which is what made the
invariant load-bearing rather than merely tidier.

IT ALSO GUARDS TWO FUTURE-CODE HAZARDS a one-time census cannot:
  * `_run_memory_cli` raises bare; that is safe only because `_cli` is its
    sole caller and enriches. Nothing else enforces that.
  * `_cli` re-raises using `block` from the enclosing scope, so a call site
    added BEFORE the slice would raise NameError inside an exception handler
    -- losing ALL context, strictly worse than the bug this fixed.
Naming those is this file's job. CLOSING them is a separate decision and is
deliberately not done here.
"""

import ast
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parent.parent / "scripts" / "archive_pin.py"
)

INVARIANT = (
    "INVARIANT: each verdict field is present iff the fact it names was "
    "actually established.\n"
    "  claude_md_path -> the file this run read (established at resolution)\n"
    "  heading        -> which pin (established at location)\n"
    "  delete_string  -> a USABLE delete handle (established once the block "
    "is sliced AND non-empty AND verbatim in source)\n"
    "A post-resolution raise must therefore carry heading + claude_md_path, "
    "and must ALSO carry delete_string UNLESS it is one of the sites that "
    "proved the handle unusable (empty block, or the verbatim tripwire). "
    "Those two omit it CORRECTLY -- emitting a handle known to be bad is "
    "worse than emitting none, because the caller's only reason to trust it "
    "is that it was checked. Do NOT 'fix' them by adding the field."
)


@pytest.fixture(scope="module")
def tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lines():
    return SOURCE.read_text(encoding="utf-8").splitlines()


def _enclosing_function(node, tree):
    best = None
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
                if best is None or fn.lineno > best.lineno:
                    best = fn
    return best


def _block_binding_line(tree):
    """Line where `block` becomes bound inside archive_pin() -- the frontier
    that separates pre- from post-resolution raises."""
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "archive_pin"
    )
    at = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "block":
                    if at is None or n.lineno < at:
                        at = n.lineno
    return at


def _raises(tree):
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc
        if not (isinstance(call, ast.Call)
                and getattr(call.func, "id", "") == "_Unevaluable"):
            continue
        fn = _enclosing_function(node, tree)
        out.append((
            node.lineno,
            fn.name if fn else "<module>",
            {kw.arg for kw in call.keywords if kw.arg},
        ))
    return sorted(out)


def _handle_provably_unusable(lineno, lines):
    """True at the two sites that computed a block and proved it NOT a usable
    handle. Read from the raise's own reason text so the classification comes
    from the code rather than from a line-number list that would rot."""
    window = " ".join(lines[max(0, lineno - 2):lineno + 3])
    return ("is empty" in window) or ("not verbatim" in window)


class TestRaiseCensusIsLive:
    """Non-vacuity. Every assertion below iterates the census, so an empty or
    narrowed walk would make all of them pass over nothing -- the exact
    reports-success-while-measuring-nothing failure this file exists for."""

    def test_source_is_readable_and_parses(self, tree):
        assert tree is not None

    def test_census_finds_a_substantial_number_of_raises(self, tree):
        found = _raises(tree)
        assert len(found) >= 10, (
            f"the AST walk found only {len(found)} `raise _Unevaluable` "
            f"sites; the walk is narrowed or the exception was renamed, and "
            f"every assertion in this file would pass over nothing"
        )

    def test_the_resolution_frontier_is_locatable(self, tree):
        assert _block_binding_line(tree) is not None, (
            "`block` is no longer assigned in archive_pin(), so pre- vs "
            "post-resolution cannot be derived and this whole guard is inert"
        )

    def test_both_deliberate_omission_sites_are_still_present(self, tree, lines):
        """The two correct-looking exceptions must remain FINDABLE. If they
        vanish, the classifier below silently stops exercising its harder
        axis and this file quietly weakens."""
        post = _post_resolution(tree)
        unusable = [r for r in post if _handle_provably_unusable(r[0], lines)]
        assert len(unusable) == 2, (
            f"expected exactly 2 provably-unusable-handle sites, found "
            f"{len(unusable)}. If a site was removed, drop it here "
            f"deliberately; if one was ADDED, confirm it truly proves the "
            f"handle unusable rather than merely failing.\n\n{INVARIANT}"
        )


def _post_resolution(tree):
    """Raises that can only execute after the pin is located."""
    frontier = _block_binding_line(tree)
    out = []
    for lineno, fname, kwargs in _raises(tree):
        if fname == "archive_pin" and frontier and lineno > frontier:
            out.append((lineno, fname, kwargs))
        elif fname == "_cli":
            out.append((lineno, fname, kwargs))
    return out


class TestVerdictContextInvariant:
    """The invariant itself, over every raise site."""

    def test_every_post_resolution_raise_carries_the_established_facts(
        self, tree, lines
    ):
        offenders = []
        for lineno, fname, kwargs in _post_resolution(tree):
            required = {"heading", "claude_md_path"}
            if not _handle_provably_unusable(lineno, lines):
                required |= {"delete_string"}
            missing = required - kwargs
            if missing:
                offenders.append(
                    f"  {SOURCE.name}:{lineno} in {fname}() "
                    f"missing {sorted(missing)} (carries {sorted(kwargs)})"
                )
        assert not offenders, (
            "post-resolution UNEVALUABLE raise(s) drop context that WAS "
            "established:\n" + "\n".join(offenders) + "\n\n" + INVARIANT
            + "\n\nConsequence if shipped: the later a failure occurs the "
            "LESS the verdict reports, which is backwards -- and a CLI "
            "timeout or missing CLI is the canonical cannot-tell case, so "
            "the escape hatch would lose its delete boundary in exactly its "
            "own primary use case."
        )

    def test_pre_resolution_raises_are_not_required_to_carry_a_handle(
        self, tree
    ):
        """The other half of the invariant, and the reason it is an `iff`.
        A pre-resolution raise legitimately reports LESS -- the facts were
        not established. Asserting this keeps the guard from drifting into
        'every raise must carry everything', which would be false."""
        frontier = _block_binding_line(tree)
        pre = [
            (l, f, k) for l, f, k in _raises(tree)
            if f == "archive_pin" and frontier and l < frontier
        ]
        assert pre, "no pre-resolution raises found — classifier is degenerate"
        for lineno, fname, kwargs in pre:
            assert "delete_string" not in kwargs, (
                f"{SOURCE.name}:{lineno} carries delete_string before the "
                f"block exists.\n\n{INVARIANT}"
            )


class TestEnrichmentSeamHazards:
    """Two hazards a one-time census cannot catch, because they are future
    CODE CHANGES rather than current state. Naming them is the deliverable;
    closing them is a separate decision."""

    def test_run_memory_cli_is_only_reached_through_the_enricher(self, tree):
        """`_run_memory_cli` raises BARE -- correct, since it is a generic
        subprocess helper with no idea which pin is being archived. That is
        safe ONLY because `_cli` is its sole caller and enriches on the way
        out. A direct call added elsewhere would bypass the enrichment
        silently and reintroduce the exact defect."""
        callers = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "_run_memory_cli"):
                fn = _enclosing_function(node, tree)
                callers.append((node.lineno, fn.name if fn else "<module>"))
        assert callers, "no _run_memory_cli call sites found — walk is narrowed"
        bad = [c for c in callers if c[1] != "_cli"]
        assert not bad, (
            f"_run_memory_cli called outside the enriching wrapper at "
            f"{bad}. Those calls raise BARE, so a post-resolution failure "
            f"there would report no heading, no claude_md_path and no "
            f"delete_string.\n\n{INVARIANT}"
        )

    def test_every_enricher_call_site_is_after_the_block_is_bound(self, tree):
        """`_cli` re-raises using `block` from the enclosing scope. A call
        site added BEFORE the slice raises NameError inside an exception
        handler — surfacing as `internal error: NameError` with ALL context
        lost, which is strictly worse than the bug this guard exists for."""
        frontier = _block_binding_line(tree)
        sites = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "_cli"
        ]
        assert sites, "no _cli call sites found — walk is narrowed"
        early = [ln for ln in sites if frontier and ln < frontier]
        assert not early, (
            f"_cli called at line(s) {early}, before `block` is bound at "
            f"{frontier}. Its except-handler references `block`, so a failure "
            f"there raises NameError INSIDE the handler and the verdict loses "
            f"everything — worse than the defect this guards.\n\n{INVARIANT}"
        )
