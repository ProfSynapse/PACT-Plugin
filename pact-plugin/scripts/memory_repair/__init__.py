"""Read-only instruments that inspect a pact-memory store file.

Location: pact-plugin/scripts/memory_repair/__init__.py

Each module here opens `sqlite3` directly and imports nothing from the
pact-memory scripts package. Keep each module here, and each module added
later, free of an import from that package. In that package, functions create
the live store directory as a side result of a path resolution, so an import
puts each of them one call away. This rule holds so that nobody must audit
which call is safe. Do not read an absent import as a guarantee, because a
subprocess reaches those functions with no import at all. These tools depend
on nothing from that package, so they run without it.
"""
from __future__ import annotations
