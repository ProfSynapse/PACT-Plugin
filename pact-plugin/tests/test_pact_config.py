"""Tests for shared/pact_config.py -- the os.environ-blind PACT_* resolver.

The resolver is the single source of truth for PACT runtime options. It is
fail-open by construction (every public function is total; any failure returns
the registry default) and os.environ-BLIND with CALL-TIME reads (zero work at
import, no caching -- so a consumer that resolves at its own module load sees
the same value a direct os.environ.get would, and these tests can monkeypatch
os.environ without importlib.reload).

Core invariants under test:
- bool parse is EXACT-MEMBERSHIP, never Python truthiness: "0"/"2"/"maybe" ->
  False (the fail-SAFE direction; a garbled flag stays OFF). bool("0")==True
  would be the F2 fail-unsafe slip this guards against.
- enum parse replicates the gates' .strip().lower() normalization; an unset var
  -> silent default; a SET-but-invalid value -> default + a stderr WARN (the
  non-vacuity tell that the invalid branch is live).
- llm_options() surfaces ONLY consumer=="llm" options as typed values.
- fail-safe: unknown option + an internal exception both resolve to the default
  without raising.
- call-time read: setting an env var AFTER import still changes the result
  (proves no import-time caching).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import shared.pact_config as pact_config
from shared.pact_config import get_bool, get_enum, llm_options


_GREEDY = "PACT_PR_GREEDY_FIX"
_AUTO = "PACT_AUTONOMOUS_SCOPE_DETECTION"
_INLINE = "PACT_DISPATCH_INLINE_MISSION_MODE"
_VARIETY = "PACT_DISPATCH_VARIETY_MODE"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start every test from an unset state for all registered options."""
    for name in (_GREEDY, _AUTO, _INLINE, _VARIETY):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestGetBoolExactMembership:
    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE", "Yes", " on ", "ON"])
    def test_true_tokens_resolve_true(self, _clean_env, raw):
        _clean_env.setenv(_GREEDY, raw)
        assert get_bool(_GREEDY) is True

    @pytest.mark.parametrize("raw", ["0", "2", "maybe", "false", "no", "off", "", "  ", "enabled", "y"])
    def test_everything_else_resolves_false(self, _clean_env, raw):
        # Includes "0" -- the F2 anchor: Python truthiness (bool("0")==True)
        # would fail UNSAFE here; exact-membership keeps it OFF.
        _clean_env.setenv(_GREEDY, raw)
        assert get_bool(_GREEDY) is False

    def test_unset_returns_default_false(self, _clean_env):
        assert get_bool(_GREEDY) is False
        assert get_bool(_AUTO) is False


