"""
Location: pact-plugin/tests/test_embedding_status_contract.py

Summary: Pins the contract of `PACTMemory._store_embedding` — one test per KIND
of exit, plus the condition-keyed removal of a vector that would otherwise go
stale. These are the tests the existing suite could not provide: it was written
against the old `bool` return and cannot distinguish a correct reason code from
a wrong one.

Used by/with:
- skills/pact-memory/scripts/memory_api.py: the contract under test.
- skills/pact-memory/scripts/search.py: supplies the capability the reason code
  reports, so save and search cannot report different things.

THE THREE KINDS, and they are kinds rather than lines because keying on line
numbers would re-introduce the list that section 4.1 exists to remove:
  CAPABILITY — this process cannot embed at all. Reported, because a caller can
               act on it.
  INPUT      — this record has nothing to embed. NOT reported: it is a property
               of the record, not of the system, and its author just caused it.
  FAULT      — storing raised. Reported.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.memory_api import PACTMemory


@pytest.fixture
def mem():
    return PACTMemory(project_id="test-project", session_id="test-session")


@pytest.fixture
def conn():
    return MagicMock()


def _memory(text_field: str = "some embeddable context") -> dict:
    return {"context": text_field, "project_id": "test-project"}


class TestCapabilityExits:
    """CAPABILITY: the process cannot embed. Must be reported."""

    def test_extensions_unavailable_reports_degraded(self, mem, conn):
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", False), \
             patch("scripts.memory_api.get_search_capabilities",
                   return_value={"search_mode": "keyword"}):
            result = mem._store_embedding(conn, "mem-1", _memory())

        assert result == "degraded:keyword"

    def test_embedding_generation_unavailable_reports_degraded(self, mem, conn):
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value="text"), \
             patch("scripts.memory_api.generate_embedding", return_value=None), \
             patch("scripts.memory_api.get_search_capabilities",
                   return_value={"search_mode": "keyword"}):
            result = mem._store_embedding(conn, "mem-1", _memory())

        assert result == "degraded:keyword"

    def test_reason_code_carries_the_search_paths_own_mode(self, mem, conn):
        """The code must come from get_search_capabilities, not a second predicate.

        If a save-side predicate were ever introduced, this test would keep
        passing on the literal 'keyword' while the two drifted apart — so it
        pins an UNUSUAL mode value that only the real call can produce.
        """
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", False), \
             patch("scripts.memory_api.get_search_capabilities",
                   return_value={"search_mode": "sentinel-mode"}):
            result = mem._store_embedding(conn, "mem-1", _memory())

        assert result == "degraded:sentinel-mode"


class TestInputExit:
    """INPUT: nothing to embed. Correct, and deliberately NOT reported."""

    def test_no_embeddable_text_reports_nothing(self, mem, conn):
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value=""), \
             patch.object(PACTMemory, "_drop_existing_vector", return_value=True):
            result = mem._store_embedding(conn, "mem-1", _memory(""))

        assert result is None, (
            "an empty record is not a degraded system; reporting it would tell "
            "the caller the process cannot embed, which is false"
        )


class TestFaultExit:
    """FAULT: storing raised. Reported, and the row is left alone."""

    def test_storage_failure_reports_fault(self, mem, conn):
        conn.execute.side_effect = RuntimeError("disk went away")
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value="text"), \
             patch("scripts.memory_api.generate_embedding", return_value=[0.1] * 256):
            result = mem._store_embedding(conn, "mem-1", _memory())

        assert result == "fault"

    def test_fault_does_not_drop_the_vector(self, mem, conn):
        """The handler wraps the insert AND the commit, so it can be reached
        after a successful write. Dropping here could destroy a good vector."""
        conn.commit.side_effect = RuntimeError("commit failed after write")
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value="text"), \
             patch("scripts.memory_api.generate_embedding", return_value=[0.1] * 256), \
             patch.object(PACTMemory, "_drop_existing_vector") as drop:
            mem._store_embedding(conn, "mem-1", _memory())

        drop.assert_not_called()


class TestSuccess:
    def test_stored_vector_reports_nothing(self, mem, conn):
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value="text"), \
             patch("scripts.memory_api.generate_embedding", return_value=[0.1] * 256):
            result = mem._store_embedding(conn, "mem-1", _memory())

        assert result is None


class TestStaleVectorIsRemoved:
    """The condition-keyed remedy: no vector may survive describing old text.

    A missing vector makes a record invisible to semantic search. A STALE one
    makes it findable, confidently, for the wrong query — the worse failure,
    and the one an `update()` produces when re-embedding fails.

    RED ARM: against the pre-change code (`6b2d1b4c^`) `_store_embedding`
    returned a bare bool and never deleted, so both tests below fail — the
    first on the missing method, the second because no DELETE is issued.
    """

    def test_input_exit_drops_an_existing_vector(self, mem, conn):
        """An update that empties the text must not leave the old vector."""
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value=""), \
             patch.object(PACTMemory, "_drop_existing_vector") as drop:
            mem._store_embedding(conn, "mem-42", _memory(""))

        drop.assert_called_once()
        assert drop.call_args[0][1] == "mem-42"

    def test_generation_failure_drops_an_existing_vector(self, mem, conn):
        with patch("scripts.memory_api.SQLITE_EXTENSIONS_ENABLED", True), \
             patch("scripts.memory_api.generate_embedding_text", return_value="text"), \
             patch("scripts.memory_api.generate_embedding", return_value=None), \
             patch("scripts.memory_api.get_search_capabilities",
                   return_value={"search_mode": "keyword"}), \
             patch.object(PACTMemory, "_drop_existing_vector") as drop:
            mem._store_embedding(conn, "mem-42", _memory())

        drop.assert_called_once()
        assert drop.call_args[0][1] == "mem-42"

    def test_drop_issues_a_delete_keyed_on_the_memory_id(self, mem, conn):
        """Pins the statement itself, so the helper cannot silently no-op."""
        with patch.dict("sys.modules", {"sqlite_vec": MagicMock()}):
            assert mem._drop_existing_vector(conn, "mem-42") is True

        sql, params = conn.execute.call_args[0]
        assert "DELETE" in sql.upper() and "vec_memories" in sql
        assert params == ("mem-42",)

    def test_drop_reports_false_when_the_vector_table_is_unreachable(self, mem, conn):
        """Without the extension a vec0 virtual table cannot be reached at all,
        so the drop is IMPOSSIBLE rather than skipped. The caller is told."""
        conn.enable_load_extension.side_effect = RuntimeError("no extension support")

        assert mem._drop_existing_vector(conn, "mem-42") is False


class TestCliSuccessEnvelopeCarriesTheStatus:
    """The CLI is the only consumer most callers have.

    If the API captures the reason and the envelope drops it, a command-line
    caller still receives unqualified success and R3 is unfinished where it
    matters most.
    """

    def _run_cmd_save(self, last_status):
        import json as _json
        from types import SimpleNamespace
        from scripts import cli

        fake = MagicMock()
        fake.save.return_value = "mem-1"
        fake.last_embedding_status = last_status

        captured = {}
        with patch.object(cli, "PACTMemory", return_value=fake), \
             patch.object(cli, "_success", side_effect=lambda r: captured.setdefault("r", r)):
            cli.cmd_save(
                SimpleNamespace(stdin=False, json_data=_json.dumps({"context": "c"}),
                                no_sync=False),
                db_path=None,
            )
        return captured["r"]

    def test_degraded_save_reports_its_status(self):
        result = self._run_cmd_save("degraded:keyword")
        assert result["memory_id"] == "mem-1"
        assert result["embedding_status"] == "degraded:keyword"

    def test_fault_is_reported_too(self):
        assert self._run_cmd_save("fault")["embedding_status"] == "fault"

    def test_clean_save_omits_the_field_entirely(self):
        """Nothing to report must stay silent, so the common case is unchanged
        and no caller has to interpret a null."""
        result = self._run_cmd_save(None)
        assert result == {"memory_id": "mem-1"}
        assert "embedding_status" not in result
