"""
Location: pact-plugin/tests/test_embedding_status_wiring.py

Summary: Pins the JOIN between the reason code `_store_embedding` returns and
the caller-visible `PACTMemory.last_embedding_status`. Without these tests the
join is covered by nothing, and the change set's headline behaviour can be
reverted with the whole suite still green.

Used by/with:
- skills/pact-memory/scripts/memory_api.py: `save`, `update`, and the
  `last_embedding_status` property — the three parts of the join.
- tests/test_embedding_status_contract.py: covers the PRODUCER in isolation.
- tests/test_embedding_status_contract.py::TestCliSuccessEnvelopeCarriesTheStatus:
  covers the CONSUMER against a MagicMock.

WHY THIS FILE EXISTS. The contract tests call `_store_embedding` directly and
assert its return. The CLI tests replace `PACTMemory` with a MagicMock whose
`last_embedding_status` is assigned by the test itself. So each half is verified
against a stub of the other, and nothing observes the wiring between them. Three
separate mutations of that wiring — dropping the capture in `save`, dropping it
in `update`, and making the property return a constant `None` — were applied
together against the full suite and produced no failure at all. A mocked
consumer cannot detect a producer that never assigns.

WHAT IS STUBBED, AND WHY IT IS NOT THE SEAM UNDER TEST. Two things:

  `_ensure_ready` is neutralised. It sweeps the DEFAULT database and touches a
  marker file under `/tmp`. Neither belongs to this assertion and both are real
  user state, so a test that reached them would be writing outside its sandbox.

  `_store_embedding` is stubbed to return a fixed sentinel. That is deliberate:
  the subject here is whether the caller PUBLISHES what the producer returned,
  not what the producer decides. Stubbing it makes the test independent of
  whether an embedding backend is installed, so it asserts the same thing in
  every environment.

The instance itself is REAL and the property read is REAL. That is the part
that must not be stubbed, because it is the part under test.

EVERY ARM IS PAIRED. A sentinel arm alone would pass against a property that
happened to return that sentinel; a `None` arm alone would pass against a
property stuck at `None` — which is exactly one of the mutations. The two arms
together admit neither.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import memory_api
from scripts.memory_api import PACTMemory


# Unusual enough that it cannot arrive from any real capability probe.
SENTINEL = "degraded:sentinel-wiring-probe"

# Captured at import, before the autouse home-redirect fixture runs, so it names
# the developer's ACTUAL home. Same convention as test_session_discovery_route.
REAL_HOME = Path(os.path.expanduser("~")).resolve()


def _assert_sandboxed(db_path: Path) -> None:
    """Refuse to run outside the sandbox.

    The conftest fixture `_isolate_config_root_to_tmp` redirects `Path.home()`
    into a per-test tmp directory. If that redirect is ever made opt-out for
    this file, these tests must fail loudly rather than quietly drive a real
    PACTMemory against the developer's live memory database.
    """
    assert Path.home().resolve() != REAL_HOME, (
        "REFUSING to run: Path.home() is the real home, so the autouse "
        "redirect is not in effect and this test would reach live user state"
    )
    assert REAL_HOME not in db_path.parents, "database escaped into the real home"


@pytest.fixture
def mem(tmp_path):
    """A real PACTMemory over a throwaway database."""
    db_path = tmp_path / "wiring-probe.db"
    _assert_sandboxed(db_path)
    return PACTMemory(project_id="wiring-probe", session_id="wiring-sess", db_path=db_path)


def _save(mem, status, text="initial context for the wiring probe"):
    """Save through the REAL save(), with the producer pinned to `status`."""
    with patch.object(memory_api, "_ensure_ready", lambda: None), \
         patch.object(PACTMemory, "_store_embedding", return_value=status):
        return mem.save({"context": text}, sync_to_claude=False)


class TestSavePublishesTheReasonCode:
    """`save` must carry the producer's answer out to the caller."""

    def test_save_publishes_a_reason_code(self, mem):
        _save(mem, SENTINEL)

        assert mem.last_embedding_status == SENTINEL, (
            "save() dropped the reason code on the floor — which is the exact "
            "defect this change set exists to remove, in its original form"
        )

    def test_save_publishes_none_when_there_is_nothing_to_report(self, mem):
        """Paired with the arm above.

        Without this arm a property hardcoded to the sentinel would pass; without
        the arm above a property hardcoded to None would pass. One of those is a
        mutation that survived the entire suite.
        """
        _save(mem, None)

        assert mem.last_embedding_status is None


class TestUpdatePublishesTheReasonCode:
    """`update` is the WORSE of the two call sites.

    A save that stores no vector leaves a record merely invisible to semantic
    search. An update that fails to re-embed leaves a vector describing text the
    record no longer contains, which is retrieved confidently for the wrong
    query — so this is the call site where a discarded reason code costs most.
    """

    def test_update_publishes_a_reason_code(self, mem):
        memory_id = _save(mem, None)
        assert mem.last_embedding_status is None, "precondition: a clean save reports nothing"

        with patch.object(memory_api, "_ensure_ready", lambda: None), \
             patch.object(PACTMemory, "_store_embedding", return_value=SENTINEL):
            mem.update(memory_id, {"context": "completely different text now"}, replace=True)

        assert mem.last_embedding_status == SENTINEL, (
            "update() dropped the reason code, so a caller cannot tell a "
            "re-embed failure from a clean update"
        )

    def test_update_publishes_none_when_there_is_nothing_to_report(self, mem):
        memory_id = _save(mem, SENTINEL)
        assert mem.last_embedding_status == SENTINEL, "precondition: the sentinel is live"

        with patch.object(memory_api, "_ensure_ready", lambda: None), \
             patch.object(PACTMemory, "_store_embedding", return_value=None):
            mem.update(memory_id, {"context": "another different text"}, replace=True)

        assert mem.last_embedding_status is None, (
            "a later clean update must CLEAR the previous reason code, or a "
            "caller reads a stale status from an operation that already succeeded"
        )


class TestPropertyIsNotAConstant:
    """The property must reflect stored state rather than return a literal."""

    def test_property_tracks_successive_writes(self, mem):
        memory_id = _save(mem, SENTINEL)
        first = mem.last_embedding_status

        with patch.object(memory_api, "_ensure_ready", lambda: None), \
             patch.object(PACTMemory, "_store_embedding", return_value=None):
            mem.update(memory_id, {"context": "text three"}, replace=True)
        second = mem.last_embedding_status

        assert (first, second) == (SENTINEL, None), (
            "the property returned the same value across two writes with "
            "different outcomes, so it is not reading the stored field"
        )

    def test_a_fresh_instance_reports_nothing(self, tmp_path):
        """No write has happened, so there is nothing to report."""
        fresh = PACTMemory(project_id="wiring-probe", session_id="wiring-sess",
                           db_path=tmp_path / "fresh.db")

        assert fresh.last_embedding_status is None
