"""
Tests for scripts/archive_pin.py — the archive-on-evict verification step.

Risk tier: CRITICAL. This script's verdict is what /PACT:prune-memory keys
its refuse-or-proceed decision on, and the pin being archived may be the
only remaining copy of the content (CLAUDE.md is gitignored, so there is no
git fallback). A FALSE `ARCHIVED` is the one error that destroys data: the
command acts on it by evicting. The inverse error (falsely refusing) costs
an over-block and loses nothing, so the two directions are NOT symmetric
and the tests here weight the false-positive direction accordingly.

Test strategy, stated because it is load-bearing:

  * At least one test drives the REAL memory CLI end-to-end against a temp
    `--db-path` database. A suite that stubs every subprocess would verify
    the stub, not the archive — the vacuous-verification defect this whole
    feature exists to remove, reproduced one layer down.
  * The failure matrix stubs `_run_memory_cli`, because a real store cannot
    be made to fail on demand in the specific ways that matter.
  * Temp DBs throughout — no test touches the shared store.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))

from helpers import make_claude_md_with_pins, make_pin_entry  # noqa: E402

import archive_pin  # noqa: E402
import pin_caps  # noqa: E402
import staleness  # noqa: E402


# Formats a curator can plausibly hand-write. B, D and E are the ones a
# part-reconstructing extractor mangles; they are here so a regression from
# slicing back to rebuilding fails loudly rather than silently archiving a
# whitespace-normalized variant.
PIN_FORMATS = {
    "canonical": "<!-- pinned: 2026-01-01 -->\n### Alpha\nbody alpha\n",
    "blank_line_before_heading": (
        "<!-- pinned: 2026-01-01 -->\n\n### Beta\nbody beta\n"
    ),
    "leading_ws_on_comment": (
        "  <!-- pinned: 2026-01-01 -->\n### Gamma\nbody gamma\n"
    ),
    "trailing_ws_on_comment": (
        "<!-- pinned: 2026-01-01 -->   \n### Delta\nbody delta\n"
    ),
    "two_blank_lines": (
        "<!-- pinned: 2026-01-01 -->\n\n\n### Epsilon\nbody epsilon\n"
    ),
}


@pytest.fixture
def claude_md(tmp_path, monkeypatch):
    """Write a CLAUDE.md and point the script's resolver at it."""
    def _write(content):
        path = tmp_path / "CLAUDE.md"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(
            archive_pin, "get_project_claude_md_path", lambda: path
        )
        return path
    return _write


def _pinned_body(content):
    """Extract the Pinned Context section body from a full CLAUDE.md."""
    parsed = staleness._parse_pinned_section(content)
    assert parsed is not None, "fixture has no Pinned Context section"
    return parsed[2]


def _two_pin_file():
    return make_claude_md_with_pins([
        make_pin_entry(title="First Pin", body_chars=40, date="2026-01-01"),
        make_pin_entry(title="Second Pin", body_chars=40, date="2026-02-02"),
    ])


