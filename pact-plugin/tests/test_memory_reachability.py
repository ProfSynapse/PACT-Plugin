"""Verification arms for the agent-memory reachability checker.

Not the comprehensive suite. Each arm here fails if one load-bearing clause of
the reachability rule is dropped, and every fixture is synthetic — the repo
holds no agent-memory-shaped material and a test against a real tree would
assert a number that moves between sessions.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import memory_reachability as mr  # noqa: E402


def _tree(root):
    """One index, one named satellite that names a second, one named archive.

    Six leaves, each reachable by a DIFFERENT key or not at all, so an arm that
    drops one key reddens rather than passing on a sibling's evidence.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "MEMORY.md").write_text(
        "# Index\n"
        "> Satellites: `MEMORY-topics.md`; retired in `MEMORY-archive-old.md`.\n"
        "\n"
        "## Rules\n"
        "- [By filename](feedback_by_filename.md)\n"
        "- [[by_wikilink_stem]]\n",
        encoding="utf-8",
    )
    (root / "MEMORY-topics.md").write_text(
        "see also `MEMORY-second-hop.md`\n- [[by-hyphen-spelling]]\n", encoding="utf-8")
    (root / "MEMORY-second-hop.md").write_text(
        "reached only at the second hop: by frontmatter name\n", encoding="utf-8")
    (root / "MEMORY-archive-old.md").write_text(
        "- [Retired](feedback_archived_only.md)\n", encoding="utf-8")

    (root / "feedback_by_filename.md").write_text("x", encoding="utf-8")
    (root / "feedback_by_wikilink_stem.md").write_text("x", encoding="utf-8")
    (root / "feedback_by_hyphen_spelling.md").write_text("x", encoding="utf-8")
    (root / "feedback_frontmatter.md").write_text(
        "---\nname: by frontmatter name\n---\nx", encoding="utf-8")
    (root / "feedback_archived_only.md").write_text("x", encoding="utf-8")
    (root / "feedback_planted_orphan.md").write_text(
        "---\nname: nobody_points_here\n---\nx", encoding="utf-8")
    return root


def test_planted_orphan_is_the_only_unreachable(tmp_path):
    """The acceptance bar: it must find a planted orphan and nothing else."""
    result = mr.scan(_tree(tmp_path / "agent"))
    assert [p.name for p in result.unreachable] == ["feedback_planted_orphan.md"]


def test_archive_only_is_not_reported_as_an_orphan(tmp_path):
    """Collapsing the tiers condemns compaction for working correctly."""
    result = mr.scan(_tree(tmp_path / "agent"))
    assert [p.name for p in result.archive_only] == ["feedback_archived_only.md"]
    assert "feedback_archived_only.md" not in [p.name for p in result.unreachable]


def test_root_discovery_reaches_a_fixed_point(tmp_path):
    """A satellite naming another satellite. One level is not enough."""
    result = mr.scan(_tree(tmp_path / "agent"))
    assert "MEMORY-second-hop.md" in [p.name for p in result.roots]
    # And the leaf that only that satellite names is live, not an orphan.
    assert "feedback_frontmatter.md" in [p.name for p in result.live_reachable]


def test_an_unnamed_satellite_and_its_exclusive_leaf_are_both_orphans(tmp_path):
    """Globbing roots would silently promote it and certify its targets."""
    root = _tree(tmp_path / "agent")
    (root / "MEMORY-unnamed.md").write_text("- [Y](feedback_only_here.md)\n", encoding="utf-8")
    (root / "feedback_only_here.md").write_text("x", encoding="utf-8")
    names = [p.name for p in mr.scan(root).unreachable]
    assert "MEMORY-unnamed.md" in names and "feedback_only_here.md" in names


