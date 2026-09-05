"""
Location: pact-plugin/tests/test_working_memory_projection.py
Summary: Verification tests for rebuilding the Working Memory section of
         CLAUDE.md from pact-memory records rather than prepending one save at
         a time. Covers the formatter's `created_at` parameter (a projected
         entry carries the record's own date, a save still carries now) and
         the parser that turns a stored `created_at` into that stamp.

         Every write in this file goes to a file under `tmp_path`. No arm
         resolves a CLAUDE.md ambiently.
Used by: pytest.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# skills/pact-memory is the package root, so `scripts.*` imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "pact-memory"))

from scripts.working_memory import (  # noqa: E402
    _format_memory_entry,
    _record_timestamp,
)


def _header(entry: str) -> str:
    return entry.split("\n", 1)[0]


class TestFormatterCreatedAt:
    """`_format_memory_entry` stamps the header from `created_at` when given."""

    def test_created_at_renders_as_the_header(self):
        stamp = datetime(2024, 3, 7, 4, 5, 59)
        entry = _format_memory_entry({"context": "ctx"}, created_at=stamp)
        assert _header(entry) == "### 2024-03-07 04:05"

    def test_without_created_at_the_header_is_now(self):
        before = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        entry = _format_memory_entry({"context": "ctx"})
        after = datetime.now(timezone.utc)
        rendered = datetime.strptime(_header(entry), "### %Y-%m-%d %H:%M")
        rendered = rendered.replace(tzinfo=timezone.utc)
        assert before <= rendered <= after

    def test_created_at_changes_only_the_header(self):
        """Control: the same record renders the same body under either stamp."""
        memory = {"context": "ctx", "goal": "g", "decisions": ["d1", "d2"]}
        stamped = _format_memory_entry(memory, ["a.py"], "a" * 32,
                                       created_at=datetime(2020, 1, 1))
        unstamped = _format_memory_entry(memory, ["a.py"], "a" * 32)
        assert _header(stamped) == "### 2020-01-01 00:00"
        assert _header(stamped) != _header(unstamped)
        assert stamped.split("\n", 1)[1] == unstamped.split("\n", 1)[1]


class TestRecordTimestamp:
    """The stored `created_at` reaches the header in both forms it takes."""

    @pytest.mark.parametrize("stored", [
        "2026-09-05 09:20:42",   # as SQLite `datetime('now')` writes it
        "2026-09-05T09:20:42",   # as `MemoryObject.to_dict()` emits it
    ])
    def test_both_stored_forms_render_the_same_header(self, stored):
        entry = _format_memory_entry(
            {"context": "ctx"}, created_at=_record_timestamp(stored)
        )
        assert _header(entry) == "### 2026-09-05 09:20"

    def test_datetime_and_none_pass_through(self):
        stamp = datetime(2026, 9, 5, 9, 20)
        assert _record_timestamp(stamp) is stamp
        assert _record_timestamp(None) is None

    def test_unparseable_value_falls_back_to_now_and_still_renders(self):
        assert _record_timestamp("not a date") is None
        before = datetime.now(timezone.utc) - timedelta(minutes=1)
        entry = _format_memory_entry(
            {"context": "still here"},
            created_at=_record_timestamp("not a date"),
        )
        rendered = datetime.strptime(_header(entry), "### %Y-%m-%d %H:%M")
        assert rendered.replace(tzinfo=timezone.utc) >= before
        assert "**Context**: still here" in entry