class TestExtractPinBlock_Verbatim:
    """The extracted block must be a VERBATIM SLICE of CLAUDE.md.

    This is the property that makes the containment criterion meaningful.
    If the block is already a lossy rendering of the pin, then saving it and
    finding it again proves only that the round-trip preserved a variant —
    all three conjuncts hold while the verdict certifies something that is
    not the pin. The fidelity gap would simply relocate upstream of where
    the criterion looks.
    """

    @pytest.mark.parametrize("label", sorted(PIN_FORMATS))
    def test_slice_is_verbatim_in_source(self, label):
        source = PIN_FORMATS[label]
        pins = pin_caps.parse_pins(source)
        assert pins, f"fixture {label} parsed no pins — test would be vacuous"
        block = archive_pin.extract_pin_block(source, 0, pins)
        assert block in source, (
            f"format {label!r}: extracted block is not a verbatim substring "
            f"of the source. Block={block!r}"
        )

    @pytest.mark.parametrize("label", sorted(PIN_FORMATS))
    def test_slice_carries_the_substance(self, label):
        """Verbatim is necessary but not sufficient — the empty string is
        also a substring. Pin that the block actually carries the heading
        and the body, so a degenerate extractor cannot pass the test above."""
        source = PIN_FORMATS[label]
        pins = pin_caps.parse_pins(source)
        block = archive_pin.extract_pin_block(source, 0, pins)
        assert pins[0].heading in block
        assert pins[0].body.strip() in block
        assert "<!-- pinned:" in block

    def test_blank_line_between_comment_and_heading_survives(self):
        """The specific loss a part-reconstruction introduces. parse_pins
        walks BACKWARD over blank lines to find the date comment, so a
        rebuild drops them; a slice keeps them."""
        source = PIN_FORMATS["blank_line_before_heading"]
        pins = pin_caps.parse_pins(source)
        block = archive_pin.extract_pin_block(source, 0, pins)
        assert "-->\n\n### Beta" in block

    def test_slice_beats_naive_rebuild_on_the_same_input(self):
        """Direct comparison against the alternative implementation.

        This is the test that would have caught the original approach. It
        asserts BOTH that the slice is verbatim for every format AND that a
        rebuild is not — so if someone 'simplifies' the extractor back to
        concatenating parts, this fails with a message naming the formats
        that broke. The rebuild arm is also the non-vacuity control: if it
        ever passed for all five, the hazard would be gone and this whole
        test would be measuring nothing.
        """
        slice_ok, rebuild_ok, rebuild_failures = [], [], []
        for label, source in PIN_FORMATS.items():
            parsed = pin_caps.parse_pins(source)
            pin = parsed[0]
            block = archive_pin.extract_pin_block(source, 0, parsed)
            date_comment = pin.date_comment or ""
            rebuild = (
                f"{date_comment}\n{pin.heading}\n{pin.body}"
                if date_comment else f"{pin.heading}\n{pin.body}"
            )
            slice_ok.append(block in source)
            rebuild_ok.append(rebuild in source)
            if rebuild not in source:
                rebuild_failures.append(label)

        assert all(slice_ok), "slice must be verbatim for EVERY format"
        assert rebuild_failures, (
            "a naive rebuild is verbatim for all formats — the hazard this "
            "extractor defends against no longer exists, so this test is "
            "now vacuous and should be re-aimed or retired"
        )

    def test_slice_includes_the_comment_lines_leading_indentation(self):
        """The span rule starts at the comment LINE's first character, not at
        the comment text. Both are verbatim substrings, so containment alone
        cannot tell them apart — this pins the stricter of the two."""
        source = PIN_FORMATS["leading_ws_on_comment"]
        pins = pin_caps.parse_pins(source)
        block = archive_pin.extract_pin_block(source, 0, pins)
        assert block.startswith("  <!-- pinned:"), (
            f"slice dropped the comment line's indentation: {block[:40]!r}"
        )

    def test_slice_is_not_stripped(self):
        """The block is taken EXACTLY — no strip, rejoin or normalize.

        Dropping the strip is safe and was measured, not assumed: `context`
        is a scalar and escapes the string-list normalization, so a value
        with trailing newlines round-trips byte-exact. Had it been stripped
        in transit, containment would have failed for every archive — an
        over-block on the whole feature rather than an edge case.
        """
        source = (
            "<!-- pinned: 2026-01-01 -->\n### First\nbody one\n\n\n"
            "<!-- pinned: 2026-02-02 -->\n### Second\nbody two\n"
        )
        pins = pin_caps.parse_pins(source)
        block = archive_pin.extract_pin_block(source, 0, pins)
        assert block in source
        assert block.endswith("\n\n\n"), (
            f"separator blank lines were stripped from the span: "
            f"{block[-12:]!r}"
        )

    def test_index_out_of_range_is_unevaluable(self):
        source = PIN_FORMATS["canonical"]
        pins = pin_caps.parse_pins(source)
        with pytest.raises(archive_pin._Unevaluable):
            archive_pin.extract_pin_block(source, 5, pins)

    def test_second_pin_slice_does_not_bleed_into_the_first(self):
        """Block boundaries: pin 1's slice must not carry pin 0's content."""
        content = _two_pin_file()
        pinned = _pinned_body(content)
        pins = pin_caps.parse_pins(pinned)
        block = archive_pin.extract_pin_block(pinned, 1, pins)
        assert "Second Pin" in block
        assert "First Pin" not in block

    def test_first_pin_slice_does_not_swallow_the_next_pins_date_comment(self):
        """The FORWARD bleed, which is the easy one to miss.

        A span starts at its date-comment LINE, which sits BEFORE the heading.
        So ending pin N's block at the next `### ` heading — the obvious rule,
        and what the spec's `end` clause says literally — puts pin N+1's date
        comment inside pin N's archived block. The record then carries another
        pin's pinned-date.

        Containment can never catch this: the block is still a verbatim
        substring of CLAUDE.md and every conjunct of the criterion holds. The
        end boundary must therefore be the next pin's SPAN start, computed by
        the same rule as its own start.
        """
        content = _two_pin_file()
        pinned = _pinned_body(content)
        pins = pin_caps.parse_pins(pinned)
        block = archive_pin.extract_pin_block(pinned, 0, pins)

        assert "First Pin" in block
        assert pins[1].date_comment not in block, (
            f"pin 0's block swallowed pin 1's date comment "
            f"({pins[1].date_comment!r}) — the archived record would carry "
            f"another pin's pinned-date"
        )
        assert block.count("<!-- pinned:") == 1, (
            "this fixture's pins carry one date comment each, so a second "
            "one in pin 0's block means it swallowed pin 1's. NOT a general "
            "invariant: a pin whose body documents the pin format "
            "legitimately contains two, and that slice is correct. The "
            "fixture-independent property is the assertion above — a block "
            "contains its OWN pin's comment and not its successor's."
        )

    def test_spans_partition_the_section_without_overlap(self):
        """Stronger than the pairwise checks: every pin's span is disjoint
        from every other's, and concatenating them in order reproduces a
        contiguous run of the source. A boundary error in either direction
        breaks one of these."""
        content = _two_pin_file()
        pinned = _pinned_body(content)
        pins = pin_caps.parse_pins(pinned)
        blocks = [
            archive_pin.extract_pin_block(pinned, i, pins)
            for i in range(len(pins))
        ]
        assert len(blocks) == 2, "fixture must have 2 pins or this is vacuous"
        assert "".join(blocks) in pinned, (
            "spans are not contiguous — they overlap or leave a gap"
        )
        for i, block in enumerate(blocks):
            others = [b for j, b in enumerate(blocks) if j != i]
            for other in others:
                assert other not in block, f"span {i} contains another span"


