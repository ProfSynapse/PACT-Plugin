"""Verification arms for the agent-memory reachability checker.

Not the comprehensive suite. Each arm here is tied to one load-bearing clause of
the reachability rule, and every fixture is synthetic — the repo
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

    Seven leaves, each reachable by a DIFFERENT key or not at all, so an arm
    that drops one key reddens rather than passing on a sibling's evidence.

    THE POINTER TEXT MUST NOT CONTAIN ANY OTHER KEY OF THE LEAF IT NAMES. An
    earlier version pointed at the frontmatter leaf with prose containing the
    bare word `frontmatter`, which is that same leaf's prefix-stripped key -- so
    the frontmatter key had no coverage through `scan()` at all, and the
    prefix-strip arm was passing on the sibling's evidence this docstring warns
    about. Both now have their own leaf and their own non-overlapping pointer.
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
    # The new pointer goes in a SATELLITE, not the index: anchor arms depend on
    # the index's last entry line, so adding one there moves their evidence.
    (root / "MEMORY-topics.md").write_text(
        "see also `MEMORY-second-hop.md`\nalso stripped_prefix\n"
        "- [[by-hyphen-spelling]]\n", encoding="utf-8")
    (root / "MEMORY-second-hop.md").write_text(
        "reached only at the second hop: a leaf named in its own header\n", encoding="utf-8")
    (root / "MEMORY-archive-old.md").write_text(
        "- [Retired](feedback_archived_only.md)\n", encoding="utf-8")

    (root / "feedback_by_filename.md").write_text("x", encoding="utf-8")
    (root / "feedback_by_wikilink_stem.md").write_text("x", encoding="utf-8")
    (root / "feedback_by_hyphen_spelling.md").write_text("x", encoding="utf-8")
    # Reached ONLY by its frontmatter name: neither its filename, its stem, nor
    # its prefix-stripped stem appears in any root.
    (root / "feedback_frontmatter.md").write_text(
        "---\nname: a leaf named in its own header\n---\nx", encoding="utf-8")
    # Reached ONLY by its prefix-stripped stem.
    (root / "feedback_stripped_prefix.md").write_text("x", encoding="utf-8")
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
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root), "## Rules"))
    assert anchor.strip() == "- [[by_wikilink_stem]]"


def test_an_empty_named_section_anchors_on_its_heading(tmp_path):
    """With no entries to land in front of, heading and section-end coincide."""
    root = _tree(tmp_path / "agent")
    index = root / "MEMORY.md"
    index.write_text(index.read_text(encoding="utf-8") + "\n## Fresh\n", encoding="utf-8")
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root), "## Fresh"))
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


# ---------------------------------------------------------------------------
# Predicate-level arms.
#
# Every arm above drives scan() end to end, so a predicate detail no fixture
# happens to exercise is invisible to all of them. These four call the predicate
# directly. Measured against the 31 arms in this file: deleting re.escape,
# deleting re.IGNORECASE, widening the boundary classes to \b, dropping the
# frontmatter key, and dropping the prefix strip are EACH killed, every one by
# the arm written for it.
#
# State the arm count beside any such result. An earlier version of this block
# reported a 16-arm measurement as current fact, and it was still being read as
# current after the suite had grown past it.
#
# Mutating this module: disable bytecode caching (PYTHONDONTWRITEBYTECODE=1). A
# mutation that preserves the file's byte length, written in a fast loop, lands
# in the same mtime second and is served stale from __pycache__ -- reporting
# SURVIVED with the mutation sitting on disk. Kills are safe; survivors lie.


def test_the_key_is_escaped_rather_than_compiled():
    """Real frontmatter names carry '+'; unescaped it is a quantifier."""
    assert not mr.mentions("ab", "a+b")


def test_matching_ignores_case():
    """Roughly a fifth of real names are prose titles with capitals."""
    assert mr.mentions("SESSION_HOOK_PATTERNS", "session_hook_patterns")


def test_a_leading_dot_is_not_a_boundary():
    """\\b would accept it, and a key would match inside a longer dotted token."""
    assert not mr.mentions("other.key", "key")


def test_the_frontmatter_name_is_a_key(tmp_path):
    """The key that carries pointers written as bare prose."""
    leaf = tmp_path / "feedback_x.md"
    leaf.write_text("---\nname: A Prose Title\n---\nx", encoding="utf-8")
    assert mr.normalise("A Prose Title") in mr.keys_for(leaf)


def test_type_prefixes_are_the_four_memory_types():
    """The tuple's CLOSEDNESS is the whole argument for four keys over six.

    Nothing in this repo defines the memory-type vocabulary -- it comes from the
    platform -- so there is nothing to derive this from and this pins the
    literals instead. Weaker than a derivation, and it makes a fifth type a
    deliberate edit rather than silent drift.
    """
    assert mr.TYPE_PREFIXES == ("feedback_", "project_", "reference_", "user_")


def _emitted(block):
    # Assert the shape before splitting on it. A REFUSED block, or None, would
    # otherwise raise IndexError here -- which reddens the arm without telling
    # you whether the SUBJECT failed or this helper did. Measured: the
    # normalised-anchor mutant killed the round-trip arm by IndexError, and a
    # kill by the wrong mechanism is indistinguishable from a real one in a
    # pass/fail summary.
    assert block is not None and not block.startswith("REFUSED"), block
    assert "old_string:\n" in block and "\n\nnew_string:\n" in block, block
    anchor = block.split("old_string:\n", 1)[1].split("\n\nnew_string:\n", 1)[0]
    new = block.split("\n\nnew_string:\n", 1)[1].split("\n\nThe file may", 1)[0]
    return anchor, new


def test_applying_the_edit_closes_the_orphan_and_then_emits_nothing(tmp_path):
    """The only arm that exercises the emit path end to end rather than its string.

    Round trip and idempotence in one: everything else here asserts what the
    block SAYS, and a block can be well-formed and still not close the finding.
    """
    root = _tree(tmp_path / "agent")
    index = root / "MEMORY.md"
    raw = index.read_text(encoding="utf-8")
    anchor, new = _emitted(mr.emit_edit(mr.scan(root)))
    assert raw.count(anchor) == 1
    index.write_text(raw.replace(anchor, new), encoding="utf-8")

    assert mr.scan(root).unreachable == ()
    assert mr.emit_edit(mr.scan(root)) is None


def test_the_anchor_fixture_still_discriminates_a_normalised_anchor(tmp_path):
    """Pins the fixture property the raw-bytes guard's kill depends on.

    normalise() maps '-' to '_' and lowercases. If the anchor region ever loses
    every character normalise() changes -- switching the '-' bullets to '*' is
    enough -- then normalised text and raw text are identical there, a
    normalised anchor still matches, and the guard above silently stops being
    tested while staying green. Measured, not hypothetical.
    """
    root = _tree(tmp_path / "agent")
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root)))
    assert mr.normalise(anchor) != anchor


def test_the_unnamed_anchor_is_the_LAST_entry_of_the_loaded_prefix(tmp_path):
    """Separates the heading-absent path from the heading-given one.

    Measured: mutating `entries[-1]` to `entries[0]` reddened nothing, while
    blanking the heading lookup reddened only the three heading arms. The two
    paths were separable in the code and not in the suite, which is the shape
    where a shared kill proves nothing. This is the missing half.
    """
    root = _tree(tmp_path / "agent")
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root)))
    assert anchor.endswith("[[by_wikilink_stem]]")


def test_a_duplicated_section_entry_expands_the_anchor(tmp_path):
    """Uniqueness expansion on the heading-GIVEN path.

    The expansion loop is shared with the heading-absent path, but only a named
    section can put a duplicated last entry in front of it -- the absent path
    anchors on the tail of the whole prefix, where a duplicate downstream cannot
    occur. So this exercises the interaction, not new code.
    """
    root = tmp_path / "agent"
    root.mkdir()
    (root / "MEMORY.md").write_text(
        "# I\n"
        "## Rules\n"
        "- [a](feedback_a.md)\n"
        "- [dup](feedback_dup.md)\n"
        "## Other\n"
        "- [dup](feedback_dup.md)\n",
        encoding="utf-8",
    )
    for name in ("feedback_a.md", "feedback_dup.md", "feedback_orphan.md"):
        (root / name).write_text("x", encoding="utf-8")

    anchor, _ = _emitted(mr.emit_edit(mr.scan(root), "## Rules"))
    raw = (root / "MEMORY.md").read_text(encoding="utf-8")
    assert "\n" in anchor, "a duplicated last entry must force expansion"
    assert raw.count(anchor) == 1


def test_the_size_cut_returns_a_line_aligned_prefix_within_the_cap():
    """The size branch: an index under the line cap but over the size cap.

    Kills two mutants no other arm sees -- dropping the size cut entirely, and
    dropping the newline snap-back. Both left every other arm green, because the
    filler fixtures above sit near 3.3k units against a 25000 ceiling, so the
    early return fires and this whole branch never executes.

    The snap-back is NOT diagnostic-only. emit_edit bounds anchor placement by
    len(truncate_as_loaded(raw).splitlines()), so a prefix ending mid-line makes
    that bound one too many and the emitted pointer lands past the cut -- the
    condition this tool exists to report.
    """
    raw = "# Index\n" + "".join(
        "- [entry {0}](feedback_e{0}.md) - {1}\n".format(i, "x" * 200) for i in range(120))
    assert len(raw.splitlines()) < mr.MAX_LINES, "must trip the SIZE cap, not the line cap"
    assert mr.utf16_units(raw) > mr.MAX_UNITS

    loaded = mr.truncate_as_loaded(raw)
    assert mr.utf16_units(loaded) <= mr.MAX_UNITS, "the size cut must actually cut"
    assert loaded.endswith("\n") and raw.startswith(loaded), "a line-aligned prefix of the raw text"


def test_the_emitted_anchor_stays_inside_the_loaded_prefix_under_a_size_cut(tmp_path):
    """The consequence the arm above protects: placement, not just truncation."""
    root = tmp_path / "agent"
    root.mkdir(parents=True)
    (root / "MEMORY.md").write_text("# Index\n" + "".join(
        "- [entry {0}](feedback_e{0}.md) - {1}\n".format(i, "x" * 200) for i in range(120)),
        encoding="utf-8")
    for i in range(120):
        (root / "feedback_e{0}.md".format(i)).write_text("x", encoding="utf-8")
    (root / "feedback_orphan.md").write_text("x", encoding="utf-8")

    raw = (root / "MEMORY.md").read_text(encoding="utf-8")
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root)))
    through = raw[: raw.index(anchor) + len(anchor)] + "\n"
    assert mr.utf16_units(through) <= mr.MAX_UNITS, "a pointer placed here is written and never read"


def test_the_bare_token_diagnostic_counts_the_leaves_carried_by_prose(tmp_path):
    """Computed, rendered and serialised; asserted nowhere until now.

    feedback_stripped_prefix is carried by the bare token `stripped_prefix`, and
    feedback_frontmatter by its frontmatter name in a satellite's prose. Neither
    is reached through link syntax, which is what this diagnostic counts.
    """
    result = mr.scan(_tree(tmp_path / "agent"))
    assert result.bare_token_only == 2


def test_an_unnamed_satellite_is_listed_in_the_glob_versus_follow_diagnostic(tmp_path):
    """Zero is the expected reading, which is why a non-zero one needs an arm."""
    root = _tree(tmp_path / "agent")
    assert mr.scan(root).unreached_index_files == ()
    (root / "MEMORY-unnamed.md").write_text("- [Y](feedback_only_here.md)\n", encoding="utf-8")
    assert [p.name for p in mr.scan(root).unreached_index_files] == ["MEMORY-unnamed.md"]


def test_the_index_shaped_and_archive_vocabularies_are_closed():
    """Same argument as TYPE_PREFIXES: nothing here derives these, so pin them.

    The fixture exercises one member of each, so dropping any other member is
    invisible to every behavioural arm.
    """
    assert mr.INDEX_SHAPED == ("MEMORY-", "INDEX_", "ARCHIVE")
    assert mr.ARCHIVE_MARKERS == ("archive", "pre-compact", "precompact")


def test_the_size_cut_accounts_for_the_line_endings_actually_on_disk(tmp_path):
    """A CRLF index costs one more unit per line, so fewer lines fit under the cap.

    Only reachable now that _read is byte-faithful. While universal-newline
    translation ran, the cut was computed on text one character per line shorter
    than the file, so the anchor could sit past the very cap it respects --
    measured here at 25083 against a 25000 ceiling, versus 24897 byte-faithful.

    This is the only arm that exercises the size branch against line endings
    rather than against length alone.
    """
    root = tmp_path / "agent"
    root.mkdir(parents=True)
    body = "".join(
        "- [entry {0}](feedback_e{0}.md) - {1}\r\n".format(i, "x" * 150) for i in range(190))
    (root / "MEMORY.md").write_bytes(("# Index\r\n" + body).encode("utf-8"))
    for i in range(190):
        (root / "feedback_e{0}.md".format(i)).write_text("x", encoding="utf-8")
    (root / "feedback_orphan.md").write_text("x", encoding="utf-8")

    raw = (root / "MEMORY.md").read_text(encoding="utf-8", newline="")
    assert len(raw.splitlines()) < mr.MAX_LINES, "must trip the SIZE cap, not the line cap"
    anchor, _ = _emitted(mr.emit_edit(mr.scan(root)))
    through = raw[: raw.index(anchor) + len(anchor)]
    assert mr.utf16_units(through) <= mr.MAX_UNITS


def _crlf_tree(root, duplicated):
    """A CRLF index whose last section entry is unique, or duplicated downstream."""
    root.mkdir(parents=True, exist_ok=True)
    tail = "## Other\r\n- [dup](feedback_dup.md)\r\n" if duplicated else ""
    (root / "MEMORY.md").write_bytes(
        ("# I\r\n## Rules\r\n- [a](feedback_a.md)\r\n- [dup](feedback_dup.md)\r\n"
         + tail).encode("utf-8"))
    for name in ("feedback_a.md", "feedback_dup.md", "feedback_orphan.md"):
        (root / name).write_text("x", encoding="utf-8")
    return root


def test_a_crlf_index_emits_a_single_line_anchor_and_refuses_a_joined_one(tmp_path):
    """On CRLF the outcome splits by anchor SHAPE, not by the file's encoding.

    A `\\r` never appears INSIDE a single-line anchor -- splitlines() consumes it
    as the terminator -- so that shape round-trips and must still emit. It is
    only the JOIN that differs: "\\n".join() puts a bare newline where the file
    has a pair, so an expanded anchor is not a raw slice and must refuse.

    Both halves are needed. Asserting only that CRLF refuses would be false for
    the common shape, and would pass for the wrong reason.
    """
    emitted = mr.emit_edit(mr.scan(_crlf_tree(tmp_path / "unique", False)), "## Rules")
    anchor, _ = _emitted(emitted)
    assert anchor.encode("utf-8") in (tmp_path / "unique" / "MEMORY.md").read_bytes(), (
        "a single-line anchor must match the bytes an agent will edit")

    joined = mr.emit_edit(mr.scan(_crlf_tree(tmp_path / "dup", True)), "## Rules")
    # Refusing is the decision, not a stopgap. Slicing raw by offsets would make
    # the anchor byte-exact for every separator and retire this branch; that is
    # tracked separately, and if it lands this arm is expected to change.
    assert joined.startswith("REFUSED"), "an expanded anchor is not a raw slice; fail closed"
