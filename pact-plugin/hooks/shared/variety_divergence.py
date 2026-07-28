"""
Location: pact-plugin/hooks/shared/variety_divergence.py
Summary: Pure-function variety divergence math for the wrap-up retrospective.
Used by: pact-plugin/commands/wrap-up.md §4 Orchestration Retrospective composer.

Computes the divergence between feature-level variety and the per-dispatch
variety distribution, surfacing miscalibration when the mean dispatch
variety differs from the feature variety by more than a threshold.

Mirrors variety_scorer.py module conventions:
- Pure function, no side effects, no disk reads.
- Fail-open semantics: bad input returns a structured advisory dict with
  `surfaced=False` and a `reason` key, NOT an exception.

Functions:
- compute_variety_divergence(feature_variety, dispatch_varieties,
  total_pact_dispatch_count=None, threshold=2) -> dict
- extract_dispatch_coverage(dispatch_site_events) -> (variety_totals,
  total, malformed) — BOTH Q5 terms from ONE pass over ONE input list.

Return shape (stable keys):
- `coverage`:  float — fraction of pact-* dispatches with variety stamped;
               normally in [0.0, 1.0] but NOT clamped. In the
               `coverage_exceeds_unity` advisory branch it is returned
               UNCLAMPED >= 1.0 (the stamped/total ratio when total > 0, or
               a finite stamped-count signal when the computed denominator
               collapsed to 0 with stamps present) so a denominator
               regression stays visible; it is debug-only there
               (surfaced=False). When total_pact_dispatch_count is None,
               assumed 1.0 (all known dispatches were stamped).
- `stamped`:   int — the numerator as a RAW COUNT.
- `total`:     int | None — the denominator as a RAW COUNT (None on the
               legacy no-denominator path). `stamped` and `total` are
               present on EVERY return path so a reader can render "0 of 5"
               rather than a bare `0.000`: the counts say which of the two
               zero-coverage states this is, and the ratio does not.
- `mean`:      int | None — rounded mean of stamped dispatch variety
               totals; None when dispatches is empty.
- `max`:       int | None — max of stamped dispatch totals; None when empty.
- `min`:       int | None — min of stamped dispatch totals; None when empty.
- `delta`:     int | None — abs(feature_variety - mean); None when either
               feature_variety is None or dispatches is empty.
- `surfaced`:  bool — True when delta >= threshold AND feature_variety is
               not None AND dispatches is non-empty; ALSO True for the
               `zero_coverage` state below, which is a finding rather than a
               degenerate case.
- `direction`: "overshot" | "undershot" | None — populated when
               surfaced=True, None otherwise. "overshot" means
               feature_variety > mean (feature was estimated too high);
               "undershot" means feature_variety < mean (estimated too low).
- `reason`:    str | None — the structural cause, or None on the ordinary
               surfaced-divergence path:
               * "no_dispatch_sites"   — total == 0: NOTHING WAS DISPATCHED,
                 so there is no entity to measure. surfaced=False. This is
                 the N/A state; rendering 0.000 for it manufactures a
                 compliance gap out of a missing stream.
               * "zero_coverage"       — total > 0 and stamped == 0: every
                 dispatch site exists and NONE was stamped. surfaced=TRUE —
                 the loudest legitimate reading of this metric, not a
                 degenerate case. (Replaces the former
                 "no_dispatches_stamped", whose name was FALSE here: it
                 said "no dispatches" when there were N.)
               * "feature_variety_missing", "within_threshold" — as before.
               * "coverage_exceeds_unity" — the defense-in-depth tripwire
                 when stamped outnumbers total. UNREACHABLE from Q5 under
                 the one-event topology (extract_dispatch_coverage cannot
                 produce it); retained for a caller assembling both terms
                 by hand.

The composer in wrap-up.md §4 reads this dict and produces the §3.4
sample output prose. compute_variety_divergence tests live in
test_per_dispatch_variety.py; the net-new helpers
(extract_dispatch_coverage, resolve_arc_start) live in
test_variety_divergence.py.
"""

from __future__ import annotations

from datetime import datetime

from .teachback_schema import resolve_variety_total