class TestGetEnumNormalizationAndValidation:
    @pytest.mark.parametrize("raw,expected", [
        ("warn", "warn"), ("deny", "deny"), ("shadow", "shadow"),
        ("DENY", "deny"), (" deny ", "deny"), ("Warn", "warn"), ("SHADOW", "shadow"),
    ])
    def test_valid_values_normalized(self, _clean_env, raw, expected):
        _clean_env.setenv(_INLINE, raw)
        assert get_enum(_INLINE) == expected

    def test_unset_returns_default_silently(self, _clean_env, capsys):
        # The two enums declare DIFFERENT defaults on purpose: the
        # dispatch-variety gate ships ENFORCING, the inline-mission gate
        # advisory. Asserting both here is what keeps a copy-paste revert of
        # either one visible.
        assert get_enum(_INLINE) == "warn"
        assert get_enum(_VARIETY) == "deny"
        # Unset is the steady state -- NOT a misconfiguration -> no warning.
        assert capsys.readouterr().err == ""

    def test_invalid_value_falls_back_and_warns(self, _clean_env, capsys):
        _clean_env.setenv(_VARIETY, "banana")
        # Falls back to the row's DECLARED `invalid_fallback` ("warn"), NOT to
        # its default ("deny"). An unparseable value is not a request for the
        # shipped posture -- it is a statement the resolver could not read, and
        # the only population that ever reaches this branch is consumers trying
        # to opt DOWN.
        assert get_enum(_VARIETY) == "warn"
        # The non-vacuity tell: the invalid branch MUST emit a stderr warning.
        err = capsys.readouterr().err
        assert "PACT_DISPATCH_VARIETY_MODE" in err
        assert "banana" in err

    def test_a_RAISING_lookup_resolves_to_default_not_invalid_fallback(
        self, _clean_env, monkeypatch,
    ):
        """The THIRD resolution path, declared in the source and therefore
        owed a check. A raise is not a user statement at all, so it belongs
        with "unset" and resolves to `default` -- NOT to `invalid_fallback`,
        which answers a different question (what an unparseable REQUEST means).

        THIS TEST HAS TO FORCE THE RAISE. The handler is structurally
        unreachable -- dict lookups, os.environ.get and tuple membership do not
        throw -- so without an injected failure the path is never entered and a
        mutation swapping its return value reddens nothing. Measured: it did
        not, which is why this exists.

        MUTATION THAT REDDENS: change the `except` handler's `return default`
        to `return invalid_fallback`."""
        import shared.pact_config as pc

        def _boom(_name):
            raise RuntimeError("simulated os.environ failure")

        monkeypatch.setattr(pc.os.environ, "get", _boom)
        # The variety row is the only one where the two landing points differ,
        # so it is the only row on which this assertion can discriminate.
        assert get_enum(_VARIETY) == "deny", (
            "a raise inside the resolver must resolve to the registry default "
            "(the same place an UNSET var lands), never to invalid_fallback -- "
            "a crash is not a request we failed to parse"
        )

    def test_invalid_and_unset_do_NOT_collapse(self, _clean_env):
        """The separation this option exists to declare. Same variable, two
        different user intents, two different resolutions -- if either branch
        ever resolved like the other this reddens. The inline row is the
        control: it declares no fallback, so its two paths legitimately DO
        coincide, which is what makes the variety row's split observable rather
        than an artifact of the assertion."""
        assert get_enum(_VARIETY) == "deny"          # unset
        _clean_env.setenv(_VARIETY, "banana")
        assert get_enum(_VARIETY) == "warn"          # set-but-unparseable

        assert get_enum(_INLINE) == "warn"           # control: unset
        _clean_env.setenv(_INLINE, "banana")
        assert get_enum(_INLINE) == "warn"           # control: coincides

    def test_the_warning_names_the_value_actually_RESOLVED(self, _clean_env, capsys):
        """The stderr line is the mistyping consumer's ONLY tell, so a message
        naming a value the function did not return sends them to inspect a
        setting that never took effect. Reds if the message reverts to
        reporting `default` while the branch returns `invalid_fallback`."""
        _clean_env.setenv(_VARIETY, "warm")
        resolved = get_enum(_VARIETY)
        err = capsys.readouterr().err
        assert resolved == "warn"

        # Assert on the "using X" CLAUSE, not on whether the string "deny"
        # occurs anywhere: the message legitimately enumerates the allowed set
        # ('warn', 'deny', 'shadow'), so a bare substring test would fail on
        # correct output. The claim is about what the message says it USED.
        clause = err.rsplit("using ", 1)[-1].strip()
        assert clause == repr(resolved), (
            f"the diagnostic's 'using' clause must name the value actually "
            f"returned ({resolved!r}); it said {clause}. A message naming the "
            f"row's default instead sends the consumer to inspect a setting "
            f"that never took effect."
        )


class TestLlmOptions:
    def test_defaults_all_off(self, _clean_env):
        assert llm_options() == {_GREEDY: False, _AUTO: False}

    def test_reflects_resolved_values(self, _clean_env):
        _clean_env.setenv(_GREEDY, "1")
        assert llm_options() == {_GREEDY: True, _AUTO: False}

    def test_excludes_hook_consumer_options(self, _clean_env):
        # get_enum options (consumer=="hook") must NOT appear in the LLM payload.
        _clean_env.setenv(_INLINE, "deny")
        _clean_env.setenv(_VARIETY, "shadow")
        keys = set(llm_options().keys())
        assert _INLINE not in keys
        assert _VARIETY not in keys
        assert keys == {_GREEDY, _AUTO}


class TestFailSafe:
    def test_unknown_option_returns_safe_defaults(self, _clean_env):
        # Unknown options are not consumed; resolve to the type-neutral safe
        # default without raising.
        assert get_bool("PACT_DOES_NOT_EXIST") is False
        assert get_enum("PACT_DOES_NOT_EXIST") == ""

    def test_internal_exception_falls_back_to_default(self, _clean_env, monkeypatch):
        # Force the parse to raise; the total contract must swallow it and
        # return the registry default (never propagate).
        def _boom(_raw):
            raise RuntimeError("normalization blew up")

        monkeypatch.setattr(pact_config, "_normalize", _boom)
        _clean_env.setenv(_GREEDY, "1")
        _clean_env.setenv(_INLINE, "deny")
        assert get_bool(_GREEDY) is False   # bool default
        assert get_enum(_INLINE) == "warn"  # enum default


class TestCallTimeReadNoCaching:
    def test_env_set_after_import_is_observed(self, _clean_env):
        # pact_config was imported at module top; setting the var now must still
        # change the result -> proves LIVE per-call reads, not import caching.
        assert get_bool(_GREEDY) is False
        _clean_env.setenv(_GREEDY, "1")
        assert get_bool(_GREEDY) is True
