"""
Location: pact-plugin/tests/test_merge_guard_why_oracle.py
Summary: Covers the merged-history loaders' failure diagnostic. Each cert module
         below loads a baked baseline with `git show` and records WHY a load
         failed into a module-level `_WHY` map; that text is the entire content
         of the skip reason its differential rows then emit. THE DIAGNOSTIC IS
         INERT ON A DEVELOPER MACHINE, where the baked bases are still reachable
         as unreferenced objects, so every row runs and nothing ever populates
         `_WHY`. CI is its only exercise, and a skip reason is read only when
         something has already gone wrong -- which is exactly when a degraded
         one costs the most. Routing the loader's stderr away from the caller
         (`stderr=subprocess.PIPE` back to `subprocess.DEVNULL`) leaves every
         reason a bare label with no cause, and without this arm nothing reddens.
         This module drives the failure directly instead of waiting for it.
Used by: pytest suite.
"""

import importlib
from pathlib import Path

import pytest

# Loader names seen so far. A module defining `_WHY` whose loader is not one of
# these fails loudly below rather than being skipped -- a silent skip is the
# defect this whole module exists to remove, so it must not reappear here.
_KNOWN_LOADERS = ("_load_classifier", "_load_module_at")


def _loader_modules():
    """(module, loader) for each module matching the glob that defines `_WHY`.

    THE BOUND IS PART OF THE CLAIM: this ranges over `test_merge_guard_*.py` in
    this directory, not over the tree. A module defining `_WHY` under any other
    name is outside it and would go uncovered -- so the glob is widened, or this
    sentence is corrected, if that ever happens.

    Import errors are deliberately NOT caught. An unimportable module and one
    without `_WHY` are indistinguishable at `hasattr`, so swallowing them would
    under-count silently -- the same blindness as the handwritten list this
    replaces, arriving through the instrument instead of the code.
    """
    for path in sorted(Path(__file__).parent.glob("test_merge_guard_*.py")):
        module = importlib.import_module(path.stem)
        if not hasattr(module, "_WHY"):
            continue
        names = [name for name in _KNOWN_LOADERS if hasattr(module, name)]
        assert len(names) == 1, (
            f"{path.stem} defines `_WHY` but exposes "
            f"{names or 'no'} known loader. Add its loader to _KNOWN_LOADERS: "
            f"a module whose loader cannot be found here would otherwise be "
            f"dropped from the parametrization without a word."
        )
        yield path.stem, names[0]


_LOADERS = list(_loader_modules())

assert _LOADERS, (
    "no module matching test_merge_guard_*.py defines `_WHY`. The derivation "
    "found nothing, so the parametrization below is empty and this oracle "
    "would pass while covering no diagnostic at all."
)

# Well-formed hex that no repository resolves. `git show` echoes the name back
# in its own error, which is what makes it a usable witness below.
_UNRESOLVABLE = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize("module_name,loader_name", _LOADERS)
def test_a_failed_baked_base_load_records_gits_own_reason(module_name, loader_name):
    """A load that fails must record the CAUSE, not just that it failed.

    Asserting the recorded text contains the object name we asked for is the
    discriminating check: that substring can only have arrived from git's
    stderr. A reason that merely says a load failed -- which is what the
    diagnostic degrades to when stderr stops reaching the caller -- names
    nothing, and the differential rows it guards skip with no way to tell an
    unreachable commit from an unrunnable git.
    """
    module = importlib.import_module(module_name)
    loader = getattr(module, loader_name)

    module._WHY.pop(_UNRESOLVABLE, None)
    try:
        assert loader(_UNRESOLVABLE) is None, (
            "the loader resolved a deliberately unresolvable object name; the "
            "fault this arm depends on did not occur, so the assertions below "
            "would measure nothing."
        )
        reason = module._WHY.get(_UNRESOLVABLE)
        assert reason, (
            f"{module_name}: the load failed and recorded NO reason, so the "
            f"skip reason its differential rows emit falls back to the "
            f"no-failure-recorded literal while a failure plainly occurred."
        )
        assert _UNRESOLVABLE in reason, (
            f"{module_name}: the recorded reason does not name the object that "
            f"failed to resolve, so it carries no cause from git -- got "
            f"{reason!r}. This is the state reached by dropping the loader's "
            f"stderr, and it is indistinguishable in CI from a git that could "
            f"not run at all."
        )
    finally:
        module._WHY.pop(_UNRESOLVABLE, None)
