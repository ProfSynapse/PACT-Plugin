#!/usr/bin/env python3
"""
Location: pact-plugin/hooks/shared/canonical_json.py
Summary: THE single canonical JSON serialization for the hooks package. Every
         size measurement, truncation head, and content-key hash in every
         journal-carrier family flows through this one function, so two
         families computing a key for the same value compute the same bytes.
Used by: task_metadata_snapshot.py (stage sizing, truncation heads, and
         payload_hash8; it re-exports this function under its historical
         module-private name _canonical_bytes) and agent_handoff_marker.py
         (the handoff content key).

Why this is a module of its own, and why it is a LEAF. The two marker
families must agree byte for byte, and neither can own the serializer:
task_metadata_snapshot imports agent_handoff_marker, so a serializer in the
snapshot module cannot be imported back without a cycle. The alternative, a
second json.dumps in the marker module, is two serializations that must
agree with nothing that makes them agree. That is the drift this package
closed before by centralizing the marker atoms, and re-opening it here would
plant the same defect one layer along.

SO THIS MODULE IMPORTS NOTHING FROM THE PACKAGE. Keep it that way. An
intra-package import here re-opens the cycle the extraction exists to close,
and the failure lands on the marker family rather than here.

THE IMPORT CONTRACT HAS THREE TERMS, AND ONLY TWO OF THEM FAIL LOUDLY:

  1. the module path             a change gives an ImportError. LOUD.
  2. the exported name           a change gives an ImportError. LOUD.
  3. the four serialization parameters, below.    SILENT.

     sort_keys=True
     separators=(",", ":")        a comma and a colon, NO SPACES
     ensure_ascii                 LEFT AT ITS DEFAULT of true
     allow_nan                    LEFT AT ITS DEFAULT of true

THAT PARAMETER LIST IS A CENSUS OF FOUR AND IT WAS PUBLISHED AS A CENSUS OF
THREE. `allow_nan` was the omitted one, and an omitted term is worse here
than an unlisted one, because a reader who trusts the list as complete does
not hold what it leaves out. MEASURED: at its default, canonical_bytes
returns b'{"n":NaN}' for a NaN value and b'{"i":Infinity}' for an infinity,
and it RAISES for neither. So a content key IS derived from those bytes, and
the bytes are NOT JSON: a strict reader such as jq returns null for that
field. That is a silent VALUE change on the read path rather than a loud
failure on the write path, which is why it belongs on this list. Setting
allow_nan=False would convert it to a raise, and that is a CONTRACT CHANGE
for both families rather than a repair, so it is recorded here and not made.

THE STRUCTURAL CAUSE FOR THAT DECLINE, WHICH IS SHARPER THAN "A CONTRACT
CHANGE". MEASURED on task_metadata_snapshot.build_snapshot_payload: it holds
EIGHT call sites of this serializer and ZERO try blocks, so a raise from any
one of them leaves that function fully, and the only handler above it is a
bare catch. The trade is thus NOT symmetric, and it runs the incorrect way:

  allow_nan at its default   a NaN reaches the journal as the token NaN, and
                             a strict reader returns null for that field.
                             A SILENT VALUE CHANGE ON THE READ PATH.
  allow_nan=False            the serializer raises, the raise crosses
                             build_snapshot_payload unhandled, the bare catch
                             above swallows it, and the WHOLE SNAPSHOT EVENT
                             VANISHES with no record.
                             A SILENT EVENT LOSS ON THE WRITE PATH.

A module built on the bias that a loss must be MARKED rather than silent
cannot take the second in exchange for the first. A later reader who wants to
change this parameter must give those eight call sites a handler FIRST.

A CHANGE TO ANY OF THE FOUR PARAMETERS CHANGES EVERY DIGEST BOTH FAMILIES
PRODUCE, AND NOTHING ANNOUNCES IT. The module keeps importing. The callers
keep running. A test suite that hashes through this same function agrees
with itself and stays green, while the two families compute DIFFERENT keys
for one mapping. That divergence is the defect class this module was
extracted to close, so a tidy-up here re-creates it from the inside.

DO NOT NORMALIZE THIS CALL. Do not re-order the arguments and do not make
ensure_ascii explicit, even though explicit is the better habit elsewhere.
IF YOU MUST CHANGE IT, PROVE THE RESULT BY BYTES: hash one mapping through
the version before and the version after, and compare the two byte strings.
A review of the diff cannot see a space inside the separators tuple, and an
import cannot detect it at all.
"""

from __future__ import annotations

import json


def canonical_bytes(value: object) -> bytes:
    """THE single serialization for sizing, truncation heads, and hashing.

    sort_keys makes the byte form insertion-order-independent, which is what
    grounds the determinism contract of every caller: an identical input
    mapping under ANY insertion order produces byte-identical output and
    therefore an identical content key. Raises TypeError on
    non-JSON-serializable input; callers on the emit paths are hermetic, and
    task metadata is JSON-safe by construction (it arrives through the JSON
    payload of TaskUpdate).
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
