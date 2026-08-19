"""
Location: pact-plugin/tests/test_snapshot_key_count_discriminator.py
Summary: The one-axis-flip discriminator for what drives the size-bounded
         snapshot payload after truncation. It separates the KEY COUNT axis
         from the TOTAL VALUE BYTES axis and from the KEY NAME WIDTH axis,
         and it holds the two-sided crossing point where stage 3b starts to
         fire. THE ARM counts are derived from the two caps by probe, so a
         cap change moves the arm fixtures with it rather than move an arm
         into a different regime. THE CONTROL counts are LITERALS. Do not
         read the first half of this sentence more widely than it is
         written: see the paragraph on literal counts below.
Used by: pytest. This file is a SIBLING of test_task_metadata_snapshot.py and
         test_snapshot_provenance_semantics.py, kept apart because its arms
         are large by necessity and cost about 25 seconds. Do not merge it
         into either of those files: their assertions are tight fire counts
         and this file would cost them signal.

WHY THIS FILE IS A DISCRIMINATOR AND NOT A DEMONSTRATION. Two arms with an
equal total prove nothing on their own when the arms differ in more than one
term. At an equal total value byte count, many small values sit below
PER_VALUE_CAP and few large values sit above it, so the two arms also differ
in the STAGE that fires. So each claim below is carried by a pair that
flips ONE term and holds the rest.

THE TWO AXES, KEPT APART. They are different claims and a clean result on one
is not support for the other.
  COUNT axis      after truncation has done all it can, the payload costs a
                  fixed number of bytes for each key, so the KEY COUNT and not
                  the total value bytes decides if stage 3b fires.
  NAME MASS axis  the stage 3b name census costs the key name width for each
                  dropped key, so a wide key name overruns PAYLOAD_CAP even
                  when the count is modest. That overrun is the documented
                  residual of stage 3b.

THE TERMINAL STAGE IS A DERIVED INSTRUMENT. build_snapshot_payload returns
(payload, truncated) and reports no stage, so _classify_stage reads the stage
back out of the payload shape. A derived instrument can be incorrect, and if
it is incorrect then every arm reads incorrectly together, which no number of
arms detects. TestStageClassifierInstrument grades it against inputs of which
the terminal stage is known by construction. If that class goes red, no arm
result in this file is readable.

THE CONTROL COUNTS ARE LITERALS AND THEY ARE NOT CAP-DERIVED. Six call
sites carry a literal count: the stage-2, stage-3a and stage-3b classifier
controls, the mixed and the unmixed guard payloads, and the determinism arm.
(The `none` and `stage1` controls hold one key each, which is a literal count
of one.) EACH OF THE SIX ASSERTS THE REGIME IT NEEDS, unconditionally, so a
change to the ratio of the two caps that moves one of them into a different
regime turns that test RED rather than let it pass having measured a weaker
thing. A MAINTAINER WHO READS "every count is derived" WILL SKIP THE RE-CHECK
OF THESE SIX AFTER A CAP CHANGE, and these six are the part that needs it.

WHAT _classify_stage CANNOT SEE, stated so a reader does not ask more of it:
  1. It reports ONE label for the payload. A mapping with one key marked at
     stage 1 and another marked at stage 2 is MIXED, and the rule is `all`,
     so a mixed payload reports "stage2". The rule degrades to the LATER
     stage, which is the safer of the two directions. NO ARM IN THIS FILE IS
     MIXED, and that is a CHECKED precondition rather than a claim: see
     _assert_not_mixed and TestTheNoMixedArmGuard. A label cannot report
     that its own input was mixed, because to collapse a mixed payload is
     what the label DOES, so the guard computes the two counts APART.
  2. It cannot see a stage that ran and changed nothing.
  3. It does not separate "stage 3a emptied every head" from "stage 3a emptied
     some heads". The kept-head count carries that and is asserted adjacent to it.
  4. A caller key named "_dropped_keys" is ordinary caller data at low
     pressure, so the classifier compares the list against the caller value
     rather than test for the name alone.
"""

import hashlib

import pytest

from shared.task_metadata_snapshot import (
    PAYLOAD_CAP,
    PER_VALUE_CAP,
    _canonical_bytes,
    build_snapshot_payload,
)

_MARKER_KEYS = frozenset({"_truncated", "original_bytes", "head"})

