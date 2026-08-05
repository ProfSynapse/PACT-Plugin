"""
Location: pact-plugin/tests/test_catchup_reason_is_read.py

Summary: Pins that the embedding catch-up's REASON is consumed, not merely
carried. `get_unembedded_memories` returns `.reason` saying whether the backlog
question was answerable at all; these arms assert that a caller BRANCHES on it
and that a status reader can see the answer.

Used by/with:
- skills/pact-memory/scripts/embedding_catchup.py: produces `UnembeddedResult.reason`.
- skills/pact-memory/scripts/memory_init.py: `maybe_embed_pending` branches on it;
  `get_embedding_catchup_status` exposes the session's outcome.
- skills/pact-memory/scripts/memory_api.py: `get_status` surfaces it, which is
  what `cli.cmd_status` renders.

WHY THIS EXISTS. The sweep returns no IDs from four exits. Three mean it COULD
NOT LOOK; one means it looked and found nothing. The reason channel that tells
them apart was already correct and already shipped -- and reached no consumer.
`maybe_embed_pending` fell through to `status='ok'`, announcing that the
catch-up succeeded in precisely the degraded state the catch-up exists to
repair, and `_ensure_ready` discarded the dict that carried the evidence. An
ignored return value is syntactically identical to a call made for its side
effects, which is why this survived review.

THE `ok` ARM IS A CONTROL, NOT A COURTESY. Without it, a branch that returned a
non-ok status for EVERY outcome would satisfy every other assertion here while
destroying the distinction the channel exists to make.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from scripts import embedding_catchup


def _live(name):
    """Resolve a `scripts.*` module AT CALL TIME, never at import time.

    `tests/test_embedding_catchup.py` deletes `scripts.*` entries from
    `sys.modules` and installs stand-ins, to exercise the sweep's
    import-failure path. A module-level `from scripts import ...` binding
    captured at collection therefore goes STALE: patching the captured object
    leaves the code under test importing a DIFFERENT one, the mock silently
    misses, and the arm passes for the wrong reason.

    The failure mode is the dangerous shape -- this file passes when run alone
    and fails only in a full run, so an isolated mutation proof cannot see it.
    Re-import on every use so the patch and the code under test always address
    one object.
    """
    return importlib.import_module(f"scripts.{name}")


def _sweep_result(reason):
    """What `embed_pending_memories` returns when it processed nothing."""
    return {
        "processed": 0,
        "failed": False,
        "skipped_ram": False,
        "error": None,
        "unembedded_unknown": reason,
    }


def _run_catchup(tmp_path, reason):
    """Drive `maybe_embed_pending` with a sweep that reports `reason`.

    The marker path is redirected into tmp so this never reads or creates the
    operator's real session marker -- the hazard this change set exists to close.
    """
    memory_init = _live("memory_init")
    catchup = _live("embedding_catchup")
    marker = tmp_path / f"marker-{reason}"
    with patch.object(
        memory_init, "_get_embedding_attempted_path", return_value=marker
    ), patch.object(
        catchup, "embed_pending_memories",
        return_value=_sweep_result(reason),
    ):
        result = memory_init.maybe_embed_pending()

    # NON-VACUITY. `maybe_embed_pending` wraps its body in a bare `except
    # Exception`, so a mock that failed to bind, or an import that broke under
    # another module's `sys.modules` surgery, surfaces as `error` with a
    # message -- which would let the `query_failed` arm below pass for entirely
    # the wrong reason.
    assert result.get("message") != "Mock", result
    return result


class TestMaybeEmbedPendingBranchesOnTheReason:
    """The three unanswerable reasons must not report success."""

    @pytest.mark.parametrize(
        "reason",
        [
            embedding_catchup.UnembeddedResult.NO_EXTENSIONS,
            embedding_catchup.UnembeddedResult.NO_VECTOR_TABLE,
        ],
    )
    def test_a_capability_limit_is_degraded_not_ok(self, tmp_path, reason):
        """Cannot look because a dependency is absent. A configuration, not a fault.

        `SQLITE_EXTENSIONS_ENABLED` tracks pysqlite3 ONLY, so a process holding
        pysqlite3 and lacking sqlite-vec clears the extensions check, fails to
        create the vector table, and reaches the sweep with the table genuinely
        missing. Both reasons are therefore ordinary degraded states.
        """
        result = _run_catchup(tmp_path, reason)

        assert result["status"] == "degraded", result
        assert result["unembedded_unknown"] == reason, (
            "the specific reason must survive, not just the coarse status"
        )

    def test_a_query_that_raised_is_an_error_not_a_degradation(self, tmp_path):
        """Both dependencies were present and the query raised anyway.

        That is an incident rather than a capability limit. Filing it under
        `degraded` would bury the one reason of the three that warrants
        attention rather than configuration.
        """
        result = _run_catchup(
            tmp_path, embedding_catchup.UnembeddedResult.QUERY_FAILED
        )

        assert result["status"] == "error", result
        assert (
            result["unembedded_unknown"]
            == embedding_catchup.UnembeddedResult.QUERY_FAILED
        )

    def test_an_answered_empty_sweep_still_reports_ok(self, tmp_path):
        """CONTROL. A branch that reddened everything would pass the arms above
        while erasing the distinction the reason channel exists to draw."""
        result = _run_catchup(tmp_path, None)

        assert result["status"] == "ok", result
        assert result["message"] is None
        assert result.get("unembedded_unknown") is None


class TestStatusSurfacesTheCatchupOutcome:
    """The reader. Without this the branch above changes a value nobody sees."""

    def test_get_status_carries_the_catchup_result(self, tmp_path):
        sentinel = {
            "status": "degraded",
            "unembedded_unknown": (
                embedding_catchup.UnembeddedResult.NO_VECTOR_TABLE
            ),
        }
        memory_api = _live("memory_api")
        with patch.object(memory_api, "_ensure_ready"), patch.object(
            memory_api, "get_embedding_catchup_status", return_value=sentinel
        ):
            status = memory_api.PACTMemory(
                db_path=tmp_path / "probe.db"
            ).get_status()

        assert status["embedding_catchup"] == sentinel, (
            "get_status must surface the catch-up outcome; cmd_status renders "
            "this dict, and it is the only place a caller meets the answer"
        )

    def test_the_accessor_returns_none_before_any_catchup_has_run(self):
        """None is 'has not run', which is NOT the same as 'nothing outstanding'."""
        memory_init = _live("memory_init")
        with patch.object(memory_init, "_last_catchup_result", None):
            assert memory_init.get_embedding_catchup_status() is None