class TestArchiveMarker:
    """The structured archive marker written into `entities[].type`.

    SCOPE, stated so no reader infers more: this marker makes archives
    DISCOVERABLE GOING FORWARD. It does not make them enumerable. Archives
    written before it shipped carry no marker at all — including ones folded
    into an existing record rather than saved standalone — so any count
    obtained by scanning for it is a FLOOR over future archives, never a
    total over all of them.
    """

    def test_marker_value_is_pinned(self):
        """The value is pinned because `entities[].type` is unconstrained
        free text — structured by POSITION, not by SCHEMA.

        Nothing in the store validates the field, so a typo or a rename
        ships SILENTLY: a scanner keyed on the old value returns a smaller
        set and raises nothing. A confident undercount is worse than a loud
        failure, and this test is what converts a silent drift into a red.
        """
        assert archive_pin.ARCHIVE_ENTITY_TYPE == "pact_memory_archive"

    def test_record_uses_the_constant_not_a_second_literal(self):
        """Any code that writes or scans the marker must read THIS constant.

        Two copies of a free-text value drift, and the drift is invisible in
        exactly the way a schema violation would not be. Asserting the
        record's value IS the constant object (rather than equal to a literal
        retyped here) is what makes this test detect a divergence instead of
        silently agreeing with a hardcoded copy.
        """
        record = archive_pin._build_record("### Pin\nbody", "Pin")
        entity = record["entities"][0]
        assert entity["type"] == archive_pin.ARCHIVE_ENTITY_TYPE
        assert entity["name"] == "Pin"
        assert "demoted from CLAUDE.md" in entity["notes"]

    def test_no_second_copy_of_the_literal_in_this_module(self):
        """Guards the drift directly: the literal may appear exactly once in
        archive_pin.py — at the constant's definition. A scan site or a
        second writer that re-types it would be invisible to the test above,
        because a hardcoded duplicate agrees with the constant right up until
        someone changes one of them."""
        source = Path(archive_pin.__file__).read_text(encoding="utf-8")
        occurrences = source.count('"pact_memory_archive"')
        assert occurrences == 1, (
            f"the marker literal appears {occurrences} times in "
            f"archive_pin.py; it must appear once (the constant) and every "
            f"other site must reference ARCHIVE_ENTITY_TYPE"
        )


