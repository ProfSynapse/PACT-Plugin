"""C2 equivalence tests: routing the two *_MODE gate reads through
shared.pact_config.get_enum must preserve the pre-refactor resolved mode
EXACTLY at BOTH gate sites.

Before C2, dispatch_gate.py and handoff_ordering_gate.py each resolved their
mode inline as:  os.environ.get(NAME, DEFAULT).strip().lower()  then a frozenset
membership check falling back to DEFAULT. `_old_resolve` below is that exact
logic, used as the oracle. The acceptance bar is: for every input in the battery
(valid values, invalid, whitespace, mixed case, unset), the new resolution ==
the old resolution.

SCOPE OF THE EQUIVALENCE CLAIM, and it is narrower than it first reads: what
C2 had to preserve is the RESOLUTION MECHANISM -- normalization, membership,
and fall-back-to-the-declared-default. It is NOT a claim that a given option's
default never changes. The two options now declare DIFFERENT defaults on
purpose (`_DEFAULT` below), so the oracle is parameterised by the declared
default rather than pinning one literal for both; pinning one would turn a
deliberate policy change into a red test, which is the shape that gets a policy
reverted to keep a suite green.

Two layers:
- TestResolverValueEquivalence drives pact_config.get_enum directly (full
  input coverage, cheap).
- TestGateSiteWiring reloads the REAL gate modules under each input and reads
  their module-level mode constant -- proving the RHS swap is actually wired
  (catches a composed-but-unwired resolver or a wrong env-var name), not merely
  that get_enum is correct in isolation.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import shared.pact_config as pact_config


_ALLOWED = frozenset({"warn", "deny", "shadow"})

INLINE = "PACT_DISPATCH_INLINE_MISSION_MODE"
VARIETY = "PACT_DISPATCH_VARIETY_MODE"

# The battery: unset (None), all valid values, an invalid value, whitespace, and
# mixed case -- the inputs whose resolution the RHS swap must not perturb.
_BATTERY = [None, "warn", "deny", "shadow", "banana", "  deny ", "DENY", "", "SHADOW", "Deny"]

# Each option's SHIPPED default, written here as an independent literal rather
# than read back from the registry -- reading the registry would make every
# unset/invalid row tautological. The dispatch-variety gate ships ENFORCING;
# the inline-mission gate ships advisory. A revert of either default reddens
# the unset and invalid rows below, which is the point.
_DEFAULT = {INLINE: "warn", VARIETY: "deny"}


def _old_resolve(raw, default="warn"):
    """The pre-refactor inline logic BOTH gates used, generalised over the
    option's declared default.

    os.environ.get(NAME, default).strip().lower(); a value outside the allowed
    set (including an unset var, empty string, or bogus token) falls back to
    `default`.
    """
    value = (raw if raw is not None else default).strip().lower()
    return value if value in _ALLOWED else default


@pytest.fixture(scope="module", autouse=True)
def _restore_gate_modules():
    """After this file's tests, reload both gate modules under a CLEAN env so a
    later test file sees their shipped default constants ("warn" for the inline
    gate, "deny" for the dispatch-variety gate). We must NOT evict
    them from sys.modules -- sibling files import them at collection time and
    call importlib.reload, which raises if the module is missing from
    sys.modules."""
    yield
    for name in (INLINE, VARIETY):
        os.environ.pop(name, None)
    for mod_name in ("dispatch_gate", "handoff_ordering_gate"):
        module = sys.modules.get(mod_name)
        if module is not None:
            importlib.reload(module)


@pytest.fixture
def clean(monkeypatch):
    """Reset both env vars for a test. Does NOT touch sys.modules (see
    _restore_gate_modules for why eviction breaks sibling test files)."""
    for name in (INLINE, VARIETY):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestResolverValueEquivalence:
    """get_enum reproduces the pre-refactor inline mode resolution exactly."""

    @pytest.mark.parametrize("name", [INLINE, VARIETY])
    @pytest.mark.parametrize("raw", _BATTERY)
    def test_get_enum_matches_old_inline_logic(self, clean, name, raw):
        if raw is None:
            clean.delenv(name, raising=False)
        else:
            clean.setenv(name, raw)
        assert pact_config.get_enum(name) == _old_resolve(raw, _DEFAULT[name])


def _reload_gate_mode(monkeypatch, module_name, env_name, raw, const_name):
    """Set env, reload the gate module (keeping it in sys.modules), and return
    its resolved-mode constant."""
    if raw is None:
        monkeypatch.delenv(env_name, raising=False)
    else:
        monkeypatch.setenv(env_name, raw)
    module = importlib.import_module(module_name)
    importlib.reload(module)
    return getattr(module, const_name)


class TestGateSiteWiring:
    """The real gate modules' mode constants reflect the resolver across the
    battery -- proves the swap is wired at each site, not just correct in the
    resolver."""

    @pytest.mark.parametrize("raw", _BATTERY)
    def test_dispatch_gate_inline_mission_mode(self, clean, raw):
        got = _reload_gate_mode(clean, "dispatch_gate", INLINE, raw, "INLINE_MISSION_MODE")
        assert got == _old_resolve(raw, _DEFAULT[INLINE])

    @pytest.mark.parametrize("raw", _BATTERY)
    def test_handoff_gate_variety_mode(self, clean, raw):
        got = _reload_gate_mode(
            clean, "handoff_ordering_gate", VARIETY, raw, "DISPATCH_VARIETY_MODE"
        )
        assert got == _old_resolve(raw, _DEFAULT[VARIETY])