# Two key widths. NARROW is the ordinary regime. WIDE is the name-mass regime
# that reaches the documented stage 3b residual. The recorded specimen for the
# residual sits at width 400, so WIDE at 200 is a SECOND point on that axis
# and not a repeat of the first.
_NARROW_WIDTH = 8
_WIDE_WIDTH = 200


def _size(value: object) -> int:
    return len(_canonical_bytes(value))


def _is_marker(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value.keys()) == set(_MARKER_KEYS)
        and value.get("_truncated") is True
    )


def _key(index: int, width: int) -> str:
    """A key of an exact width, unique in its last five characters."""
    assert width >= 5, "a key must hold its five-digit index"
    return "k" * (width - 5) + f"{index:05d}"


def _mapping(count: int, value_chars: int, width: int = _NARROW_WIDTH) -> dict:
    return {_key(index, width): "x" * value_chars for index in range(count)}


def _entry_cost(width: int, original_bytes: int) -> int:
    """Canonical bytes that ONE empty-head marker entry costs, key included.

    MEASURED BY PROBE, not frozen. Three terms move it and two of them move
    when a cap moves: the key width, the marker scaffolding, and the DIGIT
    COUNT of original_bytes. A frozen cost silently mis-derives every count
    below it, and the failure is quiet because the fixture keeps building.
    """
    probe = {
        _key(0, width): {
            "_truncated": True,
            "original_bytes": original_bytes,
            "head": "",
        }
    }
    return _size(probe) - 2 + 1  # drop the outer braces, add the separator


def _floor_crossing_count(width: int, original_bytes: int) -> int:
    """Smallest key count at which the all-heads-empty floor passes the cap.

    This is the count at which stage 3b starts to fire. It is a property of
    PAYLOAD_CAP and the entry cost ALONE. No term of it is a value size, and
    that absence is the COUNT-axis claim in its sharpest form.
    """
    return (PAYLOAD_CAP - 1) // _entry_cost(width, original_bytes) + 1