class TestStandaloneOnlyInvariant:
    """Archival MUST create a standalone record, never update an existing one.

    This is asserted directly rather than via a downstream symptom, because
    the violation is INVISIBLE AT RUNTIME. An additive `update` creates no new
    record and runs no marker code, so a folded archive is silently absent
    from any marker scan — that already happened to prior demotions. A future
    maintainer adding a fold path for a perfectly good reason (dedup,
    retrieval quality, avoiding near-duplicates) would void the audit property
    WITHOUT TOUCHING THE MARKER CODE, and nothing would fail; the symptom is a
    missing record in somebody's later audit.

    If a fold path is ever genuinely wanted, the correct move is to write the
    marker on the update path too, or to withdraw the auditability claim in
    the same change — not to relax this test.
    """

    def test_archival_calls_save_and_never_update(
        self, claude_md, monkeypatch
    ):
        claude_md(_two_pin_file())
        subcommands = []

        def _spy(args, **kwargs):
            subcommands.append(args[0])
            if args[0] == "save":
                return 0, json.dumps(
                    {"ok": True, "result": {"memory_id": "d" * 32}}
                ), ""
            return 0, json.dumps({"ok": True, "result": {"context": "x"}}), ""

        monkeypatch.setattr(archive_pin, "_run_memory_cli", _spy)
        archive_pin.build_verdict(0)

        assert "save" in subcommands, (
            "no save was attempted — the spy never saw the create path, so "
            "this test would pass vacuously"
        )
        assert "update" not in subcommands
        assert set(subcommands) <= {"save", "get"}, (
            f"archival used an unexpected subcommand: {subcommands}"
        )

    def test_archive_subcommand_constant_is_save(self):
        """The subcommand is a named constant so a fold path cannot be
        introduced by editing a bare string at the call site."""
        assert archive_pin._ARCHIVE_SUBCOMMAND == "save"

    def test_no_update_subcommand_anywhere_in_the_module(self):
        """Structural backstop for the spy above, which can only observe the
        paths a test actually drives."""
        source = Path(archive_pin.__file__).read_text(encoding="utf-8")
        assert '"update"' not in source
        assert "'update'" not in source


class TestProjectDirResolution:
    """WHERE the archive is filed.

    The memory layer detects project_id from CLAUDE_PROJECT_DIR, else git,
    else by walking UP from the CWD to the nearest project marker — and
    `.claude` is such a marker. Since the installed plugin lives beneath
    `~/.claude/`, running the memory CLI from the plugin's own directory
    files a consumer's archived pin under project `.claude`. Deriving the
    directory from the CLAUDE.md actually read is what prevents that.
    """

    def test_dot_claude_layout_resolves_to_project_root(self):
        got = archive_pin.project_dir_for(Path("/tmp/proj/.claude/CLAUDE.md"))
        assert got.name == "proj"

    def test_legacy_layout_resolves_to_project_root(self):
        got = archive_pin.project_dir_for(Path("/tmp/proj/CLAUDE.md"))
        assert got.name == "proj"

    def test_project_dir_is_never_the_plugin_directory(self, tmp_path):
        """The regression this guards: a CWD anywhere under the plugin tree
        would resolve project_id to `.claude` for every consumer."""
        claude_md = tmp_path / "myproject" / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text("x", encoding="utf-8")
        resolved = archive_pin.project_dir_for(claude_md)
        plugin_root = Path(archive_pin.__file__).resolve().parent.parent
        assert resolved.name == "myproject"
        assert plugin_root not in resolved.parents
        assert resolved != plugin_root


