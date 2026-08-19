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
  3. the three serialization parameters, below.    SILENT.

     sort_keys=True
     separators=(",", ":")        a comma and a colon, NO SPACES
     ensure_ascii                 LEFT AT ITS DEFAULT of true

A CHANGE TO ANY OF THE THREE PARAMETERS CHANGES EVERY DIGEST BOTH FAMILIES
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
