#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/pact_config.py
Summary: Single source of truth for PACT_* runtime configuration options.
         Resolves each option from os.environ at CALL TIME with a typed parse
         (bool exact-membership / enum allow-list), a registry-declared default,
         and validation. Fail-open by construction -- every public function is
         total (never raises); any resolution failure returns the registry
         default. The module does ZERO work at import: no module-level env
         reads, no caching. "module-load-safe" means importing this module has
         no side effects, NOT that values are cached at import. Each call reads
         os.environ LIVE, so a consumer that resolves once at its OWN module
         load (the dispatch/handoff gates) sees exactly the value a direct
         os.environ.get(...).strip().lower() would have produced, and tests can
         monkeypatch os.environ without reloading the module.
Used by: dispatch_gate.py + handoff_ordering_gate.py (get_enum -- the two
         *_MODE reads); session_init.py (llm_options -- the SessionStart
         injection of LLM-consumed options). Any future PACT_* consumer reuses
         this resolver by adding a _REGISTRY row.

Config source model -- os.environ-BLIND: the resolver reads ONLY os.environ. It
does NOT parse settings.json or model cross-tier precedence, because Claude Code
merges every settings tier (managed > CLI > local > project > user) into the
process environment BEFORE the hook subprocess starts -- the hook sees one
already-merged os.environ. Persisting a PACT_* option via settings.json's `env`
block is therefore transparent to this resolver. (Contrast teammate_mode.py,
which DOES read settings files, because `teammateMode` is a Claude-Code-native
setting with no env-var projection.)
"""
from __future__ import annotations

import os
import sys
from typing import Dict


# ─── Registry: the single source of truth for every PACT option ────────────
# Each row declares an option's type, default, and consumer:
#   type "bool":  parsed by EXACT MEMBERSHIP (see _BOOL_TRUE) -- NOT Python
#                 truthiness, under which bool("0") is True (a fail-UNSAFE slip).
#   type "enum":  validated against "allowed"; an unrecognized value falls back
#                 to "invalid_fallback" when the row declares one, else to
#                 "default", AND emits a one-line stderr warning naming the
#                 value actually resolved (the tell).
#   "invalid_fallback" (OPTIONAL, enum rows only): where an UNPARSEABLE value
#                 lands, when that should differ from where an UNSET one does.
#                 Omit it and the two coincide. Declare it when a row's default
#                 is the restrictive mode, because an unreadable value is not a
#                 request for that mode. Read ONLY by get_enum's unrecognized
#                 branch -- never by get_bool, and never by the raise handler.
#   consumer "llm":  surfaced to the orchestrator LLM via llm_options() +
#                    session_init's SessionStart injection (markdown flows
#                    cannot read env vars).
#   consumer "hook": read directly by a Python hook (the dispatch/handoff gates).
# Adding an option = adding a row here (Open/Closed); no other edit to this file.
_REGISTRY: Dict[str, dict] = {
    "PACT_PR_GREEDY_FIX": {
        "type": "bool", "default": False, "consumer": "llm",
    },
    "PACT_AUTONOMOUS_SCOPE_DETECTION": {
        "type": "bool", "default": False, "consumer": "llm",
    },
    "PACT_DISPATCH_INLINE_MISSION_MODE": {
        "type": "enum", "default": "warn",
        "allowed": ("warn", "deny", "shadow"), "consumer": "hook",
    },
    # The one ENFORCING default in this registry: an UNSET value DENIES. The
    # asymmetry against its sibling above is deliberate -- this gate refuses a
    # dispatch-wiring write whose Task B carries no resolvable variety, and a
    # consumer opts DOWN to "warn"/"shadow" rather than opting up.
    #
    # WHY "invalid_fallback" EXISTS AT ALL, and it is a statement about THIS
    # TABLE rather than about this option: without it, neither row here declares
    # an unknown-value policy -- both simply inherit whatever `get_enum` does
    # with an unparseable value. The two rows would then differ on that policy
    # ONLY as a side effect of their defaults differing, with nothing anywhere
    # expressing intent. An EMERGENT policy is the defect, independently of
    # which behaviour it emerges into: a reader who learns one row and predicts
    # the other has no way to know whether the difference was chosen. So the
    # policy is DECLARED here even where it merely restates what would have
    # happened, and the sibling above deliberately declares nothing because its
    # default already IS its fallback.
    "PACT_DISPATCH_VARIETY_MODE": {
        "type": "enum", "default": "deny", "invalid_fallback": "warn",
        "allowed": ("warn", "deny", "shadow"), "consumer": "hook",
    },
}

# Canonical TRUE tokens for the bool parse (case-insensitive, post-strip).
# EXACT MEMBERSHIP: any token NOT in this set -- including "0", "2", "maybe",
# "" and an unset var -- resolves to False. This is the fail-SAFE direction (a
# garbled greedy / autonomous flag stays OFF) and deliberately rejects Python
# truthiness, under which bool("0") would be True (security F2).
_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})


def _normalize(raw: str) -> str:
    """Strip + lowercase a raw env value.

    This is the SAME normalization dispatch_gate.py / handoff_ordering_gate.py
    apply to their *_MODE reads before the membership check. Replicated here so
    routing those reads through get_enum stays byte-behavior-identical to the
    pre-resolver ``os.environ.get(name, default).strip().lower()``.
    """
    return raw.strip().lower()


def get_bool(name: str) -> bool:
    """Resolve a bool-typed PACT option from os.environ (live, at call time).

    EXACT-MEMBERSHIP parse: returns True iff the stripped, lowercased value is
    one of _BOOL_TRUE ("1"/"true"/"yes"/"on"). Every other value -- and an
    unset var -- returns the registry default (False for both current bool
    options). Total: never raises; any failure returns the registry default.
    """
    entry = _REGISTRY.get(name, {})
    default = bool(entry.get("default", False))
    try:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return _normalize(raw) in _BOOL_TRUE
    except Exception:  # noqa: BLE001 -- total contract (fail-safe -> default)
        return default


def get_enum(name: str) -> str:
    """Resolve an enum-typed PACT option from os.environ (live, at call time).

    Applies the gates' existing ``.strip().lower()`` normalization, then
    validates against the registry's "allowed" tuple.

    THREE RESOLUTION PATHS, EACH DECLARED RATHER THAN INHERITED:

    * UNSET       -> the registry ``default``, silently. The expected steady
      state, not a misconfiguration, so it earns no diagnostic.
    * SET-BUT-UNRECOGNIZED -> the row's ``invalid_fallback`` when it declares
      one, else its ``default``; ALWAYS with a one-line stderr warning naming
      the value actually resolved. An unparseable value is not a request for
      the default -- it is a statement this resolver could not read -- so a row
      may declare a different landing point for it than for "unset".
    * RAISED      -> the ``default`` (never ``invalid_fallback``). See the
      handler for why the two are deliberately not the same.

    Total: never raises. Note that an empty-string env var is SET, so it takes
    the unrecognized path (and its warning), not the unset path.
    """
    entry = _REGISTRY.get(name, {})
    default = str(entry.get("default", ""))
    # Declared landing point for an unparseable value; defaults to `default`,
    # which is what every row without the key gets and is why adding the key is
    # behaviour-preserving for those rows.
    invalid_fallback = str(entry.get("invalid_fallback", default))
    allowed = entry.get("allowed", ())
    try:
        raw = os.environ.get(name)
        if raw is None:
            return default  # unset -> silent default (not a misconfiguration)
        value = _normalize(raw)
        if value in allowed:
            return value
        # Recognized option, unrecognized value: resolve to the row's DECLARED
        # invalid fallback and say so. The message must name the value actually
        # returned, not the row's default -- for a row where the two differ,
        # reporting the default would send the one consumer this branch exists
        # to serve (someone who mistyped an opt-down) to inspect a setting that
        # is not what took effect. The stderr line is their only tell.
        print(
            f"pact_config: {name}={raw!r} is not one of {tuple(allowed)}; "
            f"using {invalid_fallback!r}",
            file=sys.stderr,
        )
        return invalid_fallback
    except Exception:  # noqa: BLE001 -- total contract (fail-safe -> default)
        # DELIBERATELY `default`, NOT `invalid_fallback`, and the distinction is
        # about whose statement we are interpreting: an unrecognized value is a
        # user statement this resolver could not parse, whereas a raise here is
        # not a user statement at all -- so it belongs with "unset". Stretching
        # a key named `invalid_fallback` to cover crashes would broaden its
        # meaning past its name, which is how a precise key becomes a vague one.
        #
        # RESIDUAL, named because a can't-happen path with an undocumented
        # direction is exactly what gets re-litigated later: for a row whose
        # default is enforcing, this handler fails CLOSED -- the opposite
        # direction from the unrecognized branch above, on purpose. The exposure
        # is bounded by the path being structurally non-raising (dict lookups,
        # os.environ.get, tuple membership), i.e. a guard rather than a route.
        # If it ever becomes reachable, revisit this choice rather than assuming
        # it was made with a live path in mind.
        return default


def llm_options() -> Dict[str, object]:
    """Return {option_name: resolved_typed_value} for every consumer=="llm"
    option -- the payload session_init injects into the orchestrator's context.

    Values are typed (bool for the two current LLM options), resolved LIVE from
    os.environ via get_bool / get_enum. Total: never raises; a per-option
    failure falls back to that option's registry default inside the getter.
    """
    options: Dict[str, object] = {}
    for name, entry in _REGISTRY.items():
        if entry.get("consumer") != "llm":
            continue
        opt_type = entry.get("type")
        if opt_type == "bool":
            options[name] = get_bool(name)
        elif opt_type == "enum":
            options[name] = get_enum(name)
    return options