# ---------------------------------------------------------------------------
# Threshold default
# ---------------------------------------------------------------------------
DEFAULT_THRESHOLD = 2  # see pact-variety.md §Variety Calibration Record


def compute_variety_divergence(
    feature_variety: int | None,
    dispatch_varieties: list[int],
    total_pact_dispatch_count: int | None = None,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict:
    """Compute divergence between feature variety and dispatch distribution.

    Args:
        feature_variety: feature-level variety total (4-16) or None when the
            feature task lacks `metadata.variety` (legacy / pre-rollout).
        dispatch_varieties: list of per-dispatch variety totals (int) read
            from each pact-* work task's `metadata.variety.total`. Tasks
            without variety stamping are omitted from this list.
        total_pact_dispatch_count: total count of pact-* work tasks in the
            session, including those without variety stamping. When None,
            assumed equal to `len(dispatch_varieties)` (coverage = 1.0).
        threshold: minimum delta between feature_variety and dispatch mean
            for the divergence to be surfaced. Default 2 per pact-variety.md
            (a delta of 2 represents one full variety band off).

    Note: `mean` is round()-ed (banker's rounding, round-half-to-even) and
    the threshold check uses that rounded mean. At an exact .5 mean (e.g.
    sum/count == 6.5) round-half-to-even can tip the surfaced decision by
    one — an accepted minor boundary effect of a heuristic band, not a bug.

    Returns:
        dict with keys: coverage, mean, max, min, delta, surfaced, direction,
        reason. See module docstring for semantics.
    """
    # --- Coverage ---
    stamped_count = len(dispatch_varieties)
    if total_pact_dispatch_count is None or total_pact_dispatch_count < 0:
        # None = legacy / no denominator passed; negative = impossible /
        # garbage input (a real dispatch-site count is never < 0). Both
        # fail-open to the all-stamped assumption rather than tripping the
        # regression advisory — a negative is a caller bug, not a meaningful
        # denominator collapse.
        coverage = 1.0 if stamped_count > 0 else 0.0
    elif total_pact_dispatch_count == 0:
        # COMPUTED denominator == 0. With stamps firing (stamped > 0) this is
        # the WORST denominator regression — every dispatch marker is absent
        # while variety stamps exist. Do NOT fail-open to 1.0 (that would
        # HIDE it); the coverage_exceeds_unity advisory below trips.
        # coverage is a FINITE >=1.0 signal (the stamped count, i.e.
        # denominator-treated-as-1) rather than +inf, to avoid an inf
        # footgun in downstream formatting/arithmetic — it is debug-only
        # (surfaced=False; the composer emits the advisory, not a ratio).
        # stamped == 0 here is a genuinely empty session and returns via the
        # empty-dispatch fail-open.
        coverage = float(stamped_count) if stamped_count > 0 else 0.0
    else:
        coverage = stamped_count / total_pact_dispatch_count

    # --- Nothing stamped: `total` is the DISCRIMINATOR, not a detail ---
    # `stamped == 0` is NOT a terminal condition. Two opposite findings live
    # here and they must never render identically:
    #
    #   total == 0              -> no entity to measure. N/A.
    #   total > 0, stamped == 0 -> every site un-stamped. The metric's worst
    #                              legitimate reading, and the loudest signal
    #                              coverage can produce.
    #
    # Returning early on `stamped == 0` before consulting `total` suppressed
    # the second as if it were the first: a REAL gap reported as "nothing to
    # report". That is not a believable wrong answer beating a visible
    # refusal — it is an INVISIBLE REFUSAL reading as nothing-to-report.
    if stamped_count == 0:
        no_sites = total_pact_dispatch_count == 0 or total_pact_dispatch_count is None
        return {
            "coverage": coverage,
            "stamped": stamped_count,
            "total": total_pact_dispatch_count,
            "mean": None,
            "max": None,
            "min": None,
            "delta": None,
            # A 0% coverage gap is the finding, not a degenerate case to hide.
            "surfaced": not no_sites,
            "direction": None,
            "reason": "no_dispatch_sites" if no_sites else "zero_coverage",
        }

    # --- Stats over stamped subset ---
    dispatch_sum = sum(dispatch_varieties)
    mean = round(dispatch_sum / stamped_count)
    dispatch_max = max(dispatch_varieties)
    dispatch_min = min(dispatch_varieties)

    # --- Defense-in-depth: coverage > 1.0 tripwire (advisory, NOT a clamp) ---
    # When the stamped dispatches outnumber the counted Task-B dispatch
    # sites (stamped > total), coverage exceeds 1.0 — a denominator
    # regression. This ALSO covers the computed-total==0-with-stamps
    # collapse (every marker absent while stamps fire → coverage +inf): the
    # guard requires total >= 0 (a real, non-negative computed denominator)
    # AND stamped > total, so the total==0 collapse trips here instead of
    # fail-opening to coverage=1.0. None (legacy) and negative (garbage)
    # are handled in the coverage block above and never reach this branch.
    # Surface it as a self-reporting advisory rather than silently emitting
    # coverage > 1.0 or clamping it (a clamp would HIDE the regression this
    # is meant to catch). surfaced=False because a divergence computed over
    # a broken denominator is untrustworthy — the orchestrator should
    # investigate the count, not report the divergence. coverage is left
    # UNCLAMPED so the anomaly is visible in the output.
    if (
        total_pact_dispatch_count is not None
        and total_pact_dispatch_count >= 0
        and stamped_count > total_pact_dispatch_count
    ):
        delta = (
            abs(feature_variety - mean)
            if isinstance(feature_variety, int)
            else None
        )
        return {
            "coverage": coverage,
            "stamped": stamped_count,
            "total": total_pact_dispatch_count,
            "mean": mean,
            "max": dispatch_max,
            "min": dispatch_min,
            "delta": delta,
            "surfaced": False,
            "direction": None,
            "reason": "coverage_exceeds_unity",
        }

    # --- Feature variety missing fail-open ---
    if not isinstance(feature_variety, int):
        return {
            "coverage": coverage,
            "stamped": stamped_count,
            "total": total_pact_dispatch_count,
            "mean": mean,
            "max": dispatch_max,
            "min": dispatch_min,
            "delta": None,
            "surfaced": False,
            "direction": None,
            "reason": "feature_variety_missing",
        }

    # --- Delta + threshold check ---
    delta = abs(feature_variety - mean)
    if delta >= threshold:
        direction = "overshot" if feature_variety > mean else "undershot"
        return {
            "coverage": coverage,
            "stamped": stamped_count,
            "total": total_pact_dispatch_count,
            "mean": mean,
            "max": dispatch_max,
            "min": dispatch_min,
            "delta": delta,
            "surfaced": True,
            "direction": direction,
            "reason": None,
        }

    return {
        "coverage": coverage,
        "stamped": stamped_count,
        "total": total_pact_dispatch_count,
        "mean": mean,
        "max": dispatch_max,
        "min": dispatch_min,
        "delta": delta,
        "surfaced": False,
        "direction": None,
        "reason": "within_threshold",
    }


def extract_dispatch_coverage(
    dispatch_site_events: list[dict],
) -> tuple[list[int], int, list[dict]]:
    """Derive BOTH Q5 coverage terms from ONE pass over the `dispatch_site`
    stream.

    Returns `(variety_totals, total, malformed)`:

    - `variety_totals` — the resolved variety total of every event that
      carries a resolvable stamp. **This list IS the numerator's source**:
      the numerator is `len(variety_totals)`, and the same list object is
      passed to `compute_variety_divergence` for mean/max/min/delta.
    - `total` — the DENOMINATOR: the number of `dispatch_site` events, i.e.
      the number of dispatch SITES. It counts the event's EXISTENCE, never
      the stamp's presence.
    - `malformed` — events carrying a `variety` value that could NOT be
      resolved. A DIFFERENT category from a missing stamp (see below).

    **Why one function returning the list, rather than a count the caller
    re-derives:** the numerator and denominator must be sourced over the
    same Task-B dispatch population. Returning a count would leave the
    caller to compute the totals in a second pass, making that invariant a
    rule maintained by agreement between two derivations. Here the numerator
    IS the length of the list the caller uses, so the coupling is an
    identity, not something a test has to keep true. There is deliberately
    no `stamped == len(variety_totals)` assertion anywhere: the two cannot
    diverge, so there is nothing to pin. Its absence is the design working,
    not a missing test.

    **Coverage > 1.0 is structurally impossible here.** Every element of
    `variety_totals` comes from an event that also incremented `total`, so
    `len(variety_totals) <= total` always — including for arbitrary,
    hostile, or partially-malformed input.

    **A missing stamp and a malformed stamp are different findings with
    different remedies, and are never merged:**

    - `variety` ABSENT — counted in `total`, absent from `variety_totals`,
      and NOT in `malformed`. An honest un-stamped dispatch: the coverage
      gap the metric exists to surface. The emit merges the on-disk task
      metadata with the wiring write, so an absent `variety` means the
      dispatch was never stamped ANYWHERE — a compliance signal, not a
      producer artefact.
    - `variety` PRESENT but unresolvable — counted in `total`, absent from
      `variety_totals`, AND listed in `malformed`. A data-quality defect.
      Folding these into the missing-stamp population would leave the ratio
      unchanged while reporting a normal gap as a producer defect, which
      trains readers to ignore the signal.

    A stamp recovered through a NON-CANONICAL resolver candidate (e.g. the
    four-dimension sum, with no `total` key) is STAMPED, not malformed:
    `resolve_variety_total` returning a value IS resolution, and which
    candidate won is not this consumer's business.

    Pure function; never raises. Non-list input yields `([], 0, [])`; a
    non-dict element is counted as a site (it existed) and contributes no
    total. The caller scopes `dispatch_site_events` to the current arc
    before calling — the platform reuses task_ids across arcs.
    """
    if not isinstance(dispatch_site_events, list):
        return [], 0, []

    variety_totals: list[int] = []
    malformed: list[dict] = []

    for event in dispatch_site_events:
        if not isinstance(event, dict):
            # It existed, so it is a site; it carries no resolvable stamp.
            continue
        # Absent key vs present-but-unresolvable are different findings, so
        # membership is tested before resolution is attempted.
        has_variety = "variety" in event
        resolved = resolve_variety_total(event.get("variety"))
        if resolved is not None:
            variety_totals.append(resolved)
        elif has_variety:
            malformed.append(event)

    return variety_totals, len(dispatch_site_events), malformed


def resolve_arc_start(
    variety_assessed_events: list[dict],
    feature_task_id: str,
) -> str | None:
    """Resolve the current arc's start timestamp for `--since` scoping.

    Returns the LATEST `ts` among `variety_assessed` events whose `task_id`
    matches `feature_task_id`. The platform REUSES low task_ids across arcs,
    so the current feature's id can also match a PRIOR arc's
    `variety_assessed`; the latest-ts match is the current arc (this is why
    a plain most-recent `read-last` of ANY feature is wrong). Returns None
    when no matching `variety_assessed` exists (legacy/trivial session) →
    the caller omits `--since` → whole-journal read (fail-open; single-arc
    behavior unchanged).

    Scope boundary (comPACT-led arcs): only the orchestrate
    variety-assessment step emits `variety_assessed`, so this returns None
    for a comPACT feature id. That is BENIGN and never mis-scopes the
    retrospective: the wrap-up Q5/Q6 retrospective runs only against an
    orchestrate feature assessment (a comPACT workflow does not invoke the
    retrospective, and wrap-up skips trivial single-comPACT sessions). In a
    resumed comPACT-then-orchestrate session the wrap-up's feature id is the
    orchestrate feature, whose `variety_assessed` anchors `--since` and
    excludes the prior comPACT arc's events by ts. So None-for-comPACT never
    occurs on the retro path that consumes this helper.

    Timestamps are PARSED for the max, never lexically compared: `make_event`
    stamps `ts` as `...Z` while `canonical_since()` emits `...+00:00`, and a
    lexical compare across the two is wrong (`'+'` 0x2B sorts before `'Z'`
    0x5A). The 2-line normalize-and-parse is duplicated locally (rather than
    importing `session_journal._parse_ts`) to keep this module decoupled; if
    a third ts-parse site ever appears, extract a shared util. The RETURN
    value is the original `ts` STRING of the latest event, so the caller
    passes it to `--since`, which `_ts_ge` re-parses. The parse AND the
    max-comparison both run inside one try/except, so an entry that is
    unparseable OR un-comparable (e.g. a parseable-but-naive ts compared
    against an aware one → TypeError) is skipped (fail-open), never raised.
    If no matching, usable entry remains → None.

    task_id matching is str-normalized (`str(event task_id) == str(feature
    task_id)`) so a future bare-int `variety_assessed` emit still matches a
    str feature_task_id.

    arc_start relies on `variety_assessed` being emitted exactly once per arc
    (sole writer: the orchestrate variety-assessment step). If a future
    change ever re-emits it mid-arc for the same feature_task_id, switch from
    latest-ts to earliest-after-prior-arc-boundary — latest-ts would
    otherwise push arc_start forward and drop early-arc dispatches.

    Pure function — no disk reads, no mutation.
    """
    def _parse(value: object) -> datetime:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    latest_ts: str | None = None
    latest_dt: datetime | None = None
    for event in variety_assessed_events:
        if str(event.get("task_id")) != str(feature_task_id):
            continue
        ts = event.get("ts")
        if not ts:
            continue
        try:
            dt = _parse(ts)
            # The comparison is INSIDE the try (mirroring _ts_ge): comparing
            # a parseable-but-naive ts against an aware one raises TypeError
            # — fail open (skip the entry) instead of crashing the read.
            if latest_dt is None or dt > latest_dt:
                latest_dt = dt
                latest_ts = ts
        except (ValueError, TypeError):
            continue
    return latest_ts


# Liveness states for check_denominator_liveness. FOUR states, and the fourth
# must not collapse into any of the other three: the Q5 consumer already
# separates "surfaced", "no dispatch sites (N/A)" and "zero coverage" — three
# readings this design spent real effort disentangling — and INCONCLUSIVE is
# none of them. It means "the witness is degraded, so this measurement cannot
# be trusted", which is a statement about the INSTRUMENT rather than about the
# population. Merging it into N/A would recreate exactly the conflation the
# coverage extractor was built to remove, one field over.
LIVENESS_ALIVE = "alive"
LIVENESS_DEAD = "denominator_stream_dead"
LIVENESS_INCONCLUSIVE = "witness_degraded"

# The witness's own event type. Named here so the liveness check and the emit
# site cannot drift on the string.
WITNESS_EVENT_TYPE = "dispatch_decision"


def _is_countable_witness(subagent_type: object, exempt_types: frozenset) -> bool:
    """True iff a `dispatch_decision` names a spawn that SHOULD have produced
    a dispatch site.

    `dispatch_decision` fires on EVERY spawn, including the bootstrap
    secretary's — measured at 248 of 856 events (29%) — and including
    non-PACT helpers (Explore, general-purpose, fork). Counting those as
    witnesses is what makes the uncorrected predicate trip in 117
    legitimately-empty sessions instead of 5.

    `subagent_type` here is an AGENT-TYPE token (`pact-backend-coder`), not a
    task owner. Owners are bare names and must be resolved through team
    config — that warning does not apply to this field, and a prefix test is
    correct for it.

    The exemption set is the caller's, threaded from the SAME
    TEACHBACK_EXEMPT_AGENT_TYPES the emit predicate uses: if the witness
    excluded a different set from the denominator, the two would drift and
    this check would silently mis-aim — the same-population failure one level
    out from the one Q5 already fixed.

    DELIBERATE APPROXIMATION, stated because it has a direction: this tests
    the `pact-` prefix rather than resolving against the on-disk specialist
    registry, which would need a filesystem glob and make this module impure
    and untestable without a seeded plugin root. An unregistered `pact-*`
    type would therefore count as a witness — over-inclusive, which biases
    toward TRIPPING. That is the noisier direction rather than the silent
    one, and it is bounded in practice because an unregistered `pact-*` spawn
    is refused at the dispatch gate before it can ever emit.
    """
    if not isinstance(subagent_type, str) or not subagent_type:
        return False
    if not subagent_type.startswith("pact-"):
        return False
    return subagent_type not in exempt_types


def check_denominator_liveness(
    dispatch_site_events: list[dict],
    dispatch_decision_events: list[dict],
    skip_events: list[dict],
    exempt_types: frozenset,
) -> dict:
    """Binary liveness check over the Q5 denominator stream, plus the
    instrument's own honesty about when it cannot answer.

    Returns `{"state": ..., "dispatch_sites": int, "witness_spawns": int,
    "witness_skips": int}` — RAW COUNTS AND NO RATIO. The ratio was never the
    signal: `dispatch_decision` was chosen for being 0/45 degenerate on the
    corpus, and its ratio against dispatch sites ranges 0.20–4.00, which is
    useless. There is deliberately NO TUNABLE NUMBER anywhere in this
    function, so there is nothing to mis-set.

    The three states, in evaluation order, and the order is load-bearing:

    1. INCONCLUSIVE — a `journal_emit_skipped` naming the witness type is
       present in-window. **A liveness check that knows its own witness is
       lossy must not return "alive"** — and equally must not return "dead",
       because a missing witness makes BOTH readings untrustworthy. This is
       checked FIRST for that reason.
    2. DEAD — no dispatch sites at all, yet at least one countable spawn that
       should have produced one. Advisory: the caller reports it and never
       clamps or suppresses the coverage figure on the strength of it.
    3. ALIVE — anything else, including the common healthy case of no sites
       and no countable spawns (a session that dispatched nothing).

    🔴 WHAT THIS CANNOT SEE, and it must not be softened into sounding
    covered: PARTIAL degradation. If some dispatch_site emits are lost but
    not all, this returns ALIVE — the stream is non-empty and nothing else
    here distinguishes "fewer than expected" from "exactly as many as
    happened". The concern that motivated a liveness check WAS partial
    degradation, so this mitigation is strictly NARROWER than the concern it
    answers. The two documented skip paths are covered by counting
    `journal_emit_skipped`; everything outside them has no witness at all.
    That gap is pinned as an executable test rather than left as prose.
    """
    sites = len(dispatch_site_events) if isinstance(dispatch_site_events, list) else 0

    witness_skips = 0
    if isinstance(skip_events, list):
        for ev in skip_events:
            if isinstance(ev, dict) and ev.get("skipped_type") == WITNESS_EVENT_TYPE:
                witness_skips += 1

    countable = 0
    if isinstance(dispatch_decision_events, list):
        for ev in dispatch_decision_events:
            if not isinstance(ev, dict):
                continue
            if _is_countable_witness(ev.get("subagent_type"), exempt_types):
                countable += 1

    if witness_skips:
        state = LIVENESS_INCONCLUSIVE
    elif sites == 0 and countable > 0:
        state = LIVENESS_DEAD
    else:
        state = LIVENESS_ALIVE

    return {
        "state": state,
        "dispatch_sites": sites,
        "witness_spawns": countable,
        "witness_skips": witness_skips,
    }


def count_emit_skips(skip_events: list[dict]) -> dict:
    """Count `journal_emit_skipped` events by skipped type and cause.

    Consumer-side counting, deliberately. The hooks that record these run as a
    SEPARATE OS PROCESS PER TOOL CALL, so an in-process tally resets every
    invocation and can never deliver a session total — the durable store is
    the journal, and the count happens here at read time.

    Returns `{"total": int, "by_type": {...}, "by_cause": {...}}`. `by_cause`
    keeps RAISED separate from RETURNED-FALSE: a writer defect and a schema
    rejection have different remedies, and reporting a single "failed" number
    rebuilds the ambiguity that capturing the bool removed.
    """
    by_type: dict = {}
    by_cause: dict = {}
    total = 0
    if not isinstance(skip_events, list):
        return {"total": 0, "by_type": by_type, "by_cause": by_cause}
    for ev in skip_events:
        if not isinstance(ev, dict):
            continue
        skipped = ev.get("skipped_type")
        cause = ev.get("cause")
        if not isinstance(skipped, str) or not skipped:
            continue
        total += 1
        by_type[skipped] = by_type.get(skipped, 0) + 1
        if isinstance(cause, str) and cause:
            by_cause[cause] = by_cause.get(cause, 0) + 1
    return {"total": total, "by_type": by_type, "by_cause": by_cause}
