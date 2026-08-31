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

import pytest

# (module, loader) for every module carrying a `_WHY` diagnostic. Derived by
# predicate -- the modules defining `_WHY`, not a remembered count. The 1118
# module names its loader differently, which is why the pair is carried here
# rather than assumed.
_LOADERS = [
    ("test_merge_guard_1118_recert", "_load_module_at"),
    ("test_merge_guard_1129_r2_cert", "_load_classifier"),
    ("test_merge_guard_1129_r3_cert", "_load_classifier"),
    ("test_merge_guard_1136_canonical_join_ssot", "_load_classifier"),
    ("test_merge_guard_1140_carrier5_cert", "_load_classifier"),
    ("test_merge_guard_1178_cert", "_load_classifier"),
    ("test_merge_guard_1178_f2_cert", "_load_classifier"),
]

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