@pytest.mark.requires_embedding_backend
class TestArchivePin_RealCLI:
    """End-to-end against the REAL memory CLI and a temp database.

    Without at least one of these, the whole suite would be verifying its
    own stubs. These exercise the actual save/get envelope handling, the
    real embedding backend, and real byte round-tripping.

    DECLARED EXTERNAL DEPENDENCY (marker registered in conftest.py). The
    `save` path spins the embedding backend, which reads its model from a
    local cache. Every measurement behind these tests was taken against a
    WARM cache; cold-cache behaviour is UNMEASURED, and on a cold cache
    that read becomes a network download. In a container with no network
    it is not a slower test, it is a DIFFERENT FAILURE.

    The marker does not skip. These run by default, so the dependency
    cannot be satisfied by quietly not exercising the one path that keeps
    the suite from verifying its own stubs; a constrained environment
    deselects with `-m 'not requires_embedding_backend'`, which shows up
    in the pytest header rather than inside the skip count. The point is
    that the dependency is now NAMED: if it bites, it presents as a
    deselected marker or a legible failure, not as unexplained flakiness.
    """

    def test_archives_and_verifies_containment(self, claude_md, tmp_path):
        claude_md(_two_pin_file())
        verdict = archive_pin.build_verdict(
            0, db_path=str(tmp_path / "mem.db")
        )
        assert verdict["outcome"] == "ARCHIVED"
        assert verdict["heading"] == "First Pin"
        assert verdict["contained"] is True
        assert len(verdict["memory_id"]) == 32
        assert verdict["chars"] > 0

    def test_archived_record_carries_the_block_in_context_not_a_list_field(
        self, claude_md, tmp_path
    ):
        """D3, verified at the destination rather than asserted in a comment.

        String-list fields `.strip()` and NFC-normalize their items, so a pin
        stored there comes back ALTERED — containment returns FALSE for a
        perfectly good archive, which is an OVER-BLOCK refusing a legitimate
        eviction. This is not hypothetical: the one pin-archive record
        already in the store claims verbatim preservation while holding its
        content in `lessons_learned`.
        """
        content = _two_pin_file()
        claude_md(content)
        db = str(tmp_path / "mem.db")
        verdict = archive_pin.build_verdict(0, db_path=db)
        assert verdict["outcome"] == "ARCHIVED"

        fetched = _cli_get(verdict["memory_id"], db)
        pinned = _pinned_body(content)
        block = archive_pin.extract_pin_block(
            pinned, 0, pin_caps.parse_pins(pinned)
        )

        assert block in fetched["context"], "block must land in `context`"
        for list_field in ("lessons_learned", "reasoning_chains", "decisions"):
            assert not fetched.get(list_field), (
                f"{list_field} must stay empty — a list field cannot "
                f"preserve the block byte-exact"
            )

    def test_adversarial_body_round_trips_byte_exact(
        self, claude_md, tmp_path
    ):
        """Apostrophes, backticks, tabs, CRLF and trailing whitespace all
        survive. These are the classes that break shell-quoted or
        normalizing storage paths."""
        content = (
            "<!-- PACT_MANAGED_START -->\n## Pinned Context\n\n"
            "<!-- pinned: 2026-01-01 -->\n"
            "### Adversarial\n"
            "has 'apostrophes' and `backticks`\n"
            "\ttab-indented, trailing spaces here   \n"
            "#### not a pin heading\n\n"
            "<!-- PACT_MANAGED_END -->\n"
        )
        claude_md(content)
        db = str(tmp_path / "mem.db")
        verdict = archive_pin.build_verdict(0, db_path=db)
        assert verdict["outcome"] == "ARCHIVED"

        fetched = _cli_get(verdict["memory_id"], db)
        block = archive_pin.extract_pin_block(
            _pinned_body(content), 0,
            pin_caps.parse_pins(_pinned_body(content)),
        )
        assert block in fetched["context"]
        assert "'apostrophes'" in fetched["context"]
        assert "`backticks`" in fetched["context"]
        assert "\t" in fetched["context"]

    def test_save_writes_to_stderr_while_stdout_stays_clean_json(
        self, claude_md, tmp_path
    ):
        """The never-`2>&1` constraint, measured rather than asserted.

        `save` writes an embedding progress bar to STDERR on SUCCESS. If the
        streams were ever merged, that bar would splice into the envelope
        and every parse would break. The stderr assertion is the NON-VACUITY
        CONTROL: if the backend stops writing to stderr the hazard is gone
        and this test is measuring nothing, so it should fail loudly and be
        re-aimed rather than pass silently.
        """
        claude_md(_two_pin_file())
        pinned = _pinned_body(_two_pin_file())
        block = archive_pin.extract_pin_block(
            pinned, 0, pin_caps.parse_pins(pinned)
        )
        payload = json.dumps(archive_pin._build_record(block, "First Pin"))

        rc, stdout, stderr = archive_pin._run_memory_cli(
            ["save", "--stdin"],
            db_path=str(tmp_path / "mem.db"),
            stdin_data=payload,
            cwd=tmp_path,
        )
        assert rc == 0
        assert stderr.strip(), (
            "expected the embedding progress bar on stderr — without it "
            "this test cannot detect a merged-stream regression"
        )
        envelope = json.loads(stdout)  # would raise if streams were merged
        assert envelope["ok"] is True
        assert stderr.strip() not in stdout


