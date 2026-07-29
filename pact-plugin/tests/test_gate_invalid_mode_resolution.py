"""Coder-flagged item: the get_enum ADDITIVE stderr WARN (emitted when a *_MODE
env var is SET-but-invalid) must never CHANGE a gate's disposition, and must
never leak into the gate's stdout decision JSON.

WHAT THIS FILE NO LONGER CLAIMS (it was named ..._no_deny before this): an
invalid mode is not universally non-denying. `PACT_DISPATCH_VARIETY_MODE` now
DECLARES "deny" as its shipped default, so a misspelled opt-down at that gate
resolves to "deny" and the gate enforces. That is the declared policy acting,
not the diagnostic acting -- which is the distinction this file exists to keep
sharp. The invariant that survives is the one that was always the real subject:
the resolution lands on the option's DECLARED DEFAULT and nowhere else, and the
diagnostic goes to stderr.

Mechanism the tests pin:
- A set-but-invalid mode (e.g. "banana") resolves through get_enum to that
  option's registry default -- "warn" for the inline-mission gate, "deny" for
  the dispatch-variety gate -- and never to anything derived from the invalid
  token. (TestInvalidModeResolvesToTheDeclaredDefault)
- The additive diagnostic is written to STDERR at gate import, so it cannot
  corrupt the gate's STDOUT decision JSON. (same class -- captures the reload
  stderr)
- Behaviorally, driving the REAL handoff_ordering_gate.main() while the invalid
  mode is active emits valid, uncorrupted JSON. (TestInvalidModeStdoutStaysClean)

Reload discipline: both gate modules resolve their mode constant at IMPORT, so we
reload under the invalid env and RESTORE them under a clean env at teardown
(without evicting from sys.modules -- sibling test files import + reload them and
would break if they vanished). Mirrors test_pact_config_gate_migration.
"""
import contextlib
import importlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

INLINE_ENV = "PACT_DISPATCH_INLINE_MISSION_MODE"
VARIETY_ENV = "PACT_DISPATCH_VARIETY_MODE"

# (module, env var, mode-constant name, that option's DECLARED default).
# The default is an independent literal, not read back from the registry --
# reading the registry would make the assertion tautological.
_GATES = [
    ("dispatch_gate", INLINE_ENV, "INLINE_MISSION_MODE", "warn"),
    ("handoff_ordering_gate", VARIETY_ENV, "DISPATCH_VARIETY_MODE", "deny"),
]


@pytest.fixture(scope="module", autouse=True)
def _restore_gate_modules():
    """Reload both gates under a CLEAN env after this file so later tests see
    their default constants. Do NOT evict from sys.modules."""
    yield
    for env in (INLINE_ENV, VARIETY_ENV):
        os.environ.pop(env, None)
    for mod_name in ("dispatch_gate", "handoff_ordering_gate"):
        module = sys.modules.get(mod_name)
        if module is not None:
            importlib.reload(module)


def _reload_capturing_stderr(monkeypatch, module_name, env_name, value, const_name):
    """Set env=value, reload module capturing import-time stderr, return
    (mode_constant, stderr_text)."""
    monkeypatch.setenv(env_name, value)
    module = importlib.import_module(module_name)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        importlib.reload(module)
    return getattr(module, const_name), buf.getvalue()


class TestInvalidModeResolvesToTheDeclaredDefault:
    @pytest.mark.parametrize("module_name,env_name,const_name,default", _GATES)
    def test_invalid_value_resolves_to_the_declared_default(
        self, monkeypatch, module_name, env_name, const_name, default
    ):
        mode, _stderr = _reload_capturing_stderr(
            monkeypatch, module_name, env_name, "banana", const_name
        )
        assert mode == default, (
            f"{module_name}: an invalid {env_name} must resolve to that "
            f"option's DECLARED default {default!r}. It must never resolve to "
            f"the other gate's default, to the invalid token, or to a value "
            f"the resolver invented -- the diagnostic reports the fallback, it "
            f"does not choose it."
        )

    @pytest.mark.parametrize("module_name,env_name,const_name,default", _GATES)
    def test_additive_warn_goes_to_stderr_not_stdout(
        self, monkeypatch, module_name, env_name, const_name, default
    ):
        # The tell: the invalid branch fires the diagnostic, and it lands on
        # STDERR (so it cannot pollute the gate's stdout decision JSON).
        _mode, stderr = _reload_capturing_stderr(
            monkeypatch, module_name, env_name, "banana", const_name
        )
        assert env_name in stderr and "banana" in stderr, (
            f"{module_name}: the additive get_enum WARN for an invalid {env_name} "
            f"must be emitted to stderr (the non-vacuity tell it resolved via the "
            f"invalid branch)"
        )


class TestInvalidModeStdoutStaysClean:
    """Behavioral: with the invalid mode active, real main() still emits valid,
    parseable JSON on stdout and exits 0 on a frame the gate has no opinion
    about.

    WHAT THIS ARM CAN AND CANNOT SHOW, because the frame is doing the work: a
    non-TaskUpdate frame cannot reach EITHER branch's advisory, so it could not
    deny under any mode — this arm therefore proves the stderr diagnostic does
    not corrupt stdout and does not crash the gate. It is NOT evidence that the
    gate never denies; that question is settled by the mode constant asserted
    above, and the dispatch-variety gate's answer to it is now 'it does'."""

    def test_handoff_gate_main_stdout_is_uncorrupted_under_invalid_mode(
        self, monkeypatch
    ):
        monkeypatch.setenv(VARIETY_ENV, "banana")
        gate = importlib.import_module("handoff_ordering_gate")
        with contextlib.redirect_stderr(io.StringIO()):
            importlib.reload(gate)  # "banana" -> the option's declared default
        benign = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(benign)))
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), pytest.raises(SystemExit) as exc:
            gate.main()
        assert exc.value.code == 0, (
            "a frame the gate has no opinion about must pass through at exit 0, "
            "whatever the resolved mode"
        )
        stdout = out_buf.getvalue().strip()
        parsed = json.loads(stdout)  # must be valid JSON (stderr WARN did not leak in)
        assert "permissionDecision" not in json.dumps(parsed), (
            "a pass-through frame must not carry a permissionDecision, and the "
            "additive stderr WARN must not surface in the stdout payload"
        )
