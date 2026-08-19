"""Byte-level pins for shared.canonical_json.canonical_bytes.

WHY THIS FILE IS NOT IN EITHER FAMILY'S TEST MODULE. Two marker families hash
through this one function: the agent_handoff family (the handoff content key)
and the snapshot family (stage sizing, truncation heads, payload_hash8). The
contract belongs to neither, so it is pinned here, where either family's owner
can read it without reaching into the other's file.

WHAT WAS UNCOVERED BEFORE THIS FILE EXISTED, AND IT WAS MEASURED, NOT FEARED.
A mutation pass removed `sort_keys=True` from canonical_bytes and the whole
handoff-family suite stayed GREEN. The module header of canonical_json.py names
three terms of the import contract and states that only two of them fail loudly:
the module path and the exported name each give an ImportError, and the three
serialization parameters change every digest both families produce while nothing
announces it. That header was the entire protection for the third term. A prose
claim adjacent to a green suite inherits the green.

WHY THE EXPECTATIONS ARE TYPED AND NOT COMPUTED. A test that builds its
expectation by calling canonical_bytes agrees with a mutated canonical_bytes,
which is the defect that let the parameter survive. Every expectation below is
a byte string written out by hand from the JSON grammar, and every digest below
is the sha256 of one of those hand-written byte strings rather than of the
function's output. So a change to any serialization parameter moves the
function away from a fixed target that does not move with it.

DO NOT REPLACE A LITERAL WITH A CALL. That change is invisible in review, keeps
the suite green, and silently restores the hole this file closes.
"""

import hashlib

from shared.canonical_json import canonical_bytes


class TestSortKeysTerm:
    """Term 1 of the three silent parameters: sort_keys=True."""

    def test_top_level_keys_are_emitted_in_sorted_order(self):
        """Insertion order b, a must serialize as a, b.

        This is the assertion the removed-sort_keys mutant fails. The expected
        bytes are typed, so the mutant cannot drag the expectation along with
        it.
        """
        assert canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'

    def test_nested_keys_are_sorted_at_every_depth(self):
        """sort_keys applies recursively, and a shallow pin cannot see a
        mutant that sorts the top level alone."""
        value = {"b": {"d": 1, "c": 2}, "a": 3}
        assert canonical_bytes(value) == b'{"a":3,"b":{"c":2,"d":1}}'

    def test_two_insertion_orders_of_one_mapping_give_one_byte_string(self):
        """The determinism property the callers depend on, stated directly.

        The two emit paths of the agent_handoff family observe the same handoff
        through different routes, so a content key that moved with insertion
        order would split the two paths on content they agree about. This
        assertion compares the function against itself, so it is NOT
        independently derived and it CANNOT stand alone. It is here because it
        names the property, and the typed pins above are what make it safe.
        """
        first = {"alpha": 1, "beta": 2, "gamma": 3}
        second = {"gamma": 3, "alpha": 1, "beta": 2}
        assert canonical_bytes(first) == canonical_bytes(second)


class TestSeparatorsTerm:
    """Term 2 of the three silent parameters: separators=(",", ":")."""

    def test_no_whitespace_appears_around_the_separators(self):
        """The default json.dumps separators carry a space after each comma.

        A tidy-up that drops the separators argument changes every digest both
        families produce and raises no error. The typed expectation has no
        spaces in it, so the drop is loud here.
        """
        produced = canonical_bytes({"a": 1, "b": 2})
        assert produced == b'{"a":1,"b":2}'
        assert b" " not in produced

    def test_no_whitespace_in_a_nested_array_or_object(self):
        """The separators apply at each depth, not at the top level alone."""
        produced = canonical_bytes({"a": [1, 2], "b": {"c": 3}})
        assert produced == b'{"a":[1,2],"b":{"c":3}}'
        assert b" " not in produced


class TestEnsureAsciiTerm:
    """Term 3 of the three silent parameters: ensure_ascii left at its default.

    The module header instructs a reader NOT to make this parameter explicit.
    That instruction is a claim about behavior, and this class is what makes
    the claim checkable.
    """

    def test_a_non_ascii_character_is_escaped_rather_than_emitted_raw(self):
        """With the default, json.dumps escapes to a \\u sequence. If a change
        sets ensure_ascii=False, the same input emits raw UTF-8 bytes and every
        digest moves.
        """
        assert canonical_bytes({"k": "é"}) == b'{"k":"\\u00e9"}'

    def test_the_output_is_pure_ascii(self):
        """A second route to term 3 that does not depend on one code point."""
        produced = canonical_bytes({"k": "é中\U0001f600"})
        assert produced.decode("ascii")


class TestDigestPins:
    """The value each family actually consumes is a DIGEST of these bytes.

    A count or a length agreeing is weak evidence, because two serializers can
    land on the same length and emit different bytes. These pins compare the
    artifact. Each expected digest below is the sha256 of the hand-typed byte
    string in the sibling test above it, never of the function's output.
    """

    def test_digest_of_a_reordered_mapping_is_pinned(self):
        assert (
            hashlib.sha256(canonical_bytes({"b": 1, "a": 2})).hexdigest()[:8]
            == "d3626ac3"
        )

    def test_digest_of_a_nested_mapping_is_pinned(self):
        value = {"b": {"d": 1, "c": 2}, "a": 3}
        assert (
            hashlib.sha256(canonical_bytes(value)).hexdigest()[:8] == "37236d6e"
        )

    def test_digest_of_a_non_ascii_mapping_is_pinned(self):
        assert (
            hashlib.sha256(canonical_bytes({"k": "é"})).hexdigest()[:8]
            == "9567d6e8"
        )

    def test_digest_of_a_handoff_shaped_mapping_is_pinned(self):
        """A handoff-shaped input, so the pin sits on the shape the marker
        family hashes rather than on a toy mapping alone."""
        handoff = {"produced": ["p"], "decisions": ["d"]}
        assert (
            hashlib.sha256(canonical_bytes(handoff)).hexdigest()[:8]
            == "a86f6c34"
        )


class TestRaiseContract:
    """The callers branch on this, so it is part of the contract.

    canonical_bytes raises on a non-JSON-serializable value, and
    handoff_content_key catches that raise to stay total. A change that made
    this function total instead would make the caller's fallback unreachable
    while every test above stayed green.
    """

    def test_a_non_serializable_value_raises_type_error(self):
        import pytest

        with pytest.raises(TypeError):
            canonical_bytes({"k": {1, 2}})