def _cli_get(memory_id, db_path):
    """Fetch a record via the real CLI, streams kept separate."""
    cli = (
        Path(archive_pin.__file__).resolve().parent.parent
        / "skills" / "pact-memory" / "scripts" / "cli.py"
    )
    proc = subprocess.run(
        [sys.executable, str(cli), "get", memory_id, "--db-path", db_path],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"get failed: {proc.stderr[:400]}"
    return json.loads(proc.stdout)["result"]


class TestArchivePin_FailureMatrix:
    """Stubbed-CLI failure paths. Real stores cannot be made to fail on
    demand in these specific ways, so the seam is stubbed here — while
    TestArchivePin_RealCLI keeps the unstubbed path covered."""

    def test_save_returning_no_id_is_not_archived(self, claude_md, monkeypatch):
        """The store was reachable and said no. Definite failure, so
        NOT_ARCHIVED rather than UNEVALUABLE."""
        claude_md(_two_pin_file())
        monkeypatch.setattr(
            archive_pin, "_run_memory_cli",
            lambda *a, **k: (
                1, "", json.dumps({"ok": False, "error": "ValueError",
                                   "message": "bad field"})
            ),
        )
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "NOT_ARCHIVED"
        assert verdict["memory_id"] is None
        assert verdict["heading"] == "First Pin"
        assert "ValueError" in verdict["reason"]

    def test_error_envelope_key_is_error_not_error_type(
        self, claude_md, monkeypatch
    ):
        """cli.py's envelope key is `error`. A reader keyed on `error_type`
        would silently render every failure as an empty reason."""
        claude_md(_two_pin_file())
        monkeypatch.setattr(
            archive_pin, "_run_memory_cli",
            lambda *a, **k: (
                1, "", json.dumps({"ok": False, "error": "NOT_FOUND",
                                   "message": "Memory 'x' not found"})
            ),
        )
        verdict = archive_pin.build_verdict(0)
        assert "NOT_FOUND" in verdict["reason"]

    def test_containment_failure_is_not_archived(self, claude_md, monkeypatch):
        """THE criterion. A record that exists but does not carry the pin is
        NOT archived — this is precisely the case the old memory_id-only
        check passed, and it is the case the founding data loss was."""
        claude_md(_two_pin_file())
        calls = []

        def _stub(args, **kwargs):
            calls.append(args[0])
            if args[0] == "save":
                return 0, json.dumps(
                    {"ok": True, "result": {"memory_id": "a" * 32}}
                ), ""
            return 0, json.dumps({
                "ok": True,
                "result": {"context": "a summary that lost the pin body"},
            }), ""

        monkeypatch.setattr(archive_pin, "_run_memory_cli", _stub)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "NOT_ARCHIVED"
        assert verdict["memory_id"] == "a" * 32, (
            "the id must still be reported so the orphan record is findable"
        )
        assert "fidelity" in verdict["reason"]
        assert calls == ["save", "get"], "must re-fetch before judging"

    def test_containment_is_substring_not_equality(
        self, claude_md, monkeypatch
    ):
        """`context` may legitimately carry MORE than the block — a
        provenance preamble, for instance. An equality assertion would
        return false for a correct archive: an over-block in the one control
        whose entire purpose is not destroying content."""
        content = _two_pin_file()
        claude_md(content)
        pinned = _pinned_body(content)
        block = archive_pin.extract_pin_block(
            pinned, 0, pin_caps.parse_pins(pinned)
        )

        def _stub(args, **kwargs):
            if args[0] == "save":
                return 0, json.dumps(
                    {"ok": True, "result": {"memory_id": "b" * 32}}
                ), ""
            return 0, json.dumps({
                "ok": True,
                "result": {
                    "context": (
                        "Archive of CLAUDE.md pin, demoted 2026-07-25 to "
                        "free a slot.\n\n" + block + "\n\ntrailing note"
                    )
                },
            }), ""

        monkeypatch.setattr(archive_pin, "_run_memory_cli", _stub)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "ARCHIVED", (
            "a record wrapping the block in provenance is a GOOD archive"
        )

    def test_refetch_failure_is_unevaluable_not_not_archived(
        self, claude_md, monkeypatch
    ):
        """The id came back but the record will not re-read. We cannot tell
        whether the bytes are safe — so we must claim neither. Collapsing
        this into NOT_ARCHIVED would be defensible; collapsing it into
        ARCHIVED would destroy content."""
        claude_md(_two_pin_file())

        def _stub(args, **kwargs):
            if args[0] == "save":
                return 0, json.dumps(
                    {"ok": True, "result": {"memory_id": "c" * 32}}
                ), ""
            return 1, "", json.dumps(
                {"ok": False, "error": "NOT_FOUND", "message": "gone"}
            )

        monkeypatch.setattr(archive_pin, "_run_memory_cli", _stub)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert "c" * 32 in verdict["reason"]
        assert verdict["heading"] == "First Pin"

    @pytest.mark.parametrize("stdout", ["", "   ", "not json", "[]",
                                        '{"ok": false}'])
    def test_unparseable_save_stdout_never_reads_as_success(
        self, claude_md, monkeypatch, stdout
    ):
        """NOT_FOUND, PREFIX_TOO_SHORT and an outright crash all present as
        empty or unusable stdout. None may be mistaken for a save."""
        claude_md(_two_pin_file())
        monkeypatch.setattr(
            archive_pin, "_run_memory_cli", lambda *a, **k: (0, stdout, "")
        )
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] != "ARCHIVED"