def test_a_pointer_past_the_cut_is_reported(tmp_path):
    """In the file and out of context is its own tier, invisible to a whole-file read."""
    root = tmp_path / "agent"
    root.mkdir(parents=True)
    filler = "\n".join("- filler line {0}".format(i) for i in range(mr.MAX_LINES + 5))
    (root / "MEMORY.md").write_text(
        "# Index\n" + filler + "\n- [Late](feedback_past_the_cut.md)\n", encoding="utf-8")
    (root / "feedback_past_the_cut.md").write_text("x", encoding="utf-8")
    result = mr.scan(root)
    assert [p.name for p in result.past_the_cut] == ["feedback_past_the_cut.md"]


def test_a_directory_with_no_index_is_not_applicable(tmp_path):
    """Not an error, and not a fully orphaned directory."""
    root = tmp_path / "empty"
    root.mkdir()
    (root / "feedback_stray.md").write_text("x", encoding="utf-8")
    result = mr.scan(root)
    assert result.not_applicable and result.unreachable == ()


def test_utf16_units_are_not_code_points(tmp_path):
    """`len()` undercounts an astral character by exactly one per occurrence."""
    assert mr.utf16_units("\U0001F511") == 2
    assert len("\U0001F511") == 1


def test_the_emitted_anchor_is_a_byte_exact_slice_of_the_raw_index(tmp_path):
    """The matching haystack is normalised; an anchor taken from it never matches."""
    root = _tree(tmp_path / "agent")
    block = mr.emit_edit(mr.scan(root))
    raw = (root / "MEMORY.md").read_text(encoding="utf-8")
    assert block is not None and not block.startswith("REFUSED")
    anchor = block.split("old_string:\n", 1)[1].split("\n\nnew_string:", 1)[0]
    assert anchor in raw, "anchor must be a raw slice, not normalised text"
    # The NEIGHBOUR, not the heading: the last entry line, so placement is exact.
    assert anchor.strip().startswith("-")


def test_a_named_section_anchors_inside_that_section(tmp_path):
    """The agent names the topic; the tool computes the anchor."""
    root = _tree(tmp_path / "agent")
    block = mr.emit_edit(mr.scan(root), "## Rules")
    anchor = block.split("old_string:\n", 1)[1].split("\n\nnew_string:", 1)[0]
    assert anchor.strip() == "- [[by_wikilink_stem]]"


def test_an_empty_named_section_anchors_on_its_heading(tmp_path):
    """With no entries to land in front of, heading and section-end coincide."""
    root = _tree(tmp_path / "agent")
    index = root / "MEMORY.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n## Fresh\n", encoding="utf-8")
    block = mr.emit_edit(mr.scan(root), "## Fresh")
    anchor = block.split("old_string:\n", 1)[1].split("\n\nnew_string:", 1)[0]
    assert anchor.strip() == "## Fresh"


def test_a_section_past_the_cut_is_refused(tmp_path):
    """Placing a pointer there would create the condition this tool reports."""
    root = tmp_path / "agent"
    root.mkdir(parents=True)
    filler = "\n".join("- filler line {0}".format(i) for i in range(mr.MAX_LINES + 5))
    (root / "MEMORY.md").write_text("# Index\n" + filler + "\n## Late\n", encoding="utf-8")
    (root / "feedback_orphan.md").write_text("x", encoding="utf-8")
    block = mr.emit_edit(mr.scan(root), "## Late")
    assert block.startswith("REFUSED") and "past the loaded prefix" in block


def test_an_unknown_heading_is_refused(tmp_path):
    root = _tree(tmp_path / "agent")
    assert mr.emit_edit(mr.scan(root), "## Nope").startswith("REFUSED")


def test_emit_is_silent_on_a_clean_tree(tmp_path):
    root = _tree(tmp_path / "agent")
    (root / "feedback_planted_orphan.md").unlink()
    assert mr.emit_edit(mr.scan(root)) is None


def test_a_missing_directory_is_a_precondition_failure(tmp_path):
    with pytest.raises(mr.PreconditionError):
        mr.scan(tmp_path / "nope")


def test_the_report_refuses_to_write_into_the_scanned_directory(tmp_path):
    root = _tree(tmp_path / "agent")
    assert mr.main([str(root), "--quiet", "--report", str(root / "out.json")]) == 2
    assert not (root / "out.json").exists()