def _equal_total_partner(total_bytes: int) -> tuple[int, int]:
    """Return (count, value_chars) for the FEW LARGE arm.

    The partner must reach the SAME total canonical value bytes with the
    fewest keys of which each value is above PER_VALUE_CAP. Searched rather
    than frozen, so the pair stays exact when a cap moves.
    """
    for count in range(total_bytes // (PER_VALUE_CAP + 2), 0, -1):
        if total_bytes % count == 0:
            return count, total_bytes // count - 2
    raise AssertionError("no exact equal-total partner is available")


def _stage_split(payload: dict, cap: int = PER_VALUE_CAP) -> tuple[int, int]:
    """Marker counts for the two cut stages, computed APART.

    Stage 2 marks values that passed stage 1, so a stage-2 marker always
    carries `original_bytes` at or below the cap and a stage-1 marker always
    carries more. `original_bytes` SURVIVES stage 3a, which rebuilds the
    marker and changes `head` alone, so this split stays readable below an
    emptied head.

    THE CAP IS AN ARGUMENT AND NOT A GLOBAL READ. The builder reads the
    module value at CALL time. An arm that patches a cap and a classifier
    that reads the live constant give the same answer about different
    worlds, and nothing raises.
    """
    markers = [value for value in payload.values() if _is_marker(value)]
    above = sum(1 for m in markers if m["original_bytes"] > cap)
    return above, len(markers) - above


def _assert_not_mixed(payload: dict, cap: int = PER_VALUE_CAP) -> None:
    """The scalar label is adequate for this file BECAUSE no arm is mixed.

    A property nobody checks decays in silence, so this checks it. A future
    arm that becomes mixed turns the suite RED rather than be silently
    mis-labelled. TestTheNoMixedArmGuard watches this guard fire.
    """
    stage1_count, stage2_count = _stage_split(payload, cap)
    assert stage1_count == 0 or stage2_count == 0, (
        f"MIXED payload: {stage1_count} marked at stage 1 and "
        f"{stage2_count} at stage 2. One scalar label cannot carry that."
    )


def _classify_stage(payload: dict, source: dict) -> str:
    """DERIVED terminal-stage instrument. See the module docstring for its
    four blind spots, and TestStageClassifierInstrument for its controls."""
    dropped = payload.get("_dropped_keys")
    if isinstance(dropped, list) and dropped != source.get("_dropped_keys"):
        return "stage3b"
    markers = [value for value in payload.values() if _is_marker(value)]
    if not markers:
        return "none"
    if any(marker["head"] == "" for marker in markers):
        return "stage3a"
    if all(marker["original_bytes"] > PER_VALUE_CAP for marker in markers):
        return "stage1"
    return "stage2"


def _observe(source: dict) -> dict:
    """One arm reading. Reports the terminal stage ADJACENT TO the byte count.

    The byte count alone is a trap. Any arm that reaches stage 3a and then
    fits lands at the cap by construction, so two arms that agree at the cap
    can agree through different mechanisms.
    """
    payload, truncated = build_snapshot_payload(source)
    markers = [value for value in payload.values() if _is_marker(value)]
    dropped = payload.get("_dropped_keys")
    dropped = dropped if isinstance(dropped, list) else []
    kept = sorted(key for key in payload if key != "_dropped_keys")
    return {
        "payload": payload,
        "stage": _classify_stage(payload, source),
        "bytes": _size(payload),
        "over_cap": _size(payload) > PAYLOAD_CAP,
        "markers": len(markers),
        "heads_kept": sum(1 for m in markers if m["head"] != ""),
        "dropped": len(dropped),
        "truncated": truncated,
        # SCOPE: KEY NAMES ALONE. Two payloads that keep the same names and
        # drop nothing share this digest while they differ in stage and in
        # bytes. That scope is CORRECT for the value-size flip, of which the
        # claim is about which keys survive. Do not read an agreeing digest
        # as agreeing payloads. TestTheKeyPartitionDigestScope proves it.
        "partition": hashlib.sha256(
            _canonical_bytes([kept, sorted(dropped)])
        ).hexdigest()[:16],
        "split": _stage_split(payload),
        "shape": _shape_digest(payload),
    }


def _shape_digest(payload: dict) -> str:
    """Digest of the payload with every original_bytes projected out.

    A count agreeing is weak evidence and the artifact agreeing is strong.
    Two arms that differ ONLY in value size must produce byte-identical
    output when the recorded original size is projected away, because that
    field is the one place a value size is allowed to reach the output.
    """
    normalized = {
        key: ({**value, "original_bytes": "<projected>"}
              if _is_marker(value) else value)
        for key, value in payload.items()
    }
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()[:16]


# ─── derived fixture parameters ──────────────────────────────────────────────
# Every count below is derived from the caps at import time. The value sizes
# are expressed against PER_VALUE_CAP and the counts against PAYLOAD_CAP, so
# neither half can freeze while the other moves.

_SMALL_CHARS = 200
_SMALL_ENTRY_ORIGINAL = _SMALL_CHARS + 2

# Four percent above the crossing count, so the MANY SMALL arm reaches stage
# 3b with a margin rather than balance on the boundary. The boundary itself
# is tested two-sided in TestFloorCrossingIsTwoSided.
_MANY = _floor_crossing_count(_NARROW_WIDTH, _SMALL_ENTRY_ORIGINAL) * 104 // 100
_TOTAL_VALUE_BYTES = _MANY * (_SMALL_CHARS + 2)
_FEW, _LARGE_CHARS = _equal_total_partner(_TOTAL_VALUE_BYTES)

# The value-size flip runs at the WIDE width, where the crossing count is far
# lower, so a two times change in total value bytes costs about one second
# and not about fifteen. The two value sizes are chosen to keep the DIGIT
# COUNT of original_bytes equal, so the entry cost is equal by construction
# and any divergence is a real divergence.
_FLIP_COUNT = _floor_crossing_count(_WIDE_WIDTH, PER_VALUE_CAP + 2) * 117 // 100
_FLIP_SMALL_CHARS = PER_VALUE_CAP + 232
# The canonical size of a string is its character count plus the two quote
# bytes, so an exact doubling of the CANONICAL size adds those two bytes
# back. Doubling the character count alone lands two bytes short, and the
# precondition in the flip test is what reports that.
_FLIP_LARGE_CHARS = _FLIP_SMALL_CHARS * 2 + 2

# The name-width flip holds the count and the value size and moves only the
# key width. The count is set so the WIDE arm drops every key and its census
# alone passes PAYLOAD_CAP, which is the documented residual.
_WIDTH_FLIP_COUNT = (PAYLOAD_CAP // (_WIDE_WIDTH + 3)) * 140 // 100


class TestStageClassifierInstrument:
    """Grade the derived stage instrument against inputs of which the
    terminal stage is known BY CONSTRUCTION. If this class is red, no arm
    result in this file is readable, because a single incorrect instrument
    makes every arm read incorrectly together."""

    @pytest.mark.parametrize(
        "expected,source",
        [
            # No value is above either cap, so no stage runs.
            ("none", {"a": "x"}),
            # One value above PER_VALUE_CAP, and one marker fits PAYLOAD_CAP,
            # so stage 1 runs and stages 2, 3a and 3b cannot.
            ("stage1", {"a": "x" * (PER_VALUE_CAP + 100)}),
            # Six values each below PER_VALUE_CAP summing above PAYLOAD_CAP,
            # so stage 1 cannot fire and stage 2 must.
            (
                "stage2",
                {
                    _key(i, _NARROW_WIDTH): "x" * (PER_VALUE_CAP - 2000)
                    for i in range(6)
                },
            ),
            # Head markers pass PAYLOAD_CAP and empty heads fit below it, so
            # stage 3a runs and stage 3b cannot.
            ("stage3a", _mapping(300, PER_VALUE_CAP + 100)),
            # Empty heads pass PAYLOAD_CAP at the wide width, so stage 3b
            # must run.
            (
                "stage3b",
                _mapping(600, PER_VALUE_CAP + 232, width=_WIDE_WIDTH),
            ),
        ],
        ids=["none", "stage1", "stage2", "stage3a", "stage3b"],
    )
    def test_classifier_reports_the_known_stage(self, expected, source):
        assert _classify_stage(*_control_pair(source)) == expected


def _control_pair(source: dict) -> tuple[dict, dict]:
    payload, _ = build_snapshot_payload(source)
    return payload, source


class TestKeyCountDrivesTheFloor:
    """The COUNT axis. Each test flips ONE term and holds the rest."""

    def test_equal_total_value_bytes_diverge_by_key_count(self):
        """MANY SMALL against FEW LARGE at an EQUAL total value byte
        count. The two arms must reach different terminal stages. If the
        total value bytes drove the outcome the two arms would agree, and an
        agreement here is a refutation of the count claim rather than a
        broken fixture."""
        many = _mapping(_MANY, _SMALL_CHARS)
        few = _mapping(_FEW, _LARGE_CHARS)

        # Preconditions asserted UNCONDITIONALLY. A guard of the form
        # `if over_cap:` would stop running its body when a cap moves and
        # would report a pass having measured nothing.
        total_many = sum(_size(v) for v in many.values())
        total_few = sum(_size(v) for v in few.values())
        assert total_many == total_few, "the equal-total control must hold"
        assert _SMALL_CHARS + 2 < PER_VALUE_CAP
        assert _LARGE_CHARS + 2 > PER_VALUE_CAP
        assert len(many) > len(few) * 100, "the count arms must differ widely"

        many_seen = _observe(many)
        few_seen = _observe(few)
        _assert_not_mixed(many_seen["payload"])
        _assert_not_mixed(few_seen["payload"])

        assert many_seen["stage"] == "stage3b"
        assert few_seen["stage"] == "stage1"
        assert many_seen["dropped"] > 0
        assert few_seen["dropped"] == 0
        # The few-large arm keeps its heads, which is the positive twin of
        # the negative above: it proves the zero is a measured zero.
        assert few_seen["heads_kept"] == len(few)
        assert many_seen["bytes"] > few_seen["bytes"] * 5

    def test_value_size_flip_at_held_key_count_changes_nothing(self):
        """THE DECIDING ARM. Hold the key count and the key width, and double
        the total value bytes. The count claim predicts byte-identical output
        when the recorded original size is projected away. The competing
        reading, that total value bytes drive the outcome, predicts a
        divergence, because these two arms differ by a factor of two."""
        small = _mapping(_FLIP_COUNT, _FLIP_SMALL_CHARS, width=_WIDE_WIDTH)
        large = _mapping(_FLIP_COUNT, _FLIP_LARGE_CHARS, width=_WIDE_WIDTH)

        total_small = sum(_size(v) for v in small.values())
        total_large = sum(_size(v) for v in large.values())
        assert total_large == total_small * 2, "the value-size flip must hold"
        assert len(small) == len(large), "the count must be held"
        assert _FLIP_SMALL_CHARS + 2 > PER_VALUE_CAP
        assert len(str(_FLIP_SMALL_CHARS + 2)) == len(
            str(_FLIP_LARGE_CHARS + 2)
        ), "equal digit counts keep the entry cost equal by construction"

        small_seen = _observe(small)
        large_seen = _observe(large)
        _assert_not_mixed(small_seen["payload"])
        _assert_not_mixed(large_seen["payload"])

        assert small_seen["stage"] == "stage3b" == large_seen["stage"]
        assert small_seen["bytes"] == large_seen["bytes"]
        assert small_seen["dropped"] == large_seen["dropped"] > 0
        assert small_seen["markers"] == large_seen["markers"] > 0
        assert small_seen["partition"] == large_seen["partition"]
        # The artifact, not the count. A count agreeing is weak evidence.
        assert small_seen["shape"] == large_seen["shape"]

    def test_floor_crossing_is_two_sided(self):
        """The crossing count is a boundary and a boundary needs both sides.
        One key below the derived crossing count, stage 3b must NOT fire. At
        the crossing count it must fire. A single hit above a boundary does
        not separate the boundary from everything above it."""
        crossing = _floor_crossing_count(_NARROW_WIDTH, PER_VALUE_CAP + 102)
        assert crossing > 1, "the crossing count must be derivable"

        below = _observe(_mapping(crossing - 1, PER_VALUE_CAP + 100))
        at = _observe(_mapping(crossing, PER_VALUE_CAP + 100))
        _assert_not_mixed(below["payload"])
        _assert_not_mixed(at["payload"])

        assert below["stage"] == "stage3a"
        assert below["dropped"] == 0
        assert below["bytes"] <= PAYLOAD_CAP
        assert at["stage"] == "stage3b"
        assert at["dropped"] > 0
        # ONE key of difference in the input moves the terminal stage. That
        # is the sharpest available statement that the count is the driver.
        assert at["dropped"] - below["dropped"] >= 1


class TestNameWidthIsTheSecondAxis:
    """The NAME MASS axis. It is a DIFFERENT claim from the count axis, and
    the recorded specimen for the stage 3b residual sits on this axis rather
    than on the count axis."""

    def test_name_width_flip_reaches_the_documented_residual(self):
        """Hold the key count and the value size and move ONLY the key width.
        The narrow arm stays below PAYLOAD_CAP. The wide arm drops every key
        and its name census alone passes the cap, which reproduces the
        documented stage 3b residual at a second point on this axis."""
        narrow = _mapping(
            _WIDTH_FLIP_COUNT, PER_VALUE_CAP + 232, width=_NARROW_WIDTH
        )
        wide = _mapping(
            _WIDTH_FLIP_COUNT, PER_VALUE_CAP + 232, width=_WIDE_WIDTH
        )

        assert len(narrow) == len(wide), "the count must be held"
        assert sum(_size(v) for v in narrow.values()) == sum(
            _size(v) for v in wide.values()
        ), "the value bytes must be held"

        narrow_seen = _observe(narrow)
        wide_seen = _observe(wide)
        _assert_not_mixed(narrow_seen["payload"])
        _assert_not_mixed(wide_seen["payload"])

        assert narrow_seen["over_cap"] is False
        assert narrow_seen["bytes"] <= PAYLOAD_CAP
        assert wide_seen["over_cap"] is True
        assert wide_seen["bytes"] > PAYLOAD_CAP
        assert wide_seen["stage"] == "stage3b"
        # The overrun is the census and nothing else, so it is bounded by the
        # key name mass by construction.
        assert wide_seen["markers"] == 0
        assert wide_seen["dropped"] == len(wide)
        assert set(wide_seen["payload"]) == {"_dropped_keys"}

    def test_the_residual_is_the_census_and_not_the_values(self):
        """The overrun size tracks the key name mass and does NOT track the
        value bytes. Doubling the value size at a held count and a held width
        leaves the overrun byte-identical."""
        wide = _mapping(
            _WIDTH_FLIP_COUNT, PER_VALUE_CAP + 232, width=_WIDE_WIDTH
        )
        wide_fat = _mapping(
            _WIDTH_FLIP_COUNT, (PER_VALUE_CAP + 232) * 2, width=_WIDE_WIDTH
        )

        seen = _observe(wide)
        seen_fat = _observe(wide_fat)

        assert seen["over_cap"] is True and seen_fat["over_cap"] is True
        assert seen["bytes"] == seen_fat["bytes"]
        assert seen["payload"] == seen_fat["payload"]


class TestArmsAreMeasurementsAndNotSamples:
    def test_insertion_order_does_not_move_one_byte(self):
        """Each arm above is read ONE TIME. That is a measurement and not a
        sample only if the builder is insertion-order independent, so pin
        that here rather than assume it."""
        source = _mapping(400, PER_VALUE_CAP + 232, width=_WIDE_WIDTH)
        reversed_source = dict(reversed(list(source.items())))
        assert list(source) != list(reversed_source), "the order must differ"

        first, truncated = build_snapshot_payload(source)
        second, _ = build_snapshot_payload(reversed_source)

        # THE COUNT 400 IS A LITERAL, so assert the regime it must reach.
        # Without these two lines the equality below holds TRIVIALLY in the
        # no-truncation regime, where the payload is the input and sort_keys
        # makes it order-independent by construction. A cap change that drops
        # this arm below the payload cap would leave a green test that had
        # measured nothing about truncation order.
        assert truncated is True, "the determinism arm must reach truncation"
        assert _classify_stage(first, source) in {
            "stage2", "stage3a", "stage3b"
        }, "the arm must reach a stage of which the selection is ordered"

        assert _canonical_bytes(first) == _canonical_bytes(second)


class TestTheNoMixedArmGuard:
    """The two-sided control for _assert_not_mixed. A guard that nobody has
    watched fire is the shape it was added to prevent."""

    @staticmethod
    def _mixed_source() -> dict:
        """One value above the cap, marked at stage 1, plus twelve values
        each below the cap, of which stage 2 evicts some. That gives ONE
        payload holding markers from the two stages."""
        source = {"huge": "x" * (PER_VALUE_CAP + 500)}
        source.update(
            {f"m{i:03d}": "x" * (PER_VALUE_CAP // 2) for i in range(12)}
        )
        return source

    def test_the_guard_reddens_on_a_mixed_payload(self):
        payload, _ = build_snapshot_payload(self._mixed_source())
        stage1_count, stage2_count = _stage_split(payload)
        # The construction must BE mixed, or the guard below is tested
        # against an input it was not meant to catch.
        assert stage1_count > 0
        assert stage2_count > 0
        with pytest.raises(AssertionError, match="MIXED payload"):
            _assert_not_mixed(payload)

    def test_the_guard_passes_an_unmixed_payload(self):
        """The other side. Without it, a guard that reddens on everything
        reads the same as a guard that works."""
        payload, _ = build_snapshot_payload(
            {_key(i, _NARROW_WIDTH): "x" * (PER_VALUE_CAP - 2000)
             for i in range(6)}
        )
        stage1_count, stage2_count = _stage_split(payload)
        assert stage1_count == 0
        assert stage2_count > 0
        _assert_not_mixed(payload)

    def test_the_scalar_label_cannot_report_a_mixed_input(self):
        """WHY the guard computes the two counts APART. To collapse a mixed
        payload onto one name is what the label DOES, so a guard that read
        the label would be a check that cannot fire."""
        source = self._mixed_source()
        payload, _ = build_snapshot_payload(source)
        assert _stage_split(payload) == (1, 5)
        # The label of a MIXED payload is indistinguishable from the label
        # of a stage-2-only payload. That is the whole argument.
        assert _classify_stage(payload, source) == "stage2"


class TestTheKeyPartitionDigestScope:
    def test_the_digest_covers_key_names_alone(self):
        """SCOPE CONTROL. Two payloads that keep the same key names and drop
        nothing share the digest while they differ in terminal stage and in
        bytes. The scope is CORRECT for the value-size flip, of which the
        claim is about which keys survive. This test is here so a reader
        does not take an agreeing digest for agreeing payloads."""
        large_seen = _observe(_mapping(_FEW, _LARGE_CHARS))
        small_seen = _observe(_mapping(_FEW, _SMALL_CHARS))

        assert large_seen["partition"] == small_seen["partition"]
        assert large_seen["stage"] != small_seen["stage"]
        assert large_seen["bytes"] != small_seen["bytes"]