class TestArchivePin_Unevaluable:
    """Every path where the pin's state cannot be established."""

    def test_missing_claude_md(self, monkeypatch):
        monkeypatch.setattr(
            archive_pin, "get_project_claude_md_path", lambda: None
        )
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert verdict["heading"] is None

    def test_no_pinned_section(self, claude_md):
        claude_md("# Project\n\n## Working Memory\n\n")
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"

    def test_index_beyond_pin_count(self, claude_md):
        claude_md(_two_pin_file())
        verdict = archive_pin.build_verdict(99)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert "out of range" in verdict["reason"]

    def test_missing_memory_cli(self, claude_md, monkeypatch):
        claude_md(_two_pin_file())
        monkeypatch.setattr(archive_pin, "_MEMORY_CLI", Path("/nonexistent/cli.py"))
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert "not found" in verdict["reason"]

    def test_cli_timeout(self, claude_md, monkeypatch):
        """A hang must refuse (pin survives), never proceed."""
        claude_md(_two_pin_file())

        def _boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="save", timeout=1)

        monkeypatch.setattr(subprocess, "run", _boom)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert "timed out" in verdict["reason"]

    def test_unreadable_claude_md(self, claude_md, monkeypatch):
        claude_md(_two_pin_file())

        def _raise(*a, **k):
            raise IOError("simulated")

        monkeypatch.setattr(Path, "read_text", _raise)
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"

    def test_lossy_extractor_is_caught_before_any_write(
        self, claude_md, monkeypatch
    ):
        """The source-side tripwire.

        The slice makes 'block is verbatim in CLAUDE.md' true BY
        CONSTRUCTION, so this check costs nothing in normal operation. It
        exists to fail loudly if the extractor ever regresses into a lossy
        rebuild — and it fires BEFORE the save, so a broken extractor writes
        nothing rather than persisting a variant and certifying it.
        """
        claude_md(_two_pin_file())
        monkeypatch.setattr(
            archive_pin, "extract_pin_block",
            lambda *a, **k: "### Not from the source at all\nfabricated",
        )
        called = []
        monkeypatch.setattr(
            archive_pin, "_run_memory_cli",
            lambda *a, **k: called.append(a) or (0, "", ""),
        )
        verdict = archive_pin.build_verdict(0)
        assert verdict["outcome"] == "UNEVALUABLE"
        assert "not verbatim" in verdict["reason"]
        assert called == [], "must not save when the block is not verbatim"


