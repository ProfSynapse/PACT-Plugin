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

import scripts.working_memory as wm  # noqa: E402
from scripts.working_memory import (  # noqa: E402
    MAX_WORKING_MEMORIES,
    WORKING_MEMORY_TOKEN_BUDGET,
    SyncResult,
    _estimate_tokens,
    _format_memory_entry,
    _record_timestamp,
    project_memories_to_claude_md,
)

_SCAFFOLD = (
    "# Probe\n\n"
    "## Working Memory\n"
    f"{wm.WORKING_MEMORY_COMMENT}\n\n"
    "## Pinned Context\n\nkeep me\n"
)

# The per-entry ceiling `_apply_token_budget` applies before budgeting.
_ENTRY_CEILING = (
    WORKING_MEMORY_TOKEN_BUDGET
    - (MAX_WORKING_MEMORIES - 1) * wm.COMPRESSED_ENTRY_TOKEN_CEILING
)


def _header(entry: str) -> str:
    return entry.split("\n", 1)[0]


def _seed(tmp_path, body: str = _SCAFFOLD):
    target = tmp_path / "project" / "CLAUDE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _section_entries(text: str):
    """The Working Memory section's entries, split on their date headers."""
    section = text.split("## Working Memory\n", 1)[1].split("\n## ", 1)[0]
    return [e.strip() for e in section.split("\n### ")[1:]]


def _record(stamp: str, label: str, **fields):
    return {"id": label * 32, "context": f"{label} context",
            "created_at": stamp, **fields}


def _dense_record(stamp: str, label: str):
    """Every free-text field at its 200-char cut, in 1-char words, so the
    formatted entry estimates far past the per-entry ceiling."""
    dense = "a " * 100
    return _record(
        stamp, label, goal=dense, decisions=[dense], lessons_learned=[dense],
        reasoning_chains=[dense], agreements_reached=[dense],
        disagreements_resolved=[dense],
    )


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


class TestProjectionReplacesTheSection:
    """`project_memories_to_claude_md` writes the section from the list alone."""

    def test_empty_input_is_empty_and_touches_nothing(self, tmp_path):
        target = _seed(tmp_path)
        before = target.read_bytes()
        result = project_memories_to_claude_md([], target=target)
        assert result.reason == SyncResult.EMPTY
        assert target.read_bytes() == before

    def test_the_given_entries_replace_the_hand_written_ones(self, tmp_path):
        target = _seed(tmp_path, _SCAFFOLD.replace(
            "## Pinned Context",
            "### 2025-01-01 01:00\n**Context**: hand one\n\n"
            "### 2024-01-01 01:00\n**Context**: hand two\n\n"
            "## Pinned Context",
        ))
        assert len(_section_entries(target.read_text(encoding="utf-8"))) == 2

        result = project_memories_to_claude_md([
            _record("2026-09-05 09:20:00", "c"),
            _record("2026-09-04 08:10:00", "b"),
            _record("2026-09-03 07:00:00", "a"),
        ], target=target)

        assert result.reason == SyncResult.WROTE
        text = target.read_text(encoding="utf-8")
        entries = _section_entries(text)
        assert [_header(e) for e in entries] == [
            "2026-09-05 09:20", "2026-09-04 08:10", "2026-09-03 07:00",
        ]
        assert "hand one" not in text and "hand two" not in text
        assert "c context" in entries[0] and "**Memory ID**: " + "c" * 32 in entries[0]
        assert text.endswith("## Pinned Context\n\nkeep me\n"), "the rest of the file moved"

    def test_input_past_the_cap_is_cut_to_it(self, tmp_path):
        target = _seed(tmp_path)
        records = [_record(f"2026-01-0{i} 00:00:00", chr(ord("a") + i))
                   for i in range(1, MAX_WORKING_MEMORIES + 3)]
        assert project_memories_to_claude_md(records, target=target)
        entries = _section_entries(target.read_text(encoding="utf-8"))
        assert len(entries) == MAX_WORKING_MEMORIES
        assert _header(entries[0]) == "2026-01-01 00:00"

    def test_the_budget_is_applied_once_across_the_projection(self, tmp_path):
        """Newest entry bounded by the per-entry ceiling and not compressed;
        older entries compressed; section under budget."""
        records = [_dense_record(f"2026-03-0{i} 00:00:00", c)
                   for i, c in ((3, "c"), (2, "b"), (1, "a"))]
        # Non-vacuity: unbudgeted, each entry alone exceeds the ceiling and the
        # three together exceed the section budget.
        raw = [_format_memory_entry(r, None, r["id"]) for r in records]
        assert all(_estimate_tokens(e) > _ENTRY_CEILING for e in raw)
        assert sum(_estimate_tokens(e) for e in raw) > WORKING_MEMORY_TOKEN_BUDGET

        target = _seed(tmp_path)
        assert project_memories_to_claude_md(records, target=target)
        entries = _section_entries(target.read_text(encoding="utf-8"))

        assert len(entries) == 3
        newest, *older = entries
        assert "**Summary**" not in newest
        assert "**Goal**" in newest, "the newest entry was compressed, not cut"
        assert _estimate_tokens("### " + newest) <= _ENTRY_CEILING
        for entry in older:
            assert "**Summary**" in entry and "**Goal**" not in entry
        assert sum(_estimate_tokens("### " + e) for e in entries) <= WORKING_MEMORY_TOKEN_BUDGET


class TestProjectionRunsThroughTheSameWriteSite:
    """The replace arm inherits the write site's certifications."""

    def test_a_target_outside_the_resolved_base_is_refused(
        self, tmp_path, monkeypatch
    ):
        """Containment differential, mirroring the save path's arm: the
        resolver hands back a base that does not contain the file, the atomic
        write raises, the handler reports `failed`, the file is unchanged."""
        target = _seed(tmp_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        before = target.read_bytes()
        monkeypatch.setattr(
            wm, "_resolve_display_claude_md_with_base",
            lambda: (target, elsewhere),
        )

        result = project_memories_to_claude_md([_record("2026-01-01 00:00:00", "a")])

        assert result.reason == SyncResult.FAILED
        assert target.read_bytes() == before

    def test_a_crlf_target_stays_crlf(self, tmp_path, monkeypatch):
        target = tmp_path / "project" / "CLAUDE.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(_SCAFFOLD.replace("\n", "\r\n").encode("utf-8"))
        before = target.read_bytes()
        assert before.count(b"\r\n") > 0
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(target.parent))

        result = project_memories_to_claude_md(
            [_record("2026-01-01 00:00:00", "a", goal="one\r\ntwo")]
        )

        assert result.reason == SyncResult.WROTE
        raw = target.read_bytes()
        assert raw != before, "the write did not happen"
        crlf = raw.count(b"\r\n")
        assert crlf > 0 and raw.count(b"\n") == crlf and raw.count(b"\r\r\n") == 0