class TestArchivePin_CliContract:
    """main() surface: always exit 0, always a parseable verdict."""

    @pytest.mark.parametrize("index", [0, 1, 99, -1])
    def test_always_exits_zero(self, claude_md, capsys, index, tmp_path):
        """SACROSANCT in-band degradation: the script reports, the command
        decides. A non-zero exit would turn a measurement into a decision."""
        claude_md(_two_pin_file())
        rc = archive_pin.main(
            ["--index", str(index), "--db-path", str(tmp_path / "m.db")]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] in {
            "ARCHIVED", "NOT_ARCHIVED", "UNEVALUABLE"
        }

    def test_every_verdict_carries_outcome_and_heading_keys(
        self, claude_md, capsys, monkeypatch, tmp_path
    ):
        """`heading` is present in ALL THREE verdicts so a consumer never
        has to distinguish an absent key from a null value."""
        claude_md(_two_pin_file())
        db = str(tmp_path / "m.db")

        seen = {}
        # ARCHIVED (real CLI)
        archive_pin.main(["--index", "0", "--db-path", db])
        seen["ARCHIVED"] = json.loads(capsys.readouterr().out)
        # UNEVALUABLE
        archive_pin.main(["--index", "99", "--db-path", db])
        seen["UNEVALUABLE"] = json.loads(capsys.readouterr().out)
        # NOT_ARCHIVED
        monkeypatch.setattr(
            archive_pin, "_run_memory_cli", lambda *a, **k: (1, "", "boom")
        )
        archive_pin.main(["--index", "0", "--db-path", db])
        seen["NOT_ARCHIVED"] = json.loads(capsys.readouterr().out)

        assert set(seen) == {"ARCHIVED", "UNEVALUABLE", "NOT_ARCHIVED"}, (
            "all three verdicts must be reachable or this test is partial"
        )
        for outcome, payload in seen.items():
            assert payload["outcome"] == outcome
            assert "heading" in payload, f"{outcome} dropped the heading key"

    def test_heading_is_the_real_heading_not_an_index_echo(
        self, claude_md, capsys, tmp_path
    ):
        """The caller cross-checks this value against the curator's
        selection to catch an index shift between listing and archival —
        which would otherwise archive one pin and evict another while
        containment still passed, the right property measured on the wrong
        object. An index echo would make that check compare the index
        against itself and pass unconditionally."""
        claude_md(_two_pin_file())
        archive_pin.main(
            ["--index", "1", "--db-path", str(tmp_path / "m.db")]
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["heading"] == "Second Pin"
        assert "1" != payload["heading"]

    def test_internal_error_degrades_to_unevaluable(
        self, claude_md, capsys, monkeypatch
    ):
        """An unexpected exception must never crash the curator's flow."""
        claude_md(_two_pin_file())

        def _boom(*a, **k):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(archive_pin, "archive_pin", _boom)
        rc = archive_pin.main(["--index", "0"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] == "UNEVALUABLE"
        assert "RuntimeError" in payload["reason"]
